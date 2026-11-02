#include "infernux/core/math/MotionPath.h"
#include <fstream>
#include <iostream>

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    std::ifstream input(argv[1]);
    int kind, waypointCount, controlCount, expectedError;
    size_t size, count = 0, differences = 0;
    float offset;
    double progress;
    while (input >> kind >> size >> waypointCount >> controlCount >> offset >> progress >> expectedError) {
        const bool rawParameter = kind >= 3;
        if (rawParameter) kind -= 3;
        std::vector<infernux::motion::Point> points(size);
        for (auto &point : points) for (auto &x : point) input >> x;
        using Data = infernux::motion::PathSnapshot;
        auto data = std::make_shared<Data>(std::move(points), kind, 10, false);
        for (int group = 0; group < 2; ++group) {
            const int count = group == 0 ? waypointCount : controlCount;
            if (group == 1 && count == -2) {
                data = std::make_shared<Data>(data->WithControls(nullptr));
                continue;
            }
            if (count < 0) continue;
            auto values = std::make_shared<std::vector<infernux::motion::Point>>(count);
            for (auto &point : *values) for (auto &x : point) input >> x;
            data = std::make_shared<Data>(group == 0 ? data->WithWaypoints(values) : data->WithControls(values));
        }
        infernux::motion::Point expected;
        for (auto &x : expected) input >> x;
        if (!input) return 3;
        bool equal = true;
        try {
            auto value = rawParameter ? data->Evaluate(progress) : data->Sample(progress);
            equal = expectedError == 0;
            for (size_t axis = 0; axis < 3; ++axis) {
                value[axis] += offset;
                equal = equal && std::abs(value[axis] - expected[axis]) <= 4e-6f;
            }
        } catch (const std::out_of_range &) { equal = expectedError == 1; }
        catch (const infernux::motion::MissingPathControls &) { equal = expectedError == 2; }
        if (!equal) {
            ++differences;
            if (differences <= 10) std::cerr << "different path state " << count << '\n';
        }
        ++count;
    }
    std::cout << "PATH_STORAGE states=" << count << " differences=" << differences << '\n';
    return count && !differences ? 0 : 1;
}
