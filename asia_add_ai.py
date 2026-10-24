#!/usr/bin/env python3
from pathlib import Path
p = Path("bot.py")
c = p.read_text(encoding="utf-8")

FOOTER = '''    lines.append("")
    lines.append(f"💰 <b>Под ключ: {esc(car['price'])}</b>")
    lines.append(f"(до {esc(car.get('city', 'Владивостока'))})")
    lines.append("")
    lines.append("🤖 <b>Подбор авто с ИИ-помощником</b>")
    lines.append(
        "Напишите боту параметры, которые вас интересуют, "
        "или продиктуйте их голосом "
        "(марка, год, пробег, бюджет) — "
        "помощник подберёт подходящий вариант."
    )
    lines.append("Бот в Telegram: @ASIAMOTORS_ROSTOV")
    return "\n".join(lines)'''

old_plain = '''    lines.append("")
    lines.append(f"💰 <b>Под ключ: {esc(car['price'])}</b>")
    lines.append(f"(до {esc(car.get('city', 'Владивостока'))})")
    return "\n".join(lines)'''

if old_plain in c:
    c = c.replace(old_plain, FOOTER)
    p.write_text(c, encoding="utf-8")
    print("OK: AI footer added")
elif "Подбор авто с ИИ-помощником" in c or "ИИ-помощником" in c:
    # replace any previous AI footer block with the polished version
    import re
    c2, n = re.subn(
        r'    lines\.append\(""\)\n'
        r'    lines\.append\("🤖.*\n'
        r'(?:    lines\.append\([^\n]+\)\n)+'
        r'    return "\\n"\.join\(lines\)',
        FOOTER,
        c,
        count=1,
    )
    if n:
        p.write_text(c2, encoding="utf-8")
        print("OK: AI footer replaced with polished text")
    else:
        # fallback: simple string replacements for known old variants
        for old_snip in [
            "Надиктуйте голосом марку, год, пробег и бюджет — ИИ-помощник Asia Motors найдёт подходящие варианты.",
            "Надиктуйте голосом марку, год, пробег и бюджет — ИИ-помощник подберёт подходящие варианты.",
            "Надиктуйте марку, год, пробег и бюджет — бот подберёт варианты.",
        ]:
            if old_snip in c:
                c = c.replace(
                    old_snip,
                    "Напишите боту параметры, которые вас интересуют, или продиктуйте их голосом "
                    "(марка, год, пробег, бюджет) — помощник подберёт подходящий вариант.",
                )
        if "Подберите авто с ИИ-помощником" in c:
            c = c.replace("Подберите авто с ИИ-помощником", "Подбор авто с ИИ-помощником")
        if "Бот в Telegram:" not in c:
            c = c.replace(
                '    return "\n".join(lines)',
                '    lines.append("Бот в Telegram: @ASIAMOTORS_ROSTOV")\n    return "\n".join(lines)',
                1,
            )
        p.write_text(c, encoding="utf-8")
        print("OK: AI footer polished (fallback)")
else:
    print("FAIL: pattern not found")
