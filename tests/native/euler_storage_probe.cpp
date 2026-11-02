#include "infernux/core/math/EulerTween.h"
#include <fstream>
#include <iostream>

int main(int argc, char **argv)
{
    using namespace infernux::tween;
    if (argc != 2) return 2;
    std::ifstream input(argv[1]);
    size_t count = 0, different = 0;
    int mode, constraint;
    bool normalized, dynamic, relative;
    float factor;
    double own;
    while (input >> mode >> normalized >> dynamic >> constraint >> relative >> factor >> own) {
        Point start, change, end, up, point, position, expectedEnd, expectedChange;
        std::array<float, 4> expected;
        for (auto *v : {&start, &change, &end, &up, &point, &position, &expectedEnd, &expectedChange})
            for (auto &x : *v) input >> x;
        for (auto &x : expected) input >> x;
        if (!input) return 3;
        if (dynamic) PrepareEulerLookAt(start, end, change, point, up, position, mode, constraint, relative);
        const LiveEulerValues<Point> live(start, change, mode);
        auto value = live.Interpolate(factor, own);
        if (normalized) value = infernux::rotation::NormalizeTransform(value[0], value[1], value[2], value[3]);
        bool equal = true;
        for (size_t i = 0; i < 3; ++i)
            equal = equal && std::abs(end[i] - expectedEnd[i]) <= 5e-5f && std::abs(change[i] - expectedChange[i]) <= 5e-5f;
        for (size_t i = 0; i < 4; ++i)
            equal = equal && std::abs(value[i] - expected[i]) <= 4e-7f;
        if (!equal) {
            ++different;
            if (different <= 10) std::cerr << "different Euler state " << count << '\n';
        }
        ++count;
    }
    std::cout << "EULER_STORAGE states=" << count << " differences=" << different << '\n';
    return count && !different ? 0 : 1;
}
