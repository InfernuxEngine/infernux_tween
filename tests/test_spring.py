import pytest

from infernux_tween import Spring


def test_fixed_step_impulses_preserve_velocity_and_retarget():
    spring = Spring(1, stiffness=200, damping=10).Pull(0.2)
    assert [spring.Update(1/60) for _ in range(3)] == pytest.approx((1.188888888888889, 1.169135802469136, 1.143278463648834))
    velocity = spring.velocity
    value = spring.value
    spring.Pull(0.05)
    assert spring.velocity == velocity and spring.value == value + 0.05
    spring.Animate(2)
    for _ in range(180):
        spring.Update(1/60)
    assert spring.IsResting() and spring.value == pytest.approx(2, abs=0.00001)
