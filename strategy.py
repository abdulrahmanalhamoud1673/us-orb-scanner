"""
محرك استراتيجية "شمعة الافتتاح" — Opening Range Breakout + VWAP
ترجمة حرفية لمنطق مؤشر Pine Script الخاص بك إلى Python.

القواعد:
  - شمعة الافتتاح = أول شمعة بعد فتح السوق (9:30 ET)
  - openHigh / openLow / openRange = قمة وقاع ومدى تلك الشمعة
  - VWAP = متوسط السعر المرجح بالحجم، يبدأ من افتتاح الجلسة
  - شراء  : إغلاق فوق openHigh  و فوق VWAP
  - بيع   : (وأنت في صفقة) إغلاق تحت VWAP والشمعة السابقة كانت فوق openHigh
  - إعادة شراء: (بعد بيع) إغلاق فوق قمة شمعة البيع و فوق VWAP
  - الأهداف: openHigh + (2,4,6,8,10) × openRange
"""

from dataclasses import dataclass, field, asdict
from datetime import date

import pandas as pd

# حالات الصفقة
NO_TRADE = 0
LONG = 1
SHORT = -1

TARGET_MULTIPLIERS = (2, 4, 6, 8, 10)


@dataclass
class Signal:
    """إشارة واحدة (شراء أو بيع) مع وقتها وسعرها."""

    kind: str  # "Buy" أو "Sell"
    time: str  # وقت الشمعة بتوقيت نيويورك
    price: float


@dataclass
class ScanResult:
    """نتيجة فحص سهم واحد ليوم واحد."""

    ticker: str
    session_date: str  # تاريخ الجلسة التي حُلّلت فعلياً لهذا السهم
    state: int  # الحالة الحالية: 1 شراء / -1 بيع / 0 لا صفقة
    price: float  # آخر سعر
    open_high: float
    open_low: float
    open_range: float
    vwap: float
    ema200: float
    above_ema200: bool
    entry_price: float | None  # سعر الدخول إذا كنا في صفقة شراء
    change_pct: float  # نسبة الربح/الخسارة من سعر الدخول
    day_change_pct: float  # تغير السهم من افتتاح الجلسة
    volume: int  # حجم التداول التراكمي للجلسة
    targets: list[float]
    targets_hit: int  # كم هدف تحقق حتى الآن
    next_target: float | None
    next_target_pct: float | None  # كم % باقي للهدف القادم
    last_signal_time: str | None
    bars_since_signal: int | None
    signals: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _session_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP تراكمي يبدأ من أول شمعة في الجلسة (نفس معادلة Pine: hlc3 * volume)."""
    hlc3 = (df["High"] + df["Low"] + df["Close"]) / 3
    cum_pv = (hlc3 * df["Volume"]).cumsum()
    cum_v = df["Volume"].cumsum()
    # تجنّب القسمة على صفر في الشموع التي لا حجم فيها
    return cum_pv / cum_v.replace(0, pd.NA)


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def analyze(
    ticker: str,
    history: pd.DataFrame,
    session_date: date | None = None,
    ema_length: int = 200,
) -> ScanResult | None:
    """
    يفحص سهماً واحداً ويرجع نتيجة الاستراتيجية.

    history: شموع 5 دقائق لعدة أيام (مطلوبة لحساب EMA200)، فهرسها بتوقيت نيويورك.
    session_date: الجلسة المطلوب تحليلها. إذا لم يكن للسهم بيانات في ذلك اليوم
        يرجع None بدلاً من التراجع لجلسة أقدم — وإلا عُرضت إشارات الأمس
        وكأنها فرص اليوم.
    يرجع None إذا لم تكن هناك بيانات كافية.
    """
    df = history.dropna(subset=["Close", "High", "Low"])
    if df.empty:
        return None

    # EMA200 تُحسب على كل التاريخ المتاح (وليس على جلسة اليوم فقط)
    ema_full = _ema(df["Close"], ema_length)

    # عزل جلسة اليوم المطلوب فقط
    last_day = session_date or df.index[-1].date()
    session = df[df.index.date == last_day]
    # الجلسة النظامية فقط: من 9:30 حتى 16:00 بتوقيت نيويورك
    session = session.between_time("09:30", "15:59")
    if len(session) < 2:
        return None

    vwap = _session_vwap(session)

    open_bar = session.iloc[0]
    open_high = float(open_bar["High"])
    open_low = float(open_bar["Low"])
    open_range = open_high - open_low
    if open_range <= 0:
        return None

    targets = [open_high + m * open_range for m in TARGET_MULTIPLIERS]

    # ===== آلة الحالة: نفس ترتيب شروط Pine Script =====
    state = NO_TRADE
    last_sell_high = None
    entry_price = None
    signals: list[Signal] = []

    closes = session["Close"].to_numpy(dtype=float)
    highs = session["High"].to_numpy(dtype=float)
    vwaps = vwap.to_numpy(dtype=float)
    times = session.index

    # نبدأ من الشمعة الثانية (الأولى هي شمعة الافتتاح نفسها)
    for i in range(1, len(session)):
        close, high, vw = closes[i], highs[i], vwaps[i]
        if pd.isna(vw):
            continue
        prev_close = closes[i - 1]
        stamp = times[i].strftime("%H:%M")

        # 1) إعادة شراء بعد بيع: كسر قمة شمعة البيع + فوق VWAP
        if state == SHORT and last_sell_high is not None and close > last_sell_high and close > vw:
            state = LONG
            entry_price = close
            signals.append(Signal("Buy", stamp, round(close, 2)))

        # 2) شراء أساسي: كسر قمة شمعة الافتتاح + فوق VWAP
        elif state == NO_TRADE and close > open_high and close > vw:
            state = LONG
            entry_price = close
            signals.append(Signal("Buy", stamp, round(close, 2)))

        # 3) بيع: إغلاق تحت VWAP والشمعة السابقة فوق قمة الافتتاح
        elif state == LONG and close < vw and prev_close > open_high:
            state = SHORT
            last_sell_high = high
            entry_price = None
            signals.append(Signal("Sell", stamp, round(close, 2)))

    price = float(closes[-1])
    session_open = float(open_bar["Open"])
    hit = sum(1 for t in targets if price >= t)
    next_target = targets[hit] if hit < len(targets) else None

    bars_since = None
    if signals:
        last_time = signals[-1].time
        idx = [t.strftime("%H:%M") for t in times].index(last_time)
        bars_since = len(session) - 1 - idx

    last_vwap = float(vwaps[-1]) if not pd.isna(vwaps[-1]) else price
    last_ema = float(ema_full.iloc[-1])

    return ScanResult(
        ticker=ticker,
        session_date=str(last_day),
        state=state,
        price=round(price, 2),
        open_high=round(open_high, 2),
        open_low=round(open_low, 2),
        open_range=round(open_range, 2),
        vwap=round(last_vwap, 2),
        ema200=round(last_ema, 2),
        above_ema200=price > last_ema,
        entry_price=round(entry_price, 2) if entry_price else None,
        change_pct=round((price / entry_price - 1) * 100, 2) if entry_price else 0.0,
        day_change_pct=round((price / session_open - 1) * 100, 2),
        volume=int(session["Volume"].sum()),
        targets=[round(t, 2) for t in targets],
        targets_hit=hit,
        next_target=round(next_target, 2) if next_target else None,
        next_target_pct=round((next_target / price - 1) * 100, 2) if next_target else None,
        last_signal_time=signals[-1].time if signals else None,
        bars_since_signal=bars_since,
        signals=[asdict(s) for s in signals],
    )
