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

DATE_PATTERNS = [
    re.compile(r"(20\d{2})[-./]\s*(\d{1,2})[-./]\s*(\d{1,2})"),
    re.compile(r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일"),
]
TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
ISO_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})[T\s](\d{2}:\d{2})(?::\d{2})?")

def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

def extract_date(text):
    text = text or ""
    iso = ISO_RE.search(text)
    if iso:
        return iso.group(1), iso.group(2)
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if m:
            d = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            tm = TIME_RE.search(text[m.end():])
            return d, (f"{int(tm.group(1)):02d}:{tm.group(2)}" if tm else "")
    return "", ""

def date_from_ancestor(a):
    # Climb until we find visible date information.
    try:
        txt = a.evaluate("""el => {
          let p=el;
          for(let i=0;i<9 && p;i++,p=p.parentElement){
            const t=(p.innerText||'').trim();
            if(/20\\d{2}[-./년]/.test(t)) return t;
          }
          return '';
        }""")
        return extract_date(txt)
    except Exception:
        return "", ""

def date_from_detail(browser, url):
    page = browser.new_page(viewport={"width":1280,"height":1000})
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)

        # 1) Standard metadata/time elements
        candidates = []
        for selector, attr in [
            ('meta[property="article:published_time"]','content'),
            ('meta[name="article:published_time"]','content'),
            ('meta[property="og:published_time"]','content'),
            ('time[datetime]','datetime'),
        ]:
            loc = page.locator(selector)
            for i in range(min(loc.count(), 5)):
                v = loc.nth(i).get_attribute(attr)
                if v:
                    candidates.append(v)

        # 2) Visible document text
        try:
            candidates.append(page.locator("body").inner_text(timeout=5000))
        except Exception:
            pass

        # 3) Page HTML / hydration JSON often includes createdAt/publishedAt timestamps
        try:
            content = page.content()
            for key in [
                "publishedAt","publishDate","publishedDate","createdAt","createDate",
                "createdDate","registerDate","registeredAt","writeDate","regDate"
            ]:
                for m in re.finditer(
                    rf'"?{key}"?\s*[:=]\s*["\']([^"\']+)["\']',
                    content, re.I
                ):
                    candidates.append(m.group(1))
        except Exception:
            pass

        best_date, best_time = "", ""
        for c in candidates:
            d, t = extract_date(c)
            if d:
                if t:
                    return d, t
                if not best_date:
                    best_date = d
        return best_date, best_time
    finally:
        page.close()

def read_existing():
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {"updated_at":"","update":[],"notice":[],"cm":[]}

def collect(page, browser, list_url, href_part):
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

            date, tm = date_from_ancestor(a)
            if not date:
                date, tm = date_from_detail(browser, url)

            # Detail page fallback for time even when list already had the date
            if date and not tm:
                d2, t2 = date_from_detail(browser, url)
                if d2:
                    date = d2
                if t2:
                    tm = t2

            dt = f"{date} {tm}".strip() if date else ""
            items.append({
                "title": title,
                "date": date,
                "time": tm,
                "datetime": dt,
                "url": url
            })
            if len(items) >= 20:
                break
        except Exception as e:
            print("item skipped:", e)
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
            viewport={"width":1440,"height":1200},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"
        )
        for key, (url, href_part) in BOARDS.items():
            try:
                items = collect(page, browser, url, href_part)
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
