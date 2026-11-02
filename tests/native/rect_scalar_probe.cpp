#include "infernux/core/math/TweenNumerics.h"
#include <fstream>
#include <iostream>

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    std::ifstream input(argv[1]);
    infernux::tween::RectSnapshot::Value start, change, expected;
    float factor;
    int own, multiplier, parent;
    bool snapping;
    size_t count = 0, different = 0;
    while (input >> start[0] >> start[1] >> start[2] >> start[3]
                 >> change[0] >> change[1] >> change[2] >> change[3]
                 >> factor >> own >> multiplier >> parent >> snapping
                 >> expected[0] >> expected[1] >> expected[2] >> expected[3]) {
        const auto actual = infernux::tween::RectSnapshot(start, change, snapping).Interpolate(factor, own, multiplier, parent);
        if (actual != expected) {
            ++different;
            if (different <= 10) std::cerr << "different rectangle at row " << count << '\n';
        }
        ++count;
    }
    std::cout << "RECT_SCALAR states=" << count << " differences=" << different << '\n';
    return count && !different ? 0 : 1;
}
