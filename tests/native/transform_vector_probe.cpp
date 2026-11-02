#include "infernux/core/math/TransformVectorMath.h"
#include <nlohmann/json.hpp>
#include <array>
#include <fstream>
#include <iostream>

using Json = nlohmann::json;
using Point = std::array<float, 3>;
using Rotation = std::array<float, 4>;
using infernux::transform_math::RotateLocal;

Point point(const Json &v) { return {v.at("x"), v.at("y"), v.at("z")}; }
Rotation rotation(const Json &v) { return {v.at("x"), v.at("y"), v.at("z"), v.at("w")}; }
Rotation inverse(Rotation q) { for (int i=0;i<3;++i) q[i]=-q[i];return q; }
Point product(Point a, const Point &b) { for (int i=0;i<3;++i) a[i]*=b[i];return a; }
Point add(Point a, const Point &b) { for (int i=0;i<3;++i) a[i]+=b[i];return a; }

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    std::ifstream stream(argv[1]);Json reference;stream >> reference;
    size_t samples=0, checks=0, failures=0;
    const auto check=[&](const Point &actual,const Json &wanted) {
        const Point expected=point(wanted);
        for (int i=0;i<3;++i) { ++checks;failures+=actual[i]!=expected[i]; }
    };
    for (const auto &group:reference.at("groups")) {
        const auto local=rotation(group.at("local_rotation")), grand=rotation(group.at("grand_rotation"));
        const auto scale=point(group.at("scale")), position=point(group.at("position"));
        const auto grandScale=point(group.at("grand_scale")), grandPosition=point(group.at("grand_position"));
        const bool nested=group.at("nested");
        for (const auto &sample:group.at("samples")) {
            const Point value=point(sample.at("input"));
            auto p=add(RotateLocal(local,product(value,scale)),position);
            auto v=RotateLocal(local,product(value,scale));
            auto d=RotateLocal(local,value);
            auto id=nested?RotateLocal(inverse(grand),value):value;
            id=RotateLocal(inverse(local),id);
            if (nested) {
                p=add(RotateLocal(grand,product(p,grandScale)),grandPosition);
                v=RotateLocal(grand,product(v,grandScale));
                d=RotateLocal(grand,d);
            }
            check(p,sample.at("point"));check(v,sample.at("vector"));
            check(d,sample.at("direction"));check(id,sample.at("inverse_direction"));
            ++samples;
        }
    }
    if (samples!=1980) return 2;
    std::cout << samples << " hierarchy inputs / " << checks << " exact forward/direction components; failures=" << failures << '\n';
    return failures?1:0;
}
