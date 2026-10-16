import os
import io
import json
import re
import time
import random
import html as htmllib
import requests
from urllib.parse import urlparse, parse_qs, unquote
from bs4 import BeautifulSoup
from telegram import Bot, InputMediaPhoto, ParseMode
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
POSTED_FILE = "posted_cars.json"
CARS_PER_DAY = 8
MAX_PHOTOS = 10

# --- сторис ---
GROUP_USERNAME = "АЗИЯ_MOTORS"
BRAND = "ASIA MOTORS · РОСТОВ"
STORIES_PER_DAY = 3
BC_PREFIX = "bc:"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Referer": "https://asia-partner.ru/"}


def load_posted():
    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_posted(posted):
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(posted), f, ensure_ascii=False, indent=2)


def get_telegram_posts_via_api():
    """Получает посты, которые публикует другой бот в ваш Telegram-канал через Bot API"""
    if not TELEGRAM_BOT_TOKEN:
        print("ВНИМАНИЕ: TELEGRAM_BOT_TOKEN не задан в секретах GitHub!", flush=True)
        return []

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        r = requests.get(url, timeout=20)
        if not r.ok:
            return []
        data = r.json()
        if not data.get("ok"):
            return []

        updates = data.get("result", [])
        posts = []
        for update in updates:
            msg = update.get("channel_post") or update.get("message")
            if not msg:
                continue
            
            msg_id = msg.get("message_id")
            caption = msg.get("caption") or msg.get("text") or ""
            photo = msg.get("photo")
            media_group_id = msg.get("media_group_id")

            if photo:
                file_id = photo[-1].get("file_id")
                image_url = get_telegram_file_url(file_id)
                if image_url:
                    posts.append({
                        'id': f"tg_{media_group_id or msg_id}",
                        'images': [image_url],
                        'caption': caption,
                        'specs': {},
                        'price': "Уточняйте",
                        'city': "Ростове-на-Дону",
                        'title': caption.split("\n")[0] if caption else "Автомобиль из наличия"
                    })
        return posts
    except Exception as e:
        print(f"Ошибка получения постов из Telegram API: {e}", flush=True)
        return []


def get_telegram_file_url(file_id):
    try:
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}", timeout=15)
        if r.ok:
            file_path = r.json().get("result", {}).get("file_path")
            if file_path:
                return f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    except Exception:
        pass
    return None


def download_image(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.ok and "image" in r.headers.get("Content-Type", ""):
            return r.content
    except Exception:
        pass
    return None


def esc(s):
    return htmllib.escape(str(s), quote=False)


# ======================= СТОРИС (Без кликабельной ссылки, с надписью ASIA MOTORS) =======================

FONT_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
]
FONT_REG = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
]


def load_font(paths, size):
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def fit_cover(img, w, h):
    scale = max(w / img.width, h / img.height)
    nw, nh = int(img.width * scale) + 1, int(img.height * scale) + 1
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def paste_rounded(base, img, xy, radius):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, img.width - 1, img.height - 1], radius=radius, fill=255)
    base.paste(img, xy, mask)


def make_story_image(car):
    """Возвращает jpeg-байты сториса с надписью ASIA MOTORS внизу (без кликабельных ссылок)."""
    imgs = []
    for data in car["photos"][:1]:
        try:
            imgs.append(Image.open(io.BytesIO(data)).convert("RGB"))
        except Exception:
            pass
    if not imgs:
        return None
    hero = imgs[0]

    W, H, M = 1080, 1920, 48
    card_w = W - 2 * M

    bg = fit_cover(hero, W, H).filter(ImageFilter.GaussianBlur(30))
    canvas = ImageEnhance.Brightness(bg).enhance(0.40).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    draw.text((W // 2, 128), BRAND, font=load_font(FONT_BOLD, 32),
              fill=(255, 255, 255), anchor="mm")

    hero_y = 170
    hero_h = 1100
    paste_rounded(canvas, fit_cover(hero, card_w, hero_h), (M, hero_y), 36)

    y = hero_y + hero_h + 60

    # Название авто
    f_title = load_font(FONT_BOLD, 54)
    draw.text((M, y), car["title"][:50], font=f_title, fill=(255, 255, 255))
    y += 100

    # Текстовая плашка внизу вместо ссылки: ASIA MOTORS
    by = y + 20
    btn_h = 110
    draw.rounded_rectangle([M, by, M + card_w, by + btn_h], radius=45, fill=(0, 71, 160))
    draw.text((W // 2, by + btn_h // 2), "ASIA MOTORS · Авто из Кореи и Китая",
              font=load_font(FONT_BOLD, 38), fill=(255, 255, 255), anchor="mm")

    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=90, optimize=True)
    return buf.getvalue()


def tg_call(method, data=None, files=None):
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
                          data=data, files=files, timeout=120)
        return r.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}


