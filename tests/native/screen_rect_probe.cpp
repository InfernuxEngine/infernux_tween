#include "infernux/core/math/ScreenRect.h"
#include <cmath>
#include <iostream>

int main()
{
    using infernux::ui::ScreenRect;
    int checked = 0, failed = 0;
    const auto near = [&](double actual, double expected) {
        ++checked;
        if (std::fabs(actual - expected) > 1e-10) ++failed;
    };
    const ScreenRect corner({10, 20, 80, 40}, 90, {0, 0});
    const std::array<ScreenRect::Point, 4> expected{{{10,20}, {10,100}, {-30,100}, {-30,20}}};
    const auto actual = corner.Corners();
    for (size_t i = 0; i < actual.size(); ++i) for (size_t axis = 0; axis < 2; ++axis)
        near(actual[i][axis], expected[i][axis]);
    const auto bounds = corner.VisualRect();
    for (size_t i = 0; i < 4; ++i) near(bounds[i], ScreenRect::Rect{-30,20,40,80}[i]);
    for (double angle : {0., 30., -90., 137., 450.})
        for (const auto &pivot : {ScreenRect::Point{.5,.5}, ScreenRect::Point{0,0}, ScreenRect::Point{-.2,1.2}}) {
            const ScreenRect geometry({10,20,80,40}, angle, pivot);
            const ScreenRect centered(geometry.RenderRect(), angle);
            const auto corners = geometry.Corners(), rendered = centered.Corners();
            for (size_t i = 0; i < 4; ++i) for (size_t axis = 0; axis < 2; ++axis)
                near(corners[i][axis], rendered[i][axis]);
            for (const auto &point : {ScreenRect::Point{20,10}, ScreenRect::Point{60,30}}) {
                const auto world = geometry.ToCanvas(point), local = geometry.ToLocal(world);
                near(local[0], point[0]); near(local[1], point[1]);
                near(geometry.Contains(world), true);
            }
            near(geometry.Contains(geometry.ToCanvas({-10,20})), false);
            near(geometry.Contains(geometry.ToCanvas({-10,20}),11), true);
        }
    std::cout << "Screen rect: " << checked << " checks; " << failed << " failures\n";
    return failed ? 1 : 0;
}
