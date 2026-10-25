#!/usr/bin/env python3
"""Fix Telegram Stories only. Yandex Disk logic is left untouched."""
from pathlib import Path
import ast
import re

p = Path("bot.py")
c = p.read_text(encoding="utf-8")
orig = c

# --- make_story_image: return (bytes, position) with corner_radius ---
if "corner_radius_percentage" not in c:
    old = (
        "    buf = io.BytesIO()\n"
        '    canvas.save(buf, "JPEG", quality=90, optimize=True)\n'
        "    return buf.getvalue()\n"
    )
    new = (
        "    position = {\n"
        '        "x_percentage": 50.0,\n'
        '        "y_percentage": round((by + btn_h / 2) / H * 100, 2),\n'
        '        "width_percentage": round(card_w / W * 100, 2),\n'
        '        "height_percentage": round(btn_h / H * 100, 2),\n'
        '        "rotation_angle": 0.0,\n'
        '        "corner_radius_percentage": 5.0,\n'
        "    }\n"
        "    buf = io.BytesIO()\n"
        '    canvas.save(buf, "JPEG", quality=85, optimize=True)\n'
        "    return buf.getvalue(), position\n"
    )
    if old not in c:
        raise SystemExit("make_story return block not found")
    c = c.replace(old, new, 1)
    print("OK: make_story_image + corner_radius")
else:
    print("OK: corner_radius already present")

# --- post_story with 3 attempts ---
m = re.search(r"def post_story\(.*?
(?=def main)", c, re.S)
if not m:
    raise SystemExit("post_story not found")

new_post = '''def post_story(conn_id, img_bytes, caption, area=None):
    content = json.dumps({"type": "photo", "photo": "attach://story_photo"})
    files = {"story_photo": ("story.jpg", img_bytes, "image/jpeg")}
    attempts = []
    if area:
        attempts.append({
            "business_connection_id": conn_id,
            "content": content,
            "active_period": 86400,
            "caption": caption,
            "parse_mode": "HTML",
            "areas": json.dumps([area]),
        })
    attempts.append({
        "business_connection_id": conn_id,
        "content": content,
        "active_period": 86400,
        "caption": caption,
        "parse_mode": "HTML",
    })
    attempts.append({
        "business_connection_id": conn_id,
        "content": content,
        "active_period": 86400,
    })
    for i, data in enumerate(attempts, 1):
        res = tg_call("postStory", data=data, files=files)
        if res.get("ok"):
            print(f"  postStory OK (попытка {i})", flush=True)
            return True
        print(f"  postStory fail (попытка {i}): {res.get('description', res)}", flush=True)
    return False


'''
c = c[: m.start()] + new_post + c[m.end() :]
print("OK: post_story retries")

# --- story loop ---
old_loop = (
    "            done = 0\n"
    "            for car, mid in published:\n"
    "                if done >= STORIES_PER_DAY:\n"
    "                    break\n"
    '                link = f"https://t.me/{GROUP_USERNAME}/{mid}" if mid else f"https://t.me/{GROUP_USERNAME}"\n'
    "                img = make_story_image(car)\n"
    "                if not img:\n"
    "                    continue\n"
    "                if post_story(conn_id, img, story_caption(car, link)):\n"
    "                    done += 1\n"
    '                    print(f"Сторис опубликована: {car[\'title\']}", flush=True)\n'
    "                time.sleep(3)\n"
    '            print(f"Сторис выложено: {done}", flush=True)\n'
)

new_loop = (
    "            done = 0\n"
    "            for car, mid in published:\n"
    "                if done >= STORIES_PER_DAY:\n"
    "                    break\n"
    '                link = f"https://t.me/{GROUP_USERNAME}/{mid}" if mid else f"https://t.me/{GROUP_USERNAME}"\n'
    '                print(f"Сторис: готовлю {car.get(\'title\', \'?")[:50]}…", flush=True)\n'
    "                built = make_story_image(car)\n"
    "                if not built:\n"
    '                    print("  пропуск: нет картинки", flush=True)\n'
    "                    continue\n"
    "                if isinstance(built, tuple):\n"
    "                    img, position = built\n"
    "                else:\n"
    "                    img = built\n"
    "                    position = {\n"
    '                        "x_percentage": 50.0, "y_percentage": 85.0,\n'
    '                        "width_percentage": 90.0, "height_percentage": 6.0,\n'
    '                        "rotation_angle": 0.0, "corner_radius_percentage": 5.0,\n'
    "                    }\n"
    '                area = {"position": position, "type": {"type": "link", "url": link}}\n'
    "                if post_story(conn_id, img, story_caption(car, link), area):\n"
    "                    done += 1\n"
    '                    print(f"Сторис опубликована ({done}/{STORIES_PER_DAY}): {car[\'title\']}", flush=True)\n'
    "                else:\n"
    '                    print(f"  не удалось: {car.get(\'title\', \'?")[:40]}", flush=True)\n'
    "                time.sleep(5)\n"
    '            print(f"Сторис выложено: {done} из {STORIES_PER_DAY}", flush=True)\n'
)

if old_loop not in c:
    raise SystemExit("story loop not found")
c = c.replace(old_loop, new_loop, 1)
print("OK: story loop")

if "timeout=120" not in c:
    c = c.replace("timeout=60)", "timeout=120)", 1)
    print("OK: timeout 120")

ast.parse(c)
if "upload_car_to_yandex" in orig and "upload_car_to_yandex" not in c:
    raise SystemExit("Yandex code was accidentally removed")

p.write_text(c, encoding="utf-8")
print("patched bot.py size", len(c))
