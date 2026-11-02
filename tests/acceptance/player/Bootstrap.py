"""Gameplay probe for a cooked standalone Player, with no Editor services."""
import json
from pathlib import Path
import sys
import traceback
import struct
import numpy as np

import infernux as inx
from infernux.lib import SceneManager, Vector2, Vector3, vec4f, quatf
from infernux.screen import Rect
import infernux_tween as tween


class PlatformFixtureBootstrap(inx.InxComponent):
    def start(self):
        self._finished = False
        self._elapsed = 0.
        self._stage = -1
        self._warmup_frames = 0
        self._capture = None
        self._observations = []
        self._completions = []
        self._values = [0., 0.]
        self._integer_values = [0, 6000000000]
        self._single_value = np.float32(.1)
        self._typed_dtypes = (np.float64, np.int32, np.int64, np.uint32, np.uint64)
        self._typed_initial = (.1, 2, 2, 20, 9007199254740993)
        self._typed_end = (.9, 10, 10, 4, 9007199254740997)
        self._typed_values = [dtype(value) for dtype, value in zip(self._typed_dtypes, self._typed_initial)]
        self._array_value = Vector3()
        self._string_value = ''
        self._rect_value = Rect(0, 0, 0, 0)
        self._array_plan_reused = False
        self._rotation_plan_reused = False
        self._look_plan_reused = False
        self._vector_plan_reused = False
        self._path_plan_reused = False
        self._bezier_plan_reused = False
        self._shared_path_plan_reused = False
        self._live_vector_value = Vector3(2, 3, 4)
        try:
            assert inx.Application.is_player() and not inx.Application.is_editor()
            from infernux.lib._Infernux import _FrameTimeSmoother, _image_fill_geometry
            smoother = _FrameTimeSmoother()
            assert smoother.advance(.01) == 0
            assert abs(smoother.advance(.02) - .02) < 1e-8
            smoother.reset()
            assert smoother.value == 0
            assert _image_fill_geometry(.5, 0, 0, True) == [
                [[0., 0.], [.5, 0.], [.5, 1.], [0., 1.]]]
            self._observations.append({'stage': 'runtime_numerics', 'frame_clock': True, 'image_fill': True})
            hash_curve = inx.AnimationCurve(inx.Keyframe())
            assert hash_curve.get_hash_code() == -153111983
            assert inx.AnimationCurve(inx.Keyframe(-0., 0.)).get_hash_code() == 1994371665
            hash_curve.move_key(0, inx.Keyframe(0, 1))
            assert hash_curve.get_hash_code() == -1637895599
            self._observations.append({'stage': 'curve_hash', 'updated_hash': hash_curve.get_hash_code()})
            key_buffer = [None, None]
            hash_curve.get_keys(keys=key_buffer)
            if key_buffer[0].value != 1. or key_buffer[1] is not None:
                raise RuntimeError('Player named curve key output did not preserve its destination capacity')
            key_buffer[0].value = 3.
            if hash_curve[0].value != 1.:
                raise RuntimeError('Player curve key output aliased its source curve')
            key_copy = inx.AnimationCurve()
            key_copy.set_keys(keys=key_buffer[:1])
            key_buffer[0].value = 7.
            if key_copy[0].value != 3.:
                raise RuntimeError('Player named curve key input retained caller-owned keys')
            self._observations.append({'stage': 'curve_key_buffer_keywords', 'value_copies': True,
                                       'surplus_capacity_preserved': True})
            polynomial_samples = [
                ((-.8541792035102844,32.930511474609375,-69.33159637451172),
                 (-.8101045489311218,-32.771568298339844,-35.604713439941406),-.8519754409790039,1107380140),
                ((-.008729105815291405,-417583.875,-.0036757427733391523),
                 (-.008696835488080978,-263.4327087402344,5213.03466796875),-.008708866313099861,-927581096),
                ((9.945021629333496,-7.026381015777588,-54.23567581176758),
                 (28.880508422851562,-34.021400451660156,-82.90560913085938),19.412765502929688,1111316496),
            ]
            for left,right,time,bits in polynomial_samples:
                polynomial = inx.AnimationCurve(inx.Keyframe(left[0],left[1],0,left[2]),
                                                inx.Keyframe(right[0],right[1],right[2],0))
                expected = struct.pack('i',bits)
                assert struct.pack('f',polynomial.evaluate(time)) == expected
                assert all(struct.pack('f',value) == expected for value in polynomial.evaluate_many([time]*1024))
            self._observations.append({'stage':'curve_polynomial','scalar_cases':3,'bulk_samples':3072,
                                       'short_interval':True,'exact_bits':True})
            boundary_samples = 0
            first, last = -46.140716552734375, 10.119365692138672
            previous = struct.unpack('f', struct.pack('I', struct.unpack('I', struct.pack('f', last))[0] - 1))[0]
            for weighted in (False, True):
                for left_sign, right_sign in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
                    left = inx.Keyframe(first, 2, 0, left_sign * float('inf') if left_sign else 2)
                    right = inx.Keyframe(last, 5, right_sign * float('inf') if right_sign else 3, 0)
                    if weighted:
                        left.out_weight, left.weighted_mode = .75, inx.WeightedMode.OUT
                        right.in_weight, right.weighted_mode = .15, inx.WeightedMode.IN
                    boundary = inx.AnimationCurve(left, right, pre_wrap_mode=inx.WrapMode.CLAMP_FOREVER,
                                                  post_wrap_mode=inx.WrapMode.CLAMP_FOREVER)
                    inside = 2 if left_sign == 1 or right_sign == 1 else 5
                    assert boundary.evaluate_many([first-1,first,(first+last)*.5,previous,last,last+1]) == [2,inside,inside,inside,5,5]
                    boundary_samples += 6
            from infernux.graph.types import TypeRef, ValueType
            from infernux.particle.kernel_ir import KernelParameter
            from infernux.particle.gpu_glsl_backend import pack_gpu_particle_parameters
            prepared = inx.AnimationCurve(inx.Keyframe(2,0), inx.Keyframe(5,1))
            parameter = KernelParameter('curve','Curve',TypeRef(ValueType.CURVE),prepared.to_dict(),True,False,0)
            words = pack_gpu_particle_parameters((parameter,))
            assert len(words) == 132 and words[11] == 0x3eaaaaab
            self._observations.append({'stage':'curve_boundaries','samples':boundary_samples,
                                       'prepared_gpu_inverse':True,'unchanged_parameter_size':True})
            from infernux_tween.rotation import QuaternionTweener
            specialized_manager = tween.TweenManager()
            for kind in ('quaternion','circle'):
                end = quatf(.8,.3,.2,.4) if kind == 'quaternion' else Vector2(.8,.3)
                current = quatf(.1,.2,.3,.9) if kind == 'quaternion' else Vector2(.1,.2)
                def getter():
                    end.x = 10
                    return current
                def setter(value):
                    value.x = 999
                if kind == 'quaternion':
                    captured = specialized_manager.add(QuaternionTweener(getter,setter,quatf(.2,.4,.6,.8),1))
                else:
                    captured = specialized_manager.to(tween.CirclePlugin.get(),getter,setter,Vector2(.2,.4),1).set_options(120,False,False)
                captured.set_auto_kill(False).change_end_value(end)
                assert abs(captured.end_value.x-.8) < 1e-7
                captured.kill()
            captured_values = []
            armed = [False]
            def quaternion_ease(t,d,a,p):
                if armed[0]:
                    armed[0] = False
                    captured.start_value.x, captured.change_value.z = 1,.5
                return t/d
            captured = specialized_manager.add(QuaternionTweener(quatf.identity,captured_values.append,quatf(0,0,1,0),1))
            captured.set_ease(quaternion_ease).set_auto_kill(False).force_init()
            armed[0] = True
            captured.goto(.5)
            assert max(abs(a-b) for a,b in zip(captured_values[-1],(0,0,.7071067811865476,.7071067811865476))) < 4e-7
            specialized_manager.clear()
            branch = quatf.slerp(quatf.identity(),quatf(0,0,.31224992871284485,.949999988079071),.25)
            assert abs(branch.z-.07880477607250214) < 4e-7
            self._observations.append({'stage':'specialized_value_capture','input_kinds':2,
                                       'native_callback_capture':True,'interpolation_threshold':True})
            invocation_manager, invocation_values, invocation_times = tween.TweenManager(), [], []
            def invocation_ease(t,d,a,p):
                invocation_times.append((t,d))
                return t/d
            invoked = invocation_manager.add(QuaternionTweener(quatf.identity,invocation_values.append,quatf(0,0,1,0),1))
            invoked.set_ease(invocation_ease).set_auto_kill(False).force_init()
            supplied = quatf(.4,.5,.6,.7)
            invoked.start_value = supplied
            supplied.x = 99
            assert abs(invoked.start_value.x-.4) < 1e-7
            invoked.get_plugin().evaluate_and_apply(invoked.plug_options,invoked,False,invoked.getter,invoked.setter,
                .5,quatf.identity(),quatf(0,0,1,0),2,False,0,tween.UpdateNotice.NONE)
            assert invocation_times == [(.5,2)]
            assert abs(invocation_values[-1].z-.3826834323650898) < 4e-7
            invoked = invocation_manager.to(tween.CirclePlugin.get(),lambda:Vector2(0,1),invocation_values.append,Vector2(0,0),1)
            invoked.set_options(90,False,False).set_ease(tween.Ease.LINEAR).set_auto_kill(False).force_init()
            from copy import copy
            invocation_options = copy(invoked.plug_options)
            for angle,snapping,expected in ((180,False,(1,0)),(90,True,(1,1))):
                invocation_options.snapping = snapping
                invoked.get_plugin().evaluate_and_apply(invocation_options,invoked,False,invoked.getter,invoked.setter,
                    .5,invoked.start_value,Vector2(angle,0),1,False,0,tween.UpdateNotice.NONE)
                assert max(abs(a-b) for a,b in zip(invocation_values[-1],expected)) < 4e-7
            invocation_manager.clear()
            self._observations.append({'stage':'plugin_invocation','field_assignment_copy':True,
                                       'explicit_time':True,'circle_arguments':2})
            direct_manager,direct_values,direct_calls=tween.TweenManager(),[],[]
            direct_first,direct_change=Vector3(2,2,2),Vector3(8,8,8)
            def direct_ease(t,d,a,p):
                direct_calls.append((t,d))
                direct_first.x,direct_change.x=50,100
                direct_options.axis_constraint=tween.AxisConstraint.Y
                direct_options.snapping=True
                return t/d
            direct=direct_manager.to(lambda:Vector3(100,100,100),direct_values.append,Vector3(10,10,10),1)
            direct.set_ease(direct_ease).set_auto_kill(False).force_init()
            direct_options=copy(direct.plug_options)
            direct.get_plugin().evaluate_and_apply(direct_options,direct,False,direct.getter,direct.setter,
                .5,direct_first,direct_change,2,False,0,tween.UpdateNotice.NONE)
            if tuple(direct_values[-1])!=(4,4,4) or direct_calls!=[(.5,2)] or direct.elapsed()!=0:
                raise RuntimeError('Direct vector plugin did not preserve supplied time/value arguments')
            from infernux_tween.rotation import EulerTweener
            direct_first,direct_change=Vector3(),Vector3(0,90,0)
            direct_calls.clear()
            def direct_rotation_ease(t,d,a,p):
                direct_calls.append((t,d));direct_first.y,direct_change.y=90,180
                return t/d
            direct=direct_manager.add(EulerTweener(quatf.identity,direct_values.append,Vector3(0,90,0),1))
            direct.set_ease(direct_rotation_ease).set_auto_kill(False).force_init()
            direct.get_plugin().evaluate_and_apply(direct.plug_options,direct,False,direct.getter,direct.setter,
                .5,direct_first,direct_change,2,False,0,tween.UpdateNotice.NONE)
            if direct_calls!=[(.5,2)] or abs(direct_values[-1].y-.19509032201612825)>2e-7:
                raise RuntimeError('Direct Euler plugin did not capture values before the ease callback')
            direct_calls.clear()
            def direct_array_ease(t,d,a,p):
                direct_calls.append((t,d))
                direct.start_value[1].x,direct.change_value[1].x=100,120
                direct_options.axis_constraint=tween.AxisConstraint.X;direct_options.snapping=True
                return t/d
            direct=direct_manager.to_array(Vector3,direct_values.append,[Vector3(4,8,12),Vector3(10,20,30)],[.4,.6])
            direct.set_ease(direct_array_ease).set_auto_kill(False).force_init()
            direct_options=copy(direct.plug_options)
            previous_segment_duration=direct._segment_duration
            direct.get_plugin().evaluate_and_apply(direct_options,direct,False,direct.getter,direct.setter,
                .5,direct.start_value,direct.change_value,2,False,0,tween.UpdateNotice.NONE)
            if (max(abs(a-b) for a,b in zip(direct_values[-1],(120,10,15)))>2e-6
                    or len(direct_calls)!=1 or max(abs(a-b) for a,b in zip(direct_calls[0],(.1,.6)))>1e-7
                    or direct._segment_duration!=previous_segment_duration):
                raise RuntimeError('Direct array plugin lost shared storage or changed the owner segment clock')
            direct_manager.clear()
            self._observations.append({'stage':'builtin_plugin_invocation','kinds':3,
                                       'explicit_seconds':True,'value_capture':True,'shared_array':True,
                                       'owner_clock_preserved':True,'assert_independent_checks':True})
            import math
            from infernux.lib import _Infernux as _curve_native
            from infernux.components.builtin.line_renderer import _set_width_curve,_get_width_curve
            boundary_key=inx.Keyframe(0,1)
            boundary_key.out_weight=math.inf;boundary_key.weighted_mode=-1
            boundary_curve=inx.AnimationCurve(boundary_key,inx.Keyframe(1,2,1,0))
            if int(boundary_key.weighted_mode)!=-1 or not math.isnan(boundary_curve.evaluate(.5)):
                raise RuntimeError('Curve field values were rejected or changed by the numerical snapshot')
            boundary_curve.pre_wrap_mode=inx.WrapMode.ONCE
            boundary_curve.post_wrap_mode=255
            if int(boundary_curve.pre_wrap_mode)!=8 or int(boundary_curve.post_wrap_mode)!=8:
                raise RuntimeError('Curve wrap setter did not normalize its modes')
            native_line=_curve_native.LineRenderer();_set_width_curve(native_line,boundary_curve)
            line_copy=_curve_native.LineRenderer();line_copy.deserialize(native_line.serialize())
            line_curve=_get_width_curve(line_copy)
            if (int(line_curve[0].weighted_mode)!=-1 or line_curve[0].out_weight!=math.inf
                    or line_curve.get_hash_code()!=boundary_curve.get_hash_code()):
                raise RuntimeError('Curve metadata was lost by native line JSON storage')
            invalid_key=inx.Keyframe(math.inf,2)
            if inx.AnimationCurve(inx.Keyframe(0,0),invalid_key).length!=1:
                raise RuntimeError('Curve constructor did not filter invalid bulk key fields')
            boundary_curve=inx.AnimationCurve.linear(0,0,1,1)
            boundary_curve.add_key(invalid_key)
            boundary_curve.add_key(inx.Keyframe(.5,math.nan))
            boundary_document=json.loads(json.dumps(boundary_curve.to_dict(),allow_nan=False))
            boundary_copy=inx.AnimationCurve.from_dict(boundary_document)
            if (boundary_copy.length!=4 or not math.isnan(boundary_copy[1].value)
                    or boundary_copy[3].time!=math.inf):
                raise RuntimeError('Stored curve JSON reapplied bulk filtering to inserted keys')
            left_key,right_key=inx.Keyframe(0,0),inx.Keyframe(0,0)
            left_key.in_tangent=right_key.in_tangent=math.nan
            left_curve,right_curve=inx.AnimationCurve(left_key),inx.AnimationCurve(right_key)
            if left_key!=right_key or left_curve.equals(right_curve) or not left_curve.equals(left_curve):
                raise RuntimeError('Curve or key NaN comparison has incorrect value semantics')
            self._observations.append({'stage':'curve_field_contract','wrap_normalization':True,
                                       'bulk_filter':True,'inserted_keys_preserved':True,'signed_weight_flags':True,
                                       'native_line_json':True,'nan_equality':True,'assert_independent_checks':True})
            weighted_left,weighted_right=inx.Keyframe(0,0,0,3),inx.Keyframe(1,1,3,0)
            weighted_left.out_weight,weighted_left.weighted_mode=2,inx.WeightedMode.OUT
            weighted_right.in_weight,weighted_right.weighted_mode=2,inx.WeightedMode.IN
            weighted_curve=inx.AnimationCurve(weighted_left,weighted_right)
            root=.5+math.sqrt(.15)
            expected_weighted=18*(1-root)**2*root-15*(1-root)*root**2+root**3
            if abs(weighted_curve.evaluate(.5)-expected_weighted)>2e-6:
                raise RuntimeError('Weighted curve selected a different inverse branch')
            weighted_ease=tween.EaseCurve(weighted_curve)
            weighted_times=np.linspace(0,1,1024,dtype=np.float64)
            frozen_weighted=weighted_curve._native_snapshot()
            original_weighted=np.asarray(frozen_weighted.evaluate_many(weighted_times))
            edited_weighted=weighted_curve[0]
            edited_weighted.out_weight=.25
            weighted_curve.move_key(0,edited_weighted)
            weighted_values=np.asarray(weighted_curve.evaluate_many(weighted_times))
            weighted_output=np.empty_like(weighted_times)
            weighted_ease.evaluate_into(weighted_times,weighted_output)
            if (not np.array_equal(weighted_output,weighted_values)
                    or not np.array_equal(np.asarray(frozen_weighted.evaluate_many(weighted_times)),original_weighted)
                    or np.array_equal(original_weighted,weighted_values)):
                raise RuntimeError('Weighted easing lost live asset or immutable snapshot semantics')
            self._observations.append({'stage':'weighted_curve_runtime','inverse_branch':True,
                                        'bulk_samples':1024,'live_asset':True,'retained_snapshot':True,
                                        'assert_independent_checks':True})
            mapped_ease=tween.EaseCurve(inx.AnimationCurve.linear(0,0,1e20,1))
            mapped_times=np.asarray([0.,2.5e-301,5e-301,7.5e-301,1e-300],dtype=np.float64)
            mapped_scalar=np.asarray([mapped_ease.evaluate(time,1e-300,0,0) for time in mapped_times])
            mapped_output=np.empty_like(mapped_times)
            mapped_ease.evaluate_into(mapped_times,mapped_output,1e-300)
            if (mapped_scalar[2] != .5 or not np.array_equal(mapped_scalar,mapped_output)
                    or not np.array_equal(mapped_scalar,np.asarray(mapped_ease.evaluate_many(mapped_times,1e-300)))):
                raise RuntimeError('Curve easing changed its time mapping between scalar and batch sampling')
            if not np.isnan(mapped_ease.evaluate(float('nan'),0.,0,0)):
                raise RuntimeError('Zero-duration curve easing lost its nonfinite input')
            self._observations.append({'stage':'curve_time_mapping','division_before_scale':True,
                                        'scalar_and_bulk_equal':True,'assert_independent_checks':True})
            from infernux.lib import TextLayout
            font_grid = TextLayout('NNNP1 枫叶 |\n测试换行与 |',font_size=30)
            font_markers = [glyph for glyph in font_grid.glyphs if glyph.codepoint == ord('|')]
            if len(font_markers) != 2 or font_markers[0].bounds[0] != font_markers[1].bounds[0]:
                raise RuntimeError('Default font columns do not align')
            latin_width = TextLayout('A',font_size=30).width
            chinese_width = TextLayout('中',font_size=30).width
            if chinese_width != latin_width*2:
                raise RuntimeError(f'Default font cell ratio is invalid: {latin_width=}, {chinese_width=}')
            for font_size in (18,24,25.5,30,32):
                long_grid = TextLayout('A'*512+'|\n'+'中'*256+'|',font_size=font_size)
                long_markers = [glyph for glyph in long_grid.glyphs if glyph.codepoint == ord('|')]
                if long_markers[0].bounds[0] != long_markers[1].bounds[0] or long_grid.lines[0].width != long_grid.lines[1].width:
                    raise RuntimeError(f'Long font columns drift at {font_size=}')
                if len(TextLayout(long_grid.text,font_size=font_size,wrap_width=long_grid.width).lines) != 2:
                    raise RuntimeError(f'Measured font width does not fit its wrap limit at {font_size=}')
            self._observations.append({'stage':'default_font_cells','latin':latin_width,'chinese':chinese_width,
                                       'aligned_columns':True,'extra_spacing':0,'long_column_sizes':5,
                                       'assert_independent_checks':True})
            curve = inx.AnimationCurve(inx.Keyframe(0, 0, 0, 4, .2, .8, inx.WeightedMode.BOTH),
                                       inx.Keyframe(1, 1, -2, 0, .1, .5, inx.WeightedMode.BOTH))
            curve_value = [0.]
            curve_tween = tween.to(lambda: curve_value[0], lambda v: curve_value.__setitem__(0, v), 10., 1.).set_ease(curve)
            curve_tween.goto(.25)
            before_smoothing = curve_value[0]
            curve.smooth_tangents(0, 0)
            curve.smooth_tangents(1, 0)
            curve_tween.goto(.25)
            assert curve_value[0] != before_smoothing and abs(curve_value[0] - 2.5) < 1e-6
            curve_tween.kill()
            self._observations.append({'stage': 'curve_key_edit', 'live_value': curve_value[0]})
            core_values = [np.float32(2)]
            core = tween.to(lambda: core_values[0], lambda value: core_values.__setitem__(0, value), np.float32(10), 1.)
            core.set_ease(tween.Ease.LINEAR).set_auto_kill(False).pause()
            core.force_init()
            assert isinstance(core, tween.TweenerCore)
            core.start_value, core.end_value, core.change_value = 5., 20., 40.
            core.plug_options.snapping = True
            prepared = core._numeric_job
            core.goto(.26)
            assert core_values[0] == 15. and core.end_value == 20. and core.change_value == 40.
            assert core._numeric_job is prepared and isinstance(core.get_plugin(), tween.AbsTweenPlugin)
            core.kill()
            self._observations.append({'stage': 'typed_core', 'value': float(core_values[0]), 'prepared_job_reused': True})
            colors = [[2., 3., 4., 5.]]
            color = tween.to(lambda: colors[0], lambda value: colors.__setitem__(0, value),
                             [10., 13., 16., 19.], 1.).set_ease(tween.Ease.LINEAR).set_auto_kill(False).pause()
            color.force_init()
            color_job = color._numeric_job
            color.start_value[0], color.change_value[0], color.end_value[0] = 5, 20, 999
            color.goto(.5)
            assert colors[0] == [15., 8., 10., 12.] and color._numeric_job is color_job
            color.plug_options.alpha_only = True
            colors[0] = [100., 200., 300., 0.]
            color.start_value[-1], color.change_value[-1] = .25, .5
            color.goto(.5)
            assert colors[0] == [100., 200., 300., .5] and color._numeric_job is color_job
            color.kill()
            self._observations.append({'stage': 'color_fields', 'red': 15., 'alpha': .5, 'prepared_job_reused': True})
            reentry_values, reentry_calls, reentry_state = [[2.,3.,4.,5.]], [], {'armed': False}
            def original_color(value):
                reentry_values[0] = value
                reentry_calls.append('original')
            def replacement_color(value):
                reentry_values[0] = value
                reentry_calls.append('replacement')
            def edit_during_ease(t, d, amplitude, period):
                if reentry_state['armed']:
                    reentry_state['armed'] = False
                    reentry.start_value.r, reentry.change_value.r = 50, 100
                    reentry.plug_options.alpha_only = True
                    reentry.setter = replacement_color
                return t / d
            reentry = tween.to(lambda: reentry_values[0], original_color, [10.,13.,16.,19.], 1.)
            reentry.set_ease(edit_during_ease).set_auto_kill(False).force_init()
            reentry_values[0], reentry_state['armed'] = [100.,200.,300.,0.], True
            reentry.goto(.5)
            assert reentry_values[0] == [6.,8.,10.,12.] and reentry_calls == ['original']
            reentry_values[0] = [100.,200.,300.,0.]
            reentry.goto(.75)
            assert reentry_values[0] == [100.,200.,300.,15.5] and reentry_calls == ['original','replacement']
            reentry.kill()
            self._observations.append({'stage': 'value_callback_snapshot', 'first_red': 6.,
                                       'next_alpha': 15.5, 'setters': reentry_calls})
            self._check_value_arguments()
            self._array_handle = tween.to_array(lambda: self._array_value, lambda value: setattr(self, '_array_value', value),
                [Vector3(1, 2, 3), Vector3(2, 3, 4)], [.15, .15]).set_ease(tween.Ease.LINEAR)
            self._array_handle.force_init()
            self._array_handle.start_value[0].x = 1
            self._array_plan = self._array_handle._numeric_segments
            self._array_handle.on_complete(self._array_completed)
            tween.to(lambda: self._string_value, lambda value: setattr(self, '_string_value', value), 'ABCD', .3).set_ease(tween.Ease.LINEAR)
            tween.to(lambda: self._rect_value, lambda value: setattr(self, '_rect_value', value), Rect(2, 4, 6, 8), .3).set_ease(tween.Ease.LINEAR)
            scene = SceneManager.instance().get_active_scene()
            self._vector_handle = tween.to(lambda: self._live_vector_value,
                lambda value: setattr(self, '_live_vector_value', value), Vector3(10, 12, 14), .3).set_ease(tween.Ease.LINEAR)
            self._vector_handle.force_init()
            self._vector_plan = self._vector_handle._numeric_job
            self._vector_handle.start_value.x, self._vector_handle.change_value.x = 5, 7
            self._vector_handle.on_complete(self._vector_completed)
            self._rotator = scene.create_game_object('Player Euler rotation probe').transform
            self._rotator.euler_angles = Vector3(10, 20, 30)
            self._rotation_handle = tween.twn_rotate(self._rotator, Vector3(0, 90, 0), .3).set_ease(tween.Ease.LINEAR)
            self._rotation_handle.force_init()
            self._rotation_plan = self._rotation_handle._numeric_job
            self._rotation_handle.on_complete(self._rotation_completed)
            self._look_owner = scene.create_game_object('Player dynamic orientation probe').transform
            self._look_owner.position = Vector3(1, 2, 3)
            self._look_point = Vector3(5, 4, 9)
            self._look_handle = tween.twn_dynamic_look_at(self._look_owner, self._look_point, .3).set_ease(tween.Ease.LINEAR)
            self._look_handle.force_init()
            self._look_plan = self._look_handle._numeric_job
            self._look_handle.on_complete(self._look_completed)
            self._authored = scene.find('Cooked Tween authoring probe')
            assert self._authored is not None
            self._authored_ui = scene.find('Cooked Tween UI rectangle').get_component(inx.UIImage)
            assert (self._authored_ui.width, self._authored_ui.height) == (620., 330.)
            self._mover = scene.create_game_object('Player path probe')
            path = tween.twn_path(self._mover.transform, [(1, 0, 0), (2, 1, 0)], .3,
                                  tween.PathType.CATMULL_ROM).set_ease(tween.Ease.LINEAR)
            path.set_look_at(.01).set_update(tween.UpdateType.MANUAL).set_auto_kill(False)
            path.goto(.3)
            assert abs(self._mover.transform.position.x - 2) < 1e-5
            assert abs(self._mover.transform.position.y - 1) < 1e-5
            path.kill()
            self._live_path_owner = scene.create_game_object('Player mutable path probe').transform
            self._live_path_handle = tween.twn_path(self._live_path_owner, [(1, 0, 0), (2, 1, 0)], .3,
                tween.PathType.CATMULL_ROM).set_ease(tween.Ease.LINEAR)
            self._live_path_handle.force_init()
            assert isinstance(self._live_path_handle, tween.TweenerCore)
            assert self._live_path_handle.start_value is self._live_path_handle.end_value is self._live_path_handle.change_value
            self._path_plan = self._live_path_handle.change_value._tables
            self._live_path_handle.on_complete(self._path_completed)
            self._bezier_owner = scene.create_game_object('Player Bezier storage probe').transform
            self._bezier_handle = tween.twn_path(self._bezier_owner,
                [(2,1,0),(.5,0,0),(1.5,1,0),(4,1,0),(2.5,1,0),(3.5,1,0)], .3,
                tween.PathType.CUBIC_BEZIER).set_ease(tween.Ease.LINEAR)
            self._bezier_handle.force_init()
            assert len(self._bezier_handle.change_value.wps) == 3
            assert len(self._bezier_handle.change_value.control_points) == 2
            self._bezier_plan = self._bezier_handle.change_value._tables
            self._bezier_handle.on_complete(self._bezier_completed)
            self._prepare_shared_path_probe(scene)
            self._verify_orientation_callback(scene)
            self._verify_frame_dispatch()
            self._verify_unbound_ui_parent(scene)
            self._verify_path_clock_refresh(scene)
            self._verify_text_frame_commit(scene)
            self._verify_material_property_ids()
            self._verify_circle_from_keyword(scene)
            self._verify_clock_preparation(scene)
            self._verify_plugin_keyword_calls(scene)
            self._verify_curve_utilities(scene)
            self._verify_color_pair_values(scene)
            self._verify_rect_offset_values(scene)
            self._verify_public_clock_properties(scene)
            self._verify_single_clock_fields(scene)
            self._verify_public_math_utilities(scene)
            self._verify_prepared_clock(scene)
            self._verify_bounded_playback_clock(scene)
            self._verify_ease_factor_width(scene)
            self._verify_time_query_width(scene)
            self._verify_waypoint_lengths(scene)
            self._verify_direct_path_application(scene)
            self._verify_path_batch_mutations(scene)
            self._verify_signed_path_clock(scene)
            self._verify_path_rotation_axes(scene)
            self._prepare_scheduler_probe()

            self._body_object = scene.create_game_object('Player fixed-step probe')
            self._body_object.transform.position = Vector3(-1, 1, 0)
            self._body_object.add_component(inx.BoxCollider)
            self._body = self._body_object.add_component(inx.Rigidbody)
            self._body.is_kinematic, self._body.use_gravity = True, False
            tween.twn_move(self._body, Vector3(1, 1, 0), .3).set_ease(tween.Ease.LINEAR) \
                .set_update(tween.UpdateType.FIXED).on_complete(lambda: self._completions.append('fixed'))

            curve = inx.AnimationCurve.linear(0, 0, 1, 1)
            for index, independent in enumerate((False, True)):
                tween.to(lambda i=index: self._values[i], lambda value, i=index: self._values.__setitem__(i, value),
                         1., .3).set_ease(curve).set_update(tween.UpdateType.NORMAL, independent) \
                    .on_complete(lambda i=index: self._completions.append(str(i)))
            for index, end in enumerate((1000, 6000000008)):
                tween.to(lambda i=index: self._integer_values[i],
                         lambda value, i=index: self._integer_values.__setitem__(i, value), end, .3) \
                    .set_ease(tween.Ease.LINEAR)
            tween.to(lambda: self._single_value, lambda value: setattr(self, '_single_value', value), np.float32(.9), .3) \
                .set_ease(tween.Ease.LINEAR)
            for index, dtype in enumerate(self._typed_dtypes):
                tween.to(lambda i=index: self._typed_values[i], lambda value, i=index: self._typed_values.__setitem__(i, value),
                         dtype(self._typed_end[index]), .3).set_ease(tween.Ease.LINEAR)

            sequence_object = scene.create_game_object('Player sequence probe')
            tween.sequence().append(tween.twn_local_move(sequence_object.transform, Vector3(2, 0, 0), .1)) \
                .append(tween.twn_scale(sequence_object.transform, 1.5, .1)) \
                .on_complete(lambda: self._completions.append('sequence'))
            self._sequence_object = sequence_object

            canvas = scene.create_game_object('Player UI probe').add_component(inx.UICanvas)
            canvas.reference_width, canvas.reference_height = 640, 360
            self._canvas = canvas
            font_object = scene.create_game_object('Player monospace font columns')
            font_object.set_parent(canvas.game_object, False)
            font_text = font_object.add_component(inx.UIText)
            font_text.text = 'AAAA|\n中中|'
            font_text.font_size = 24
            font_text.color = [1., 1., 0., 1.]
            font_text.set_rect(60, 230, 180, 100, 640, 360)
            static_object = scene.create_game_object('Player unchanged UI sibling')
            static_object.set_parent(canvas.game_object, False)
            self._static_image = static_object.add_component(inx.UIImage)
            self._static_image.color = [0., 0., 1., 1.]
            self._static_image.set_rect(20, 20, 24, 24, 640, 360)
            image_object = scene.create_game_object('Player animated rectangle')
            image_object.set_parent(canvas.game_object, False)
            self._image = image_object.add_component(inx.UIImage)
            self._image.anchor_min = self._image.anchor_max = Vector2(.5, .5)
            self._image.size_delta = Vector2(40, 30)
            self._image.color = [0., 1., 0., 1.]
            tween.twn_anchor_pos(self._image, Vector2(60, 20), .3).set_ease(tween.Ease.LINEAR)
            tween.twn_size_delta(self._image, Vector2(80, 40), .3).set_ease(tween.Ease.LINEAR)
            unit_object = scene.create_game_object('Player UI unit transition')
            self._unit_image = unit_object.add_component(inx.UIImage)
            self._unit_image.enabled = False
            self._unit_image.anchor_min = self._unit_image.anchor_max = Vector2(.5, .5)
            self._unit_image.anchored_position3d = Vector3(150, 75, 3)
            tween.twn_anchor_pos3d(self._unit_image, Vector3(250, 175, 7), .3).set_ease(tween.Ease.LINEAR)
            self._handles = tuple(tween.playing_tweens())
            for handle in self._handles:
                handle.pause()
        except BaseException:
            self._finish(False, traceback.format_exc())

    def update(self, delta_time):
        if self._finished:
            return
        try:
            if self._stage == -1:
                self._warmup_frames += 1
                if self._warmup_frames >= 8:
                    inx.Time.time_scale = 0
                    self._stage = 0
                return
            if self._stage == 0:
                for handle in self._handles:
                    handle.play()
                self._stage = 1
                return
            self._elapsed += inx.Time.unscaled_delta_time
            if self._stage == 1 and self._elapsed > .04:
                self._frozen = self._values[0], tuple(self._body.position), SceneManager.instance().fixed_time
                self._stage = 2
            elif self._stage == 2 and self._elapsed > .12:
                assert self._values[0] == self._frozen[0]
                assert tuple(self._body.position) == self._frozen[1]
                assert SceneManager.instance().fixed_time == self._frozen[2]
                assert self._values[1] > self._values[0]
                assert self._integer_values == [0, 6000000000]
                assert tuple(self._array_value) == (0, 0, 0) and self._string_value == ''
                assert self._rect_value == Rect(0, 0, 0, 0)
                self._near(self._rotator.rotation, quatf.euler(10, 20, 30))
                self._look_owner.position = Vector3(2, 2, 3)
                assert tuple(self._live_vector_value) == (2, 3, 4)
                self._vector_handle.start_value.x = 6
                assert tuple(self._live_path_owner.position) == (0, 0, 0)
                self._live_path_handle.change_value.points[-1].x = 3
                assert tuple(self._bezier_owner.position) == (0,0,0)
                self._bezier_handle.change_value.wps[-1].x = 5
                self._bezier_handle.change_value.control_points[0].a.y = 2
                self._resume_shared_path_probe()
                assert type(self._single_value) is np.float32 and self._single_value == np.float32(.1)
                assert all(type(value) is dtype and value == dtype(initial)
                           for dtype, value, initial in zip(self._typed_dtypes, self._typed_values, self._typed_initial))
                self._observations.append({'stage': 'paused', 'values': list(self._values),
                                           'body': tuple(self._body.position)})
                scene = SceneManager.instance().get_active_scene()
                destination = scene.create_game_object('Player fresh Canvas').add_component(inx.UICanvas)
                destination.reference_width, destination.reference_height = 1280, 720
                rectangle_owner = self._image.rect_transform
                self._image.anchor_min, self._image.anchor_max = Vector2(0, 0), Vector2(1, 1)
                self._image.size_delta = Vector2(-20, -30)
                self._image.game_object.set_parent(destination.game_object, False)
                assert self._image.rect_transform is rectangle_owner
                assert (self._image.width, self._image.height) == (1260., 690.)
                destination.reference_width = 1440
                assert self._image.width == 1420
                self._image.game_object.set_parent(self._canvas.game_object, False)
                assert self._image.rect_transform is rectangle_owner
                self._image.anchor_min = self._image.anchor_max = Vector2(.5, .5)
                self._image.size_delta = Vector2(40, 30)
                self._observations.append({'stage': 'reparented', 'same_native_owner': True})
                self._unit_image.game_object.set_parent(self._canvas.game_object, False)
                self._near(self._unit_image.transform.local_position, (150, 75, 3))
                inx.Time.time_scale = 1
                self._stage = 3
            elif self._stage == 3 and not tween.total_active_tweens():
                assert self._values == [1., 1.]
                assert self._integer_values == [1000, 6000000008]
                assert tuple(self._array_value) == (2, 3, 4) and self._array_plan_reused
                assert self._string_value == 'ABCD' and self._rect_value == Rect(2, 4, 6, 8)
                assert self._rotation_plan_reused and self._look_plan_reused
                assert self._vector_plan_reused and tuple(self._live_vector_value) == (13, 12, 14)
                assert self._path_plan_reused and tuple(self._live_path_owner.position) == (3, 1, 0)
                assert self._shared_path_plan_reused and tuple(self._shared_owner.position) == (4,0,0)
                assert self._bezier_plan_reused and tuple(self._bezier_owner.position) == (5,1,0)
                self._near(self._rotator.rotation, quatf.euler(0, 90, 0))
                self._near(self._look_owner.rotation, quatf.look_rotation(self._look_point - self._look_owner.position, Vector3(0, 1, 0)))
                assert all(type(value) is int for value in self._integer_values)
                assert type(self._single_value) is np.float32 and self._single_value == np.float32(.9)
                assert all(type(value) is dtype and value == dtype(end)
                           for dtype, value, end in zip(self._typed_dtypes, self._typed_values, self._typed_end))
                assert sorted(self._completions) == ['0', '1', 'fixed', 'sequence']
                assert tuple(self._body.position) == (1., 1., 0.)
                assert tuple(self._sequence_object.transform.local_position) == (2., 0., 0.)
                assert tuple(self._sequence_object.transform.local_scale) == (1.5, 1.5, 1.5)
                assert tuple(self._authored.transform.local_position) == (0., 2., 0.)
                assert tuple(self._authored_ui.size_delta) == (-40., -50.)
                assert (self._authored_ui.width, self._authored_ui.height) == (600., 310.)
                assert tuple(self._image.anchored_position) == (60., 20.)
                assert tuple(self._image.size_delta) == (80., 40.)
                assert self._image.get_rect(640, 360) == (340., 140., 80., 40.)
                assert not self._static_image.transform._has_rect_layout
                assert self._static_image.get_rect(640, 360) == (20., 20., 24., 24.)
                self._near(self._unit_image.transform.local_position, (250, 175, 7))
                self._unit_image.game_object.set_parent(None, False)
                self._near(self._unit_image.transform.local_position, (2.5, 1.75, .07))
                corners = tuple(tuple(point) for point in self._unit_image.rect_transform.get_world_corners())
                self._unit_image.game_object.set_parent(self._canvas.game_object, True)
                for point, expected in zip(self._unit_image.rect_transform.get_world_corners(), corners):
                    self._near(point, expected)
                self._unit_image.game_object.set_parent(None, True)
                for point, expected in zip(self._unit_image.rect_transform.get_world_corners(), corners):
                    self._near(point, expected)
                self._observations.append({'stage': 'space_units', 'world_position': tuple(self._unit_image.transform.position),
                                           'world_corners': corners})
                editor_modules = [name for name in ('infernux.engine.play_mode', 'infernux.engine.ui.curve_editor',
                                                    'infernux.engine.interaction.previews') if name in sys.modules]
                assert not editor_modules, editor_modules
                self._observations.append({'stage': 'completed', 'values': list(self._values),
                                           'array_value': tuple(self._array_value), 'string_value': self._string_value,
                                           'rect_value': tuple(self._rect_value), 'array_native_plan_reused': self._array_plan_reused,
                                           'rotation': tuple(self._rotator.rotation), 'dynamic_look_rotation': tuple(self._look_owner.rotation),
                                           'rotation_native_plan_reused': self._rotation_plan_reused,
                                           'dynamic_look_native_plan_reused': self._look_plan_reused,
                                           'live_vector_value': tuple(self._live_vector_value), 'vector_native_plan_reused': self._vector_plan_reused,
                                           'live_path_position': tuple(self._live_path_owner.position), 'path_native_plan_reused': self._path_plan_reused,
                                           'bezier_position': tuple(self._bezier_owner.position), 'bezier_native_plan_reused': self._bezier_plan_reused,
                                           'shared_path_position': tuple(self._shared_owner.position), 'shared_path_native_plan_reused': self._shared_path_plan_reused,
                                           'integer_values': list(self._integer_values),
                                           'single_value': float(self._single_value), 'single_dtype': type(self._single_value).__name__,
                                           'typed_values': [str(value) for value in self._typed_values],
                                           'typed_dtypes': [type(value).__name__ for value in self._typed_values],
                                           'body': tuple(self._body.position), 'editor_modules': editor_modules})
                self._stage = 4
            elif self._stage == 4:
                self._capture_output()
            if self._elapsed > 15:
                raise AssertionError('Player probe exceeded its frame-time deadline')
        except BaseException:
            self._finish(False, traceback.format_exc())

    def _capture_output(self):
        if not inx.Application.renderer_state()['submission_ready']:
            return
        if self._capture is None:
            self._capture = inx.Application.request_render_target_capture(
                'game', str(Path(inx.Application.persistent_data_path()) / 'tween-player.png'))
            return
        capture = inx.Application.query_render_target_capture(self._capture)
        assert capture['status'] not in ('failed', 'cancelled'), capture
        if capture['status'] == 'completed':
            self._observations.append({'stage': 'rendered', 'capture': capture})
            self._complete_checks()

    def _complete_checks(self):
        assert self._scheduler_first == 1, self._scheduler_first
        assert self._scheduler_retired_in_trigger is False
        assert self._scheduler_late_retired
        self._observations.append({'stage': 'scheduler_dynamic',
            'resumed_on_first_update': True, 'paused_late_root_retired': True,
            'retirement_deferred_in_callback': True})
        self._finish(True)

    def _verify_path_rotation_axes(self, scene):
        directions = []
        for kind in ('unlocked', 'locked_builtin', 'locked_custom'):
            target = scene.create_game_object('Player path axes ' + kind).transform
            handle = tween.twn_path(target, [Vector3(2, 2, 0), Vector3(4, 3, 2)], 1,
                tween.PathType.CATMULL_ROM).set_ease(tween.Ease.LINEAR).set_look_at(.01)
            if kind != 'unlocked':
                handle.set_options(tween.AxisConstraint.NONE, tween.AxisConstraint.X | tween.AxisConstraint.Z)
            if kind == 'locked_custom':
                handle.setter = lambda value, target=target: setattr(target, 'position', value)
            handle.pause().goto(.25)
            directions.append(tuple(target.forward))
            if kind == 'unlocked':
                assert target.forward.y > .1
            else:
                assert abs(target.forward.y) < 2e-5 and abs(target.up.y - 1) < 2e-5
            handle.kill()
        assert directions[1] == directions[2]
        self._observations.append({'stage': 'path_rotation_axes',
            'locked_forward': directions[1], 'custom_setter_matches': True})

    def _verify_signed_path_clock(self, scene):
        target = scene.create_game_object('Player signed waypoint clock').transform
        handle = tween.twn_path(target, [Vector3(1, 0, 0), Vector3(2, 0, 0)], 1)
        handle.set_ease(tween.Ease.LINEAR).set_loops(3).set_auto_kill(False)
        handle.set_update(tween.UpdateType.MANUAL).pause().force_init()
        handle.end_value.wp_lengths = [0, -.5, 3]
        events = []
        for name in ('start', 'play', 'rewind', 'step_complete', 'complete', 'pause'):
            getattr(handle, 'on_' + name)(lambda name=name: events.append(name))
        handle.goto_waypoint(1, True)
        assert handle.elapsed() == -1 and target.position.x == 0
        for _ in range(4):
            tween.manual_update(.25, .25)
        assert handle.elapsed() == 0 and handle.is_playing() and target.position.x == 0
        assert events == ['start', 'play', 'rewind', 'step_complete']
        tween.manual_update(3, 3)
        assert handle.is_complete() and not handle.is_playing() and target.position.x == 2
        assert events[-2:] == ['complete', 'pause']
        handle.kill()
        self._observations.append({'stage': 'signed_path_clock', 'crossed_zero': True,
            'lifecycle_order': True, 'completed': True})

    def _verify_path_batch_mutations(self, scene):
        target = scene.create_game_object('Player path callback batch').transform
        events = []
        handle = tween.twn_path(target, [Vector3(i, 0, 0) for i in (1, 2, 3)], 3)
        handle.set_ease(tween.Ease.LINEAR).set_auto_kill(False).pause()
        def notify(index):
            events.append(('old', index))
            if index == 1:
                handle.on_waypoint_change(lambda next_index: events.append(('new', next_index)))
        handle.on_waypoint_change(notify).goto(2.5)
        assert events == [('old', 0), ('old', 1), ('new', 2)]
        handle.kill()
        target.position = Vector3()
        child = tween.twn_path(target, [Vector3(i, 0, 0) for i in (1, 2, 3)], 3).set_ease(tween.Ease.LINEAR)
        root = tween.sequence().append(child).set_update(tween.UpdateType.MANUAL).set_auto_kill(False)
        events, changed = [], False
        def seek(index):
            nonlocal changed
            events.append(index)
            if index == 1 and not changed:
                changed = True
                root.goto(.5, True)
        child.on_waypoint_change(seek)
        root.goto(2.5, True)
        assert events == [0, 1, 1, 2] and target.position.x == root.elapsed() == .5
        tween.manual_update(.25, .25)
        assert events == [0, 1, 1, 2, 0] and root.elapsed() == .75
        root.kill()
        self._observations.append({'stage': 'path_batch_mutations',
            'live_callback_replacement': True, 'reentrant_sequence_clock': True})

    def _prepare_scheduler_probe(self):
        self._scheduler_hits = 0
        self._scheduler_first = None
        self._scheduler_late_retired = False
        self._scheduler_retired_in_trigger = None
        def retired():
            self._scheduler_late_retired = True
        late = tween.to(lambda: 0., lambda value: None, 1., 1.)
        late.set_update(tween.UpdateType.LATE).pause().on_kill(retired)
        def first_update():
            self._scheduler_hits += 1
            if self._scheduler_hits == 1:
                second.play()
                late.kill()
                self._scheduler_retired_in_trigger = self._scheduler_late_retired
        first = tween.to(lambda: 0., lambda value: None, 1., .3)
        first.set_ease(tween.Ease.LINEAR).on_update(first_update)
        def second_update():
            if self._scheduler_first is None:
                self._scheduler_first = self._scheduler_hits
        second = tween.to(lambda: 0., lambda value: None, 1., .3)
        second.set_ease(tween.Ease.LINEAR).pause().on_update(second_update)

    def _verify_orientation_callback(self, scene):
        target = scene.create_game_object('Player orientation callback').transform
        value = [0.]
        receiver = tween.to(lambda:value[0],lambda v:value.__setitem__(0,v),1.,1).set_target(target).pause()
        receiver.force_init()
        options = tween.PathOptions()
        options.mode = tween.PathMode.FULL3_D
        options.orient_type = tween.OrientType.LOOK_AT_POSITION
        options.look_at_position = Vector3(10,0,0)
        path = tween.Path(Vector3(),[Vector3(2,0,0),Vector3(2/3,0,0),Vector3(4/3,0,0)],tween.PathType.CUBIC_BEZIER)
        tween.PathPlugin.get().set_orientation(options,receiver,path,.25,Vector3(),tween.UpdateNotice.NONE)
        self._near(target.rotation,quatf.look_rotation(Vector3(1,0,0)))
        assert tuple(target.position)==(0,0,0) and receiver.elapsed()==0 and value[0]==0
        try:
            path.evaluate(-.1)
        except IndexError:
            pass
        else:
            raise AssertionError('Raw negative curve parameters must report an index error')
        receiver.kill()
        self._observations.append({'stage':'orientation_callback','rotation':tuple(target.rotation),
                                   'clock_unchanged':True,'native_negative_parameter_error':True})

    def _verify_direct_path_application(self, scene):
        target = scene.create_game_object('Player direct path application').transform
        value = [0.]
        caller = tween.to(lambda:value[0],lambda v:value.__setitem__(0,v),1.,1.)
        caller.set_target(target).set_ease(tween.Ease.LINEAR).set_auto_kill(False).pause().force_init()
        path = tween.Path(Vector3(),[Vector3(2,0,0),Vector3(5,0,0)])
        options = tween.PathOptions()
        options.reset()
        events = []
        caller.on_waypoint_change(events.append)
        tween.PathPlugin.get().evaluate_and_apply(options,caller,False,caller.getter,
            lambda sample:setattr(target,'position',sample),.5,None,path,1,False,0,tween.UpdateNotice.NONE)
        assert abs(target.position.x - 2.5) < 1e-6 and caller._waypoint == 1 and events == [0,1]
        assert caller.elapsed() == 0 and value[0] == 0 and not caller.is_playing()
        caller.kill()
        aim = Vector3(30,10,20)
        handle = tween.twn_path(target,[Vector3(10,13,16),Vector3(20,23,26)],1,tween.PathType.CATMULL_ROM)
        handle.set_look_at(aim).set_ease(tween.Ease.LINEAR).set_auto_kill(False).pause().force_init()
        before_up = target.up
        def write(sample):
            target.position = sample
            handle.plug_options.look_at_position.x = -40
        handle.setter = write
        handle.goto(.5)
        assert quatf.angle(target.rotation,quatf.look_rotation(aim-target.position,before_up)) < .06
        assert handle.plug_options.look_at_position.x == -40
        handle.kill()
        self._observations.append({'stage':'direct_path_application','owner_state':True,'clock_preserved':True,'option_snapshot':True})

    def _verify_waypoint_lengths(self, scene):
        target = scene.create_game_object('Player waypoint buffer').transform
        handle = tween.twn_path(target, [Vector3(2,0,0),Vector3(5,0,0)], 1)
        handle.set_ease(tween.Ease.LINEAR).set_auto_kill(False).pause().force_init()
        path = handle.end_value
        geometry = path._tables
        lengths = path.wp_lengths
        view = memoryview(lengths)
        view[1], view[2] = 1, 4
        events = []
        handle.on_waypoint_change(events.append)
        handle.goto_waypoint(1)
        assert abs(handle.elapsed() - .2) < 1e-6 and abs(target.position.x - 1) < 1e-6
        assert events == [0,1] and geometry is path._tables
        handle.goto(.5)
        assert abs(target.position.x - 2.5) < 1e-6 and geometry is path._tables
        handle.kill()
        assert path.wp_lengths is None and list(view) == [0,1,4]
        self._observations.append({'stage':'waypoint_lengths','position':target.position.x,'shared_buffer':True,'geometry_reused':True})

    def _verify_time_query_width(self, scene):
        owner = scene.create_game_object('Player time query probe')
        manager = tween.TweenManager()
        try:
            handle = manager.to(lambda: 0., lambda value: setattr(owner.transform, 'position', Vector3(value, 0, 0)),
                                1., 1.1).set_delay(.1).set_ease(tween.Ease.LINEAR)
            manager.update(.35)
            if handle.position != .25 or handle.elapsed() != .25 or handle.full_position != .25:
                raise RuntimeError('Delayed public time queries did not retain Single precision')
            fraction = float(np.float32(.25 / np.float32(1.1)))
            if handle.elapsed_percentage(False) != fraction or handle.elapsed_directional_percentage() != fraction:
                raise RuntimeError('Public time percentage kept a double-width result')
            if owner.transform.position.x != fraction:
                raise RuntimeError('Delayed time sampling did not reach the native target')
            self._observations.append({'stage': 'time_query_width', 'elapsed_fields': True,
                'single_percentage': True, 'native_target': True})
        finally:
            manager.clear()
            inx.GameObject.destroy(owner)

    def _verify_ease_factor_width(self, scene):
        owner = scene.create_game_object('Player ease factor probe')
        manager, values = tween.TweenManager(), []
        def write(value):
            values.append(value)
            owner.transform.position = Vector3(value, 0, 0)
        try:
            for kind in (float, np.float64, np.float32):
                handle = manager.to(lambda: kind(0), write, kind(3), 3.).set_ease(tween.Ease.LINEAR)
                handle.goto(1.)
                if type(values[-1]) is not kind or values[-1] != kind(3 * float(np.float32(1 / 3))):
                    raise RuntimeError('Native easing widened its factor or changed target storage')
            progress = np.linspace(.001, .999, 1024, dtype=np.float64)
            output = np.empty_like(progress)
            tween.EaseManager.compile(tween.Ease.LINEAR).sample_into(progress, output)
            if not np.array_equal(output, progress.astype(np.float32).astype(np.float64)):
                raise RuntimeError('Bulk easing and scalar factor widths differ')
            if owner.transform.position.x != 1.:
                raise RuntimeError('Single factor did not reach the native scene target')
            child = manager.to(lambda: np.float32(2), write, np.float32(10), 1.)
            child.set_ease(tween.Ease.LINEAR).set_loops(3)
            root = manager.sequence().append(child).set_loops(2, tween.LoopType.YOYO).set_auto_kill(False)
            root.goto(root.duration())
            root.play_backwards()
            manager.update(.25)
            if child.elapsed(False) != .25 or values[-1] != np.float32(4.):
                raise RuntimeError('Linear sequence timing lost its exact child phase')
            self._observations.append({'stage': 'ease_factor_width', 'single_factor': True,
                'target_types': True, 'bulk_storage': True, 'linear_child_clock': True, 'native_target': True})
        finally:
            manager.clear()
            inx.GameObject.destroy(owner)

    def _verify_bounded_playback_clock(self, scene):
        owner = scene.create_game_object('长期循环播放测试')
        manager = tween.TweenManager()
        try:
            handle = manager.to(lambda: 0., lambda value: setattr(owner.transform, 'position', Vector3(value, 0, 0)),
                                1., 1.).set_ease(tween.Ease.LINEAR).set_loops(-1).set_auto_kill(False)
            handle.goto(262144., True)
            manager.update(1 / 64)
            assert handle.completed_loops() == 262144 and handle.position == 1 / 64
            assert owner.transform.position.x == 1 / 64
            handle.play_backwards()
            manager.update(1 / 64)
            assert handle.completed_loops() == 262144 and handle.position == 1.
            self._observations.append({'stage': 'bounded_playback_clock', 'large_loop_count': True,
                                       'forward_and_backward': True, 'native_target': True})
        finally:
            manager.clear()
            inx.GameObject.destroy(owner)

    def _verify_prepared_clock(self, scene):
        owner = scene.create_game_object('Player prepared timing probe')
        manager = tween.TweenManager()
        try:
            handle = manager.to(lambda: 0., lambda value: setattr(owner.transform, 'position', Vector3(value, 0, 0)),
                                4., 2.).set_ease(tween.Ease.LINEAR)
            handle.force_init()
            clock = handle._sample_clock
            manager.update(.5)
            if handle._sample_clock is not clock or owner.transform.position.x != 1.:
                raise RuntimeError('Prepared native timing was rebuilt or sampled incorrectly')
            control = manager.to(lambda: 0., lambda value: None, 1., 1.).set_loops(3)
            retained = control._sample_clock
            control.loop_type = tween.LoopType.YOYO
            control.set_inverted()
            if control._progress_at(1.25) != (1, .25) or control._sample_clock is not retained:
                raise RuntimeError('Prepared timing ignored live orientation flags')
            control.set_delay(.5).set_loops(4)
            if retained(3., True, False) != (2, 1.) or control._sample_clock is retained:
                raise RuntimeError('Reconfiguration changed a retained timing snapshot')
            instance = tween.instance
            try:
                tween.instance = None
            except AttributeError:
                pass
            else:
                raise RuntimeError('The public instance view accepted an assignment')
            if tween.instance is not instance:
                raise RuntimeError('The public instance view was shadowed')
            self._observations.append({'stage': 'prepared_clock', 'reused_recipe': True,
                'live_orientation': True, 'immutable_capture': True, 'instance_read_only': True, 'native_target': True})
        finally:
            manager.clear()
            inx.GameObject.destroy(owner)

    def _verify_public_math_utilities(self, scene):
        owner = scene.create_game_object('Player public math probe')
        manager = tween.TweenManager()
        try:
            point = tween.TweenUtils.get_point_on_circle(center=inx.Vector2(2, 3), radius=2., degrees=90.)
            owner.transform.position = Vector3(point.x, point.y, 0)
            if tuple(owner.transform.position) != (4., 3., 0.):
                raise RuntimeError('Public circle utility did not reach the native scene target')
            if tween.Bounce.ease_out(.5, 1., 0., 0.) != .765625:
                raise RuntimeError('Public bounce helper changed its half-time sample')
            if tween.Flash.ease_in(.125, 1., 4., 0.) != .25:
                raise RuntimeError('Public flash helper changed its pulse shape')
            values = []
            handle = manager.to(lambda: np.float32(0), values.append, np.float32(8), 1.)
            handle.set_ease(tween.Bounce.ease_out).goto(.5)
            if type(values[-1]) is not np.float32 or values[-1] != np.float32(6.125):
                raise RuntimeError('Public helper lost its typed callback integration')
            if tween.EaseManager.evaluate(tween.Ease.LINEAR, None, 1., 3., 0., 0.) != float(np.float32(1 / 3)):
                raise RuntimeError('Public ease result did not retain Single precision')
            self._observations.append({'stage': 'public_math_utilities', 'bounce': True,
                'flash': True, 'circle_point': True, 'typed_callback': True,
                'single_factor': True, 'native_target': True})
        finally:
            manager.clear()
            inx.GameObject.destroy(owner)

    def _verify_single_clock_fields(self, scene):
        owner = scene.create_game_object('Player prepared clock probe')
        manager, arguments, values = tween.TweenManager(), [], []
        single = lambda value: float(np.float32(value))
        def write(value):
            values.append(value)
            owner.transform.position = Vector3(value, 0, 0)
        def custom(*args):
            arguments.append(args)
            return .1
        try:
            manager.time_scale = 1.1
            manager.default_ease_period = .4
            handle = manager.to(lambda: 0., write, 1., 1.1).set_ease(custom).set_auto_kill(False)
            handle.set_delay(.1).goto(.25)
            if manager.time_scale != single(1.1) or handle.duration(False) != single(1.1) or handle.delay() != single(.1):
                raise RuntimeError('Clock fields did not retain Single storage')
            if arguments[-1] != (single(.25), single(1.1), single(1.70158), single(.4)):
                raise RuntimeError('Custom easing lost its prepared Single arguments')
            if values[-1] != single(.1) or owner.transform.position.x != single(.1):
                raise RuntimeError('Custom easing factor changed before reaching its native target')
            typed = manager.to(lambda: np.float32(0), values.append, np.float32(1), 1.)
            typed.set_ease(custom).set_auto_kill(False).goto(.5)
            if type(values[-1]) is not np.float32 or values[-1] != np.float32(.1):
                raise RuntimeError('Prepared custom sampling lost its declared scalar type')
            extent = manager.to(lambda: 0., lambda value: None, 1., 1.0000001192092896)
            extent.set_loops(16777217)
            if extent.duration() != 16777218.:
                raise RuntimeError('Loop count conversion moved after multiplication')
            final_values = []
            terminal = manager.to(lambda: 0., final_values.append, 1., .1)
            terminal.set_ease(tween.Ease.LINEAR).set_loops(3).set_auto_kill(False).complete()
            if final_values[-1] != 1. or terminal.position != float(np.float32(.1)):
                raise RuntimeError('Rounded repeat extent sampled the next cycle at completion')
            self._observations.append({'stage': 'single_clock_fields', 'prepared_fields': True,
                'callback_arguments': True, 'single_result': True, 'typed_scalar': True,
                'loop_extent': True, 'terminal_phase': True, 'native_target': True})
        finally:
            manager.clear()
            inx.GameObject.destroy(owner)

    def _verify_public_clock_properties(self, scene):
        owner = scene.create_game_object('Player public clock probe')
        manager, observed = tween.TweenManager(), []
        try:
            def write(value):
                owner.transform.position = Vector3(value, 0, 0)
            handle = manager.to(lambda: 0., write, 8., 1.).set_ease(tween.Ease.LINEAR)
            handle.set_delay(.5).set_loops(3).set_auto_kill(False).pause()
            handle.full_position = 1.25
            if (handle.position != .25 or handle.full_position != 1.25
                    or handle.is_playing() or owner.transform.position.x != 2.):
                raise RuntimeError('Public position mixed cycle, delay or playing state')
            for name, value in (('position', .5), ('active', False)):
                try:
                    setattr(handle, name, value)
                except AttributeError:
                    pass
                else:
                    raise RuntimeError('Playback state accepted a direct external write')
            child = manager.to(lambda: 0., write, 8., 1.).set_ease(tween.Ease.LINEAR)
            root = manager.sequence().append(child).set_loops(3).set_auto_kill(False)
            root.on_update(lambda: observed.append((root.position, root.full_position, child.position)))
            root.full_position = 1.25
            child.full_position = .75
            if observed[-1] != (.25, 1.25, .25) or child.full_position != .25:
                raise RuntimeError('Public clock assignment bypassed sequence ownership')
            self._observations.append({'stage': 'public_clock_properties', 'cycle_position': True,
                'full_position_assignment': True, 'playing_preserved': True, 'read_only_state': True,
                'sequence_ownership': True, 'callback_clock': True, 'native_target': True})
        finally:
            manager.clear()
            inx.GameObject.destroy(owner)

    def _verify_rect_offset_values(self, scene):
        from infernux import RectOffset
        owner = scene.create_game_object('Player integer edge probe')
        manager, values = tween.TweenManager(), []
        def write(value):
            values.append(value)
            owner.transform.position = Vector3(value.left, value.top, 0)
        try:
            for explicit in (False, True):
                plugin = tween.RectOffsetPlugin()
                arguments = (lambda: RectOffset(1, 2, 3, 4), write, RectOffset(5, 6, 7, 8), 1.)
                handle = manager.to(plugin, *arguments) if explicit else manager.to(*arguments)
                handle.set_ease(tween.Ease.LINEAR).set_auto_kill(False).force_init()
                if not isinstance(handle, tween.TweenerCore) or not isinstance(handle.get_plugin(), tween.RectOffsetPlugin):
                    raise RuntimeError('Offset handle lost typed storage or its plugin')
                if explicit and handle.get_plugin() is not plugin:
                    raise RuntimeError('Offset handle replaced the explicitly supplied plugin')
                handle.start_value.left, handle.change_value.right = 9, 12
                handle.goto(.5)
                if tuple(owner.transform.position) != (11, 5, 0) or values[-1].right != 8:
                    raise RuntimeError('Offset channel edits did not reach the native scene target')
            captured = manager.to(lambda: RectOffset(16777217, 0, 0, 0), values.append,
                                  RectOffset(16777219, 0, 0, 0), 1.)
            captured.set_ease(tween.Ease.LINEAR).set_auto_kill(False).goto(.5)
            if values[-1].left != 16777217:
                raise RuntimeError('Offset sampling lost its integer-to-float boundary')
            observed = []
            def custom(t, d, a, p):
                controlled.start_value.left, controlled.change_value.left = 99, 8
                return t / d
            controlled = manager.to(lambda: RectOffset(1, 0, 0, 0), observed.append,
                                     RectOffset(5, 0, 0, 0), 1.)
            controlled.set_ease(custom).set_auto_kill(False).goto(.5)
            if observed[-1].left != 5:
                raise RuntimeError('Offset custom callback changed the prepared start')
            self._observations.append({'stage': 'rect_offset_values', 'typed_storage': True,
                'explicit_plugin': True, 'int32_math': True, 'native_target': True, 'callback_start_capture': True})
        finally:
            manager.clear()
            inx.GameObject.destroy(owner)

    def _verify_color_pair_values(self, scene):
        from infernux.components.builtin import LineRenderer
        owner = scene.create_game_object('Player paired color probe')
        manager = tween.TweenManager()
        try:
            line = owner.add_component(LineRenderer)
            start = tween.Color2([1, 0, 0, 1], [0, 1, 0, .5])
            end = tween.Color2([0, 0, 1, .5], [1, 0, 0, 1])
            handle = tween.twn_color(line, start, end, 1.).set_ease(tween.Ease.LINEAR).set_auto_kill(False)
            manager.add(handle)
            start.ca[0], end.cb[0] = 9, 9
            handle.goto(.5)
            if line.start_color != [.5, 0, .5, .75] or line.end_color != [.5, .5, 0, .75]:
                raise RuntimeError('Paired line colors did not capture their value arguments')
            value = tween.Color2()
            value.ca = [.25, .5, .75, 1]
            previous = value.ca
            value.ca = [0, 0, 0, 0]
            previous[0] = 9
            if value.ca != [0, 0, 0, 0] or value.cb != [0, 0, 0, 0]:
                raise RuntimeError('Paired color fields alias a replaced view')
            times = np.array([0., .5, 1.], dtype=np.float64)
            result = np.empty((3, 8), dtype=np.float32)
            handle._numeric_job.sample_into(times, result)
            if list(result[1]) != [.5, 0, .5, .75, .5, .5, 0, .75]:
                raise RuntimeError('Paired color native batch changed its channel order')
            self._observations.append({'stage': 'color_pair_values', 'creation_capture': True,
                'writable_fields': True, 'detached_view': True, 'native_channels': 8, 'native_line': True})
        finally:
            manager.clear()
            inx.GameObject.destroy(owner)

    def _verify_curve_utilities(self, scene):
        owner = scene.create_game_object('Player cubic utility probe')
        try:
            points = (Vector3(), Vector3(0, 2, 0), Vector3(2, 0, 0), Vector3(2, 2, 0))
            point = tween.TweenCurve.CubicBezier.get_point_on_segment(*points, .5)
            owner.transform.position = point
            if tuple(owner.transform.position) != (1, 1.5, 0):
                raise RuntimeError('Cubic utility did not reach the native scene target')
            cloud = tween.CubicBezier.get_segment_point_cloud(*points, resolution=3)
            existing = [Vector3(9, 8, 7)]
            result = tween.CubicBezier.get_segment_point_cloud(existing, *points, resolution=3)
            if (result is not None or len(existing) != 4 or tuple(existing[0]) != (9, 8, 7)
                    or [tuple(value) for value in existing[1:]] != [tuple(value) for value in cloud]):
                raise RuntimeError('Cubic utility changed append or resolution semantics')
            curve = inx.AnimationCurve.linear(0, 0, 1, 1)
            sample = tween.EaseFactory.stop_motion(motion_fps=4, anim_curve=curve)
            if sample(.49, 1., 1., 0.) != .25:
                raise RuntimeError('Stop-motion factory did not use the engine curve')
            curve.set_keys([inx.Keyframe(0, 0, 2, 2), inx.Keyframe(1, 2, 2, 2)])
            if sample(.49, 1., 1., 0.) != .5:
                raise RuntimeError('Stop-motion factory lost live curve edits')
            clock = tween.EaseFactory.stop_motion(4, custom_ease=lambda t, d, a, p: t)
            owner.transform.position = Vector3(clock(-.49, 1., 1., 0.), clock(1.5, 1., 1., 0.), 0)
            if tuple(owner.transform.position) != (-.25, 1.5, 0):
                raise RuntimeError('Discrete clock changed signed or extended time')
            controls = tween.ControlPoint(Vector3(1, 2, 3), Vector3(4, 5, 6)) + Vector3(1, 0, -1)
            owner.transform.position = controls.a
            if tuple(owner.transform.position) != (2, 2, 2) or str(controls) != '[(2.00, 2.00, 2.00) | (5.00, 5.00, 5.00)]':
                raise RuntimeError('Control pair translation or text changed its value contract')
            self._observations.append({'stage': 'curve_utilities', 'native_point': True,
                'cloud_points': len(cloud), 'append': True, 'ease_factory': True, 'live_asset': True,
                'signed_discrete_time': True, 'unclamped_discrete_time': True,
                'control_translation': True, 'control_text': True})
        finally:
            inx.GameObject.destroy(owner)

    def _verify_plugin_keyword_calls(self, scene):
        owner = scene.create_game_object('Player direct plugin keywords')
        manager = tween.TweenManager()
        try:
            owner.transform.position = Vector3(2, 0, 0)
            def write(value):
                owner.transform.position = Vector3(value, 0, 0)
            handle = manager.to(lambda: owner.transform.position.x, write, 10., 1.)
            handle.set_target(owner.transform).set_ease(tween.Ease.LINEAR).set_auto_kill(False).force_init()
            plugin = handle.get_plugin()
            plugin.set_from(t=handle, from_value=6., set_immediately=True, is_relative=False)
            plugin.set_change_value(t=handle)
            plugin.evaluate_and_apply(options=handle.plug_options, t=handle, is_relative=False,
                getter=handle.getter, setter=write, elapsed=.25, start_value=handle.start_value,
                change_value=handle.change_value, duration=1., using_inverse_position=False,
                new_completed_steps=0, update_notice=tween.UpdateNotice.NONE)
            if owner.transform.position.x != 7. or handle.elapsed() != 0.:
                raise RuntimeError('Direct plugin keyword dispatch changed values or its owner clock')
            explicit = tween.FloatPlugin()
            declared = manager.to(explicit, lambda: np.float32(2), write, np.float32(10), 1.)
            declared.set_ease(tween.Ease.LINEAR).set_auto_kill(False).goto(.5)
            if declared.get_plugin() is not explicit or owner.transform.position.x != 6.:
                raise RuntimeError('Explicit built-in plugin lost its identity or native scene result')
            path = tween.Path(type=tween.PathType.LINEAR, waypoints=[Vector3(0, 0, 1)])
            options = tween.PathOptions()
            options.mode = tween.PathMode.FULL3_D
            options.orient_type = tween.OrientType.LOOK_AT_POSITION
            options.look_at_position = Vector3(10, 0, 0)
            tween.PathPlugin.get().set_orientation(options=options, t=handle, path=path,
                path_perc=.5, t_pos=owner.transform.position, update_notice=tween.UpdateNotice.NONE)
            if quatf.angle(owner.transform.rotation, quatf.look_rotation(Vector3(1, 0, 0))) > .001:
                raise RuntimeError('Named path orientation did not reach the native scene target')
            self._observations.append({'stage': 'plugin_keyword_calls', 'named_owner': True,
                'start_overload': True, 'path_type_keyword': True, 'path_orientation_keyword': True,
                'explicit_builtin_instance': True})
        finally:
            manager.clear()
            inx.GameObject.destroy(owner)

    def _verify_clock_preparation(self, scene):
        owner = scene.create_game_object('Player prepared clock probe')
        manager, observed = tween.TweenManager(), []
        edited = False
        def write(value):
            nonlocal edited
            owner.transform.position = Vector3(value, 0, 0)
            if not edited:
                edited = True
                observed.append(handle.full_duration)
                handle.change_end_value(2., new_duration=2.)
                observed.append(handle.full_duration)
        try:
            handle = manager.to(lambda: owner.transform.position.x, write, 1., 1.)
            handle.set_ease(tween.Ease.LINEAR).set_loops(2).set_delay(.25).set_auto_kill(False)
            manager.update(.75)
            if observed != [2.25, 4.25] or handle.full_duration != 4.25:
                raise RuntimeError('Player reentrant duration edit did not publish its new clock')
            manager.update(4.)
            if not handle.is_complete() or owner.transform.position.x != 2.:
                raise RuntimeError('Player edited clock did not finish at its endpoint')
            handle.restart(change_delay_to=.5)
            if handle.full_duration != 4.5:
                raise RuntimeError('Player restart delay retained its previous total time')
            child = manager.to(lambda: 0., lambda value: None, 1., .5).set_loops(2).set_delay(.25)
            root = manager.sequence().set_loops(2).set_delay(.5, False).append(child).prepend_interval(.25)
            if root.full_duration != 3.5 or child.full_duration != 1.:
                raise RuntimeError('Player sequence construction did not publish its clock extent')
            self._observations.append({'stage': 'clock_preparation', 'reentrant_duration': True,
                                       'restart_delay': True, 'sequence_extent': True})
        finally:
            manager.clear()
            inx.GameObject.destroy(owner)

    def _verify_circle_from_keyword(self, scene):
        owner = scene.create_game_object('Player named circle start')
        manager = tween.TweenManager()
        try:
            owner.transform.position = Vector3(1, 0, 0)
            def read():
                position = owner.transform.position
                return Vector2(position.x, position.y)
            def write(value):
                owner.transform.position = Vector3(value.x, value.y, 0)
            handle = manager.to(tween.CirclePlugin.get(), read, write, Vector2(0, 0), 1.)
            handle.set_options(90., False).set_ease(tween.Ease.LINEAR)
            handle.from_(from_value_degrees=180., set_immediately=False)
            if tuple(read()) != (1., 0.):
                raise RuntimeError('Player deferred circle start changed the target immediately')
            manager.update(.5)
            position, diagonal = read(), float(np.sqrt(.5))
            if abs(position.x - diagonal) > 1e-6 or abs(position.y + diagonal) > 1e-6:
                raise RuntimeError('Player named circle start did not use its angular interpolation')
            manager.update(.5)
            if abs(read().x - 1.) > 1e-6 or abs(read().y) > 1e-6:
                raise RuntimeError('Player named circle start did not reach its endpoint')
            self._observations.append({'stage': 'circle_from_keyword', 'scalar_degrees': True,
                                       'deferred_application': True, 'ordinary_frame_updates': True})
        finally:
            manager.clear()
            inx.GameObject.destroy(owner)

    def _verify_material_property_ids(self):
        from infernux.core.material import Material
        from infernux.core.shader import Shader
        from infernux.lib import InxMaterial
        material = Material.create_lit()
        texture_material = Material(InxMaterial('Player texture IDs', 'Unlit'))
        manager = tween.TweenManager()
        default_roots = tween.total_active_tweens()
        try:
            scalar = Shader.property_to_id('metallic')
            vector = Shader.property_to_id('metallicChannels')
            color = Shader.property_to_id('baseColor')
            texture = Shader.property_to_id('texSampler')
            material.set_color(color, 1., 1., 1., 1.)
            texture_material.set_texture_guid(texture, '')
            handles = (
                tween.twn_float(material, 1., property_id=scalar, duration=1.),
                tween.twn_vector(material, vec4f(0, 1, 0, 0), vector, 1.),
                tween.twn_color(material, [0., 0., 0., 1.], property_id=color, duration=1.),
                tween.twn_offset(texture_material, Vector2(1, 2), property_id=texture, duration=1.),
                tween.twn_tiling(texture_material, Vector2(3, 5), texture, 1.),
            )
            for handle in handles:
                manager.add(handle).set_ease(tween.Ease.LINEAR)
            manager.update(.5)
            if material.get_float(scalar) != .5 or material.get_vector4(vector) != (.5, .5, 0., 0.):
                raise RuntimeError('Player material ID values did not reach their native properties')
            if material.get_color(color) != (.5, .5, .5, 1.):
                raise RuntimeError('Player color ID selected a different property')
            if texture_material.get_vector4('texSampler_ST') != (2., 3., .5, 1.):
                raise RuntimeError('Player texture ID lost its independent UV channels')
            if tween.total_active_tweens() != default_roots:
                raise RuntimeError('Player material ID probe retained default-manager roots')
            self._observations.append({'stage': 'material_property_ids', 'native_properties': 4,
                                       'shortcut_kinds': 5, 'shared_uv_channels': True})
        finally:
            manager.clear()
            material.dispose()
            texture_material.dispose()

    def _verify_path_clock_refresh(self, scene):
        owner = scene.create_game_object('Player edited path clock')
        manager, steps = tween.TweenManager(), []
        default_roots = tween.total_active_tweens()
        try:
            handle = manager.add(tween.twn_path(owner.transform, [Vector3(10, 0, 0)], 1e-40,
                                               tween.PathType.LINEAR))
            handle.set_as(tween_params=tween.TweenParams().set_ease(tween.Ease.LINEAR).set_loops(3))
            handle.set_auto_kill(False)
            handle.on_step_complete(lambda: steps.append(True)).force_init()
            handle.change_end_value(tween.Path(tween.PathType.LINEAR, [Vector3(10, 0, 0)], 10), new_duration=1.)
            manager.update(.25)
            manager.update(1.)
            if (handle.elapsed() != 1.25 or handle.completed_loops() != 1 or len(steps) != 1
                    or abs(owner.transform.position.x - 2.5) > 1e-6):
                raise RuntimeError('Player edited path retained its old clock classification')
            manager.update(.25)
            if handle.elapsed() != 1.5 or abs(owner.transform.position.x - 5) > 1e-6:
                raise RuntimeError('Player edited path did not continue with its new clock')
            if tween.total_active_tweens() != default_roots:
                raise RuntimeError('Player transferred path remained registered with its previous manager')
            self._observations.append({'stage': 'path_clock_refresh', 'elapsed': handle.elapsed(),
                'completed_loops': handle.completed_loops(), 'steps': len(steps), 'direct_frame_updates': True})
        finally:
            manager.clear()
            inx.GameObject.destroy(owner)

    def _verify_text_frame_commit(self, scene):
        root = scene.create_game_object('Player text commit probe')
        root.active = False
        root.add_component(inx.UICanvas)
        manager, animators = tween.TweenManager(), []
        default_roots = tween.total_active_tweens()
        class ProbeAnimator(tween.TextTweenAnimator):
            __hash__ = None
            def __eq__(self, other):
                return self is other
            def apply(self):
                self.commits += 1
                return super().apply()
        try:
            for index in range(2):
                owner = scene.create_game_object(f'Player text owner {index}')
                owner.set_parent(root, False)
                label = owner.add_component(inx.UIText)
                label.text, label.font_size = 'ABCD', 24
                label.width, label.height = 300, 80
                animator = ProbeAnimator(label)
                animator.commits = 0
                animators.append(animator)
            first, second = animators
            manager.add(first.twn_offset_char(0, Vector3(10, 20, 30), 1).set_ease(tween.Ease.LINEAR))
            manager.add(first.twn_fade_char(1, 0, 1).set_ease(tween.Ease.LINEAR))
            manager.add(second.range(0, 4).twn_rotate(Vector3(0, 0, 90), 1).set_ease(tween.Ease.LINEAR))
            manager.add(second.character(0).twn_color((0, 0, 0, 1), 1)
                        .from_(from_alpha_value=.25, set_immediately=False).set_ease(tween.Ease.LINEAR))
            manager.update(.5)
            if tween.total_active_tweens() != default_roots:
                raise RuntimeError('Player transferred character tweens remained registered with their previous manager')
            if first.commits != 1 or second.commits != 1:
                raise RuntimeError('Player text writes did not coalesce independently by owner')
            if (not np.array_equal(first.buffer.affine_transforms[0, :, 3], [5, -10, 15])
                    or not np.all(first.buffer.colors[1, :, 3] == .5)):
                raise RuntimeError('Player text position or alpha commit is incorrect')
            diagonal = np.float32(np.sqrt(.5))
            expected = np.array([[diagonal, diagonal, 0], [-diagonal, diagonal, 0], [0, 0, 1]], dtype=np.float32)
            if not np.allclose(second.buffer.affine_transforms[:, :, :3], expected, rtol=0, atol=2e-6):
                raise RuntimeError('Player batched text rotation matrix is incorrect')
            if float(second.buffer.colors[0, 0, 3]) != .625 or float(second.buffer.color_overrides[0]) != 2.:
                raise RuntimeError('Player character color group did not share the named alpha start')
            self._observations.append({'stage': 'text_frame_commit', 'owners': 2,
                'uploads_per_owner': 1, 'rotated_characters': 4, 'native_geometry': True, 'named_alpha_from': True})
        finally:
            manager.clear()
            for animator in animators:
                animator.dispose()
            inx.GameObject.destroy(root)

    def _verify_unbound_ui_parent(self, scene):
        root = scene.create_game_object('Player UI parent preparation')
        root.active = False
        handle = None
        try:
            first = scene.create_game_object('Original parent Canvas')
            first.set_parent(root, False)
            first_canvas = first.add_component(inx.UICanvas)
            first_canvas.reference_width, first_canvas.reference_height = 640, 360
            second = scene.create_game_object('New parent Canvas')
            second.set_parent(root, False)
            second_canvas = second.add_component(inx.UICanvas)
            second_canvas.reference_width, second_canvas.reference_height = 960, 540
            obj = scene.create_game_object('Animated parent preparation probe')
            obj.set_parent(first, False)
            image = obj.add_component(inx.UIImage)
            image.anchor_min, image.anchor_max = Vector2(0, 0), Vector2(1, 1)
            image.size_delta, image.anchored_position = Vector2(-20, -30), Vector2(0, 0)
            handle = tween.twn_size_delta(image, Vector2(-60, -70), 1).set_ease(tween.Ease.LINEAR).pause()
            handle.goto(.25)
            parent = second
            for index in range(3):
                bridge = scene.create_game_object(f'Player unbound parent {index}')
                bridge.set_parent(parent, False)
                parent = bridge
            if parent.transform._has_rect_layout:
                raise RuntimeError('Player parent probe was already initialized')
            obj.set_parent(parent, False)
            if (image.width, image.height) != (930, 500):
                raise RuntimeError(f'Player unbound bridge size mismatch: {(image.width, image.height)}')
            frame_object = scene.create_game_object('Player unbound UI frame')
            frame_object.set_parent(second, False)
            frame = frame_object.add_component(inx.UIFrame)
            frame.width, frame.height = 300, 200
            obj.transform.set_parent(frame_object.transform, False)
            if (image.width, image.height) != (270, 160):
                raise RuntimeError('Player unbound UI frame size mismatch')
            handle.goto(.75)
            if (image.width, image.height) != (250, 140):
                raise RuntimeError('Player animation did not continue in its new parent frame')
            world_position = tuple(obj.transform.position)
            obj.transform.parent = first.transform
            if ((image.width, image.height) != (250, 140)
                    or max(abs(a - b) for a, b in zip(obj.transform.position, world_position)) > 1e-5):
                raise RuntimeError('Player reparent failed to preserve world pose and rectangle size')
            self._observations.append({'stage': 'ui_unbound_parent', 'bridge_depth': 3,
                'bridge_size': [930, 500], 'frame_size': [270, 160], 'continued_size': [250, 140],
                'world_pose_preserved': True, 'assert_independent_checks': True})
        finally:
            if handle is not None:
                handle.kill()
            inx.GameObject.destroy(root)

    def _verify_frame_dispatch(self):
        manager, events = tween.TweenManager(), []
        first = manager.to(lambda:0.,lambda value:events.append('first'),10.,1.)
        manager.to(lambda:0.,lambda value:events.append('second'),10.,1.)
        manager.update(.25)
        first.pause().play()
        events.clear()
        manager.update(.25)
        assert events == ['first','second']
        manager.clear()
        value, writes, steps = [2.], [], []
        def write(sample):
            value[0] = sample
            writes.append(sample)
        child = manager.to(lambda:value[0],write,10.,1.).set_ease(tween.Ease.LINEAR)
        child.set_loops(3).on_step_complete(lambda:steps.append('step'))
        manager.sequence().append(child).set_loops(2,tween.LoopType.INCREMENTAL)
        manager.update(2.25)
        writes.clear()
        steps.clear()
        manager.update(.75)
        assert writes == [18.,18.] and steps == ['step'] and not child.is_backwards()
        manager.update(.25)
        assert value[0] == 12. and len(steps) == 3 and child.is_backwards()
        manager.clear()
        reverse_steps = []
        def flip_after_sampling():
            handle.step_complete_callback = lambda:reverse_steps.append('step')
            handle.flip()
        handle = manager.to(lambda:2.,lambda value:None,10.,1.).set_ease(tween.Ease.LINEAR)
        handle.set_loops(3).on_update(flip_after_sampling)
        manager.update(1.25)
        assert handle.is_backwards() and reverse_steps == ['step']
        manager.clear()
        self._observations.append({'stage':'frame_dispatch','resume_order':events,
                                   'boundary_writes':writes[:2],'next_loop_value':value[0],
                                   'flipped_update_steps':len(reverse_steps)})

    def _prepare_shared_path_probe(self, scene):
        self._shared_owner = scene.create_game_object('Player shared path owner').transform
        self._shared_other = scene.create_game_object('Player shared path companion').transform
        path = tween.Path(tween.PathType.CUBIC_BEZIER,
                          [Vector3(2,0,0),Vector3(2/3,0,0),Vector3(4/3,0,0)],10)
        plugin = tween.PathPlugin.get()
        self._shared_handle = tween.to(plugin, lambda: self._shared_owner.position,
            lambda value: setattr(self._shared_owner,'position',value),path,.3).set_target(self._shared_owner)
        self._shared_companion = tween.to(plugin, lambda: self._shared_other.position,
            lambda value: setattr(self._shared_other,'position',value),path,.3).set_target(self._shared_other)
        for handle in (self._shared_handle,self._shared_companion):
            handle.set_ease(tween.Ease.LINEAR).set_loops(2,tween.LoopType.INCREMENTAL).pause().force_init()
        self._shared_handle.on_complete(self._shared_path_completed)

    def _resume_shared_path_probe(self):
        self._shared_handle.goto(.375)
        path = self._shared_handle.change_value
        self._shared_plan = path._incremental_geometry._tables
        path.wps[-1].x = 4
        self._shared_companion.goto(.525)
        self._near(self._shared_other.position,(3.5,0,0))
        self._shared_companion.kill()
        assert path.wps is None
        self._shared_handle.play()
        self._observations.append({'stage':'shared_path','companion_position':tuple(self._shared_other.position),
                                   'authored_geometry_released':True})

    def _shared_path_completed(self):
        assert self._shared_handle.change_value._incremental_geometry._tables is self._shared_plan
        self._shared_path_plan_reused = True

    def _check_value_arguments(self):
        manager = tween.TweenManager()
        for kind, channels in ((list,4),(Vector2,2),(Vector3,3),(vec4f,4),(Rect,4)):
            def make(values):
                return list(values) if kind is list else kind(*values[:channels])
            def edit(value, first):
                if kind is Rect:
                    return Rect(first, value.y, value.width, value.height)
                if kind is list:
                    value[0] = first
                else:
                    value.x = first
                return value
            for operation in ('from_now','from_relative','change_end_snap','change_both_new'):
                first, last = make([4,5,6,7]), make([20,23,26,29])
                current = [make([2,3,4,5])]
                state = {'armed':False, 'reads':0}
                def getter():
                    nonlocal first, last
                    state['reads'] += 1
                    if state['armed']:
                        state['armed'] = False
                        first, last = edit(first,50), edit(last,100)
                    return current[0]
                getter.__annotations__['return'] = kind
                handle = manager.to(getter,lambda v:current.__setitem__(0,v),make([10,13,16,19]),1)
                handle.set_ease(tween.Ease.LINEAR).set_auto_kill(False).pause()
                if operation == 'change_end_snap':
                    handle.force_init()
                state['armed'] = True
                if operation.startswith('from_'):
                    handle.from_(first,True,operation == 'from_relative')
                elif operation == 'change_end_snap':
                    handle.change_end_value(last,True)
                else:
                    handle.change_values(first,last)
                first, last = edit(first,200), edit(last,400)
                handle.goto(.5)
                expected, reads = {
                    'from_now':([7,9,11,13],0),
                    'from_relative':([9,12,15,18],1),
                    'change_end_snap':([11,13,15,17],2),
                    'change_both_new':([12,14,16,18],0),
                }[operation]
                assert tuple(current[0]) == tuple(expected[:channels]), (kind,operation,current[0])
                assert state['reads'] == reads, (kind,operation,state)
                handle.kill()
            seen = []
            def receive(value):
                seen.append(tuple(value))
                edit(value,999)
            handle = manager.to(lambda:make([2,3,4,5]),receive,make([10,13,16,19]),1)
            handle.set_ease(tween.Ease.LINEAR).set_auto_kill(False).from_()
            assert tuple(handle.start_value) == (10,13,16,19)[:channels]
            handle.goto(.5)
            assert seen == [(10,13,16,19)[:channels],(6,8,10,12)[:channels]]
            handle.kill()
        manager.clear()
        self._observations.append({'stage':'value_arguments','kinds':5,'operations':5,'cases':25})

    def _array_completed(self):
        assert self._array_handle._numeric_segments is self._array_plan
        self._array_plan_reused = True

    def _rotation_completed(self):
        assert self._rotation_handle._numeric_job is self._rotation_plan
        self._rotation_plan_reused = True

    def _look_completed(self):
        assert self._look_handle._numeric_job is self._look_plan
        self._look_plan_reused = True

    def _vector_completed(self):
        assert self._vector_handle._numeric_job is self._vector_plan
        self._vector_plan_reused = True

    def _path_completed(self):
        assert self._live_path_handle.change_value._tables is self._path_plan
        self._path_plan_reused = True

    def _bezier_completed(self):
        assert self._bezier_handle.change_value._tables is self._bezier_plan
        self._bezier_plan_reused = True

    def _finish(self, passed, error=''):
        self._finished = True
        proof = dict(passed=passed, player=inx.Application.is_player(), error=error,
                     observations=self._observations, completions=self._completions,
                     library_origin=tween.__file__, native_origin=inx.lib._Infernux.__spec__.origin)
        destination = Path(inx.Application.persistent_data_path()) / 'tween-player-proof.json'
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(proof, indent=2) + '\n', encoding='utf8')
        inx.Debug.log('TWEEN_PLAYER_ACCEPTANCE_' + ('PASS' if passed else 'FAIL') + ('\n' + error if error else ''))
        self._request_exit(0 if passed else 1)

    def _request_exit(self, code):
        inx.Application.quit(code)

    @staticmethod
    def _near(actual, expected):
        assert max(abs(a - b) for a, b in zip(actual, expected)) < 1e-5, (tuple(actual), expected)
