import requests
import json
import os
from datetime import datetime, timezone, timedelta

NAMES_ZH = {
    "Aoarashi": "青嵐", "Isuzu": "五十鈴", "Chigi no Shiro": "千木の白",
    "Yugen": "又玄", "Wako": "和光", "Kinrin": "金輪", "Kiwami Choan": "極長安",
}
URL = "https://www.marukyu-koyamaen.co.jp/english/shop/products/catalog/matcha/principal"
STATE_FILE = "matcha_state.json"
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

def send_telegram(msg):
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}
    )
    print("Telegram 回應：", r.status_code, r.text[:200])

def fetch_and_parse():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ))
        page.goto(URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        products = page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('li.product, article.product').forEach(el => {
                const nameEl = el.querySelector('h2, h3, h4, .product-name');
                const name = nameEl ? nameEl.innerText.trim() : '';
                if (name) {
                    results.push({
                        name: name,
                        classes: el.className,
                        outofstock: el.classList.contains('outofstock')
                    });
                }
            });
            return results;
        }""")

        browser.close()

        print("偵測結果：")
        result = {}
        for p in products:
            print(" ", p)
            status = "sold_out" if p["outofstock"] else "in_stock"
            result[p["name"]] = status

        return result

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def format_status(current):
    in_stock = [NAMES_ZH.get(n, n) for n, s in current.items() if s == "in_stock"]
    sold_out = [NAMES_ZH.get(n, n) for n, s in current.items() if s == "sold_out"]
    lines = []
    if in_stock:
        lines.append("✅ 有貨：" + "、".join(in_stock))
    if sold_out:
        lines.append("❌ 缺貨：" + "、".join(sold_out))
    return "\n".join(lines)

def main():
    current = fetch_and_parse()
    old = load_state()

    any_in_stock = any(s == "in_stock" for s in current.values())
    was_any_in_stock = any(s == "in_stock" for s in old.values())

    now = datetime.now(timezone(timedelta(hours=8))).strftime("%m/%d %H:%M")

    if any_in_stock:
        restocked = [n for n in current if old.get(n) == "sold_out" and current[n] == "in_stock"]
        header = "🍵 <b>補貨了！快去買！</b>" if restocked else "🛒 <b>還有貨，記得去買！</b>"
        msg = f"{header}\n\n{format_status(current)}\n\n🔗 {URL}\n⏰ {now}"
        send_telegram(msg)
    elif was_any_in_stock and not any_in_stock:
        send_telegram(f"😢 <b>全部賣完了</b>，繼續幫你盯著...\n⏰ {now}")

    save_state(current)
    print(datetime.now(), current)

if __name__ == "__main__":
    main()
