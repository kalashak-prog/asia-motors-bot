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
YANDEX_TOKEN = os.getenv("YANDEX_TOKEN", "").strip()
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
    if not YANDEX_TOKEN:
        return False
    try:
        r = requests.put(
            "https://cloud-api.yandex.net/v1/disk/resources",
            params={"path": path},
            headers=yandex_headers(),
            timeout=30
        )
        return r.status_code in (201, 409)
    except Exception as e:
        print(f"  Ошибка создания папки {path}: {e}", flush=True)
        return False


def yandex_upload_bytes(data: bytes, remote_path: str) -> bool:
    if not YANDEX_TOKEN:
        return False
    try:
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
        res = requests.put(upload_url, data=data, timeout=120)
        return res.status_code in (201, 202)
    except Exception as e:
        print(f"  Ошибка загрузки на Яндекс {remote_path}: {e}", flush=True)
        return False


def upload_car_to_yandex_queue(car: dict, plain_caption: str) -> bool:
    if not YANDEX_TOKEN:
        print("  YANDEX_TOKEN не задан — пропускаю очередь Instagram", flush=True)
        return False

    car_id = str(car["id"])
    folder = f"{YANDEX_QUEUE_FOLDER.rstrip('/')}/{car_id}"

    yandex_create_folder(YANDEX_QUEUE_FOLDER)
    yandex_create_folder(folder)

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

        mileage = None
        mileage_str = specs.get("Пробег", "")
        mm = re.search(r"([\d\s]+)", mileage_str.replace("\u00a0", " "))
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


AI_FOOTER = (
    "\n\n🤖 <b>Подбор авто с ИИ-помощником</b>\n"
    "Напишите боту параметры, которые вас интересуют, или продиктуйте их голосом "
    "(марка, год, пробег, бюджет) — помощник подберёт подходящий вариант.\n"
    "Бот в Telegram: @AsiaMotorsRostovBot"
)

def build_caption(car):
    return format_caption(car, full=True)

def build_caption_tg(car):
    return format_caption(car, full=True) + AI_FOOTER


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

    def get_brand(car):
        title = (car.get("title") or "").strip()
        if not title:
            return ""
        brand = title.split()[0].upper()
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
            caption_tg = build_caption_tg(car)
            media = []
            for i, data in enumerate(car["photos"]):
                bio = io.BytesIO(data)
                bio.name = f"photo{i}.jpg"
                if i == 0:
                    media.append(InputMediaPhoto(bio, caption=caption_tg, parse_mode=ParseMode.HTML))
                else:
                    media.append(InputMediaPhoto(bio))
            msgs = bot.send_media_group(chat_id=CHAT_ID, media=media, timeout=120)
            mid = msgs[0].message_id if msgs else None
            posted.add(car["id"])
            published.append((car, mid))
            print(f"Опубликовано: {car['title']} (сообщение {mid})", flush=True)

            try:
                plain_caption = strip_html(caption_html)
                upload_car_to_yandex_queue(car, plain_caption)
            except Exception as e:
                print(f"  Ошибка загрузки в очередь Instagram: {e}", flush=True)

            time.sleep(3)
        except Exception as e:
            print(f"Ошибка публикации {car.get('title')}: {e}", flush=True)

    save_posted(posted)
    print("Готово!", flush=True)


if __name__ == "__main__":
    main()
