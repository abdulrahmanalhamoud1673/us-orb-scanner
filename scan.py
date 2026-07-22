"""
السكانر الرئيسي — يجلب بيانات الأسهم الأمريكية ويطبق استراتيجية شمعة الافتتاح
ثم يكتب النتائج في docs/results.json لتعرضها لوحة التحكم.

التشغيل:
    python scan.py                      # فحص كل الأسهم في tickers.txt
    python scan.py AAPL NVDA TSLA       # فحص أسهم محددة فقط
    python scan.py --date 2026-07-21    # فحص جلسة يوم سابق (للتجربة)
"""

import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from strategy import LONG, SHORT, analyze

ROOT = Path(__file__).parent
TICKERS_FILE = ROOT / "tickers.txt"
OUTPUT_FILE = ROOT / "docs" / "results.json"

NY = ZoneInfo("America/New_York")
AMMAN = ZoneInfo("Asia/Amman")

# كم سهم نجلبه في الطلب الواحد (yfinance يدعم الجلب الجماعي)
BATCH_SIZE = 40


def parse_args() -> tuple[list[str], date | None]:
    """يفصل وسائط سطر الأوامر إلى (قائمة أسهم، تاريخ جلسة اختياري)."""
    args = sys.argv[1:]
    forced_date = None

    if "--date" in args:
        i = args.index("--date")
        forced_date = date.fromisoformat(args[i + 1])
        args = args[:i] + args[i + 2 :]

    if args:
        return [t.upper() for t in args], forced_date

    lines = TICKERS_FILE.read_text(encoding="utf-8").splitlines()
    tickers = [s for line in lines if (s := line.split("#")[0].strip().upper())]
    return tickers, forced_date


def extract(data: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    """يستخرج أعمدة سهم واحد من نتيجة yfinance.

    شكل الأعمدة يختلف حسب عدد الأسهم المطلوبة وإصدار المكتبة:
    قد يكون الرمز في المستوى الأول أو الثاني أو غير موجود أصلاً (سهم واحد).
    """
    cols = data.columns
    if not isinstance(cols, pd.MultiIndex):
        return data
    for level in (0, 1):
        if ticker in cols.get_level_values(level):
            return data.xs(ticker, axis=1, level=level)
    return None


def fetch(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """يجلب شموع 5 دقائق لآخر 5 أيام لكل سهم، على دفعات."""
    frames: dict[str, pd.DataFrame] = {}

    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i : i + BATCH_SIZE]
        print(f"  جلب البيانات {i + 1}-{i + len(batch)} من {len(tickers)}...", flush=True)

        data = yf.download(
            batch,
            period="5d",
            interval="5m",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
        if data is None or data.empty:
            continue

        for ticker in batch:
            df = extract(data, ticker)
            if df is None:
                continue
            df = df.dropna(how="all")
            if df.empty:
                continue
            # توحيد التوقيت على نيويورك حتى تُحسب الجلسة بشكل صحيح
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            frames[ticker] = df.tz_convert(NY)

    return frames


def main() -> None:
    tickers, forced_date = parse_args()
    now_ny = datetime.now(NY)
    print(f"فحص {len(tickers)} سهم — {now_ny:%Y-%m-%d %H:%M} بتوقيت نيويورك\n")

    frames = fetch(tickers)
    print(f"\nوصلت بيانات {len(frames)} سهم. تطبيق الاستراتيجية...\n")

    # جلسة السوق الحالية = أحدث تاريخ شمعة عبر كل الأسهم.
    # نثبّتها للجميع حتى لا يُحلَّل سهم متأخر البيانات على جلسة الأمس
    # فتظهر إشارة قديمة وكأنها فرصة اليوم.
    session_date = forced_date or (
        max(df.index[-1].date() for df in frames.values()) if frames else None
    )

    results = []
    errors = []
    waiting = []  # أسهم لم تتكوّن لها شموع كافية بعد (بداية الجلسة عادةً)
    for ticker, df in frames.items():
        try:
            result = analyze(ticker, df, session_date=session_date)
        except Exception as exc:  # سهم واحد معطوب يجب ألا يوقف الفحص كله
            errors.append(f"{ticker}: {exc}")
            continue
        if result:
            results.append(result.to_dict())
        else:
            waiting.append(ticker)

    # الفرص النشطة أولاً، ثم الأحدث إشارة، ثم الأعلى ربحاً
    buys = [r for r in results if r["state"] == LONG]
    sells = [r for r in results if r["state"] == SHORT]
    buys.sort(key=lambda r: (r["bars_since_signal"] or 999, -r["change_pct"]))

    payload = {
        "updated_ny": now_ny.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_amman": now_ny.astimezone(AMMAN).strftime("%Y-%m-%d %H:%M:%S"),
        "session_date": str(session_date) if session_date else None,
        "requested": len(tickers),
        "scanned": len(results),
        "waiting": len(waiting),
        "buy_count": len(buys),
        "sell_count": len(sells),
        "errors": errors,
        "opportunities": buys,
        "all": sorted(results, key=lambda r: r["ticker"]),
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if waiting:
        print(f"⏳ {len(waiting)} سهم بانتظار تكوّن شموع كافية في جلسة اليوم\n")
    print(f"✅ فرص شراء نشطة: {len(buys)}")
    for r in buys[:15]:
        arrow = "▲" if r["change_pct"] >= 0 else "▼"
        print(
            f"   {r['ticker']:<6} ${r['price']:<8} دخول ${r['entry_price']:<8} "
            f"{arrow}{abs(r['change_pct'])}%  أهداف محققة: {r['targets_hit']}/5"
        )
    if errors:
        print(f"\n⚠️  {len(errors)} خطأ: {errors[:3]}")
    print(f"\n💾 النتائج محفوظة في {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
