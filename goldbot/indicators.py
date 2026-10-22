"""Texnik indikatorlar (faqat oddiy Python, tashqi kutubxonasiz).

Hamma funksiyalar ro'yxat qaytaradi, uzunligi kirish bilan bir xil;
hisoblab bo'lmaydigan boshlang'ich qiymatlar o'rnida None turadi.
"""


def ema(values, n):
    out = [None] * len(values)
    if len(values) < n:
        return out
    k = 2 / (n + 1)
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def _true_ranges(highs, lows, closes):
    tr = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    return tr


def _wilder(values, n, start=0):
    """Wilder silliqlashi: birinchi qiymat — oddiy o'rtacha, keyin (prev*(n-1)+x)/n."""
    out = [None] * len(values)
    if len(values) - start < n:
        return out
    prev = sum(values[start:start + n]) / n
    out[start + n - 1] = prev
    for i in range(start + n, len(values)):
        prev = (prev * (n - 1) + values[i]) / n
        out[i] = prev
    return out


def atr(highs, lows, closes, n=14):
    return _wilder(_true_ranges(highs, lows, closes), n)


def rsi(closes, n=14):
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains, losses = [0.0], [0.0]
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = _wilder(gains, n, start=1)
    al = _wilder(losses, n, start=1)
    for i in range(len(closes)):
        if ag[i] is None:
            continue
        if al[i] == 0:
            out[i] = 100.0 if ag[i] > 0 else 50.0
        else:
            out[i] = 100 - 100 / (1 + ag[i] / al[i])
    return out


def adx(highs, lows, closes, n=14):
    """Trend kuchi (0–100). 20 dan past — narx yonboshlab yuribdi, 25 dan yuqori — aniq trend."""
    size = len(closes)
    out = [None] * size
    if size < 2 * n + 1:
        return out
    plus_dm, minus_dm = [0.0], [0.0]
    for i in range(1, size):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    tr = _true_ranges(highs, lows, closes)
    tr_s = _wilder(tr, n, start=1)
    p_s = _wilder(plus_dm, n, start=1)
    m_s = _wilder(minus_dm, n, start=1)
    dx = [None] * size
    for i in range(size):
        if tr_s[i] is None or tr_s[i] == 0:
            continue
        pdi = 100 * p_s[i] / tr_s[i]
        mdi = 100 * m_s[i] / tr_s[i]
        dx[i] = 0.0 if pdi + mdi == 0 else 100 * abs(pdi - mdi) / (pdi + mdi)
    first = next((i for i, v in enumerate(dx) if v is not None), None)
    if first is None or size - first < n:
        return out
    prev = sum(dx[first:first + n]) / n
    out[first + n - 1] = prev
    for i in range(first + n, size):
        prev = (prev * (n - 1) + dx[i]) / n
        out[i] = prev
    return out
