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
YANDEX_TOKEN = os.getenv("YANDEX_TOKEN", "").strip()          # тот же токен, что и в Instagram-боте
YANDEX_QUEUE_FOLDER = os.getenv("YANDEX_QUEUE_FOLDER", "disk:/instagram_queue")

POSTED_FILE = "posted_cars.json"
CARS_PER_DAY = 5
MAX_PHOTOS = 10
MAX_CHECK = 40

CATALOG_FILTER = "year=2022-&preferential=1"
CITY_BY_MARKET = {"china": "Уссурийска", "korea": "Владивостока"}
KNOWN_CITIES = {
    "уссурийска": "Уссурийска", "уссурийск": "Уссурийска",
    "владивостока": "Владивостока", "владивосток": "Владивостока",
}

GROUP_USERNAME = "ASIAMOTORS_ROSTOV"
BRAND = "ASIA MOTORS · РОСТОВ"
STORIES_PER_DAY = 2
BC_PREFIX = "bc:"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Referer": "https://asia-partner.ru/"}
HEADERS_AUTO = {"User-Agent": UA, "Referer": "https://www.autohome.com.cn/"}
HEADERS_ENCAR = {"User-Agent": UA, "Referer": "https://www.encar.com/"}
HEADERS_NO_REF = {"User-Agent": UA}

LABELS = [
    "Год выпуска", "Пробег", "Объём двигателя", "Мощность",
    "Мощность для растаможки", "Тип топлива", "Коробка передач",
    "Привод", "Цвет", "Класс", "Мест", "Комплектация", "VIN",
]


def load_posted():
    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_posted(posted):
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(posted), f, ensure_ascii=False, indent=2)


