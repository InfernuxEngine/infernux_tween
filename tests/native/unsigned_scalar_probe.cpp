#include "infernux/core/math/TweenNumerics.h"
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    std::ifstream input(argv[1]);
    int bits;
    uint64_t start, delta, expected;
    uint32_t factorBits;
    int64_t own, multiplier, parent;
    bool negative, expectedError;
    size_t count = 0, different = 0;
    while (input >> bits >> start >> delta >> factorBits >> own >> multiplier >> parent >> negative >> expectedError >> expected) {
        float factor;
        std::memcpy(&factor, &factorBits, sizeof(factor));
        bool failed = false;
        uint64_t actual = 0;
        try {
            actual = bits == 32 ? infernux::tween::Unsigned32Snapshot(uint32_t(start), uint32_t(delta), negative)
                                     .Interpolate(factor, own, multiplier, parent)
                               : infernux::tween::Unsigned64Snapshot(start, delta).Interpolate(factor, own, multiplier, parent);
        } catch (const infernux::tween::NumericOverflow &) { failed = true; }
        if (failed != expectedError || (!failed && actual != expected)) {
            ++different;
            if (different <= 10) std::cerr << "row " << count << ": " << actual << " != " << expected
                                         << "; error " << failed << " != " << expectedError << '\n';
        }
        ++count;
    }
    std::cout << "UNSIGNED_SCALAR states=" << count << " differences=" << different << '\n';
    return count && !different ? 0 : 1;
}
