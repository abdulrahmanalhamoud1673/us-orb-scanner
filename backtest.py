"""
تقرير أداء الاستراتيجية على البيانات التاريخية.

⚠️ هذا الملف لا يعدّل الاستراتيجية إطلاقاً — هو يستورد `analyze` من strategy.py
   ويشغّلها كما هي على كل يوم تداول سابق، ثم يحوّل الإشارات الناتجة إلى صفقات.

قواعد احتساب الصفقة (مأخوذة من إشارات الاستراتيجية نفسها، بلا أي إضافة):
  • كل إشارة Buy تفتح صفقة بسعرها.
  • إشارة Sell التالية تغلقها بسعرها.
  • إذا بقيت صفقة مفتوحة عند نهاية الجلسة، تُغلق بسعر إغلاق الجلسة.

التشغيل:
    python backtest.py           # آخر 55 يوم تداول
    python backtest.py 30        # آخر 30 يوم
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from scan import BATCH_SIZE, TICKERS_FILE, extract  # نفس أدوات السكانر
from strategy import analyze  # ← الاستراتيجية كما هي، بلا تعديل

ROOT = Path(__file__).parent
OUTPUT_FILE = ROOT / "docs" / "backtest.json"
NY = ZoneInfo("America/New_York")
AMMAN = ZoneInfo("Asia/Amman")

# ياهو يسمح بشموع 5 دقائق لآخر 60 يوماً فقط
MAX_DAYS = 60


def load_tickers() -> list[str]:
    lines = TICKERS_FILE.read_text(encoding="utf-8").splitlines()
    return [s for line in lines if (s := line.split("#")[0].strip().upper())]


def trades_from(result) -> list[dict]:
    """يحوّل إشارات الاستراتيجية إلى صفقات مغلقة. لا منطق تداول جديد هنا."""
    sig = result.signals
    out, i = [], 0
    while i < len(sig):
        if sig[i]["kind"] != "Buy":
            i += 1
            continue
        entry = sig[i]["price"]
        if i + 1 < len(sig) and sig[i + 1]["kind"] == "Sell":
            exit_price, exit_time, closed_by = sig[i + 1]["price"], sig[i + 1]["time"], "إشارة خروج"
            i += 2
        else:
            # صفقة بقيت مفتوحة حتى إغلاق الجلسة
            exit_price, exit_time, closed_by = result.price, "16:00", "إغلاق الجلسة"
            i += 1
        if entry > 0:
            out.append({
                "entry": entry, "exit": exit_price,
                "entry_time": sig[i - 2]["time"] if closed_by == "إشارة خروج" else sig[i - 1]["time"],
                "exit_time": exit_time, "closed_by": closed_by,
                "ret_pct": round((exit_price / entry - 1) * 100, 3),
            })
    return out


def summarize(trades: list[dict]) -> dict:
    """إحصاءات وصفية بحتة عن مجموعة صفقات."""
    n = len(trades)
    if not n:
        return {"trades": 0, "win_rate": 0, "avg_win": 0, "avg_loss": 0,
                "total_pct": 0, "expectancy": 0, "best": 0, "worst": 0}
    rets = [t["ret_pct"] for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    return {
        "trades": n,
        "win_rate": round(len(wins) / n * 100, 1),
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
        # المجموع البسيط للنسب (ليس عائداً مركّباً)
        "total_pct": round(sum(rets), 2),
        "expectancy": round(sum(rets) / n, 3),
        "best": round(max(rets), 2),
        "worst": round(min(rets), 2),
    }


def main() -> None:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 55
    days = min(days, MAX_DAYS)
    tickers = load_tickers()

    print(f"📉 تقرير أداء الاستراتيجية — {len(tickers)} سهم × آخر {days} يوم\n", flush=True)

    per_ticker: dict[str, list[dict]] = {}
    per_day: dict[str, list[dict]] = {}
    all_trades: list[dict] = []
    sessions_seen = set()

    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i : i + BATCH_SIZE]
        print(f"  جلب {i + 1}-{i + len(batch)} من {len(tickers)}...", flush=True)

        data = yf.download(batch, period=f"{MAX_DAYS}d", interval="5m",
                           group_by="ticker", auto_adjust=False,
                           progress=False, threads=True)
        if data is None or data.empty:
            continue

        for ticker in batch:
            df = extract(data, ticker)
            if df is None:
                continue
            df = df.dropna(how="all")
            if df.empty:
                continue
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            df = df.tz_convert(NY)

            all_days = sorted(set(df.index.date))[-days:]
            for d in all_days:
                try:
                    res = analyze(ticker, df, session_date=d)  # ← الاستراتيجية كما هي
                except Exception:
                    continue
                if not res:
                    continue
                sessions_seen.add(str(d))
                for t in trades_from(res):
                    t = {**t, "ticker": ticker, "date": str(d)}
                    all_trades.append(t)
                    per_ticker.setdefault(ticker, []).append(t)
                    per_day.setdefault(str(d), []).append(t)

    # ترتيب الأسهم: الأفضل توقعاً أولاً (بشرط 5 صفقات على الأقل ليكون الرقم ذا معنى)
    rows = []
    for tk, trs in per_ticker.items():
        s = summarize(trs)
        s["ticker"] = tk
        s["reliable"] = s["trades"] >= 5
        rows.append(s)
    rows.sort(key=lambda r: (r["reliable"], r["expectancy"]), reverse=True)

    days_rows = [{"date": d, **summarize(t)} for d, t in sorted(per_day.items())]

    now_ny = datetime.now(NY)
    payload = {
        "generated_ny": now_ny.strftime("%Y-%m-%d %H:%M"),
        "generated_amman": now_ny.astimezone(AMMAN).strftime("%Y-%m-%d %H:%M"),
        "sessions": len(sessions_seen),
        "date_from": min(sessions_seen) if sessions_seen else None,
        "date_to": max(sessions_seen) if sessions_seen else None,
        "overall": summarize(all_trades),
        "by_ticker": rows,
        "by_day": days_rows,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    o = payload["overall"]
    print(f"\n{'=' * 54}")
    print(f"  إجمالي الصفقات : {o['trades']}")
    print(f"  نسبة النجاح    : {o['win_rate']}%")
    print(f"  متوسط الرابحة  : +{o['avg_win']}%   متوسط الخاسرة: {o['avg_loss']}%")
    print(f"  التوقع/صفقة    : {o['expectancy']}%")
    print(f"  الجلسات        : {payload['sessions']} يوم ({payload['date_from']} → {payload['date_to']})")
    print(f"{'=' * 54}\n")
    print("🏆 أفضل 10 أسهم (5 صفقات فأكثر):")
    for r in [x for x in rows if x["reliable"]][:10]:
        print(f"   {r['ticker']:<6} صفقات {r['trades']:<3} نجاح {r['win_rate']:<5}% توقع {r['expectancy']:+.3f}%")
    print(f"\n💾 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
