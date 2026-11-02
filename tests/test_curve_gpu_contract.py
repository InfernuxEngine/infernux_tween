"""Prepared GPU curve data keeps its layout and invalidates stale programs."""
import struct
import math

import pytest
from infernux import AnimationCurve,Keyframe,WeightedMode,WrapMode
from infernux.graph.types import TypeRef,ValueType
from infernux.particle import gpu_glsl_backend as gpu
from infernux.particle.kernel_ir import KernelParameter


def parameter(curve):
    return KernelParameter('curve','Curve',TypeRef(ValueType.CURVE),curve.to_dict(),True,False,0)


@pytest.mark.parametrize('first,last,reciprocal_bits', [
    (2,5,0x3eaaaaab),
    (0,.00001,0x461c4000),
    (-3.4028234663852886e38,3.4028234663852886e38,0),
])
def test_curve_prepares_float32_inverse_without_growing_the_buffer(first,last,reciprocal_bits):
    curve=AnimationCurve(Keyframe(first,0),Keyframe(last,1))
    words=gpu.pack_gpu_particle_parameters((parameter(curve),))
    assert len(words)==(1+16*2)*4
    assert words[:4]==(2,0,0,0)
    assert words[11]==reciprocal_bits
    assert words[19]==0


def test_partial_parameter_update_prepares_the_new_curve_inverse():
    initial=AnimationCurve(Keyframe(2,0),Keyframe(5,1))
    replacement=AnimationCurve(Keyframe(0,0),Keyframe(.25,1))
    updates=gpu.pack_gpu_particle_parameter_updates((parameter(initial),),{'curve':replacement.to_dict()},('curve',))
    assert len(updates)==1 and updates[0][0]==0
    assert updates[0][1][11]==0x40800000  # 4.0, replacing the original 1/3.


def test_weighted_segment_retains_its_weights_and_unused_reciprocal():
    curve=AnimationCurve(Keyframe(0,0,0,4,.2,.75),Keyframe(1,1,-2,0,.15,.4))
    words=gpu.pack_gpu_particle_parameters((parameter(curve),))
    weights=struct.unpack('<4f',struct.pack('<4I',*words[8:12]))
    assert weights[:3]==pytest.approx((.2,.75,3))
    assert weights[3]==0


@pytest.mark.parametrize('helper', ['_curve_interpolation_glsl','_ramp_parameter_glsl'])
def test_changing_curve_shader_helpers_invalidates_the_persisted_abi(monkeypatch,helper):
    before=gpu._particle_graphics_abi_hash()
    original=getattr(gpu,helper)
    monkeypatch.setattr(gpu,helper,lambda *a,**kw:original(*a,**kw)+'\n// changed curve code\n')
    assert gpu._particle_graphics_abi_hash()!=before


@pytest.mark.parametrize('left_sign,right_sign,inside', [
    (-1,-1,5),(-1,0,5),(-1,1,2),(0,-1,5),(0,1,2),(1,-1,2),(1,0,2),(1,1,2),
])
@pytest.mark.parametrize('weighted',[False,True])
def test_step_direction_and_positive_precedence_at_key_boundaries(left_sign,right_sign,inside,weighted):
    first,last=-46.140716552734375,10.119365692138672
    previous=struct.unpack('f',struct.pack('I',struct.unpack('I',struct.pack('f',last))[0]-1))[0]
    left=Keyframe(first,2,0,math.copysign(math.inf,left_sign) if left_sign else 2)
    right=Keyframe(last,5,math.copysign(math.inf,right_sign) if right_sign else 3,0)
    if weighted:
        left.out_weight=.75;left.weighted_mode=WeightedMode.OUT
        right.in_weight=.15;right.weighted_mode=WeightedMode.IN
    curve=AnimationCurve(left,right,pre_wrap_mode=WrapMode.CLAMP_FOREVER,post_wrap_mode=WrapMode.CLAMP_FOREVER)
    assert curve.evaluate_many([first-1,first,(first+last)*.5,previous,last,last+1])==[2,inside,inside,inside,5,5]
