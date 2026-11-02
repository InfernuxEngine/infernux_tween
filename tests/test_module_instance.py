"""The module's live manager view is read-only throughout initialization."""
import pytest
import infernux_tween as api


def test_instance_cannot_be_shadowed_before_or_after_initialization():
    api.clear(True)
    try:
        assert api.instance is None
        with pytest.raises(AttributeError):
            api.instance = object()
        api.init()
        current = api.instance
        assert isinstance(current, api.TweenManager)
        with pytest.raises(AttributeError):
            api.instance = None
        assert api.instance is current
    finally:
        api.__dict__.pop('instance', None)
        api.clear(True)
    assert api.instance is None
