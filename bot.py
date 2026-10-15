import os
import json
import re
import time
import random
import requests
from bs4 import BeautifulSoup
from telegram import Bot, InputMediaPhoto
from telegram.constants import ParseMode

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
POSTED_FILE = "posted_cars.json"
CARS_PER_DAY = 8
MAX_PHOTOS = 10

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def load_posted():
    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except:
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
            print(f"Ошибка списка {market} стр {page}: {e}")
    return links

def parse_car(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        soup = BeautifulSoup(r.text, "lxml")
        text = soup.get_text("\n", strip=True)

        # ID машины
        car_id = url.rstrip("/").split("-")[-1]

        # Название
        title = ""
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

        # Цена под ключ
        price = ""
        price_match = re.search(r"(\d[\d\s]{4,})\s*₽", text)
        if price_match:
            price = price_match.group(1).replace(" ", "") + " ₽"

        # Год
        year = None
        year_match = re.search(r"(?:Год выпуска|Октябрь|Январь|Февраль|Март|Апрель|Май|Июнь|Июль|Август|Сентябрь|Ноябрь|Декабрь)\s*(\d{4})", text)
        if year_match:
            year = int(year_match.group(1))
        else:
            year_match2 = re.search(r"(\d{4})\s*год", text)
            if year_match2:
                year = int(year_match2.group(1))

        # Пробег
        mileage = ""
        mile_match = re.search(r"([\d\s]+)\s*км", text)
        if mile_match:
            mileage = mile_match.group(1).strip() + " км"

        # Мощность
        hp = None
        hp_match = re.search(r"(\d+)\s*л\.?\s*с", text)
        if hp_match:
            hp = int(hp_match.group(1))

        # Объём, топливо, КПП
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
