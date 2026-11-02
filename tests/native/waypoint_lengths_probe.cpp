#include "infernux/core/math/WaypointLengths.h"
#include "infernux/core/math/TweenNumerics.h"
#include <fstream>
#include <iostream>

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    std::ifstream input(argv[1]);
    char kind;
    int size, pointCount, index, direction, expectedIndex, expectedError;
    float percentage, length, expectedTime;
    size_t count = 0, differences = 0;
    while (input >> kind >> size >> pointCount >> index >> percentage >> length >> direction >> expectedIndex >> expectedTime >> expectedError) {
        infernux::Float32Array lengths;
        lengths.values.resize(static_cast<size_t>(std::max(0, size)));
        for (float &value : lengths.values) input >> value;
        if (!input) return 3;
        const auto *values = size < 0 ? nullptr : &lengths;
        bool equal = false;
        try {
            if (kind == 'I') {
                equal = infernux::motion::WaypointIndex(values, pointCount, percentage, length, direction) == expectedIndex;
            } else if (kind == 'Q') {
                float time = infernux::motion::WaypointFraction(values, index, length);
                time = time < 0 ? std::floor(time) : std::min(1.f, time);
                equal = std::abs(time - expectedTime) <= 1e-6f;
            } else if (kind == 'S') {
                const auto time = infernux::tween::AdvanceClock(-1, .1, 1, false, 1, false);
                const auto sample = infernux::tween::SampleProgress(time, 0, 1, false, false, false);
                equal = time == expectedTime && sample.cycle == -1 && std::abs(sample.progress - .1) < 1e-6;
            } else return 4;
            equal = equal && expectedError == 0;
        } catch (const infernux::motion::MissingWaypointLengths &) { equal = expectedError == 1; }
        catch (const std::out_of_range &) { equal = expectedError == 2; }
        if (!equal) {
            ++differences;
            if (differences <= 10) std::cerr << "different waypoint state " << count << '\n';
        }
        ++count;
    }
    std::cout << "WAYPOINT_LENGTHS states=" << count << " differences=" << differences << '\n';
    return count && !differences ? 0 : 1;
}