def strip_html(html_text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html_text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = htmllib.unescape(text)
    return text.strip()


# ======================= ЯНДЕКС.ДИСК =======================

def yandex_headers():
    return {"Authorization": f"OAuth {YANDEX_TOKEN}"}


def yandex_create_folder(path: str) -> bool:
    """Создаёт папку на Яндекс.Диске (если уже есть — ок)"""
    if not YANDEX_TOKEN:
        return False
    try:
        r = requests.put(
            "https://cloud-api.yandex.net/v1/disk/resources",
            params={"path": path},
            headers=yandex_headers(),
            timeout=30
        )
        # 201 = создана, 409 = уже существует
        return r.status_code in (201, 409)
    except Exception as e:
        print(f"  Ошибка создания папки {path}: {e}", flush=True)
        return False


def yandex_upload_bytes(data: bytes, remote_path: str) -> bool:
    """Загружает байты на Яндекс.Диск"""
    if not YANDEX_TOKEN:
        return False
    try:
        # Получаем URL для загрузки
        r = requests.get(
            "https://cloud-api.yandex.net/v1/disk/resources/upload",
            params={"path": remote_path, "overwrite": "true"},
            headers=yandex_headers(),
            timeout=30
        )
        if not r.ok:
            print(f"  Не удалось получить URL загрузки: {r.text}", flush=True)
            return False
        upload_url = r.json().get("href")
        if not upload_url:
            return False

        # Загружаем
        res = requests.put(upload_url, data=data, timeout=120)
        return res.status_code in (201, 202)
    except Exception as e:
        print(f"  Ошибка загрузки на Яндекс {remote_path}: {e}", flush=True)
        return False


def upload_car_to_yandex_queue(car: dict, plain_caption: str) -> bool:
    """
    Загружает машину в очередь Instagram на Яндекс.Диск.
    Структура:
      disk:/instagram_queue/{car_id}/
        meta.json
        0.jpg
        1.jpg
        ...
    """
    if not YANDEX_TOKEN:
        print("  YANDEX_TOKEN не задан — пропускаю очередь Instagram", flush=True)
        return False

    car_id = str(car["id"])
    folder = f"{YANDEX_QUEUE_FOLDER.rstrip('/')}/{car_id}"

    # Создаём корневую папку очереди и папку машины
    yandex_create_folder(YANDEX_QUEUE_FOLDER)
    yandex_create_folder(folder)

    # Загружаем фото
    photo_names = []
    for i, data in enumerate(car["photos"]):
        name = f"{i}.jpg"
        remote = f"{folder}/{name}"
        if yandex_upload_bytes(data, remote):
            photo_names.append(name)
            print(f"  загружено фото {name}", flush=True)
        else:
            print(f"  не удалось загрузить фото {name}", flush=True)

    if not photo_names:
        print("  Нет загруженных фото — пропускаю", flush=True)
        return False

    # meta.json
    meta = {
        "id": car_id,
        "title": car.get("title", ""),
        "caption": plain_caption,
        "photos": photo_names,
        "market": car.get("market", ""),
        "price": car.get("price", ""),
    }
    meta_bytes = json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8")
    if yandex_upload_bytes(meta_bytes, f"{folder}/meta.json"):
        print(f"  ✅ Машина {car_id} добавлена в очередь Instagram на Яндекс.Диск", flush=True)
        return True
    else:
        print(f"  Не удалось загрузить meta.json для {car_id}", flush=True)
        return False


# ======================= ПАРСИНГ =======================

def fetch_links(url, market):
    r = requests.get(url, headers=HEADERS, timeout=20)
    found = re.findall(rf'cars/{market}/[a-z0-9\-]+-\d+', r.text)
    return list(dict.fromkeys("https://asia-partner.ru/" + f for f in found))


def get_car_links(market="china", pages=3):
    links = []
    base = f"https://asia-partner.ru/catalog/{market}"
    use_filter = True
    for page in range(1, pages + 1):
        if use_filter:
            url = f"{base}?{CATALOG_FILTER}" + ("" if page == 1 else f"&page={page}")
        else:
            url = base if page == 1 else f"{base}?page={page}"
        try:
            found = fetch_links(url, market)
            if page == 1 and use_filter and not found:
                print(f"  фильтр не сработал для {market}, беру каталог без фильтра", flush=True)
                use_filter = False
                found = fetch_links(base, market)
            new = [l for l in found if l not in links]
            print(f"  {market} стр {page}: найдено {len(found)}, новых {len(new)}", flush=True)
            links += new
            if not new:
                break
            time.sleep(1)
        except Exception as e:
            print(f"Ошибка списка {market} стр {page}: {e}", flush=True)
    print(f"Ссылок {market}: {len(links)} ({'с фильтром' if use_filter else 'без фильтра'})", flush=True)
    return links


def unwrap(u):
    if "/img?" in u and "src=" in u:
        try:
            q = parse_qs(urlparse(u).query)
            if q.get("src"):
                return unquote(q["src"][0])
        except Exception:
            pass
    return u


def photo_key(u):
    orig = unwrap(u)
    name = orig.split("?")[0].split("/")[-1]
    return re.sub(r"^\d+x\d+_", "", name)


def extract_photos(soup, html):
    urls = []
    for img in soup.find_all("img"):
        for attr in ("src", "data-src", "data-lazy-src", "data-original"):
            v = img.get(attr)
            if v:
                urls.append(v)
        ss = img.get("srcset")
        if ss:
            urls += [p.strip().split(" ")[0] for p in ss.split(",") if p.strip()]
    for m in soup.find_all("meta", attrs={"property": "og:image"}):
        if m.get("content"):
            urls.append(m["content"])
    urls += re.findall(r'(?:https?:)?\\?/\\?/[^"\'\s)<>]+?\.(?:jpg|jpeg|png|webp)[^"\'\s)<>]*', html)
    urls += re.findall(r'/img\?src=[^"\'\s)<>]+', html)

    clean = []
    for u in urls:
        u = u.replace("\\/", "/").replace("&", "&").replace("\\u0026", "&")
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("/"):
            u = "https://asia-partner.ru" + u
        if not u.startswith("http"):
            continue
        clean.append(u)

    bad = ("logo", "icon", "avatar", "sprite", ".svg", "banner", "favicon", "wt_mark")
    result, seen = [], set()
    for u in clean:
        orig = unwrap(u).lower()
        if any(b in orig.split("?")[0] for b in bad):
            continue
        if not re.search(r"\.(jpg|jpeg|png|webp)", orig):
            continue
        k = photo_key(u)
        if k in seen:
            continue
        seen.add(k)
        result.append(u)

    pref = [u for u in result if any(d in unwrap(u) for d in ("autoimg", "carpicture", "encar", "che168", "dongchedi"))]
    return pref if pref else result


def candidates_for(u):
    orig = unwrap(u)
    cands = []
    if orig != u:
        big = re.sub(r"/\d+x\d+_", "/960x720_", orig)
        for x in (big, orig):
            if x.endswith(".webp"):
                cands.append(x[:-5])
            cands.append(x)
    elif "carpicture" in u:
        cands.append(re.sub(r"impolicy=[^&]+", "impolicy=heightRate&rh=720&cw=960&ch=720", u))
    cands.append(u)
    out = []
    for c in cands:
        if c not in out:
            out.append(c)
    return out


def headers_for(cand):
    if "autoimg" in cand or "autohome" in cand:
        return (HEADERS_AUTO, HEADERS_NO_REF)
    if "encar.com" in cand:
        return (HEADERS_ENCAR, HEADERS_NO_REF)
    return (HEADERS, HEADERS_NO_REF)


def download_image(u):
    for cand in candidates_for(u):
        for hdrs in headers_for(cand):
            try:
                r = requests.get(cand, headers=hdrs, timeout=20)
                ctype = r.headers.get("Content-Type", "")
                print(f"  фото {r.status_code} {ctype} {len(r.content)} байт: {cand[:100]}", flush=True)
                if r.ok and "image" in ctype and len(r.content) > 5000:
                    return r.content
            except Exception as e:
                print(f"  ошибка фото: {e}", flush=True)
    return None


def parse_specs(text):
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    start = 0
    for i, l in enumerate(lines):
        if l == "Год выпуска":
            start = i
            break
    specs = {}
    i = start
    while i < len(lines) - 1:
        if lines[i] in LABELS and lines[i] not in specs and lines[i + 1] not in LABELS:
            specs[lines[i]] = lines[i + 1]
            i += 2
        else:
            i += 1
    return specs


def detect_city(text, market):
    m = re.search(r"под\s*ключ\s*до\s+([А-Яа-яЁё]+)", text, re.IGNORECASE)
    if m:
        city = KNOWN_CITIES.get(m.group(1).lower())
        if city:
            return city
    return CITY_BY_MARKET.get(market, "Владивостока")


def parse_car(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        soup = BeautifulSoup(r.text, "lxml")
        text = soup.get_text("\n", strip=True)

        car_id = url.rstrip("/").split("-")[-1]
        market = "korea" if "/cars/korea/" in url else "china"

        title = ""
        h1 = soup.find("h1")
        if h1:
            title = re.sub(r"\s+", " ", h1.get_text(" ", strip=True)).strip()

        price = ""
        price_match = re.search(r"(\d[\d\s]{4,})\s*₽", text)
        if price_match:
            digits = re.sub(r"\D", "", price_match.group(1))
            if digits:
                price = f"{int(digits):,}".replace(",", " ") + " ₽"

        city = detect_city(text, market)
        specs = parse_specs(text)

        if "Год выпуска" not in specs:
            m = re.search(r"(?:Год выпуска|Октябрь|Январь|Февраль|Март|Апрель|Май|Июнь|Июль|Август|Сентябрь|Ноябрь|Декабрь)\s*(\d{4})", text)
            if m:
                specs["Год выпуска"] = m.group(1)
        if "Пробег" not in specs:
            m = re.search(r"([\d\s]+)\s*км", text)
            if m:
                specs["Пробег"] = m.group(1).strip() + " км"
        if "Мощность" not in specs:
            m = re.search(r"(\d+)\s*л\.?\s*с", text)
            if m:
                specs["Мощность"] = m.group(1) + " л.с."
        if "Объём двигателя" not in specs:
            m = re.search(r"([\d\s]+)\s*см³", text)
            if m:
                specs["Объём двигателя"] = m.group(1).strip() + " см³"

        year = None
        ym = re.search(r"(\d{4})", specs.get("Год выпуска", ""))
        if ym:
            year = int(ym.group(1))

        hp = None
        hm = re.search(r"(\d+)", specs.get("Мощность", ""))
        if hm:
            hp = int(hm.group(1))

        # Пробег в километрах
        mileage = None
        mileage_str = specs.get("Пробег", "")
        mm = re.search(r"([\d\s]+)", mileage_str.replace(" ", " "))
        if mm:
            try:
                mileage = int(re.sub(r"\D", "", mm.group(1)))
            except Exception:
                mileage = None

        photo_urls = extract_photos(soup, r.text)
        print(f"{url[:80]}", flush=True)
        print(f"  название: {title[:40]!r}, цена: {price!r}, до {city}, год: {year}, пробег: {mileage}, характеристик: {len(specs)}", flush=True)
        print(f"  найдено фото: {len(photo_urls)}", flush=True)

        if year and year < 2021:
            print("  пропуск: старше 2021", flush=True)
            return None
        if mileage is not None and mileage > 80000:
            print(f"  пропуск: пробег {mileage} км > 80 000", flush=True)
            return None
        if not title or not price:
            print("  пропуск: нет названия или цены", flush=True)
            return None

        photos = []
        failed = 0
        for pu in photo_urls:
            data = download_image(pu)
            if data:
                photos.append(data)
            else:
                failed += 1
            if len(photos) >= MAX_PHOTOS:
                break
            if not photos and failed >= 3:
                break
        print(f"  скачано фото: {len(photos)}", flush=True)
        if not photos:
            return None

        return {
            "id": car_id, "url": url, "market": market, "title": title,
            "year": year, "hp": hp, "specs": specs, "price": price,
            "city": city, "photos": photos,
            "is_prefer": hp is not None and hp <= 160,
        }
    except Exception as e:
        print(f"Ошибка парсинга {url}: {e}", flush=True)
        return None


def esc(s):
    return htmllib.escape(str(s), quote=False)


def format_caption(car, full=True):
    s = car["specs"]
    flag = "🇰🇷" if car.get("market") == "korea" else "🇨🇳"
    lines = [f"{flag} <b>{esc(car['title'])}</b>"]

    summary = [s.get("Год выпуска"), s.get("Пробег"), s.get("Мощность")]
    summary = [x for x in summary if x]
    if summary:
        lines.append(esc(" · ".join(summary)))

    lines.append("")
    lines.append("<b>Характеристики</b>")

    def add(icon, label, key):
        if s.get(key):
            lines.append(f"{icon} {label}: {esc(s[key])}")

    add("📅", "Год выпуска", "Год выпуска")
    add("🛣", "Пробег", "Пробег")
    add("⚙️", "Объём двигателя", "Объём двигателя")
    add("🐎", "Мощность", "Мощность")
    add("📋", "Для растаможки", "Мощность для растаможки")
    add("⛽", "Топливо", "Тип топлива")
    add("🔧", "КПП", "Коробка передач")
    add("🚙", "Привод", "Привод")
    add("🎨", "Цвет", "Цвет")

    cls = " · ".join(
        x for x in [s.get("Класс"), (s.get("Мест") + " мест") if s.get("Мест") else None] if x
    )
    if cls:
        lines.append(f"🚘 Класс: {esc(cls)}")

    if full:
        add("🏷", "Комплектация", "Комплектация")
        add("🔑", "VIN", "VIN")

    lines.append("")
    lines.append(f"💰 <b>Под ключ: {esc(car['price'])}</b>")
    lines.append(f"(до {esc(car.get('city', 'Владивостока'))})")
    return "\n".join(lines)


def build_caption(car):
    cap = format_caption(car, full=True)
    if len(cap) > 1000:
        cap = format_caption(car, full=False)
    return cap[:1024]


# ======================= СТОРИС =======================

FONT_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]
FONT_REG = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]

