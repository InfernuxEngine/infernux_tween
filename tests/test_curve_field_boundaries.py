"""Curve values retain field semantics across editing, storage and consumers."""
import copy
import json
import math
import struct
import threading

import numpy as np
import pytest
from infernux import AnimationCurve,Keyframe,WeightedMode,WrapMode
from infernux.lib import _Infernux as native
from infernux.components.builtin.line_renderer import _get_width_curve,_set_width_curve
from infernux.graph.types import TypeRef,ValueType
from infernux.particle import gpu_glsl_backend as gpu
from infernux.particle.kernel_ir import KernelParameter

FIELDS=('time','value','in_tangent','out_tangent','in_weight','out_weight')
bits=lambda value:struct.unpack('<I',struct.pack('<f',value))[0]
number=lambda value:struct.unpack('<f',struct.pack('<I',value))[0]
def records(curve):
    return [(tuple(bits(getattr(key,name)) for name in FIELDS),int(key.weighted_mode)) for key in curve.keys]


@pytest.mark.parametrize('field',FIELDS)
@pytest.mark.parametrize('value',[number(0xffc00001),math.inf,-math.inf])
def test_nonfinite_key_fields_keep_their_float32_values_in_strict_json(field,value):
    key=Keyframe(0,1);setattr(key,field,value)
    assert bits(getattr(key,field))==bits(value)
    document=json.loads(json.dumps(key.to_dict(),allow_nan=False))
    restored=Keyframe.from_dict(document)
    assert bits(getattr(restored,field))==bits(value)
    assert restored==key


@pytest.mark.parametrize('field',FIELDS)
def test_key_fields_convert_numpy_numbers_and_float32_overflow(field):
    key=Keyframe();setattr(key,field,np.float32(.25));assert getattr(key,field)==.25
    setattr(key,field,1e40);assert getattr(key,field)==math.inf
    setattr(key,field,-1e40);assert getattr(key,field)==-math.inf


@pytest.mark.parametrize('field',['pre_wrap_mode','post_wrap_mode'])
@pytest.mark.parametrize('value,expected',[
    (-1,8),(0,0),(1,8),(2,2),(3,8),(4,4),(5,8),(255,8),
])
def test_wrap_setters_normalize_to_supported_native_curve_modes(field,value,expected):
    curve=AnimationCurve.linear(0,0,1,1);setattr(curve,field,value)
    assert int(getattr(curve,field))==expected
    restored=AnimationCurve.from_dict(curve.to_dict())
    assert getattr(restored,field)==getattr(curve,field)


@pytest.mark.parametrize('field',['time','value'])
@pytest.mark.parametrize('value',[math.nan,math.inf,-math.inf])
def test_bulk_keys_filter_invalid_time_value_while_individual_edits_keep_accepted_keys(field,value):
    invalid=Keyframe(.25,.5);setattr(invalid,field,value)
    first,last=Keyframe(0,0,1,1),Keyframe(1,1,1,1)
    assert AnimationCurve(first,invalid,last).length==2
    curve=AnimationCurve();curve.keys=[first,invalid,last];assert curve.length==2
    expected=-1 if field=='time' and math.isnan(value) else 1
    index=curve.add_key(invalid)
    assert (index==-1)==(expected==-1)
    assert curve.length==(2 if expected==-1 else 3)
    if expected!=-1:
        assert records(AnimationCurve.from_dict(json.loads(json.dumps(curve.to_dict(),allow_nan=False))))==records(curve)
        assert records(copy.deepcopy(curve))==records(curve)
        copied=AnimationCurve();copied.copy_from(curve);assert records(copied)==records(curve)
    curve=AnimationCurve(first,last);index=curve.move_key(0,invalid)
    assert (index==-1)==(expected==-1)
    assert curve.length==(1 if expected==-1 else 2)


@pytest.mark.parametrize('mode',[-1,4,5,255,0x1000001,0x80000001])
def test_unused_weight_flags_survive_native_hash_line_storage_and_json(mode):
    key=Keyframe(0,1,0,1);key.weighted_mode=mode
    expected=((mode+0x80000000)&0xffffffff)-0x80000000
    assert int(key.weighted_mode)==expected
    curve=AnimationCurve(key,Keyframe(1,2,1,0))
    line=native.LineRenderer();_set_width_curve(line,curve)
    clone=native.LineRenderer();clone.deserialize(line.serialize())
    restored=_get_width_curve(clone)
    assert records(restored)==records(curve)
    assert restored.get_hash_code()==curve.get_hash_code()


@pytest.mark.parametrize('field',['in_tangent','out_tangent','in_weight','out_weight'])
@pytest.mark.parametrize('value',[number(0xffc00001),math.inf,-math.inf])
def test_nonfinite_slopes_and_weights_roundtrip_through_native_line_json(field,value):
    key=Keyframe(0,1,0,1);setattr(key,field,value)
    curve=AnimationCurve(key,Keyframe(1,2,1,0));line=native.LineRenderer();_set_width_curve(line,curve)
    encoded=json.loads(line.serialize());json.dumps(encoded,allow_nan=False)
    clone=native.LineRenderer();clone.deserialize(json.dumps(encoded))
    assert records(_get_width_curve(clone))==records(curve)


