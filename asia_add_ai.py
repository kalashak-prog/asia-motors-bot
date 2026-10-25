#!/usr/bin/env python3
"""Ensure AI assistant footer is present in bot.py captions (idempotent, safe)."""
from pathlib import Path
import ast

p = Path("bot.py")
c = p.read_text(encoding="utf-8")
changed = False

# Normalize old bot username if still present
if "Бот в Telegram: @ASIAMOTORS_ROSTOV" in c:
    c = c.replace("Бот в Telegram: @ASIAMOTORS_ROSTOV", "Бот в Telegram: @AsiaMotorsRostovBot")
    changed = True
    print("OK: renamed @ASIAMOTORS_ROSTOV -> @AsiaMotorsRostovBot")

has_post = "Подбор авто с ИИ-помощником" in c.split("def story_caption")[0]
has_story = "Бот: @AsiaMotorsRostovBot" in c and "def story_caption" in c

if has_post and has_story:
    print("posts: already polished")
    print("stories: already polished")
else:
    # Footers should already be in bot.py; do not attempt fragile regex edits.
    if not has_post:
        print("WARN: post caption AI footer missing — check bot.py format_caption")
    if not has_story:
        print("WARN: story_caption AI footer missing — check bot.py story_caption")

if changed:
    p.write_text(c, encoding="utf-8")

ast.parse(p.read_text(encoding="utf-8"))
print("OK syntax check passed, size", p.stat().st_size)
