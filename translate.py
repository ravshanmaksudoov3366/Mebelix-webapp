"""
O'zbekcha -> ruscha avtomatik tarjima (kalitsiz, Google Translate ochiq manzili orqali).
Tarjima bo'lmasa (internet, cheklov) — bo'sh qaytadi va keyinroq qayta urinib ko'riladi.
"""
import asyncio
import logging

import aiohttp

URL = "https://translate.googleapis.com/translate_a/single"
log = logging.getLogger("translate")
_cache: dict = {}
_sem = asyncio.Semaphore(4)


async def translate(session: aiohttp.ClientSession, text: str, src: str = "uz", tgt: str = "ru") -> str:
    text = (text or "").strip()
    if not text:
        return ""
    key = (text, src, tgt)
    if key in _cache:
        return _cache[key]
    async with _sem:
        async with session.post(URL, params={"client": "gtx", "sl": src, "tl": tgt, "dt": "t"},
                                data={"q": text}, timeout=aiohttp.ClientTimeout(total=12)) as r:
            r.raise_for_status()
            data = await r.json(content_type=None)
    out = "".join(seg[0] for seg in (data[0] or []) if seg and seg[0]).strip()
    if out:
        _cache[key] = out
    return out


async def translate_many(session: aiohttp.ClientSession, texts: list, src: str = "uz", tgt: str = "ru") -> list:
    return list(await asyncio.gather(*(translate(session, t, src, tgt) for t in texts)))
