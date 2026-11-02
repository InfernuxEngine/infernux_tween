#include "infernux/core/math/TweenNumerics.h"
#include <fstream>
#include <iostream>

int main(int argc, char **argv)
{
    using namespace infernux::tween;
    if (argc != 2) return 2;
    std::ifstream input(argv[1]);
    size_t size, count = 0, different = 0;
    while (input >> size) {
        auto starts = std::make_shared<std::vector<Point>>(size);
        auto changes = std::make_shared<std::vector<Point>>(size);
        std::vector<double> durations(size);
        for (auto &v : *starts) for (auto &x : v) input >> x;
        for (auto &v : *changes) for (auto &x : v) input >> x;
        for (auto &d : durations) input >> d;
        double elapsed, duration, own;
        Point expected;
        input >> elapsed >> duration >> own;
        for (auto &x : expected) input >> x;
        if (!input) return 3;
        const LiveSegmentSnapshot<Point> plan(starts, changes, durations);
        const auto actual = plan.SampleTime(elapsed, duration, EaseKernel(1), own);
        if (actual != expected) {
            ++different;
            if (different <= 10) std::cerr << "different array state " << count << '\n';
        }
        ++count;
    }
    auto starts = std::make_shared<std::vector<Point>>(1, Point{0, 0, 0});
    auto changes = std::make_shared<std::vector<Point>>(1, Point{2, 4, 6});
    const LiveSegmentSnapshot<Point> live(starts, changes, {1});
    const auto frozen = live.Frozen();
    (*starts)[0][0] = 10;
    if (live.Sample(.5, 1, EaseKernel(1), 0) != Point{11, 2, 3}) return 4;
    if (frozen.Sample(.5, 1, EaseKernel(1), 0) != Point{1, 2, 3}) return 5;
    const auto speeds = SegmentSpeedDurations(*changes, {2});
    if (speeds[0] != std::sqrt(56.f) / 2.f) return 6;
    std::cout << "ARRAY_STORAGE states=" << count << " differences=" << different << "; live/frozen/speeds PASS\n";
    return count && !different ? 0 : 1;
}
