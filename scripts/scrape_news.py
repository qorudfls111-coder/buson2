from playwright.sync_api import sync_playwright
from urllib.parse import urljoin
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json, re

BASE = "https://aion2.plaync.com"
BOARDS = {
    "update": ("https://aion2.plaync.com/ko-kr/board/update/list", "/board/update/view"),
    "notice": ("https://aion2.plaync.com/ko-kr/board/notice/list", "/board/notice/view"),
    "cm": ("https://aion2.plaync.com/ko-kr/board/cm_story/list", "/board/cm_story/view"),
}
OUT = Path("news.json")
DATE_RE = re.compile(r"(20\d{2})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})")

def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

def date_from_text(text):
    m = DATE_RE.search(text or "")
    if not m:
        return ""
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

def read_existing():
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {"updated_at":"","update":[],"notice":[],"cm":[]}

def collect(page, list_url, href_part):
    page.goto(list_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(7000)
    anchors = page.locator(f'a[href*="{href_part}"]')
    count = anchors.count()
    items, seen = [], set()

    for i in range(min(count, 100)):
        a = anchors.nth(i)
        try:
            href = a.get_attribute("href") or ""
            title = clean(a.inner_text(timeout=3000))
            if not href or not title or len(title) < 2:
                continue
            url = urljoin(BASE, href)
            if url in seen:
                continue
            seen.add(url)

            context = a.evaluate("""el => {
              let p = el;
              for (let i=0; i<5 && p; i++, p=p.parentElement) {
                const t = (p.innerText || '').trim();
                if (t.length > 0 && t.length < 1200) return t;
              }
              return el.innerText || '';
            }""")
            date = date_from_text(context)
            items.append({"title": title, "date": date, "url": url})
            if len(items) >= 20:
                break
        except Exception:
            continue
    return items

def main():
    existing = read_existing()
    result = {
        "updated_at": datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST"),
        "update": existing.get("update", []),
        "notice": existing.get("notice", []),
        "cm": existing.get("cm", []),
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1200},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"
        )
        for key, (url, href_part) in BOARDS.items():
            try:
                items = collect(page, url, href_part)
                if items:
                    result[key] = items
                    print(f"{key}: {len(items)} items")
                else:
                    print(f"{key}: no items; keeping previous data")
            except Exception as e:
                print(f"{key}: failed: {e}; keeping previous data")
        browser.close()

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
