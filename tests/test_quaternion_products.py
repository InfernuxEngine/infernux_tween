"""Public quaternion arithmetic preserves raw components and cancellation."""
from infernux.lib import quatf


def test_product_keeps_wide_intermediates_until_the_result_components_are_stored():
    left = quatf(100_000_000, 1, 1, 100_000_000)
    right = quatf(1, 1, 1, 1)
    assert tuple(left * right) == (200_000_000, 2, 200_000_000, -2)
    left *= right
    assert tuple(left) == (200_000_000, 2, 200_000_000, -2)


def test_product_does_not_normalize_the_input_or_result():
    left, right = quatf(1, 2, 3, 4), quatf(-2, 1, .5, 3)
    assert tuple(left * right) == (-7, 3.5, 16, 10.5)
    assert tuple(left) == (1, 2, 3, 4)
    assert tuple(right) == (-2, 1, .5, 3)
