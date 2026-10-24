#!/usr/bin/env python3
"""Add polished AI assistant footer to posts and Stories in bot.py."""
from pathlib import Path
import re
import ast

p = Path("bot.py")
c = p.read_text(encoding="utf-8")
changed = False

# --- 1) format_caption (обычные посты) ---
if "Бот в Telegram: @ASIAMOTORS_ROSTOV" in c:
    c = c.replace("Бот в Telegram: @ASIAMOTORS_ROSTOV", "Бот в Telegram: @AsiaMotorsRostovBot")
    changed = True

if "Подбор авто с ИИ-помощником" not in c or "Бот в Telegram: @AsiaMotorsRostovBot" not in c.split("def story_caption")[0]:
    marker = '    lines.append(f"(до {esc(car.get(\'city\', \'Владивостока\'))})")'
    if marker in c:
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
            '    lines.append("Бот в Telegram: @AsiaMotorsRostovBot")\n'
        )
        pat = re.compile(
            re.escape(marker) + r'.*?(?=    return "\\n"\.join\(lines\))',
            re.DOTALL,
        )
        c2, n = pat.subn(block, c, count=1)
        if n:
            c = c2
            changed = True
            print("OK: post caption footer")
        else:
            print("WARN: post caption replace failed")
    else:
        print("WARN: city line not found for posts")
else:
    print("posts: already polished")

# --- 2) story_caption (сторис в профиле) ---
old_story = '''def story_caption(car, link):
    flag = "🇰🇷" if car.get("market") == "korea" else "🇨🇳"
    return (f"{flag} <b>{esc(car['title'])}</b>\n"
            f"💰 Под ключ до {esc(car.get('city', 'Владивостока'))}: <b>{esc(car['price'])}</b>\n\n"
            f"👉 Подробности и фото в группе: {link}")'''

new_story = '''def story_caption(car, link):
    flag = "🇰🇷" if car.get("market") == "korea" else "🇨🇳"
    return (
        f"{flag} <b>{esc(car['title'])}</b>\n"
        f"💰 Под ключ до {esc(car.get('city', 'Владивостока'))}: <b>{esc(car['price'])}</b>\n\n"
        f"🤖 <b>Подбор авто с ИИ-помощником</b>\n"
        f"Напишите боту параметры или продиктуйте голосом "
        f"(марка, год, пробег, бюджет) — помощник подберёт подходящий вариант.\n"
        f"Бот: @AsiaMotorsRostovBot\n\n"
        f"👉 Подробности и фото в группе: {link}"
    )'''

if "Бот: @AsiaMotorsRostovBot" in c and "def story_caption" in c:
    print("stories: already polished")
elif old_story in c:
    c = c.replace(old_story, new_story)
    changed = True
    print("OK: story_caption updated")
else:
    # fallback: replace return body of story_caption
    pat = re.compile(
        r"def story_caption\(car, link\):\n"
        r"    flag = .*?\n"
        r"    return \(.*?\)",
        re.DOTALL,
    )
    c2, n = pat.subn(new_story, c, count=1)
    if n:
        c = c2
        changed = True
        print("OK: story_caption updated (regex)")
    else:
        print("WARN: story_caption pattern not found")
        i = c.find("def story_caption")
        print(repr(c[i : i + 350]) if i >= 0 else "no story_caption")

if changed:
    p.write_text(c, encoding="utf-8")
    ast.parse(c)
    print("OK saved, size", len(c))
else:
    print("no changes needed")
