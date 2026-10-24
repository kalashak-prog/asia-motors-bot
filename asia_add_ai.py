#!/usr/bin/env python3
"""Add polished AI assistant footer to format_caption in bot.py."""
from pathlib import Path
import re
import ast

p = Path("bot.py")
c = p.read_text(encoding="utf-8")

if "Подбор авто с ИИ-помощником" in c and "Бот в Telegram: @ASIAMOTORS_ROSTOV" in c:
    print("already polished")
    raise SystemExit(0)

marker = '    lines.append(f"(до {esc(car.get(\'city\', \'Владивостока\'))})")'
if marker not in c:
    print("FAIL: city line not found")
    idx = c.find("Владивостока")
    print(repr(c[idx - 80 : idx + 80]) if idx >= 0 else "no city")
    raise SystemExit(1)

block = (
    marker + "\n"
    '    lines.append("")\n'
    '    lines.append("🤖 <b>Подбор авто с ИИ-помощником</b>")\n'
    "    lines.append(\n"
    '        "Напишите боту параметры, которые вас интересуют, "\n'
    '        "или продиктуйте их голосом "\n'
    '        "(марка, год, пробег, бюджет) — "\n'
    '        "помощник подберёт подходящий вариант."\n'
    "    )\n"
    '    lines.append("Бот в Telegram: @ASIAMOTORS_ROSTOV")\n'
)

pat = re.compile(
    re.escape(marker) + r'.*?(?=    return "\\n"\.join\(lines\))',
    re.DOTALL,
)
c2, n = pat.subn(block, c, count=1)
if not n:
    print("FAIL: replace failed")
    raise SystemExit(1)

p.write_text(c2, encoding="utf-8")
ast.parse(c2)
print("OK polished footer, size", len(c2))
