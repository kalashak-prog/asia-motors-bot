#!/usr/bin/env python3
from pathlib import Path
p = Path("bot.py")
c = p.read_text(encoding="utf-8")
old = """    lines.append("")
    lines.append(f"💰 <b>Под ключ: {esc(car['price'])}</b>")
    lines.append(f"(до {esc(car.get('city', 'Владивостока'))})")
    return "\n".join(lines)"""
new = """    lines.append("")
    lines.append(f"💰 <b>Под ключ: {esc(car['price'])}</b>")
    lines.append(f"(до {esc(car.get('city', 'Владивостока'))})")
    lines.append("")
    lines.append("🤖 <b>Подберите авто с ИИ-помощником</b>")
    lines.append(
        "Надиктуйте голосом марку, год, пробег и бюджет — "
        "ИИ-помощник подберёт подходящие варианты."
    )
    lines.append("Бот в Telegram: @ASIAMOTORS_ROSTOV")
    return "\n".join(lines)"""
if old in c:
    c = c.replace(old, new)
    p.write_text(c, encoding="utf-8")
    print("OK: AI footer added")
elif "ИИ-помощником" in c:
    # already patched once — upgrade text if old version without @handle
    if "Бот в Telegram:" not in c:
        c = c.replace(
            "ИИ-помощник Asia Motors найдёт подходящие варианты.",
            "ИИ-помощник подберёт подходящие варианты.\nБот в Telegram: @ASIAMOTORS_ROSTOV",
        )
        p.write_text(c, encoding="utf-8")
        print("OK: AI footer upgraded with bot username")
    else:
        print("already has AI footer with bot username")
else:
    print("FAIL: pattern not found")
    i = c.find("Под ключ")
    print(repr(c[i:i+200]) if i >= 0 else "no match")
