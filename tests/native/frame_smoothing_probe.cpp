#include "infernux/core/math/FrameTimeSmoothing.h"
#include <cmath>
#include <iostream>

int main()
{
    infernux::timing::FrameTimeSmoother clock;
    int checks = 0;
    bool good = true;
    const auto near = [&](float actual, float expected, float tolerance = 2e-8f) {
        ++checks;
        if (std::abs(actual - expected) > tolerance) {
            good = false;
            std::cerr << "Frame smoothing check " << checks << " failed: " << actual << " vs " << expected << '\n';
        }
    };
    near(clock.Value(), 0);
    near(clock.Advance(.02), 0);
    near(clock.Advance(.01f), .01f);
    near(clock.Advance(.1f), .1f);
    near(clock.Advance(.02f), .05555556f);
    near(clock.Advance(1.f / 60), .0396174863f);
    for (int i = 0; i < 128; ++i) clock.Advance(.02);
    near(clock.Value(), .02f);
    near(clock.Advance(.1), .036f);
    near(clock.Advance(.02), .0328f);
    near(clock.Advance(0), .02624f);
    for (int i = 0; i < 128; ++i) clock.Advance(0);
    near(clock.Value(), 0);
    clock.Reset();
    near(clock.Value(), 0);
    near(clock.Advance(.2), 0);
    near(clock.Advance(.005), .005f);
    near(clock.Advance(.005), .005f);
    std::cout << checks << " frame smoothing checks: " << (good ? "PASS" : "FAIL") << '\n';
    return good ? 0 : 1;
}