def post_story(conn_id, img_bytes, caption):
    base = {
        "business_connection_id": conn_id,
        "content": json.dumps({"type": "photo", "photo": "attach://story_photo"}),
        "active_period": 86400,
        "caption": caption,
        "parse_mode": "HTML",
    }
    res = tg_call("postStory", data=base,
                  files={"story_photo": ("story.jpg", img_bytes, "image/jpeg")})
    if res.get("ok"):
        return True
    print(f"  postStory ошибка: {res.get('description')}", flush=True)
    return False


def find_business_connection():
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
            params={"allowed_updates": json.dumps(["business_connection"]), "timeout": 0},
            timeout=30)
        res = r.json()
        for upd in reversed(res.get("result", [])):
            bc = upd.get("business_connection")
            if bc and bc.get("is_enabled", True) and bc.get("id"):
                return bc["id"]
    except Exception:
        pass
    return None


# ======================= ГЛАВНАЯ ЧАСТЬ =======================

def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("Нет BOT_TOKEN или CHAT_ID", flush=True)
        return

    posted = load_posted()
    print(f"Уже опубликовано: {len(posted)} записей", flush=True)

    # Получаем новые посты из канала, которые опубликовал другой бот
    raw_posts = get_telegram_posts_via_api()
    candidates = []

    for post in raw_posts:
        if post["id"] in posted:
            continue
        # Скачиваем фото
        photos = []
        for img_url in post["images"]:
            data = download_image(img_url)
            if data:
                photos.append(data)
        if photos:
            post["photos"] = photos
            candidates.append(post)

    to_post = candidates[:CARS_PER_DAY]
    print(f"Новых постов от другого бота найдено: {len(to_post)}", flush=True)

    published = []
    for car in to_post:
        try:
            posted.add(car["id"])
            published.append((car, None))
            print(f"Обработан пост: {car['title']}", flush=True)
        except Exception as e:
            print(f"Ошибка обработки поста: {e}", flush=True)

    # ---- публикация сторис (без кликабельных ссылок, только текст) ----
    try:
        conn_id = os.getenv("BUSINESS_CONNECTION_ID")
        if not conn_id:
            stored = [x for x in posted if isinstance(x, str) and x.startswith(BC_PREFIX)]
            if stored:
                conn_id = stored[0][len(BC_PREFIX):]
        if not conn_id:
            conn_id = find_business_connection()
            if conn_id:
                posted.add(BC_PREFIX + conn_id)

        if not conn_id:
            print("Сторис: бот не подключён к бизнес-аккаунту.", flush=True)
        elif not published:
            print("Сторис: нет новых постов для сторис.", flush=True)
        else:
            done = 0
            for car, mid in published:
                if done >= STORIES_PER_DAY:
                    break
                img = make_story_image(car)
                if not img:
                    continue
                caption = f"<b>{esc(car['title'])}</b>\n\nASIA MOTORS"
                if post_story(conn_id, img, caption):
                    done += 1
                    print(f"Сторис опубликована без ссылки: {car['title']}", flush=True)
                time.sleep(3)
            print(f"Сторис выложено: {done}", flush=True)
    except Exception as e:
        print(f"Ошибка сторис: {e}", flush=True)

    save_posted(posted)
    print("Готово!", flush=True)


if __name__ == "__main__":
    main()
