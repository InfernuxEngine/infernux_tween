#include "infernux/core/math/TweenNumerics.h"
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>

float Decode(uint32_t bits) { float value; std::memcpy(&value, &bits, sizeof(value)); return value; }
uint32_t Encode(float value) { uint32_t bits; std::memcpy(&bits, &value, sizeof(bits)); return bits; }

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    std::ifstream input(argv[1]);
    uint32_t start, delta, factor, expected;
    double own, multiplier, parent;
    bool snapping;
    size_t count = 0, different = 0;
    while (input >> start >> delta >> factor >> own >> multiplier >> parent >> snapping >> expected) {
        const infernux::tween::Float32Snapshot snapshot(Decode(start), Decode(delta), snapping);
        const auto actual = Encode(snapshot.Interpolate(Decode(factor), own, multiplier, parent));
        if (actual != expected) {
            ++different;
            std::cerr << "row " << count << ": " << actual << " != " << expected << '\n';
        }
        ++count;
    }
    std::cout << "SINGLE_PRECISION states=" << count << " differences=" << different << '\n';
    return count && !different ? 0 : 1;
}