@pytest.mark.parametrize('value',[math.nan,math.inf,-math.inf])
@pytest.mark.parametrize('side',['in','out'])
def test_only_active_nonfinite_weights_produce_nan_between_keys(side,value):
    first,last=Keyframe(0,0,1,1),Keyframe(1,1,1,1)
    key=first if side=='out' else last
    setattr(key,side+'_weight',value)
    key.weighted_mode=WeightedMode.OUT if side=='out' else WeightedMode.IN
    curve=AnimationCurve(first,last)
    assert curve.evaluate(-1)==0 and math.isnan(curve.evaluate(.5)) and curve.evaluate(1)==1
    key.weighted_mode=WeightedMode.IN if side=='out' else WeightedMode.OUT
    assert AnimationCurve(first,last).evaluate(.5)==.5


def test_curve_equality_distinguishes_nan_values_while_key_equality_accepts_them():
    first=Keyframe(0,0,1,1);first.in_tangent=number(0x7fc00001)
    second=Keyframe(0,0,1,1);second.in_tangent=number(0x7fc00002)
    assert first==second
    left=AnimationCurve(first,Keyframe(1,1));same=copy.deepcopy(left)
    different=AnimationCurve(second,Keyframe(1,1))
    assert left.equals(left) and not left.equals(same) and not left.equals(different)
    assert left.get_hash_code()==same.get_hash_code()!=different.get_hash_code()


def test_large_cached_curve_comparison_releases_gil():
    curve=AnimationCurve(keys=[Keyframe(index,index) for index in range(128000)])
    other=copy.deepcopy(curve)
    curve._native_snapshot();other._native_snapshot()
    started,stopped=threading.Event(),threading.Event();observed=[0]
    def worker():
        started.set()
        while not stopped.is_set():observed[0]+=1
    thread=threading.Thread(target=worker);thread.start();started.wait()
    try:
        before=observed[0]
        for _ in range(4):assert curve.equals(other)
        assert observed[0]>before+100
    finally:
        stopped.set();thread.join(timeout=5)


@pytest.mark.parametrize('difference',['length','pre_wrap','post_wrap'])
@pytest.mark.parametrize('cached',['neither','left','right','both'])
def test_metadata_mismatches_do_not_build_numerical_snapshots(difference,cached):
    first,second=AnimationCurve(Keyframe()),AnimationCurve(Keyframe())
    if cached in ('left','both'):first._native_snapshot()
    if cached in ('right','both'):second._native_snapshot()
    if difference=='length':second.add_key(Keyframe(1,1))
    elif difference=='pre_wrap':second.pre_wrap_mode=WrapMode.LOOP
    else:second.post_wrap_mode=WrapMode.PING_PONG
    def unexpected_snapshot():raise AssertionError('Metadata mismatch must not compile a numerical snapshot')
    first._native_snapshot=second._native_snapshot=unexpected_snapshot
    assert not first.equals(second) and not second.equals(first)


def test_cached_equality_uses_snapshots_until_a_key_edit_changes_the_revision():
    first=AnimationCurve.linear(0,0,1,1);second=copy.deepcopy(first)
    first._native_snapshot();second._native_snapshot()
    def unexpected_snapshot():raise AssertionError('Unchanged curves must reuse their snapshots directly')
    first._native_snapshot=second._native_snapshot=unexpected_snapshot
    assert first.equals(second)
    del first._native_snapshot,second._native_snapshot
    changed=second[1];changed.value=2;second.move_key(1,changed)
    assert not first.equals(second) and not second.equals(first)


def test_gpu_weights_encode_only_used_bits_and_nonfinite_literals_compile():
    first,last=Keyframe(0,0,1,1),Keyframe(1,1,1,1)
    first.weighted_mode=0x1000001;first.in_weight=math.inf
    last.weighted_mode=-1;last.in_weight=math.nan
    curve=AnimationCurve(first,last)
    parameter=KernelParameter('curve','Curve',TypeRef(ValueType.CURVE),curve.to_dict(),True,False,0)
    words=gpu.pack_gpu_particle_parameters((parameter,))
    assert struct.unpack('<f',struct.pack('<I',words[10]))[0]==1
    assert struct.unpack('<f',struct.pack('<I',words[18]))[0]==3
    expression=gpu._glsl_curve_sample('0.5',curve)
    source=('#version 450\nlayout(local_size_x=1) in;\n'
            'layout(set=0,binding=0,std430) buffer Results {float values[];};\n'
            +gpu._curve_interpolation_glsl()+'\nvoid main(){values[0]='+expression+';}')
    compiled=native._compile_compute_glsl_batch({'nonfinite_curve':source},'curve-field-encoding')
    assert bytes(compiled['nonfinite_curve'])[:4]==b'\x03\x02\x23\x07'


def test_editor_preview_does_not_submit_nonfinite_vertices_or_rewrite_untouched_tokens():
    from infernux.engine.ui.curve_editor import _draw_curve,_view_bounds,_edit_key_number
    class Context:
        def draw_filled_rect(self,*args):assert all(math.isfinite(v) for v in args)
        def draw_line(self,*args):assert all(math.isfinite(v) for v in args)
        def draw_filled_circle(self,*args):assert all(math.isfinite(v) for v in args)
        def label(self,*args):pass
        def same_line(self,*args):pass
        def button(self,*args):return False
    ctx=Context();key=Keyframe(0,0);key.out_tangent=math.nan
    curve=AnimationCurve(key,Keyframe(1,1));curve.add_key(Keyframe(2,math.nan))
    keys=curve.to_dict()['keys'];bounds=_view_bounds(keys,non_negative=False)
    assert all(math.isfinite(v) for v in bounds)
    _draw_curve(ctx,keys,(0,0,200,100),bounds,dpi_scale=1,selected=2,show_handles=True)
    assert _edit_key_number(ctx,'weight','nan:ffc00001',.1,0,1)=='nan:ffc00001'
