"""
المراقب الحي — يعيد تشغيل الفحص تلقائياً كل بضع دقائق طوال جلسة التداول.

التشغيل:
    python watch.py            # فحص كل 5 دقائق
    python watch.py 3          # فحص كل 3 دقائق

أوقفه بالضغط على  Ctrl + C
"""

import subprocess
import sys
import time
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
NY = ZoneInfo("America/New_York")
AMMAN = ZoneInfo("Asia/Amman")

MARKET_OPEN = dtime(9, 30)
MARKET_CLOSE = dtime(16, 0)


def market_is_open(now_ny: datetime) -> bool:
    """الجلسة النظامية: 9:30–16:00 بتوقيت نيويورك، أيام الاثنين–الجمعة.

    لا يعرف العطل الرسمية — في يوم عطلة سيفحص ولن يجد شموعاً جديدة، وهذا غير ضار.
    """
    if now_ny.weekday() >= 5:  # 5 = السبت، 6 = الأحد
        return False
    return MARKET_OPEN <= now_ny.time() < MARKET_CLOSE


def main() -> None:
    minutes = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    print("=" * 58)
    print("  🤖 مراقب السوق الأمريكي — استراتيجية شمعة الافتتاح")
    print(f"  ⏱️  إعادة الفحص كل {minutes} دقيقة")
    print("  🌐 اللوحة: http://localhost:8777")
    print("  ⛔ للإيقاف: اضغط Ctrl + C")
    print("=" * 58, flush=True)

    while True:
        now_ny = datetime.now(NY)
        now_jo = now_ny.astimezone(AMMAN)
        stamp = f"{now_jo:%H:%M} الأردن / {now_ny:%H:%M} نيويورك"

        if market_is_open(now_ny):
            print(f"\n🔄 فحص جديد — {stamp}\n", flush=True)
            # subprocess بدل الاستيراد: أي خطأ في فحص واحد لا يُسقط المراقب
            subprocess.run([sys.executable, "scan.py"], cwd=ROOT)
        else:
            # نحسب موعد الفتح بتوقيت الأردن ديناميكياً (يتغير مع التوقيت الصيفي الأمريكي)
            open_ny = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
            open_jo = open_ny.astimezone(AMMAN)
            print(f"😴 السوق مغلق — {stamp} (الفتح 9:30 نيويورك = {open_jo:%H:%M} الأردن)", flush=True)

        time.sleep(minutes * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 تم إيقاف المراقب.")
