"""Fixed-width curve identity and reuse after authored edits."""
import copy

import pytest

from infernux import AnimationCurve, Keyframe, WeightedMode, WrapMode


@pytest.mark.parametrize('count,expected', [
    (0, 0), (1, -153111983), (2, 1469805713), (3, -837335343),
    (4, 2000103697), (5, 551492433), (6, -1980555887),
    (7, -1571344431), (8, -890285551),
])
def test_zero_keys_keep_fixed_signed_32_bit_content_hash(count, expected):
    assert AnimationCurve(keys=[Keyframe()] * count).get_hash_code() == expected


@pytest.mark.parametrize('field,value,expected', [
    ('time', 1., 56603217), ('value', 1., -1637895599),
    ('in_tangent', 1., -1151356335), ('out_tangent', 1., -1503677871),
    ('in_weight', 1., 778023505), ('out_weight', 1., -1419791791),
    ('time', -0., 1994371665), ('weighted_mode', WeightedMode.IN, -153099816),
    ('tangent_mode', 17, -153111966),
])
def test_hash_keeps_float_bits_and_key_metadata(field, value, expected):
    key = Keyframe()
    setattr(key, field, value)
    assert AnimationCurve(key).get_hash_code() == expected


def test_unchanged_hash_reuses_computation_and_edits_invalidate_it():
    curve = AnimationCurve(Keyframe())
    original = curve._native_snapshot
    calls = []
    def snapshot():
        calls.append(True)
        return original()
    curve._native_snapshot = snapshot
    assert [curve.get_hash_code() for _ in range(8)] == [-153111983] * 8
    assert len(calls) == 1
    curve.move_key(0, Keyframe(0, 1))
    assert curve.get_hash_code() == -1637895599
    curve.post_wrap_mode = WrapMode.LOOP
    assert curve.get_hash_code() == -1637895599
    assert copy.deepcopy(curve).get_hash_code() == curve.get_hash_code()
    assert AnimationCurve.from_dict(curve.to_dict()).get_hash_code() == curve.get_hash_code()


def test_hash_owns_metadata_when_source_changes_after_snapshot_acquisition():
    curve = AnimationCurve(Keyframe(tangent_mode=17))
    original = curve._native_snapshot
    def interleaved_edit():
        snapshot = original()
        curve.keys = [Keyframe(), Keyframe()]
        return snapshot
    curve._native_snapshot = interleaved_edit
    assert curve.get_hash_code() == -153111966
    curve._native_snapshot = original
    assert curve.get_hash_code() == 1469805713
