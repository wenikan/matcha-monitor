import requests
import json
import os
from datetime import datetime

PRODUCTS = [
    "Aoarashi", "Isuzu", "Chigi", "Yugen", "Wako", "Kinrin", "Kiwami Choan"
]
URL = "https://www.marukyu-koyamaen.co.jp/english/shop/products/catalog/matcha/principal"
STATE_FILE = "matcha_state.json"
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

def send_telegram(msg):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}
    )

def fetch_page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ))
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        html = page.content()
        browser.close()
        return html

def parse(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    result = {}
    for name in PRODUCTS:
        idx = text.upper().find(name.upper())
        if idx == -1:
            result[name] = "unknown"
            continue
        window = text[max(0, idx-100):idx+300].upper()
        result[name] = "sold_out" if "SOLD OUT" in window else "in_stock"
    return result

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def main():
    html = fetch_page()
    current = parse(html)
    old = load_state()
    restocked = [n for n in current if old.get(n) == "sold_out" and current[n] == "in_stock"]
    if restocked:
        names = "、".join(restocked)
        send_telegram(f"🍵 <b>抹茶補貨了！</b>\n{names} 現在有貨，快去買！\n\n{URL}")
    save_state(current)
    print(datetime.now(), current)

if __name__ == "__main__":
    main()
