#include "infernux/core/math/CurveAuthoring.h"
#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>

struct Key { float time, value; };

float AsFloat(uint32_t bits)
{
    float value;
    std::memcpy(&value, &bits, sizeof(value));
    return value;
}

int main()
{
    size_t cases;
    if (!(std::cin >> cases)) return 2;
    for (size_t sample = 0; sample < cases; ++sample) {
        size_t count, index;
        uint32_t weight;
        std::cin >> count >> index >> weight;
        std::vector<Key> keys(count);
        for (auto &key : keys) {
            uint32_t time, value;
            std::cin >> time >> value;
            key = {AsFloat(time), AsFloat(value)};
        }
        if (!std::cin) return 2;
        const float tangent = infernux::curve::SmoothedTangent(keys.data(), count, index, AsFloat(weight));
        uint32_t bits;
        std::memcpy(&bits, &tangent, sizeof(bits));
        std::cout << bits << '\n';
    }
}
