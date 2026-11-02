"""Specialized storage stays typed and updates prepared plans on edits."""
from copy import copy
from array import array

import pytest
import numpy as np

from infernux.screen import Rect
from infernux.lib._Infernux import _EaseKernel, _RectTweenSnapshot
import infernux_tween as api


def test_rect_fields_options_and_original_callbacks_remain_live():
    m, values = api.TweenManager(), [Rect(2, 3, 4, 5)]
    get = lambda: values[0]
    put = lambda value: values.__setitem__(0, value)
    h = m.to(get, put, Rect(10, 13, 16, 21), 1).set_ease(api.Ease.LINEAR).set_auto_kill(False)
    assert h.getter is get and h.setter is put
    assert h.start_value == h.change_value == Rect(0, 0, 0, 0)
    assert type(h.plug_options) is api.RectOptions
    h.force_init()
    h.start_value, h.change_value = Rect(5, 6, 7, 8), Rect(40, 50, 60, 70)
    h.end_value = Rect(100, 200, 300, 400)
    h.plug_options.snapping = True
    job = h._numeric_job
    h.goto(.25)
    assert values[0] == Rect(15, 18, 22, 26)
    assert h.end_value == Rect(100, 200, 300, 400) and h._numeric_job is job
    plugin = h.get_plugin()
    assert plugin.storage_default() == Rect(0, 0, 0, 0)
    plugin.evaluate_and_apply(h.plug_options, h, False, h.getter, h.setter, .25,
        h.start_value, h.change_value, 1, False, 0, api.UpdateNotice.NONE)
    assert values[0] == Rect(15, 18, 22, 26)
    other = m.to(plugin, get, put, Rect(6, 7, 8, 9), 1)
    assert other.get_plugin() is plugin
    m.clear()


@pytest.mark.parametrize('numpy_buffer', [False, True])
def test_rect_native_batch_writes_four_float_channels(numpy_buffer):
    job = _RectTweenSnapshot((2, 3, 4, 5), (8, 10, 12, 16), True).bind(_EaseKernel(1), 1)
    times = array('d', [0, .25, .5, .75, 1])
    values = np.empty((5, 4), dtype=np.float32) if numpy_buffer else memoryview(array('f', [0] * 20)).cast('B').cast('f', shape=[5, 4])
    job.sample_into(times, values, 1, 3, 2)
    expected = [list(job.sample_nested(t, 1, 3, 2)) for t in times]
    assert values.tolist() == expected


def test_rect_stores_float_channels_before_snapping_at_large_coordinates():
    snapshot = _RectTweenSnapshot((4194304., 0., 0., 0.), (1., 0., 0., 0.), True)
    assert snapshot.interpolate(.51)[0] == 4194304.


def test_string_text_edits_preserve_rich_length_cache_but_new_options_replace_it():
    m, values = api.TweenManager(), ['<b>ABCDE</b>']
    h = m.to(lambda: values[0], lambda value: values.__setitem__(0, value), '<i>uvwxyz</i>', 1)
    h.set_ease(api.Ease.LINEAR).set_auto_kill(False).set_options(True).force_init()
    assert h.change_value == '<i>uvwxyz</i>'
    h.start_value = '<u>0123456789</u>'
    h.goto(.25)
    assert values[0] == '<i>uv</i><u>234</u>'
    cached = copy(h.plug_options)
    h.plug_options = cached
    h.goto(.5)
    assert values[0] == '<i>uvw</i><u>34</u>'
    options = api.StringOptions()
    options.rich_text_enabled = True
    h.plug_options = options
    h.goto(1)
    assert values[0] == ''
    m.clear()


def test_shared_string_characters_rebind_only_on_edits_and_old_plans_stay_immutable():
    m, values = api.TweenManager(), ['']
    h = m.to(lambda: values[0], lambda value: values.__setitem__(0, value), 'abcd', 1)
    h.set_ease(api.Ease.LINEAR).set_auto_kill(False).set_options(False, api.ScrambleMode.CUSTOM, 'XX').force_init()
    chars, old_plan = h.plug_options.scrambled_chars, h._string_plan
    copied = copy(h.plug_options)
    other = m.to(lambda: '', lambda value: None, 'abcd', 1).set_ease(api.Ease.LINEAR).set_auto_kill(False)
    other.plug_options = copied
    other.force_init()
    chars[:] = ['Y', 'Y']
    assert h._string_plan is not old_plan and copied.scrambled_chars is chars
    assert old_plan(.5) == 'abXX'
    assert h._string_plan(.5) == other._string_plan(.5) == 'abYY'
    prepared = h._string_plan
    h.goto(.25)
    h.goto(.5)
    assert h._string_plan is prepared
    with pytest.raises(TypeError):
        chars.append('Z')
    with pytest.raises(ValueError):
        chars[0] = 'ab'
    h.kill()
    chars[:] = ['Z', 'Z']
    assert other._string_plan(.5) == 'abZZ'
    m.clear()


def test_string_plugin_reset_and_speed_use_the_captured_text_options():
    m, values = api.TweenManager(), ['12']
    h = m.to(lambda: values[0], lambda value: values.__setitem__(0, value), '<b>abcd</b>', 1)
    h.set_ease(api.Ease.LINEAR).set_auto_kill(False).set_options(True).force_init()
    plugin = h.get_plugin()
    assert plugin.convert_to_start_value(h, None) is None
    assert plugin.get_speed_based_duration(h.plug_options, 2, '<i>abcdef</i>') == 2
    plugin.reset(h)
    h.goto(.5)
    assert values[0] == h.start_value == h.end_value == h.change_value == ''
    m.clear()
