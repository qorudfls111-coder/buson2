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
KST = timezone(timedelta(hours=9))


DATE_PATTERNS = [
    re.compile(r"(20\d{2})[-./]\s*(\d{1,2})[-./]\s*(\d{1,2})"),
    re.compile(r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일"),
]
TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
ISO_RE = re.compile(
    r"(20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)"
)

def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

def extract_date(text):
    text = text or ""

    # ISO 날짜/시간 우선 확인
    iso = ISO_RE.search(text)
    if iso:
        raw = iso.group(1)

        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))

            # UTC 또는 timezone 정보가 있으면 한국시간으로 변환
            if dt.tzinfo is not None:
                dt = dt.astimezone(KST)

            return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")

        except Exception:
            pass

    # 일반적인 화면 표시 날짜
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if m:
            d = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

            tm = TIME_RE.search(text[m.end():])

            return d, (
                f"{int(tm.group(1)):02d}:{tm.group(2)}"
                if tm else ""
            )

    return "", ""
def date_from_ancestor(a):
    try:
        txt = a.evaluate("""el => {
          let p = el;

          for (let i = 0; i < 8 && p; i++, p = p.parentElement) {

            // 현재 게시물 링크가 들어있는 한 행/카드 후보
            const links = p.querySelectorAll(
              'a[href*="/board/"][href*="/view"]'
            );

            // 여러 게시물이 같이 들어있는 큰 부모는 제외
            if (links.length > 1) {
              continue;
            }

            // 해당 영역 안에서 날짜/시간처럼 보이는 작은 요소들만 확인
            const nodes = p.querySelectorAll(
              'time, span, div, p, em'
            );

            for (const node of nodes) {
              const text = (node.innerText || '').trim();

              // 날짜 + 시간이 같이 있는 경우 우선
              if (
                /20\\d{2}[-./]\\d{1,2}[-./]\\d{1,2}/.test(text) &&
                /(?:[01]?\\d|2[0-3]):[0-5]\\d/.test(text)
              ) {
                return text;
              }
            }

            // 날짜만 있는 경우
            for (const node of nodes) {
              const text = (node.innerText || '').trim();

              if (/20\\d{2}[-./]\\d{1,2}[-./]\\d{1,2}/.test(text)) {
                return text;
              }
            }
          }

          return '';
        }""")
        print("ANCESTOR RAW:", repr(txt))
        print("ANCESTOR PARSED:", extract_date(txt))

        return extract_date(txt)

    except Exception:
        return "", ""
def date_from_detail(browser, url):
    page = browser.new_page(viewport={"width":1280,"height":1000})
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        # AION2 실제 게시 등록시간 직접 찾기
        try:
            body_text = page.locator("body").inner_text(timeout=10000)

            m = re.search(
                r"관리자[\s.]*"
                r"(20\d{2}-\d{2}-\d{2})\s+"
                r"([01]\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?",
                body_text
            )

            if m:
                real_date = m.group(1)
                real_time = f"{m.group(2)}:{m.group(3)}"

                print("REAL AION2 PUBLISH TIME:", real_date, real_time)

                return real_date, real_time

        except Exception as e:
            print("publish time search failed:", e)
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

        # 2) Page HTML / hydration JSON - 구조화된 게시시간 우선
        try:
            content = page.content()

            for key in [
                "publishedAt",
                "publishDate",
                "publishedDate",
                "publishedDateTime",
                "publishDateTime",
                "openDate",
                "displayDate"
            ]:
                pattern = rf"""["']?{re.escape(key)}["']?\s*[:=]\s*["']([^"']+)["']"""

                for m in re.finditer(pattern, content, re.I):
                    candidates.append(m.group(1))

        except Exception:
            pass

        best_date, best_time = "", ""

        print("\n========== DETAIL DEBUG ==========")
        print("URL:", url)

        for idx, c in enumerate(candidates):
            d, t = extract_date(c)

            print(
                f"CANDIDATE {idx}:",
                repr(str(c)[:300]),
                "=>",
                d,
                t
            )

            if d:
                if t:
                    print("SELECTED DETAIL TIME:", d, t)
                    print("==================================\n")
                    return d, t

                if not best_date:
                    best_date = d

        print("NO DETAIL TIME FOUND")
        print("BEST DATE ONLY:", best_date)
        print("==================================\n")

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

            seen.add(url)

            # 1순위: 상세 페이지에서 실제 게시 날짜/시간 확인
            date, tm = date_from_detail(browser, url)

            # 2순위: 상세 페이지에서 못 찾았을 때만 목록 날짜 사용
            if not date or not tm:
                d2, t2 = date_from_ancestor(a)

                if not date and d2:
                    date = d2

                if not tm and t2:
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
