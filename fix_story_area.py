#!/usr/bin/env python3
"""Patch bot.py for current Telegram StoryAreaPosition API."""
from pathlib import Path

p = Path("bot.py")
c = p.read_text(encoding="utf-8")
changed = False

old_pos = (
    '        "rotation_angle": 0.0,\n'
    "    }"
)
new_pos = (
    '        "rotation_angle": 0.0,\n'
    '        "corner_radius_percentage": 5.0,\n'
    "    }"
)
if "corner_radius_percentage" not in c:
    if old_pos not in c:
        raise SystemExit("fix_story_area: position block not found in bot.py")
    c = c.replace(old_pos, new_pos, 1)
    changed = True
    print("OK: corner_radius_percentage added")
else:
    print("OK: corner_radius_percentage already present")

old_tg = (
    "    try:\n"
    '        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",\n'
    "                          data=data, files=files, timeout=60)\n"
    "        return r.json()\n"
)
new_tg = (
    '    timeout = 120 if method == "postStory" else 60\n'
    "    try:\n"
    '        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",\n'
    "                          data=data, files=files, timeout=timeout)\n"
    "        return r.json()\n"
)
if "timeout = 120 if method" not in c:
    if old_tg not in c:
        print("WARN: tg_call timeout pattern not found (skip)")
    else:
        c = c.replace(old_tg, new_tg, 1)
        changed = True
        print("OK: postStory timeout -> 120s")
else:
    print("OK: postStory timeout already 120s")

if changed:
    p.write_text(c, encoding="utf-8")
print("fix_story_area done, size", p.stat().st_size)
