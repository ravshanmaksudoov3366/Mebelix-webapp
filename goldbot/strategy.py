"""Oltin (XAUUSD) strategiyasi: katta trend bo'yicha, kichik orqaga qaytishdan keyin kirish.

1. Trend (H1): EMA50 EMA200 dan yuqori, narx EMA50 dan yuqori va ADX >= 20 — faqat SOTIB OLISH.
   Teskarisi — faqat SOTISH. Trend aniq bo'lmasa savdo yo'q.
2. Kirish (M15): narx oxirgi 3 shamda EMA21 ga qaytib tekkan, so'ng trend tomonga kuchli yopilgan
   (EMA21 dan yuqorida, avvalgi sham cho'qqisidan yuqorida, RSI 45–70). Sotish — teskarisi.
3. Stop-loss: oxirgi 5 shamning eng past (sotishda — eng baland) nuqtasi orqasida, ATR bilan
   1.0–2.5 ATR oralig'ida cheklangan. Take-profit: stop masofasining RR baravari (standart 2).
4. Boshqaruv: foyda 1R ga yetsa stop kirish narxidan biroz foydaga, 1.5R da 0.5R foyda qulflanadi.

Hammasi faqat YOPILGAN shamlar bo'yicha hisoblanadi (oxirgi tugamagan shamni chaqiruvchi olib tashlaydi).
"""
from dataclasses import dataclass
from datetime import datetime

from indicators import adx, atr, ema, rsi


@dataclass
class Params:
    rr: float = 2.0                 # take-profit = RR × stop masofasi
    adx_min: float = 20.0
    rsi_buy: tuple = (45.0, 70.0)
    rsi_sell: tuple = (30.0, 55.0)
    pullback_bars: int = 3
    swing_bars: int = 5
    sl_min_atr: float = 1.0
    sl_max_atr: float = 2.5
    max_extension_atr: float = 1.0  # EMA21 dan juda uzoqlashgan narxda kirmaymiz
    max_spread_frac: float = 0.2    # spred stop masofasining 20% idan oshsa — kirmaymiz
    session_start_utc: int = 7      # London ochilishi
    session_end_utc: int = 20       # Nyu-York tushdan keyin
    friday_last_entry_utc: int = 18
    be_at_r: float = 1.0
    lock_at_r: float = 1.5
    lock_r: float = 0.5


@dataclass
class Signal:
    side: str          # "buy" | "sell"
    entry: float       # taxminiy kirish (oxirgi yopilish narxi)
    sl: float
    tp: float
    atr: float
    reason: str

    @property
    def sl_dist(self):
        return abs(self.entry - self.sl)


def in_session(t: datetime, p: Params) -> bool:
    """Savdo vaqti (UTC): ish kunlari 07:00–20:00, juma 18:00 gacha."""
    wd = t.weekday()
    if wd >= 5:
        return False
    if not (p.session_start_utc <= t.hour < p.session_end_utc):
        return False
    if wd == 4 and t.hour >= p.friday_last_entry_utc:
        return False
    return True


def trend(h1, p: Params):
    """'up' | 'down' | None — H1 yopilgan shamlar bo'yicha."""
    if len(h1) < 210:
        return None
    c = [x["close"] for x in h1]
    e50, e200 = ema(c, 50), ema(c, 200)
    a = adx([x["high"] for x in h1], [x["low"] for x in h1], c, 14)
    if e50[-1] is None or e200[-1] is None or a[-1] is None or a[-1] < p.adx_min:
        return None
    if e50[-1] > e200[-1] and c[-1] > e50[-1]:
        return "up"
    if e50[-1] < e200[-1] and c[-1] < e50[-1]:
        return "down"
    return None


def evaluate(h1, m15, p: Params = Params()):
    """Yangi kirish signali yoki None. h1, m15 — eskidan yangiga tartiblangan yopilgan shamlar."""
    if len(m15) < 60:
        return None
    tr = trend(h1, p)
    if tr is None:
        return None
    o = [x["open"] for x in m15]
    h = [x["high"] for x in m15]
    lo = [x["low"] for x in m15]
    c = [x["close"] for x in m15]
    e21 = ema(c, 21)
    a = atr(h, lo, c, 14)
    r = rsi(c, 14)
    if None in (e21[-1], a[-1], r[-1]) or a[-1] <= 0:
        return None
    A, close = a[-1], c[-1]
    k = p.pullback_bars
    recent = range(len(c) - 1 - k, len(c) - 1)  # oxirgi shamdan oldingi k ta sham

    if tr == "up":
        touched = any(e21[i] is not None and lo[i] <= e21[i] for i in recent)
        ok = (touched and close > e21[-1] and close > o[-1] and close > h[-2]
              and p.rsi_buy[0] <= r[-1] <= p.rsi_buy[1] and close - e21[-1] <= p.max_extension_atr * A)
        if not ok:
            return None
        swing = min(lo[-p.swing_bars:]) - 0.2 * A
        dist = close - swing
        if dist > p.sl_max_atr * A:
            return None
        dist = max(dist, p.sl_min_atr * A)
        return Signal("buy", close, close - dist, close + p.rr * dist, A,
                      f"H1 trend yuqoriga, M15 EMA21 dan qaytish, RSI {r[-1]:.0f}")

    touched = any(e21[i] is not None and h[i] >= e21[i] for i in recent)
    ok = (touched and close < e21[-1] and close < o[-1] and close < lo[-2]
          and p.rsi_sell[0] <= r[-1] <= p.rsi_sell[1] and e21[-1] - close <= p.max_extension_atr * A)
    if not ok:
        return None
    swing = max(h[-p.swing_bars:]) + 0.2 * A
    dist = swing - close
    if dist > p.sl_max_atr * A:
        return None
    dist = max(dist, p.sl_min_atr * A)
    return Signal("sell", close, close + dist, close - p.rr * dist, A,
                  f"H1 trend pastga, M15 EMA21 dan qaytish, RSI {r[-1]:.0f}")


def managed_stop(side, open_price, sl, tp, price, p: Params = Params()):
    """Ochiq pozitsiya uchun yangi stop-loss (yoki None — o'zgartirish kerak emas).

    R (1 birlik risk) take-profit masofasidan tiklanadi: R = |tp - open| / RR — shuning uchun
    bot qayta ishga tushsa ham hech narsa saqlash shart emas.
    """
    if not tp or not open_price:
        return None
    R = abs(tp - open_price) / p.rr
    if R <= 0:
        return None
    sign = 1 if side == "buy" else -1
    gained = (price - open_price) * sign / R
    target = None
    if gained >= p.lock_at_r:
        target = open_price + sign * p.lock_r * R
    elif gained >= p.be_at_r:
        target = open_price + sign * 0.1 * R
    if target is None:
        return None
    if sl and (target - sl) * sign <= 1e-9:  # stop allaqachon shu yerda yoki yaxshiroq
        return None
    return target
