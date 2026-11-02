#include "infernux/core/math/VectorTween.h"
#include <fstream>
#include <iostream>

template <size_t Channels> bool Check(std::istream &input, bool snapping, double factor, double own)
{
    using Value = std::array<float, Channels>;
    Value start{}, change{}, expected{};
    const infernux::tween::LiveVectorValues<Value, Channels> live(start, change, snapping);
    for (auto *v : {&start, &change, &expected})
        for (auto &x : *v) input >> x;
    if (!input) return false;
    const auto frozen = live.Frozen();
    const auto first = live.Interpolate(factor, own);
    start[0] += 10;
    change[0] += 20;
    return first == expected && frozen.Interpolate(factor, own) == expected
        && live.Interpolate(factor, own) != expected;
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    std::ifstream input(argv[1]);
    size_t count = 0, differences = 0;
    int channels;
    bool snapping;
    double factor, own;
    while (input >> channels >> snapping >> factor >> own) {
        const bool equal = channels == 2 ? Check<2>(input, snapping, factor, own)
                         : channels == 3 ? Check<3>(input, snapping, factor, own)
                                         : Check<4>(input, snapping, factor, own);
        if (!equal) {
            ++differences;
            if (differences <= 10) std::cerr << "different vector state " << count << '\n';
        }
        ++count;
    }
    std::cout << "VECTOR_STORAGE states=" << count << " differences=" << differences << '\n';
    return count && !differences ? 0 : 1;
}