_font_warned = False

def load_font(candidates, size):
    global _font_warned
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    if not _font_warned:
        print("  шрифт не найден, текст может быть кривым", flush=True)
        _font_warned = True
    try:
        return ImageFont.load_default(size)
    except Exception:
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


def wrap_text(draw, text, font, max_w, max_lines):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_w:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines


def make_story_image(car):
    imgs = []
    for data in car["photos"][:3]:
        try:
            imgs.append(Image.open(io.BytesIO(data)).convert("RGB"))
        except Exception:
            pass
    if not imgs:
        return None
    hero, extra = imgs[0], imgs[1:3]

    W, H, M = 1080, 1920, 48
    card_w = W - 2 * M

    bg = fit_cover(hero, W, H).filter(ImageFilter.GaussianBlur(30))
    canvas = ImageEnhance.Brightness(bg).enhance(0.40).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    draw.text((W // 2, 128), BRAND, font=load_font(FONT_BOLD, 32),
              fill=(255, 255, 255), anchor="mm")

    hero_y = 170
    hero_h = 738 if extra else 1080
    paste_rounded(canvas, fit_cover(hero, card_w, hero_h), (M, hero_y), 36)

    is_korea = car.get("market") == "korea"
    label = "КОРЕЯ" if is_korea else "КИТАЙ"
    color = (0, 71, 160) if is_korea else (215, 38, 24)
    f_pill = load_font(FONT_BOLD, 34)
    tw = draw.textlength(label, font=f_pill)
    px, py = M + 24, hero_y + 24
    draw.rounded_rectangle([px, py, px + tw + 48, py + 64], radius=32, fill=color)
    draw.text((px + 24 + tw / 2, py + 32), label, font=f_pill,
              fill=(255, 255, 255), anchor="mm")

    y = hero_y + hero_h + 28

    if extra:
        th = 260
        if len(extra) == 1:
            paste_rounded(canvas, fit_cover(extra[0], card_w, th), (M, y), 28)
        else:
            tw2 = (card_w - 24) // 2
            for i, im in enumerate(extra):
                paste_rounded(canvas, fit_cover(im, tw2, th), (M + i * (tw2 + 24), y), 28)
        y += th + 28

    f_title = load_font(FONT_BOLD, 64)
    for line in wrap_text(draw, car["title"], f_title, card_w, 2):
        draw.text((M, y), line, font=f_title, fill=(255, 255, 255))
        y += 76

    s = car["specs"]
    spec_line = " · ".join(x for x in [s.get("Год выпуска"), s.get("Пробег"), s.get("Мощность")] if x)
    if spec_line:
        draw.text((M, y + 2), spec_line, font=load_font(FONT_REG, 38), fill=(225, 225, 225))
        y += 60

    y += 10
    city_up = car.get("city", "Владивостока").upper()
    draw.text((M, y), f"ПОД КЛЮЧ ДО {city_up}", font=load_font(FONT_BOLD, 28), fill=(255, 196, 61))
    y += 40
    size = 90
    f_price = load_font(FONT_BOLD, size)
    while draw.textlength(car["price"], font=f_price) > card_w and size > 50:
        size -= 6
        f_price = load_font(FONT_BOLD, size)
    draw.text((M, y), car["price"], font=f_price, fill=(255, 255, 255))
    y += 104

    btn_h = 90
    by = y + 16
    draw.rounded_rectangle([M, by, M + card_w, by + btn_h], radius=45, fill=(255, 255, 255))
    draw.text((W // 2, by + btn_h // 2), "Смотреть в группе  →",
              font=load_font(FONT_BOLD, 40), fill=(20, 20, 20), anchor="mm")

    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=90, optimize=True)
    return buf.getvalue()


def story_caption(car, link):
    flag = "🇰🇷" if car.get("market") == "korea" else "🇨🇳"
    return (f"{flag} <b>{esc(car['title'])}</b>\n"
            f"💰 Под ключ до {esc(car.get('city', 'Владивостока'))}: <b>{esc(car['price'])}</b>\n\n"
            f"👉 Подробности и фото в группе: {link}")


def tg_call(method, data=None, files=None):
    try:
        # Story uploads can take longer than ordinary Bot API requests.
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
                          data=data, files=files, timeout=120)
        try:
            result = r.json()
        except Exception:
            result = {"ok": False, "description": f"HTTP {r.status_code}: {r.text[:500]}"}
        if not result.get("ok"):
            print(f"  Telegram API {method}: HTTP {r.status_code}; {result}", flush=True)
        return result
    except Exception as e:
        print(f"tg_call {method}: {type(e).__name__}: {e}", flush=True)
        return {"ok": False, "description": f"{type(e).__name__}: {e}"}


