import os
import io
import json
import re
import time
import random
import requests
from bs4 import BeautifulSoup
from telegram import Bot, InputMediaPhoto, ParseMode

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
POSTED_FILE = "posted_cars.json"
CARS_PER_DAY = 8
MAX_PHOTOS = 10

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://asia-partner.ru/",
}

def load_posted():
    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_posted(posted):
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(posted), f, ensure_ascii=False, indent=2)

def get_car_links(market="china", pages=3):
    links = []
    base = f"https://asia-partner.ru/catalog/{market}"
    for page in range(1, pages + 1):
        url = base if page == 1 else f"{base}?page={page}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            found = re.findall(rf'cars/{market}/[a-z0-9\-]+-\d+', r.text)
            for f in found:
                full = "https://asia-partner.ru/" + f
                if full not in links:
                    links.append(full)
            time.sleep(1)
        except Exception as e:
            print(f"Ошибка списка {market} стр {page}: {e}", flush=True)
    return links

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
    urls += re.findall(r'https?://[^"\'\s)\\]+carpicture[^"\'\s)\\]+', html)

    clean = []
    for u in urls:
        u = u.replace("&amp;", "&")
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("/"):
            u = "https://asia-partner.ru" + u
        if not u.startswith("http"):
            continue
        if u not in clean:
            clean.append(u)

    car_pics = [u for u in clean if "carpicture" in u]
    if car_pics:
        result = []
        for u in car_pics:
            u = re.sub(r"impolicy=[^&]+", "impolicy=heightRate&rh=720&cw=960&ch=720", u)
            if u not in result:
                result.append(u)
        return result

    bad = ("logo", "icon", "avatar", "sprite", ".svg", "banner")
    return [u for u in clean
            if re.search(r"\.(jpg|jpeg|png|webp)", u.lower())
            and not any(b in u.lower() for b in bad)]

def download_image(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        ctype = r.headers.get("Content-Type", "")
        if r.ok and "image" in ctype and len(r.content) > 5000:
            return r.content
    except Exception:
        pass
    return None

def parse_car(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        soup = BeautifulSoup(r.text, "lxml")
        text = soup.get_text("\n", strip=True)

        car_id = url.rstrip("/").split("-")[-1]

        title = ""
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

        price = ""
        price_match = re.search(r"(\d[\d\s]{4,})\s*₽", text)
        if price_match:
            price = price_match.group(1).replace(" ", "") + " ₽"

        year = None
        year_match = re.search(r"(?:Год выпуска|Октябрь|Январь|Февраль|Март|Апрель|Май|Июнь|Июль|Август|Сентябрь|Ноябрь|Декабрь)\s*(\d{4})", text)
        if year_match:
            year = int(year_match.group(1))
        else:
            year_match2 = re.search(r"(\d{4})\s*год", text)
            if year_match2:
                year = int(year_match2.group(1))

        mileage = ""
        mile_match = re.search(r"([\d\s]+)\s*км", text)
        if mile_match:
            mileage = mile_match.group(1).strip() + " км"

        hp = None
        hp_match = re.search(r"(\d+)\s*л\.?\s*с", text)
        if hp_match:
            hp = int(hp_match.group(1))

        engine = ""
        eng_match = re.search(r"([\d\s]+)\s*см³", text)
        if eng_match:
            engine = eng_match.group(1).strip() + " см³"

        fuel = ""
        for f in ["Бензин", "Дизель", "Гибрид", "Электро"]:
            if f in text:
                fuel = f
                break

        transmission = ""
        for t in ["Автомат", "Механика", "Вариатор", "Робот"]:
            if t in text:
                transmission = t
                break

        photo_urls = extract_photos(soup, r.text)
        print(f"{url}: найдено ссылок на фото: {len(photo_urls)}", flush=True)

        if year and year < 2021:
            return None
        if not title or not price:
            return None

        photos = []
        for pu in photo_urls:
            data = download_image(pu)
            if data:
                photos.append(data)
            if len(photos) >= MAX_PHOTOS:
                break
        print(f"  скачано фото: {len(photos)}", flush=True)
        if not photos:
            return None

        return {
            "id": car_id, "url": url, "title": title, "year": year,
            "mileage": mileage, "hp": hp, "engine": engine, "fuel": fuel,
            "transmission": transmission, "price": price, "photos": photos,
            "is_prefer": hp is not None and hp <= 160,
        }
    except Exception as e:
        print(f"Ошибка парсинга {url}: {e}", flush=True)
        return None

def format_caption(car):
    lines = [f"<b>{car['title']}</b>", ""]
    if car.get("year"):
        lines.append(f"📅 {car['year']} год")
    if car.get("mileage"):
        lines.append(f"🛣 {car['mileage']}")
    specs = []
    if car.get("engine"):
        specs.append(car["engine"])
    if car.get("hp"):
        specs.append(f"{car['hp']} л.с.")
    if car.get("fuel"):
        specs.append(car["fuel"])
    if car.get("transmission"):
        specs.append(car["transmission"])
    if specs:
        lines.append("⚙️ " + " · ".join(specs))
    lines.append("")
    lines.append(f"💰 <b>Под ключ: {car['price']}</b>")
    lines.append("(до Владивостока)")
    return "\n".join(lines)

def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("Нет BOT_TOKEN или CHAT_ID", flush=True)
        return

    bot = Bot(token=BOT_TOKEN)
    posted = load_posted()
    print(f"Уже опубликовано: {len(posted)} машин", flush=True)

    all_links = get_car_links("china", pages=4) + get_car_links("korea", pages=2)
    random.shuffle(all_links)

    candidates = []
    for link in all_links:
        car_id = link.rstrip("/").split("-")[-1]
        if car_id in posted:
            continue
        car = parse_car(link)
        if car:
            candidates.append(car)
            if len(candidates) >= 15:
                break
        time.sleep(1.5)

    candidates.sort(key=lambda x: (not x["is_prefer"], random.random()))
    to_post = candidates[:CARS_PER_DAY]
    print(f"Будем публиковать: {len(to_post)} машин", flush=True)

    for car in to_post:
        try:
            caption = format_caption(car)
            media = []
            for i, data in enumerate(car["photos"]):
                bio = io.BytesIO(data)
                bio.name = f"photo{i}.jpg"
                if i == 0:
                    media.append(InputMediaPhoto(bio, caption=caption, parse_mode=ParseMode.HTML))
                else:
                    media.append(InputMediaPhoto(bio))
            bot.send_media_group(chat_id=CHAT_ID, media=media, timeout=120)
            posted.add(car["id"])
            print(f"Опубликовано: {car['title']}", flush=True)
            time.sleep(3)
        except Exception as e:
            print(f"Ошибка публикации {car['title']}: {e}", flush=True)

    save_posted(posted)
    print("Готово!", flush=True)

if __name__ == "__main__":
    main()
