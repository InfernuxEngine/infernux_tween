// Exercise the engine's numerical header with canonical input words.
#include "infernux/core/math/CurveContentHash.h"
#include <array>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>

struct Key
{
    float time, value, inTangent, outTangent, inWeight, outWeight;
    uint32_t weightedMode;
    int32_t tangentMode;
};

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
        size_t count;
        std::cin >> count;
        std::vector<Key> keys;
        keys.reserve(count);
        for (size_t index = 0; index < count; ++index) {
            std::array<uint32_t, 8> words;
            for (auto &word : words) std::cin >> word;
            int32_t tangentMode;
            std::memcpy(&tangentMode, &words[7], sizeof(tangentMode));
            keys.push_back({AsFloat(words[0]), AsFloat(words[1]), AsFloat(words[2]),
                            AsFloat(words[3]), AsFloat(words[5]), AsFloat(words[6]), words[4], tangentMode});
        }
        if (!std::cin) return 2;
        std::cout << infernux::curve::ContentHash(keys.data(), count) << '\n';
    }
}
