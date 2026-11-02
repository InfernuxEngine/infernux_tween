#include "infernux/core/math/QuaternionEuler.h"
#include <nlohmann/json.hpp>
#include <array>
#include <fstream>
#include <iostream>

using Json = nlohmann::json;

std::array<float, 4> components(const Json &value)
{
    return {value.at("x"), value.at("y"), value.at("z"), value.at("w")};
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    std::ifstream stream(argv[1]);
    if (!stream) return 2;
    Json reference;
    stream >> reference;
    size_t count = 0, differences = 0;
    for (const auto &sample : reference.at("samples")) {
        const auto actual = infernux::rotation::MultiplyPublic(
            components(sample.at("left")), components(sample.at("right")));
        const auto expected = components(sample.at("value"));
        for (size_t axis = 0; axis < 4; ++axis) differences += actual[axis] != expected[axis];
        ++count;
    }
    std::cout << count << " public products / " << count * 4
              << " exact components; differences=" << differences << '\n';
    return count != 2048 ? 2 : differences ? 1 : 0;
}
