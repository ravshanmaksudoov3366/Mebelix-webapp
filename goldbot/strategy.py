"""Oltin (XAUUSD) strategiyalari. Uchta mustaqil kirish usuli + ishonch bali (risk ko'paytirgichi).

A) «Qaytish» — katta trend bo'yicha, kichik orqaga qaytishdan keyin kirish (quyida batafsil).
B) «Osiyo diapazoni» — kechasi (00–07 UTC) oltin tor oraliqda yuradi; London ochilgach (07–11 UTC)
   shu oraliqdan H1 trend tomonga birinchi chiqishda kirish. Stop — diapazon o'rtasi orqasida.
C) «Siqilish → portlash» — narx 8 sham davomida odatdagidan ancha tor qutida yursa (volatillik
   siqilgan), so'ng trend tomonga kuchli, katta tanali sham bilan qutidan chiqsa — kirish.
   Stop — qutining narigi tomonida.
Ishonch bali (0.5–1.5): kuchli trend (ADX ≥ 30), London–Nyu-York kesishuvi (12–16 UTC) va bir nechta
usul bir xil yo'nalishni ko'rsatsa — oshadi; kech soatlarda — kamayadi. Bot riskni shu balga ko'paytiradi.

A usuli batafsil:

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
from datetime import datetime, timedelta, timezone

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
    # B) Osiyo diapazoni
    asia_end_utc: int = 7
    asia_break_from_utc: int = 7
    asia_break_to_utc: int = 11
    asia_min_width_h1atr: float = 1.0
    asia_max_width_h1atr: float = 4.0
    # C) Siqilish → portlash
    squeeze_bars: int = 8
    squeeze_box_atr: float = 1.5     # 8 shamlik quti uzoq muddatli ATR(100) ning 1.5 baravaridan tor
    squeeze_break_atr: float = 1.2   # chiqish shami odatdagidan 1.2 baravar katta


@dataclass
class Signal:
    side: str          # "buy" | "sell"
    entry: float       # taxminiy kirish (oxirgi yopilish narxi)
    sl: float
    tp: float
    atr: float
    reason: str
    name: str = "A"    # qaysi usul: A | B | C
    score: float = 1.0  # ishonch bali — risk ko'paytirgichi

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


def evaluate_pullback(h1, m15, p: Params = Params()):
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
                      f"A «Qaytish»: H1 trend yuqoriga, M15 EMA21 dan qaytish, RSI {r[-1]:.0f}")

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
                  f"A «Qaytish»: H1 trend pastga, M15 EMA21 dan qaytish, RSI {r[-1]:.0f}")


def _make(side, close, dist, A, p, reason, name):
    if dist > p.sl_max_atr * A:
        return None
    dist = max(dist, p.sl_min_atr * A)
    sign = 1 if side == "buy" else -1
    return Signal(side, close, close - sign * dist, close + sign * p.rr * dist, A, reason, name)


def evaluate_asia(h1, m15, p: Params = Params()):
    """B) Osiyo diapazonidan London ochilishida trend tomonga chiqish."""
    if len(m15) < 60:
        return None
    tr = trend(h1, p)
    if tr is None:
        return None
    last = m15[-1]
    t_close = last["time"] + timedelta(minutes=15)
    if not (p.asia_break_from_utc <= t_close.hour < p.asia_break_to_utc) or t_close.date() != last["time"].date():
        return None
    day = last["time"].date()
    asia = [x for x in m15 if x["time"].date() == day and x["time"].hour < p.asia_end_utc]
    if len(asia) < 20:  # kamida 5 soatlik ma'lumot
        return None
    hi_r, lo_r = max(x["high"] for x in asia), min(x["low"] for x in asia)
    width = hi_r - lo_r
    c = [x["close"] for x in m15]
    a = atr([x["high"] for x in m15], [x["low"] for x in m15], c, 14)
    ah = atr([x["high"] for x in h1], [x["low"] for x in h1], [x["close"] for x in h1], 14)
    if a[-1] is None or ah[-1] is None or a[-1] <= 0:
        return None
    if not (p.asia_min_width_h1atr * ah[-1] <= width <= p.asia_max_width_h1atr * ah[-1]):
        return None  # juda tor (shovqin) yoki juda keng (harakat allaqachon bo'lgan) diapazon
    mid = (hi_r + lo_r) / 2
    close, prev = c[-1], c[-2]
    body_ok = abs(close - last["open"]) >= 0.4 * (last["high"] - last["low"])
    if tr == "up" and close > hi_r and prev <= hi_r and close > last["open"] and body_ok:
        return _make("buy", close, close - (mid - 0.1 * a[-1]), a[-1], p,
                     f"B «Osiyo diapazoni»: {lo_r:.2f}–{hi_r:.2f} yuqoriga yorib o'tildi, H1 trend yuqoriga", "B")
    if tr == "down" and close < lo_r and prev >= lo_r and close < last["open"] and body_ok:
        return _make("sell", close, (mid + 0.1 * a[-1]) - close, a[-1], p,
                     f"B «Osiyo diapazoni»: {lo_r:.2f}–{hi_r:.2f} pastga yorib o'tildi, H1 trend pastga", "B")
    return None


def evaluate_squeeze(h1, m15, p: Params = Params()):
    """C) Volatillik siqilishidan keyin trend tomonga kuchli chiqish."""
    k = p.squeeze_bars
    if len(m15) < 120:
        return None
    tr = trend(h1, p)
    if tr is None:
        return None
    h = [x["high"] for x in m15]
    lo = [x["low"] for x in m15]
    c = [x["close"] for x in m15]
    a14 = atr(h, lo, c, 14)
    a100 = atr(h, lo, c, 100)
    if a14[-2] is None or a100[-2] is None or a100[-2] <= 0:
        return None
    box_h, box_l = max(h[-k - 1:-1]), min(lo[-k - 1:-1])
    if box_h - box_l > p.squeeze_box_atr * a100[-2]:
        return None  # siqilish yo'q
    last = m15[-1]
    rng = last["high"] - last["low"]
    if rng < p.squeeze_break_atr * a14[-2] or abs(last["close"] - last["open"]) < 0.6 * rng:
        return None  # chiqish shami kuchsiz
    A = a14[-1]
    if tr == "up" and last["close"] > box_h:
        return _make("buy", last["close"], last["close"] - (box_l - 0.1 * A), A, p,
                     f"C «Siqilish→portlash»: {k} shamlik tor qutidan yuqoriga chiqish, H1 trend yuqoriga", "C")
    if tr == "down" and last["close"] < box_l:
        return _make("sell", last["close"], (box_h + 0.1 * A) - last["close"], A, p,
                     f"C «Siqilish→portlash»: {k} shamlik tor qutidan pastga chiqish, H1 trend pastga", "C")
    return None


EVALUATORS = {"A": evaluate_pullback, "B": evaluate_asia, "C": evaluate_squeeze}


def score(sig, h1, all_sigs, p: Params = Params()):
    """Ishonch bali 0.5–1.5 (riskga ko'paytiriladi)."""
    s = 1.0
    a = adx([x["high"] for x in h1], [x["low"] for x in h1], [x["close"] for x in h1], 14)
    if a and a[-1] is not None and a[-1] >= 30:
        s += 0.25
    agree = sum(1 for x in all_sigs if x.side == sig.side) - 1
    s += 0.25 * min(agree, 1)
    if any(x.side != sig.side for x in all_sigs):
        s -= 0.5  # usullar bir-biriga zid — ehtiyot
    return max(0.5, min(1.5, s))


def evaluate(h1, m15, p: Params = Params(), enabled="ABC"):
    """Yoqilgan usullardan eng kuchli signal (ishonch bali bilan) yoki None."""
    sigs = [s for s in (EVALUATORS[n](h1, m15, p) for n in enabled if n in EVALUATORS) if s]
    if not sigs:
        return None
    for s in sigs:
        s.score = score(s, h1, sigs, p)
        hour = (m15[-1]["time"] + timedelta(minutes=15)).hour
        if 12 <= hour < 16:
            s.score = min(1.5, s.score + 0.25)
        elif hour >= 17:
            s.score = max(0.5, s.score - 0.25)
    order = {n: i for i, n in enumerate(enabled)}
    return max(sigs, key=lambda s: (s.score, -order.get(s.name, 9)))


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