def find_business_connection():
    # Telegram Bot API requires a specific business_connection_id for getBusinessConnection.
    # The ID is normally saved from an incoming business_connection update or supplied as a secret.
    configured = os.getenv("BUSINESS_CONNECTION_ID", "").strip()
    if configured:
        return configured
    return None


def post_story(conn_id, img_bytes, caption):
    base = {
        "business_connection_id": conn_id,
        "content": json.dumps({"type": "photo", "photo": "attach://story_photo"}),
        "active_period": 86400,
        "caption": caption,
        "parse_mode": "HTML",
    }

    # Публикуем сторис только с фотографией и подписью.
    # Никаких clickable areas / areas поверх изображения не добавляем.
    res = tg_call("postStory", data=base,
                  files={"story_photo": ("story.jpg", img_bytes, "image/jpeg")})
    if res.get("ok"):
        print("  Telegram Story: успешно опубликована без кликабельной области", flush=True)
        return True
    print(f"  Telegram Story: попытка с подписью не удалась: {res.get('description', res)}", flush=True)
    # Final compatibility attempt: omit caption/parse_mode in case the API rejects caption metadata.
    minimal = {
        "business_connection_id": conn_id,
        "content": json.dumps({"type": "photo", "photo": "attach://story_photo"}),
        "active_period": 86400,
    }
    res = tg_call("postStory", data=minimal,
                  files={"story_photo": ("story.jpg", img_bytes, "image/jpeg")})
    if res.get("ok"):
        print("  Telegram Story: опубликована без подписи (резервная попытка)", flush=True)
        return True
    print(f"  Telegram Story: все попытки не удались: {res.get('description', res)}", flush=True)
    return False


