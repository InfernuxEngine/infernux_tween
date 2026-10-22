"""A scalar damped spring for fixed-step animation and interactive impulses."""
from math import isfinite


class Spring:
    def __init__(self, value=0.0, stiffness=100.0, damping=10.0):
        if not all(isfinite(item) for item in (value, stiffness, damping)) or stiffness < 0 or damping < 0:
            raise ValueError("Spring value must be finite, with nonnegative stiffness and damping")
        self.value = self.target = float(value)
        self.velocity = 0.0
        self.stiffness, self.damping = float(stiffness), float(damping)

    def Pull(self, amount):
        self.value += amount
        return self

    def Animate(self, target):
        self.target = target
        return self

    def Update(self, delta):
        acceleration = -self.stiffness * (self.value - self.target) - self.damping * self.velocity
        self.velocity += acceleration * delta
        self.value += self.velocity * delta
        return self.value

    def IsResting(self, tolerance=0.00001):
        return abs(self.value - self.target) <= tolerance and abs(self.velocity) <= tolerance
