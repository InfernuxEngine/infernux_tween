"""Read actual Vulkan curve results through literal, parameter and direct paths.

Build tests/native's infernux_curve_gpu_probe first. An optional external JSON
corpus has cases with left/right [time,value,out_or_in_tangent], times and bits.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess

from infernux import AnimationCurve,Keyframe,WeightedMode,WrapMode
from infernux.graph.types import TypeRef,ValueType
from infernux.particle import gpu_glsl_backend as gpu
from infernux.particle.kernel_ir import KernelParameter
from infernux.lib import _Infernux as native


def run(args):
    source_cases=(json.loads(args.reference.read_bytes())['cases'] if args.reference else [
        dict(left=[0,0,0],right=[1,1,0],times=[0,.25,.5,.75,1]),
        dict(left=[-.008729105815291405,-417583.875,-.0036757427733391523],
             right=[-.008696835488080978,-263.4327087402344,5213.03466796875],
             times=[-.008708866313099861],bits=[-927581096]),
    ])
    args.output.mkdir(parents=True,exist_ok=True)
    parameters=[]
    curves=[]
    slots=[]
    expected=[]
    rows=[]
    case_ids=[]
    sample_times=[]
    domains=[]
    for index,case in enumerate(source_cases):
        t0,v0,m0=case['left'];t1,v1,m1=case['right']
        left_sign=case.get('left_step') or (1 if case.get('step')==1 else 0)
        right_sign=case.get('right_step') or (-1 if case.get('step')==2 else 0)
        left=Keyframe(t0,v0,0,math.copysign(math.inf,left_sign) if left_sign else m0)
        right=Keyframe(t1,v1,math.copysign(math.inf,right_sign) if right_sign else m1,0)
        if case.get('weighted'):
            left.out_weight=.75;left.weighted_mode=WeightedMode.OUT
            right.in_weight=.15;right.weighted_mode=WeightedMode.IN
        left=Keyframe.from_dict({**left.to_dict(),**case.get('left_fields',{})})
        right=Keyframe.from_dict({**right.to_dict(),**case.get('right_fields',{})})
        curve=AnimationCurve(left,right,
                             pre_wrap_mode=WrapMode.CLAMP_FOREVER,post_wrap_mode=WrapMode.CLAMP_FOREVER)
        keys=curve.keys
        slots.append(len(parameters)//4)
        parameter=KernelParameter(str(index),'Curve',TypeRef(ValueType.CURVE),curve.to_dict(),True,False,0)
        packed=gpu.pack_gpu_particle_parameters((parameter,))
        parameters.extend(packed)
        curves.append(curve)
        domains.append((keys[0].time,keys[-1].time))
        cpu=[struct.unpack('<I',struct.pack('<f',v))[0] for v in curve.evaluate_many(case['times'])]
        if 'bits' in case:
            assert cpu==[v&0xffffffff for v in case['bits']], ('CPU oracle mismatch',index)
        inverse=struct.unpack('<f',struct.pack('<I',packed[11]))[0]
        for time,bits in zip(case['times'],cpu):
            row=bytearray()
            for key in keys:
                row.extend(struct.pack('<4f',key.time,key.value,key.in_tangent,key.out_tangent))
            for key in keys:
                row.extend(struct.pack('<4f',key.in_weight,key.out_weight,int(key.weighted_mode)&3,0))
            row.extend(struct.pack('<fIIf',time,slots[-1],index,inverse))
            assert len(row)==80
            rows.append(row);expected.append(bits);case_ids.append(index);sample_times.append(time)
    parameter_path=args.output/'parameters.bin'
    parameter_path.write_bytes(struct.pack('<'+'I'*len(parameters),*parameters))
    helper=args.helper_source.read_text() if args.helper_source else gpu._curve_interpolation_glsl()
    header=('''#version 450
layout(local_size_x=64) in;
layout(set=0,binding=0,std430) readonly buffer Samples { uvec4 samples[]; };
layout(set=0,binding=1,std430) readonly buffer Parameters { uvec4 parameter_words[]; };
layout(set=0,binding=2,std430) writeonly buffer Results { uint output_values[]; };
'''+helper+'\n'+gpu._ramp_parameter_glsl({'curve':(0,TypeRef(ValueType.CURVE))}))
    results=[]
    for mode in ('direct','parameter','literal'):
        chosen=[i for i,case in enumerate(case_ids) if (mode!='literal' or case<16)
                and (mode!='direct' or domains[case][0]<=sample_times[i]<=domains[case][1])]
        functions=''
        if mode=='literal':
            functions='float literal_curve(uint index,float time) { switch(index) {\n'
            for index,curve in enumerate(curves[:16]):
                functions+=f'case {index}u: return {gpu._glsl_curve_sample("time",curve)};\n'
            functions+='default:return 0.0; } }\n'
        expression={
            'direct':'''inx_curve_segment(time,uintBitsToFloat(samples[base]),uintBitsToFloat(samples[base+1u]),
                       uintBitsToFloat(samples[base+2u]).xyz,uintBitsToFloat(samples[base+3u]).xyz,
                       uintBitsToFloat(samples[base+4u].w))''',
            'parameter':'inx_sample_curve_parameter(samples[base+4u].y,time)',
            'literal':'literal_curve(samples[base+4u].z,time)',
        }[mode]
        source=header+functions+'''void main() {
uint index=gl_GlobalInvocationID.x;
if(index>=uint(output_values.length())) return;
uint base=index*5u;
float time=uintBitsToFloat(samples[base+4u].x);
output_values[index]=floatBitsToUint('''+expression+');\n}\n'
        shader_path=args.output/(mode+'.spv')
        (args.output/(mode+'.comp')).write_text(source)
        shader_path.write_bytes(bytes(native._compile_compute_glsl_batch({mode:source},'curve-gpu-readback')[mode]))
        sample_path=args.output/(mode+'-samples.bin')
        sample_path.write_bytes(b''.join(rows[i] for i in chosen))
        output_path=args.output/(mode+'-output.bin')
        process=subprocess.run([str(args.probe),str(shader_path),str(sample_path),str(parameter_path),
                                str(output_path),str(len(chosen))],capture_output=True,text=True,timeout=90)
        assert process.returncode==0, process.stdout+'\n'+process.stderr
        values=struct.unpack('<'+'I'*len(chosen),output_path.read_bytes())
        differences=[]
        value_differences=0
        maximum_error=0.0
        for location,(actual,original_index) in enumerate(zip(values,chosen)):
            wanted=expected[original_index]
            if actual!=wanted:
                af=struct.unpack('<f',struct.pack('<I',actual))[0]
                ef=struct.unpack('<f',struct.pack('<I',wanted))[0]
                if math.isfinite(af) and math.isfinite(ef):
                    maximum_error=max(maximum_error,abs(af-ef))
                within_tolerance=(args.absolute_tolerance > 0 and math.isfinite(af) and math.isfinite(ef)
                                  and abs(af-ef) <= args.absolute_tolerance)
                value_differences+=not within_tolerance
                differences.append(dict(location=location,case=case_ids[original_index],actual=af,expected=ef,
                                        actual_bits=actual,expected_bits=wanted))
        results.append(dict(mode=mode,samples=len(chosen),bit_differences=len(differences),
                            value_differences=value_differences,
                            max_absolute_error=maximum_error,
                            examples=differences[:12],device=process.stdout.strip()))
    report=dict(passed=all(not row['value_differences'] for row in results),results=results,
                absolute_tolerance=args.absolute_tolerance,
                helper_sha256=hashlib.sha256(helper.encode()).hexdigest(),graphics_abi=gpu._particle_graphics_abi_hash())
    (args.output/'proof.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({**report,'results':[{k:v for k,v in row.items() if k!='examples'} for row in results]}))
    assert report['passed'], args.output/'proof.json'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe',type=Path,required=True)
    parser.add_argument('--reference',type=Path)
    parser.add_argument('--helper-source',type=Path)
    parser.add_argument('--absolute-tolerance',type=float,default=0,
                        help='Explicit finite-value error bound; zero requires identical float32 bits.')
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args())


if __name__=='__main__':main()
