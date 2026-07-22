"""
جالب أخبار السوق الأمريكي.

يقرأ خلاصات RSS مجانية (بدون مفاتيح)، يبقي الأخبار المؤثرة على اتجاه السوق فقط،
ويصنّف كل خبر مبدئياً: صعودي / هبوطي / مهم — ثم يكتب docs/news.json.

⚠️ التصنيف تقديري بالكلمات المفتاحية، وليس تحليلاً مالياً. الرابط الأصلي مرفق دائماً
   ليقرأ المستخدم الخبر بنفسه.

التشغيل:
    python news.py
"""

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
OUTPUT_FILE = ROOT / "docs" / "news.json"

NY = ZoneInfo("America/New_York")
AMMAN = ZoneInfo("Asia/Amman")

UA = "Mozilla/5.0 (compatible; ORBScanner/1.0)"
TIMEOUT = 15
MAX_AGE_HOURS = 24  # نتجاهل الأخبار الأقدم من يوم
MAX_ITEMS = 45

# مصادر عربية (أخبار جوجل) + إنجليزية رئيسية
def google(query: str) -> str:
    """رابط بحث أخبار جوجل — الاستعلام العربي يجب ترميزه، وإلا فشل urllib."""
    return ("https://news.google.com/rss/search?q="
            + urllib.parse.quote(query) + "&hl=ar&gl=JO&ceid=JO:ar")


FEEDS: list[tuple[str, str]] = [
    ("أخبار جوجل", google("الأسهم الأمريكية وول ستريت")),
    ("أخبار جوجل", google("الاحتياطي الفيدرالي أسعار الفائدة")),
    ("أخبار جوجل", google("التضخم الأمريكي بيانات الوظائف")),
    ("أخبار جوجل", google("مؤشر ناسداك داو جونز")),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("CNBC", "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
]

# كلمات تدل على أن الخبر يحرّك السوق ككل (وليس خبر شركة صغيرة)
IMPORTANT = [
    # عربي
    "الفيدرالي", "الفائدة", "التضخم", "الوظائف", "البطالة", "الركود", "الناتج المحلي",
    "وول ستريت", "ناسداك", "داو جونز", "إس آند بي", "الأسهم الأمريكية", "السوق الأمريكي",
    "رسوم جمركية", "تعريفة", "حرب تجارية", "النفط", "الذهب", "الدولار", "السندات",
    "باول", "ترامب", "الخزانة", "تحفيز", "أرباح الشركات", "انهيار", "تصحيح",
    # إنجليزي
    "fed", "fomc", "interest rate", "rate cut", "rate hike", "inflation", "cpi", "ppi",
    "jobs report", "payrolls", "unemployment", "recession", "gdp", "powell",
    "wall street", "nasdaq", "dow jones", "s&p 500", "stocks", "market",
    "tariff", "trade war", "treasury", "yields", "stimulus", "selloff", "rally", "crash",
]

# كلمات الاتجاه — تقديرية
BULL = [
    "ارتفاع", "صعود", "مكاسب", "يرتفع", "تصعد", "قفزة", "انتعاش", "تفاؤل", "قياسي",
    "خفض الفائدة", "تراجع التضخم", "أفضل من المتوقع", "تحفيز",
    "rally", "surge", "jump", "soar", "gains", "rise", "rises", "climb", "record high",
    "beat", "beats", "optimism", "rate cut", "cools", "stronger than expected", "rebound",
]
BEAR = [
    "هبوط", "انخفاض", "خسائر", "يهبط", "تراجع", "انهيار", "قلق", "مخاوف", "تحذير",
    "رفع الفائدة", "ارتفاع التضخم", "أسوأ من المتوقع", "ركود", "بيع مكثف",
    "fall", "falls", "drop", "plunge", "slump", "sink", "tumble", "losses", "selloff",
    "fears", "worries", "warning", "recession", "miss", "misses", "rate hike",
    "hotter than expected", "crash", "slide",
]


def fetch(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"    تعذّر الجلب: {exc}")
        return None


def clean(text: str) -> str:
    """يزيل وسوم HTML ويضغط المسافات."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text or "")).strip()


def parse_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except Exception:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def classify(title: str) -> tuple[bool, str]:
    """يرجع (هل الخبر مهم؟، الاتجاه المرجّح)."""
    low = title.lower()
    important = any(k in low for k in IMPORTANT)
    bull = sum(1 for w in BULL if w in low)
    bear = sum(1 for w in BEAR if w in low)
    direction = "up" if bull > bear else "down" if bear > bull else "neutral"
    return important, direction


def parse_feed(source: str, xml: str) -> list[dict]:
    out = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out

    # RSS 2.0 و Atom
    ATOM = "{http://www.w3.org/2005/Atom}"
    items = root.findall(".//item")
    if not items:
        items = root.findall(f".//{ATOM}entry")

    for it in items:
        def get(tag: str) -> str | None:
            # ملاحظة: عنصر XML بلا أبناء قيمته المنطقية False في بايثون،
            # لذلك نفحص "is not None" صراحةً بدل استخدام or.
            el = it.find(tag)
            if el is None:
                el = it.find(ATOM + tag)
            if el is None:
                return None
            if tag == "link" and not (el.text or "").strip():
                return el.get("href")
            return el.text

        title = clean(get("title") or "")
        link = clean(get("link") or "")
        if not title or not link:
            continue

        when = parse_time(get("pubDate") or get("published") or get("updated"))
        if when and datetime.now(timezone.utc) - when > timedelta(hours=MAX_AGE_HOURS):
            continue

        important, direction = classify(title)
        if not important:
            continue

        # أخبار جوجل تضيف " - اسم الموقع" بآخر العنوان؛ نستخرج المصدر الحقيقي
        real_source = source
        if " - " in title and source == "أخبار جوجل":
            title, _, real_source = title.rpartition(" - ")

        out.append({
            "title": title.strip(),
            "url": link,
            "source": real_source.strip(),
            "direction": direction,
            "ts": when.isoformat() if when else None,
            "amman": when.astimezone(AMMAN).strftime("%H:%M") if when else "",
        })
    return out


def main() -> None:
    print("📰 جلب أخبار السوق...\n")
    items: list[dict] = []
    for source, url in FEEDS:
        print(f"  {source}...", flush=True)
        xml = fetch(url)
        if xml:
            got = parse_feed(source, xml)
            print(f"    {len(got)} خبر مؤثر")
            items += got

    # إزالة المكرر حسب العنوان المبسّط
    seen, unique = set(), []
    for it in items:
        key = re.sub(r"[^\w؀-ۿ]+", "", it["title"].lower())[:70]
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)

    unique.sort(key=lambda x: x["ts"] or "", reverse=True)
    unique = unique[:MAX_ITEMS]

    now_ny = datetime.now(NY)
    payload = {
        "updated_amman": now_ny.astimezone(AMMAN).strftime("%Y-%m-%d %H:%M"),
        "count": len(unique),
        "up": sum(1 for i in unique if i["direction"] == "up"),
        "down": sum(1 for i in unique if i["direction"] == "down"),
        "items": unique,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ {len(unique)} خبر ({payload['up']} صعودي / {payload['down']} هبوطي)")
    for i in unique[:8]:
        arrow = "▲" if i["direction"] == "up" else "▼" if i["direction"] == "down" else "•"
        print(f"   {arrow} [{i['amman']}] {i['title'][:70]} — {i['source']}")
    print(f"\n💾 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
