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
        "ИИ-помощник Asia Motors найдёт подходящие варианты."
    )
    return "\n".join(lines)"""
if old in c:
    c = c.replace(old, new)
    p.write_text(c, encoding="utf-8")
    print("OK: AI footer added")
elif "ИИ-помощником" in c:
    print("already has AI footer")
else:
    print("FAIL: pattern not found")
    i = c.find("Под ключ")
    print(repr(c[i:i+200]))