def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("Нет BOT_TOKEN или CHAT_ID", flush=True)
        return

    bot = Bot(token=BOT_TOKEN)
    posted = load_posted()
    print(f"Уже опубликовано: {len(posted)} записей", flush=True)

    all_links = get_car_links("china", pages=4) + get_car_links("korea", pages=2)
    random.shuffle(all_links)

    candidates = []
    checked = 0
    for link in all_links:
        car_id = link.rstrip("/").split("-")[-1]
        if car_id in posted:
            continue
        if checked >= MAX_CHECK:
            break
        checked += 1
        car = parse_car(link)
        if car:
            candidates.append(car)
            if len(candidates) >= CARS_PER_DAY * 2:
                break
        time.sleep(1.5)

    # Избегаем двух машин одной марки подряд
    def get_brand(car):
        title = (car.get("title") or "").strip()
        if not title:
            return ""
        # Берём первое слово (обычно марка: Toyota, Hyundai, Geely...)
        brand = title.split()[0].upper()
        # Убираем лишние символы
        brand = re.sub(r"[^A-ZА-ЯЁ0-9]", "", brand)
        return brand

    candidates.sort(key=lambda x: (not x["is_prefer"], random.random()))

    to_post = []
    used_brands = set()
    for car in candidates:
        brand = get_brand(car)
        if brand and brand in used_brands:
            continue
        to_post.append(car)
        if brand:
            used_brands.add(brand)
        if len(to_post) >= CARS_PER_DAY:
            break

    # Если не набрали достаточно из-за фильтра марок — добираем оставшимися
    if len(to_post) < CARS_PER_DAY:
        for car in candidates:
            if car not in to_post:
                to_post.append(car)
                if len(to_post) >= CARS_PER_DAY:
                    break

    print(f"Проверено: {checked}, годных: {len(candidates)}, публикуем: {len(to_post)} (без повторов марок)", flush=True)

    published = []
    for car in to_post:
        try:
            caption_html = build_caption(car)
            media = []
            for i, data in enumerate(car["photos"]):
                bio = io.BytesIO(data)
                bio.name = f"photo{i}.jpg"
                if i == 0:
                    media.append(InputMediaPhoto(bio, caption=caption_html, parse_mode=ParseMode.HTML))
                else:
                    media.append(InputMediaPhoto(bio))
            msgs = bot.send_media_group(chat_id=CHAT_ID, media=media, timeout=120)
            mid = msgs[0].message_id if msgs else None
            posted.add(car["id"])
            published.append((car, mid))
            print(f"Опубликовано: {car['title']} (сообщение {mid})", flush=True)

            # ========== ЗАГРУЖАЕМ В ОЧЕРЕДЬ INSTAGRAM НА ЯНДЕКС ==========
            try:
                plain_caption = strip_html(caption_html)
                upload_car_to_yandex_queue(car, plain_caption)
            except Exception as e:
                print(f"  Ошибка загрузки в очередь Instagram: {e}", flush=True)
            # ============================================================

            time.sleep(3)
        except Exception as e:
            print(f"Ошибка публикации {car['title']}: {e}", flush=True)

    # ---- сторис ----
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
            print("Сторис: бот не подключён к бизнес-аккаунту (Настройки → Telegram для бизнеса → Чат-боты).", flush=True)
        elif not published:
            print("Сторис: нет новых машин для сторис.", flush=True)
        else:
            done = 0
            for car, mid in published:
                if done >= STORIES_PER_DAY:
                    break
                link = f"https://t.me/{GROUP_USERNAME}/{mid}" if mid else f"https://t.me/{GROUP_USERNAME}"
                img = make_story_image(car)
                if not img:
                    continue
                if post_story(conn_id, img, story_caption(car, link))
                    done += 1
                    print(f"Сторис опубликована: {car['title']}", flush=True)
                time.sleep(3)
            print(f"Сторис выложено: {done}", flush=True)
    except Exception as e:
        print(f"Ошибка сторис: {e}", flush=True)

    save_posted(posted)
    print("Готово!", flush=True)


if __name__ == "__main__":
    main()
