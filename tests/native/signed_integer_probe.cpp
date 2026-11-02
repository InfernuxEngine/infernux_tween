#include "infernux/core/math/TweenNumerics.h"
#include <cstdint>
#include <fstream>
#include <iostream>

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    std::ifstream input(argv[1]);
    int bits;
    int64_t start, end, own, multiplier, parent, expected;
    double factor;
    size_t count = 0, different = 0;
    while (input >> bits >> start >> end >> factor >> own >> multiplier >> parent >> expected) {
        const infernux::tween::SignedIntegerSnapshot value(static_cast<uint64_t>(start), static_cast<uint64_t>(end), bits);
        const auto actual = value.Interpolate(factor, own, multiplier, parent);
        if (actual != expected) {
            ++different;
            std::cerr << "row " << count << ": " << actual << " != " << expected << '\n';
        }
        ++count;
    }
    std::cout << "SIGNED_INTEGER states=" << count << " differences=" << different << '\n';
    return count && !different ? 0 : 1;
}
