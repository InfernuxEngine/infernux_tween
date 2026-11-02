#include "infernux/core/math/DecimalUInt64.h"
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>

void Normalize(infernux::tween::detail::DecimalFactor &value)
{
    while (value.scale) {
        auto next = value.coefficient;
        if (next.Divide10()) break;
        value.coefficient = next;
        --value.scale;
    }
    if (value.coefficient.Compare(infernux::tween::detail::UInt160()) == 0) {
        value.scale = 0;
        value.negative = false;
    }
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    std::ifstream input(argv[1]);
    uint32_t bits, low, middle, high;
    int scale;
    bool negative, expectedError;
    size_t count = 0, different = 0;
    while (input >> bits >> low >> middle >> high >> scale >> negative >> expectedError) {
        infernux::tween::detail::DecimalFactor expected{infernux::tween::detail::UInt160(), scale, negative};
        expected.coefficient.words = {low, middle, high, 0, 0};
        Normalize(expected);
        float factor;
        std::memcpy(&factor, &bits, sizeof(factor));
        bool failed = false, match = false;
        try {
            auto actual = infernux::tween::detail::ToDecimalFactor(factor);
            Normalize(actual);
            match = actual.coefficient.Compare(expected.coefficient) == 0
                    && actual.scale == expected.scale && actual.negative == expected.negative;
        } catch (const infernux::tween::NumericOverflow &) { failed = true; }
        if (failed != expectedError || (!failed && !match)) {
            ++different;
            if (different <= 10) std::cerr << "row " << count << ": factor bits " << bits << '\n';
        }
        ++count;
    }
    std::cout << "DECIMAL_FACTOR states=" << count << " differences=" << different << '\n';
    return count && !different ? 0 : 1;
}
