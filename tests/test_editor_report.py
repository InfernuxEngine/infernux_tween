"""Creation-time counters keep optional Editor reports out of frame traversal."""
from types import SimpleNamespace

import infernux_tween as tween
from infernux_tween import TweenManager, UpdateType


def test_report_tracks_peak_roots_across_nesting_phase_changes_and_recycling():
    manager = TweenManager().init(recycle_all_by_default=True)
    first = manager.to(lambda: 0., lambda value: None, 1., 1.)
    sequence = manager.sequence().append(manager.to(lambda: 0., lambda value: None, 1., 1.))
    first.set_update(UpdateType.LATE).set_update(UpdateType.MANUAL)
    assert manager.get_editor_report() == {'peak_tweeners': 2, 'peak_sequences': 1, 'safe_mode_errors': 0}
    assert manager.total_active_tweeners() == manager.total_active_sequences() == 1
    sequence.kill()
    manager._reset_editor_report()
    assert manager.get_editor_report() == {'peak_tweeners': 1, 'peak_sequences': 0, 'safe_mode_errors': 0}
    first.kill()
    recycled = manager.to(lambda: 0., lambda value: None, 1., 1.)
    assert manager.get_editor_report()['peak_tweeners'] == 1
    recycled.kill()
    assert manager._active_counts == [0, 0]


def test_report_emits_only_on_editor_stop_when_enabled_and_resets_at_next_play(monkeypatch):
    from editor.TweenTools import _report_play_state
    from infernux.debug import Debug
    from infernux.engine.play_mode import PlayModeState

    manager, messages = TweenManager(), []
    monkeypatch.setattr(tween, '_default_manager', manager)
    monkeypatch.setattr(Debug, 'log', messages.append)
    stop = SimpleNamespace(old_state=PlayModeState.PLAYING, new_state=PlayModeState.EDIT)
    enter = SimpleNamespace(old_state=PlayModeState.EDIT, new_state=PlayModeState.ENTERING)
    handle = manager.to(lambda: 0., lambda value: None, 1., 1.)
    handle.kill()
    _report_play_state(stop)
    assert not messages
    tween.show_editor_report = True
    _report_play_state(stop)
    assert messages == ['Tween Play report: peak roots 1 tweeners / 0 sequences; 0 handled errors']
    _report_play_state(enter)
    _report_play_state(stop)
    assert messages[-1] == 'Tween Play report: peak roots 0 tweeners / 0 sequences; 0 handled errors'
