import os
import json
import time
import requests as req
from datetime import datetime, timezone, timedelta

NAMES_ZH = {
    "Aoarashi": "青嵐", "Isuzu": "五十鈴", "Chigi no Shiro": "千木の白",
    "Yugen": "又玄", "Wako": "和光", "Kinrin": "金輪",
    "Kiwami Choan": "極長安", "Choan": "長安",
    "Unkaku": "雲鶴", "Tenju": "天授", "Eiju": "栄寿",
}
URL = "https://www.marukyu-koyamaen.co.jp/english/shop/products/catalog/matcha/principal"
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
CHECK_INTERVAL = 30
STATE_FILE = "matcha_state.json"
TZ = timezone(timedelta(hours=8))
REMIND_MINUTES = 10

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def send_telegram(msg):
    try:
        req.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        print(f"Telegram 發送失敗: {e}")

def fetch_with_requests():
    from bs4 import BeautifulSoup
    r = req.get(URL, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        raise Exception(f"HTTP {r.status_code}")
    soup = BeautifulSoup(r.text, "html.parser")
    products = soup.select("li.product, article.product")
    if not products:
        raise Exception("找不到商品元素")
    result = {}
    for p in products:
        name_el = p.select_one("h2, h3, h4, .product-name")
        if name_el:
            name = name_el.get_text(strip=True)
            result[name] = "sold_out" if "outofstock" in p.get("class", []) else "in_stock"
    return result

def fetch_with_playwright():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        page.goto(URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        products = page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('li.product, article.product').forEach(el => {
                const nameEl = el.querySelector('h2, h3, h4, .product-name');
                const name = nameEl ? nameEl.innerText.trim() : '';
                if (name) results.push({ name, outofstock: el.classList.contains('outofstock') });
            });
            return results;
        }""")
        browser.close()
        return {p["name"]: ("sold_out" if p["outofstock"] else "in_stock") for p in products}

def detect_method():
    print("偵測最佳抓取方式...")
    try:
        result = fetch_with_requests()
        print(f"✅ 直接抓取成功，找到 {len(result)} 個商品，不需要瀏覽器！")
        return "requests"
    except Exception as e:
        print(f"❌ 直接抓取失敗（{e}），改用 Playwright")
        return "playwright"

def fetch_and_parse(method):
    if method == "requests":
        return fetch_with_requests()
    return fetch_with_playwright()

def format_status(current):
    in_stock = [NAMES_ZH.get(n, n) for n, s in current.items() if s == "in_stock"]
    sold_out = [NAMES_ZH.get(n, n) for n, s in current.items() if s == "sold_out"]
    lines = []
    if in_stock:
        lines.append("✅ 有貨：" + "、".join(in_stock))
    if sold_out:
        lines.append("❌ 缺貨：" + "、".join(sold_out))
    return "\n".join(lines)

def check(old_state, method):
    current_products = fetch_and_parse(method)
    now = datetime.now(TZ)
    now_str = now.strftime("%m/%d %H:%M")

    old_products = old_state.get("products", {})
    restock_at = dict(old_state.get("restock_at", {}))

    newly_in_stock = []
    remind_list = []
    newly_sold_out = []

    for name, status in current_products.items():
        old_status = old_products.get(name)
        if old_status == "sold_out" and status == "in_stock":
            newly_in_stock.append(name)
            restock_at[name] = now.isoformat()
        elif status == "in_stock" and name in restock_at:
            elapsed = (now - datetime.fromisoformat(restock_at[name])).total_seconds()
            if elapsed <= REMIND_MINUTES * 60:
                remind_list.append((name, int(elapsed / 60)))
            else:
                del restock_at[name]
        elif status == "sold_out":
            if name in restock_at:
                del restock_at[name]
            if old_status == "in_stock":
                newly_sold_out.append(name)

    status_text = format_status(current_products)

    if newly_in_stock:
        names = "、".join(NAMES_ZH.get(n, n) for n in newly_in_stock)
        send_telegram(f"🍵 <b>補貨了！快去買！</b>\n\n✅ 新補貨：{names}\n\n{status_text}\n\n🔗 {URL}\n⏰ {now_str}")

    if remind_list:
        lines = "\n".join(f"✅ {NAMES_ZH.get(n, n)}（補貨 {m} 分鐘）" for n, m in remind_list)
        send_telegram(f"⏰ <b>還有貨！</b>\n\n{lines}\n\n{status_text}\n\n🔗 {URL}\n⏰ {now_str}")

    if newly_sold_out:
        names = "、".join(NAMES_ZH.get(n, n) for n in newly_sold_out)
        send_telegram(f"😢 <b>{names} 賣完了</b>\n\n{status_text}\n⏰ {now_str}")

    print(f"[{now_str}] [{method}] {current_products}")
    return {"products": current_products, "restock_at": restock_at}

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"products": {}, "restock_at": {}}
    with open(STATE_FILE) as f:
        saved = json.load(f)
    if "products" not in saved:
        return {"products": saved, "restock_at": {}}
    return saved

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    method = detect_method()
    loop_mode = os.environ.get("LOOP_MODE", "false").lower() == "true"

    if loop_mode:
        print(f"🍵 監控啟動，每 {CHECK_INTERVAL} 秒檢查一次...")
        state = {"products": {}, "restock_at": {}}
        while True:
            try:
                state = check(state, method)
            except Exception as e:
                print(f"[錯誤] {e}")
            time.sleep(CHECK_INTERVAL)
    else:
        state = load_state()
        new_state = check(state, method)
        save_state(new_state)
