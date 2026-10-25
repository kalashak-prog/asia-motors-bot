#!/usr/bin/env python3
"""Fix Telegram Stories: compress image + longer timeout + retries.
Yandex Disk logic is left untouched.
"""
from pathlib import Path
import ast

p = Path("bot.py")
c = p.read_text(encoding="utf-8")
orig = c

# --- tg_call: longer timeout for postStory ---
if 'to = (20, 300) if method == "postStory"' not in c:
    if "timeout=120" in c:
        c = c.replace(
            "data=data, files=files, timeout=120)",
            'data=data, files=files, timeout=((20, 300) if method == "postStory" else 60))',
            1,
        )
        print("OK: tg_call postStory timeout 300s")
    elif "timeout=60)" in c and "def tg_call" in c:
        idx = c.find("def tg_call")
        idx2 = c.find("timeout=", idx)
        if idx2 > 0:
            end = c.find(")", idx2)
            c = c[:idx2] + 'timeout=((20, 300) if method == "postStory" else 60)' + c[end:]
            print("OK: tg_call timeout patched")
        else:
            print("WARN: timeout= not found near tg_call")
    else:
        print("WARN: no known timeout pattern")
else:
    print("OK: postStory timeout already set")

# --- make_story_image compress ---
new_ret = (
    "    position = {\n"
    '        "x_percentage": 50.0,\n'
    '        "y_percentage": round((by + btn_h / 2) / H * 100, 2),\n'
    '        "width_percentage": round(card_w / W * 100, 2),\n'
    '        "height_percentage": round(btn_h / H * 100, 2),\n'
    '        "rotation_angle": 0.0,\n'
    '        "corner_radius_percentage": 5.0,\n'
    "    }\n"
    "    canvas = canvas.resize((1080, 1920), Image.LANCZOS)\n"
    "    data = None\n"
    "    for q in (70, 55, 40, 30):\n"
    "        buf = io.BytesIO()\n"
    '        canvas.save(buf, "JPEG", quality=q, optimize=True)\n'
    "        data = buf.getvalue()\n"
    "        if len(data) <= 900_000:\n"
    "            break\n"
    '    print(f"  story image: {len(data)} bytes", flush=True)\n'
    "    return data, position\n"
)

old_ret = (
    "    buf = io.BytesIO()\n"
    '    canvas.save(buf, "JPEG", quality=90, optimize=True)\n'
    "    return buf.getvalue()\n"
)

if "story image:" not in c:
    if old_ret in c:
        c = c.replace(old_ret, new_ret, 1)
        print("OK: make_story compress + corner_radius")
    elif "corner_radius_percentage" in c:
        start = c.find('    position = {\n        "x_percentage": 50.0')
        end = c.find("def story_caption")
        if start > 0 and end > start:
            c = c[:start] + new_ret + "\n\n\n" + c[end:]
            print("OK: recompress story image")
        else:
            raise SystemExit("cannot find position block to replace")
    else:
        raise SystemExit("make_story return block not found")
else:
    print("OK: story compress already present")

# --- post_story ---
start = c.find("def post_story(")
end = c.find("\ndef main")
if start < 0 or end < 0:
    raise SystemExit("post_story / main markers not found")

new_post = r'''def post_story(conn_id, img_bytes, caption, area=None):
    content = json.dumps({"type": "photo", "photo": "attach://story_photo"})
    attempts = []
    # without area first (more reliable under slow network)
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
    if area:
        attempts.append({
            "business_connection_id": conn_id,
            "content": content,
            "active_period": 86400,
            "caption": caption,
            "parse_mode": "HTML",
            "areas": json.dumps([area]),
        })
    for i, data in enumerate(attempts, 1):
        files = {"story_photo": ("story.jpg", img_bytes, "image/jpeg")}
        res = tg_call("postStory", data=data, files=files)
        if res.get("ok"):
            print(f"  postStory OK (попытка {i})", flush=True)
            return True
        desc = str(res.get("description", res))
        print(f"  postStory fail (попытка {i}): {desc}", flush=True)
        if "ReadTimeout" in desc or "timed out" in desc.lower():
            time.sleep(5)
    return False


'''
c = c[:start] + new_post + c[end + 1:]
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

new_loop = r'''            done = 0
            for car, mid in published:
                if done >= STORIES_PER_DAY:
                    break
                link = f"https://t.me/{GROUP_USERNAME}/{mid}" if mid else f"https://t.me/{GROUP_USERNAME}"
                title_short = (car.get("title") or "?")[:50]
                print(f"Сторис: готовлю {title_short}…", flush=True)
                built = make_story_image(car)
                if not built:
                    print("  пропуск: нет картинки", flush=True)
                    continue
                if isinstance(built, tuple):
                    img, position = built
                else:
                    img = built
                    position = {
                        "x_percentage": 50.0,
                        "y_percentage": 85.0,
                        "width_percentage": 90.0,
                        "height_percentage": 6.0,
                        "rotation_angle": 0.0,
                        "corner_radius_percentage": 5.0,
                    }
                area = {"position": position, "type": {"type": "link", "url": link}}
                if post_story(conn_id, img, story_caption(car, link), area):
                    done += 1
                    print(f"Сторис опубликована ({done}/{STORIES_PER_DAY}): {car['title']}", flush=True)
                else:
                    fail_title = (car.get("title") or "?")[:40]
                    print(f"  не удалось: {fail_title}", flush=True)
                time.sleep(8)
            print(f"Сторис выложено: {done} из {STORIES_PER_DAY}", flush=True)
'''

if old_loop in c:
    c = c.replace(old_loop, new_loop, 1)
    print("OK: story loop")
elif "Сторис: готовлю" in c:
    print("OK: story loop already patched")
else:
    raise SystemExit("story loop not found")

ast.parse(c)
if "upload_car_to_yandex" in orig and "upload_car_to_yandex" not in c:
    raise SystemExit("Yandex code was accidentally removed")

p.write_text(c, encoding="utf-8")
print("patched bot.py size", len(c))
