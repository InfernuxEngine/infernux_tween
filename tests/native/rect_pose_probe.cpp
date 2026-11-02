#include "infernux/core/math/RectLayout.h"
#include <iostream>

int main()
{
    using namespace infernux::ui;
    bool good = true;
    int checks = 0;
    const auto point = [&](RectPoint actual, RectPoint expected) {
        ++checks;
        if (actual != expected) {
            good = false;
            std::cerr << "Rectangle pose check " << checks << " failed\n";
        }
    };
    RectTransformState layout;
    layout.spec.parentSize = {200,100};
    layout.spec.anchorMin = {0,0};
    layout.spec.anchorMax = {1,1};
    layout.spec.pivot = {.25f,.75f};
    layout.spec.sizeDelta = {-20,-10};
    layout.spec.anchoredPosition = {10,-5};
    layout.RefreshReference();
    point(layout.anchorReference, {-50,25});
    point(layout.LocalPosition(), {-40,20});
    const auto first = CompileRectLayout(layout.spec);
    point({first.rect[2],first.rect[3]}, {180,90});
    layout.spec.parentSize = {400,200};
    layout.RefreshReference();
    point(layout.spec.anchoredPosition, {10,-5});
    point(layout.LocalPosition(), {-90,45});
    point(layout.SetLocalPosition({17,23}), {17,23});
    point(layout.spec.anchoredPosition, {117,-27});
    layout.spec.pivot = {-.5f,1.5f};
    layout.RefreshReference();
    point(layout.LocalPosition(), {-283,173});
    layout.spec.parentPivot = {1,0};
    layout.RefreshReference();
    point(layout.LocalPosition(), {-483,273});
    layout.spec.parentSize = {0,0};
    layout.RefreshReference();
    point(layout.LocalPosition(), {117,-27});
    point(layout.SetLocalPosition({-8,16}), {-8,16});
    point(layout.spec.anchoredPosition, {-8,16});
    const auto root = CompileRectLayout(layout.spec);
    point({root.rect[2],root.rect[3]}, {-20,-10});
    layout.positionScale = .125f;
    point(layout.LocalPosition(), {-1,2});
    point(layout.SetLocalPosition({.5f,-.25f}), {.5f,-.25f});
    point(layout.spec.anchoredPosition, {4,-2});
    layout.spec.parentSize = {400,200};
    layout.RefreshReference();
    point(layout.LocalPosition(), {-74.5f,37.25f});
    const auto scaled = CompileRectLayout(layout.spec);
    point({scaled.rect[2],scaled.rect[3]}, {380,190});
    RectTransformState driven;
    driven.spec.sizeDelta = {200, 100};
    driven.spec.anchoredPosition = {10, -5};
    driven.RefreshReference();
    driven.BeginDrive(7, false, 1);
    driven.spec.sizeDelta = {80, 130};
    point(driven.AuthoringSpec().sizeDelta, {200, 130});
    point(driven.AuthoringSpec().anchoredPosition, {10, -5});
    driven.BeginDrive(7, true, 2);
    point(driven.spec.sizeDelta, {200, 130});
    driven.spec.sizeDelta[1] = 60;
    driven.spec.anchoredPosition = {30, 40};
    point(driven.AuthoringSpec().sizeDelta, {200, 130});
    point(driven.AuthoringLocalPosition(), {10, -5});
    driven.EndDrive();
    point(driven.spec.sizeDelta, {200, 130});
    point(driven.LocalPosition(), {10, -5});
    driven.spec.parentSize = {400, 200};
    driven.spec.anchorMin = {0, 0};
    driven.spec.anchorMax = {1, 1};
    driven.spec.pivot = {.25f, .75f};
    driven.authoringParentSize = {200, 100};
    driven.drivenParent = true;
    driven.RefreshReference();
    point(driven.LocalPosition(), {-90, 45});
    point(driven.AuthoringLocalPosition(), {-40, 20});
    driven.BeginDrive(7, true);
    driven.spec.anchoredPosition = {45, 30};
    driven.spec.sizeDelta = {70, 20};
    point(driven.AuthoringSpec().sizeDelta, {200, 130});
    point(driven.AuthoringLocalPosition(), {-40, 20});
    driven.EndDrive();
    point(driven.LocalPosition(), {-90, 45});
    std::cout << checks << " canonical rectangle pose checks: " << (good ? "PASS" : "FAIL") << '\n';
    return good ? 0 : 1;
}
