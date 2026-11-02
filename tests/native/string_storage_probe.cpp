#include "infernux/core/math/StringTween.h"
#include <iostream>

int main()
{
    using namespace infernux::tween;
    const StringSnapshot text(u"<b>12345678</b>", u"<i>abcdef</i>");
    if (text.StartLength(true) != 8 || text.Length(true) != 6) return 1;
    const auto reset = text.Bind(EaseKernel(1), 1, true, false, 0, nullptr, 0, 0);
    if (!reset.Sample(.5, 0).empty()) return 2;
    const auto first = std::make_shared<StringAlphabet>(u"XX", false);
    const auto second = std::make_shared<StringAlphabet>(u"YY", false);
    const StringSnapshot plain(u"", u"abcd");
    const auto oldPlan = plain.Bind(EaseKernel(1), 1, false, false, 5, first);
    const auto newPlan = plain.Bind(EaseKernel(1), 1, false, false, 5, second);
    if (oldPlan.Sample(.5, 0) != u"abXX" || newPlan.Sample(.5, 0) != u"abYY") return 3;
    if (oldPlan.Sample(.5, 0) != u"abXX") return 4;
    const StringSnapshot unicode(u"", u"\U0001f341AB");
    if (unicode.Length(false) != 4 || unicode.Bind(EaseKernel(1), 1, false, false, 0, nullptr).Sample(.5, 0) != u"\U0001f341") return 5;
    std::cout << "STRING_STORAGE cache/immutable-alphabets/utf16 PASS\n";
}
