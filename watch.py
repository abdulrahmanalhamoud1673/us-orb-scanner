"""
المراقب الحي — يعيد تشغيل الفحص كل بضع دقائق طوال جلسة التداول، ثم يرفع
النتائج إلى جيت هَب فيتحدّث الموقع (الكمبيوتر والجوال) خلال دقيقة.

هذا هو الحل المجاني الموثوق: جدولة جيت هَب المجانية تُلغي المهام كثيراً، أما
تشغيل الفحص من جهازك فيضمن تحديثاً منتظماً طول ما الجهاز شغّال.

التشغيل:
    python watch.py            # فحص كل 5 دقائق + نشر تلقائي
    python watch.py 3          # فحص كل 3 دقائق
    python watch.py 5 --local  # فحص فقط للوحة المحلية بدون نشر

أوقفه بالضغط على  Ctrl + C
"""

import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).parent
NY = ZoneInfo("America/New_York")
AMMAN = ZoneInfo("Asia/Amman")

MARKET_OPEN = dtime(9, 30)
MARKET_CLOSE = dtime(16, 0)

RESULTS = ROOT / "docs" / "results.json"
NEWS = ROOT / "docs" / "news.json"


def market_is_open(now_ny: datetime) -> bool:
    """الجلسة النظامية: 9:30–16:00 بتوقيت نيويورك، أيام الاثنين–الجمعة.

    لا يعرف العطل الرسمية — في يوم عطلة سيفحص ولن يجد شموعاً جديدة، وهذا غير ضار.
    """
    if now_ny.weekday() >= 5:  # 5 = السبت، 6 = الأحد
        return False
    return MARKET_OPEN <= now_ny.time() < MARKET_CLOSE


def _git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def _commit_and_push() -> str:
    """يضيف النتائج ويحاول الدفع. يرجع: nochange / ok / rejected."""
    _git("add", "-f", "docs/results.json", "docs/news.json")
    if _git("diff", "--cached", "--quiet").returncode == 0:
        return "nochange"
    _git("commit", "-m", f"تحديث محلي {datetime.now(NY):%H:%M} ET")
    return "ok" if _git("push").returncode == 0 else "rejected"


def push_results() -> None:
    """يرفع نتائج الفحص إلى جيت هَب.

    المسار العادي: إضافة + كوميت + دفع فقط — بلا أي مزامنة قوية، فلا خطر على شيء.
    فقط إذا رُفض الدفع (لأن فحصاً آخر سبقنا) نتزامن بأمان: نحفظ نتائجنا جانباً،
    نأخذ أحدث نسخة من السحابة (‎reset --hard‎)، نعيد نتائجنا، وندفع دلتا واحدة.
    هكذا لا يبقى المستودع في حالة عالقة أبداً، ولا نلمس المزامنة القوية إلا نادراً.
    """
    if not RESULTS.exists():
        return
    try:
        outcome = _commit_and_push()
        if outcome == "nochange":
            print("   لا تغيير في النتائج — لا نشر", flush=True)
            return
        if outcome == "ok":
            print("   ✅ نُشر — الموقع (كمبيوتر/جوال) يتحدّث خلال دقيقة", flush=True)
            return

        # رُفض الدفع → مزامنة آمنة ثم إعادة المحاولة
        tmp = Path(tempfile.gettempdir())
        shutil.copy2(RESULTS, tmp / "orb_results.json")
        if NEWS.exists():
            shutil.copy2(NEWS, tmp / "orb_news.json")
        _git("fetch", "origin", "main")
        _git("reset", "--hard", "origin/main")
        shutil.copy2(tmp / "orb_results.json", RESULTS)
        if (tmp / "orb_news.json").exists():
            shutil.copy2(tmp / "orb_news.json", NEWS)

        again = _commit_and_push()
        print("   ✅ نُشر بعد المزامنة" if again == "ok"
              else "   ⚠️ تأجّل النشر — ستصلحه الدورة القادمة", flush=True)
    except Exception as exc:
        print(f"   ⚠️ خطأ في النشر: {exc}", flush=True)


def main() -> None:
    plain = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_push = "--local" not in sys.argv
    minutes = int(plain[0]) if plain else 5

    print("=" * 58)
    print("  🤖 مراقب السوق الأمريكي — استراتيجية شمعة الافتتاح")
    print(f"  ⏱️  إعادة الفحص كل {minutes} دقيقة" + ("  +  نشر تلقائي" if do_push else "  (محلي فقط)"))
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
            if do_push:
                push_results()
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
