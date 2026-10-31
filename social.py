"""Instagram va Facebook'ga avtomatik joylash (Meta Graph API).

Admin botga rasm yuboradi → «Post», «Stories», «Ikkalasi» yoki «Karusel»ni tanlaydi → «Hozir» yoki «Navbatga».
Navbatdagilar har kuni belgilangan soatda (standart 19:00, Toshkent) bittadan chiqadi.

Sozlash (Render → Environment):
  META_TOKEN   — Business Manager'dagi tizim foydalanuvchisi (System User) tokeni, muddati «Never»
  FB_PAGE_ID   — Facebook sahifa ID si (Instagram biznes hisobi shu sahifaga bog'langan bo'lishi kerak)
  META_API_VERSION — ixtiyoriy, masalan "v23.0" (bo'sh bo'lsa — ilovaning standart versiyasi)

Bu fayl web-freymvorkka bog'liq emas: rasmlarni tayyorlash, navbat (SQLite) va Graph API so'rovlari.
"""
import asyncio
import io
import json
import logging
import os
import re
import time
import uuid

import aiohttp

log = logging.getLogger("social")

TZ_OFFSET = 5 * 3600  # Toshkent (UTC+5), yozgi vaqt yo'q
META_TOKEN = os.getenv("META_TOKEN", "").strip()
FB_PAGE_ID = os.getenv("FB_PAGE_ID", "").strip()
API_VERSION = os.getenv("META_API_VERSION", "").strip().strip("/")
GRAPH = "https://graph.facebook.com/" + (API_VERSION + "/" if API_VERSION else "")

KINDS = {"post": "📸 Post", "story": "⭕ Stories", "both": "📸 Post + ⭕ Stories", "carousel": "🖼 Karusel (bitta post)"}
STATUS = {"queued": "🗓 navbatda", "posting": "⏳ joylanmoqda", "posted": "✅ joylandi", "failed": "⚠️ xato",
          "cancelled": "❌ bekor qilindi"}
DEFAULT_TIME = "19:00"
# Har bir postga qo'shiladigan Telegram botga chaqiruv ({bot} — botning manzili bilan almashtiriladi).
# Asosiy savdo botda bo'ladi, Instagram/Facebook — mijoz jalb qiluvchi manba.
DEFAULT_CTA = "📲 Narxini bilish va buyurtma berish uchun Telegram botimizga yozing:\nt.me/{bot}"
DEFAULT_TAGS = "#isofa #mebel #mebeltoshkent #oshxonamebeli #shkaf #garderob #toshkent #мебель #мебельназаказ #ташкент"

SCHEMA = """
CREATE TABLE IF NOT EXISTS social_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, images TEXT NOT NULL, caption TEXT DEFAULT '',
    status TEXT DEFAULT 'queued', scheduled_at INTEGER DEFAULT 0, posted_at INTEGER DEFAULT 0,
    result TEXT DEFAULT '{}', error TEXT DEFAULT '', created INTEGER
);
"""


class MetaError(Exception):
    pass


def configured() -> bool:
    return bool(META_TOKEN and FB_PAGE_ID)


# ------------------------------------------------------------------ rasmlarni tayyorlash
def _open(data: bytes):
    from PIL import Image, ImageOps
    img = Image.open(io.BytesIO(data))
    return ImageOps.exif_transpose(img).convert("RGB")


def _blur_canvas(img, w: int, h: int):
    """Rasm w×h ga sig'maydigan bo'lsa — orqa fonni xiralashtirilgan nusxa bilan to'ldirib, o'rtaga qo'yadi."""
    from PIL import Image, ImageFilter, ImageEnhance
    bg = img.copy()
    k = max(w / bg.width, h / bg.height)
    bg = bg.resize((max(1, round(bg.width * k)), max(1, round(bg.height * k))))
    left, top = (bg.width - w) // 2, (bg.height - h) // 2
    bg = bg.crop((left, top, left + w, top + h)).filter(ImageFilter.GaussianBlur(40))
    bg = ImageEnhance.Brightness(bg).enhance(0.75)
    fg = img.copy()
    fg.thumbnail((w, h), Image.LANCZOS)
    if fg.width < w and fg.height < h:  # kichik rasmni kattalashtiramiz
        k = min(w / fg.width, h / fg.height)
        fg = img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)
    bg.paste(fg, ((w - fg.width) // 2, (h - fg.height) // 2))
    return bg


def prepare_feed(data: bytes, fixed: bool = False):
    """Instagram lentasi: tomonlar nisbati 4:5 … 1.91:1 bo'lishi shart. Karuselda hammasi 4:5 (1080×1350)."""
    img = _open(data)
    if fixed:
        return _blur_canvas(img, 1080, 1350)
    r = img.width / img.height
    if r < 0.8:
        w = min(1080, img.width)
        return _blur_canvas(img, w, round(w / 0.8))
    if r > 1.91:
        w = min(1440, img.width)
        return _blur_canvas(img, w, round(w / 1.91))
    img.thumbnail((1440, 1440))
    return img


def prepare_story(data: bytes):
    """Stories: 1080×1920 (9:16), rasm butunligicha o'rtada, atrofi xira fon."""
    return _blur_canvas(_open(data), 1080, 1920)


def save_jpeg(img, folder: str) -> str:
    os.makedirs(folder, exist_ok=True)
    name = uuid.uuid4().hex[:16] + ".jpg"
    img.save(os.path.join(folder, name), "JPEG", quality=90, optimize=True)
    return name


# ------------------------------------------------------------------ vaqt
def parse_time(s: str) -> str:
    m = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", s or "")
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ValueError("Vaqtni HH:MM ko'rinishida yozing, masalan 19:00")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def local_str(ts: int) -> str:
    return time.strftime("%d.%m %H:%M", time.gmtime(ts + TZ_OFFSET))


# ------------------------------------------------------------------ navbat
class SocialStore:
    def __init__(self, shop):
        self.shop = shop
        self.db = shop.db
        self.db.executescript(SCHEMA)
        self.db.execute("UPDATE social_posts SET status='queued' WHERE status='posting'")  # qayta ishga tushganda
        self.db.commit()
        self.folder = os.path.join(shop.upload_dir, "social")

    # sozlamalar
    def post_time(self) -> str:
        return self.shop.settings().get("social_time") or DEFAULT_TIME

    def set_post_time(self, s: str) -> str:
        v = parse_time(s)
        self.shop.set_setting("social_time", v)
        return v

    def tags(self) -> str:
        v = self.shop.settings().get("social_tags")
        return DEFAULT_TAGS if v is None else v

    def set_tags(self, s: str) -> str:
        v = re.sub(r"\s+", " ", s or "").strip()[:500]
        self.shop.set_setting("social_tags", v)
        return v

    def cta(self) -> str:
        v = self.shop.settings().get("social_cta")
        return DEFAULT_CTA if v is None else v

    def set_cta(self, s: str) -> str:
        v = (s or "").strip()[:400]
        self.shop.set_setting("social_cta", v)
        return v

    def next_slot(self, now: int = 0) -> int:
        """Keyingi bo'sh kun: belgilangan soatda, har kuni bittadan."""
        now = now or int(time.time())
        hh, mm = map(int, self.post_time().split(":"))
        day0 = (now + TZ_OFFSET) // 86400
        taken = {(r[0] + TZ_OFFSET) // 86400 for r in self.db.execute(
            "SELECT scheduled_at FROM social_posts WHERE status IN ('queued','posting')").fetchall()}
        for d in range(day0, day0 + 400):
            ts = d * 86400 + hh * 3600 + mm * 60 - TZ_OFFSET
            if ts > now + 60 and d not in taken:
                return ts
        return now + 86400

    def add(self, kind: str, images: list, caption: str, when: str = "queue") -> dict:
        if kind not in KINDS:
            raise ValueError("Noto'g'ri tur")
        ts = int(time.time()) if when == "now" else self.next_slot()
        cur = self.db.execute(
            "INSERT INTO social_posts(kind, images, caption, status, scheduled_at, created) VALUES (?,?,?,?,?,?)",
            (kind, json.dumps(images), caption or "", "queued", ts, int(time.time())))
        self.db.commit()
        return self.get(cur.lastrowid)

    def get(self, pid: int) -> dict:
        r = self.db.execute("SELECT * FROM social_posts WHERE id=?", (pid,)).fetchone()
        if not r:
            raise KeyError(pid)
        d = dict(r)
        d["images"] = json.loads(d["images"] or "[]")
        d["result"] = json.loads(d["result"] or "{}")
        return d

    def queued(self) -> list:
        rows = self.db.execute("SELECT id FROM social_posts WHERE status='queued' ORDER BY scheduled_at, id").fetchall()
        return [self.get(r[0]) for r in rows]

    def due(self) -> list:
        rows = self.db.execute("SELECT id FROM social_posts WHERE status='queued' AND scheduled_at<=? "
                               "ORDER BY scheduled_at, id", (int(time.time()),)).fetchall()
        return [self.get(r[0]) for r in rows]

    def set(self, pid: int, **kw):
        cols = ", ".join(f"{k}=?" for k in kw)
        vals = [json.dumps(v, ensure_ascii=False) if k == "result" else v for k, v in kw.items()]
        self.db.execute(f"UPDATE social_posts SET {cols} WHERE id=?", (*vals, pid))
        self.db.commit()

    def cancel(self, pid: int):
        self.set(pid, status="cancelled")

    def reschedule(self):
        """Post vaqti o'zgarsa — navbatdagilarni yangi soatga qayta taqsimlaymiz (tartib saqlanadi)."""
        items = self.queued()
        self.db.execute("UPDATE social_posts SET scheduled_at=0 WHERE status='queued'")
        for it in items:
            self.db.execute("UPDATE social_posts SET scheduled_at=? WHERE id=?", (self.next_slot(), it["id"]))
        self.db.commit()

    def full_caption(self, caption: str, footer: str, bot: str = "") -> str:
        text = (caption or "").strip()
        if not text:
            text = footer
        cta = self.cta()
        if cta and bot:
            cta = cta.replace("{bot}", bot)
        if cta and "{bot}" not in cta and "t.me/" not in text:  # matnda bot havolasi bo'lmasa — qo'shamiz
            text += "\n\n" + cta
        tags = self.tags()
        if tags and "#" not in text:
            text += "\n\n" + tags
        return text[:2200]


# ------------------------------------------------------------------ Graph API
class Meta:
    def __init__(self, token: str = META_TOKEN, page_id: str = FB_PAGE_ID):
        self.token, self.page_id = token, page_id
        self._page_token = ""
        self._ig_id = ""
        self.page_name, self.ig_username = "", ""

    async def _call(self, method: str, path: str, **params) -> dict:
        token = params.pop("_token", None) or self.token
        params = {k: v for k, v in params.items() if v is not None}
        params["access_token"] = token
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90)) as s:
            req = s.get(GRAPH + path, params=params) if method == "GET" else s.post(GRAPH + path, data=params)
            async with req as r:
                try:
                    data = await r.json(content_type=None)
                except Exception:
                    data = {}
        if not isinstance(data, dict) or "error" in data or r.status >= 400:
            err = (data or {}).get("error") or {} if isinstance(data, dict) else {}
            msg = err.get("error_user_msg") or err.get("message") or f"HTTP {r.status}"
            raise MetaError(msg)
        return data

    async def connect(self) -> dict:
        """Sahifa tokeni va unga bog'langan Instagram biznes hisobini topadi."""
        if not (self.token and self.page_id):
            raise MetaError("META_TOKEN yoki FB_PAGE_ID kiritilmagan")
        d = await self._call("GET", self.page_id, fields="name,access_token,instagram_business_account{id,username}")
        self.page_name = d.get("name", "")
        self._page_token = d.get("access_token") or self.token
        ig = d.get("instagram_business_account") or {}
        self._ig_id, self.ig_username = ig.get("id", ""), ig.get("username", "")
        return {"page": self.page_name, "instagram": self.ig_username}

    async def _ready(self):
        if not self._page_token:
            await self.connect()

    # Instagram
    async def _ig_wait(self, cid: str):
        for _ in range(20):
            st = (await self._call("GET", cid, fields="status_code")).get("status_code")
            if st == "FINISHED":
                return
            if st in ("ERROR", "EXPIRED"):
                raise MetaError(f"Instagram rasmni qabul qilmadi ({st})")
            await asyncio.sleep(3)
        raise MetaError("Instagram rasmni tayyorlashga ulgurmadi")

    async def _ig_publish(self, cid: str) -> str:
        await self._ig_wait(cid)
        return (await self._call("POST", f"{self._ig_id}/media_publish", creation_id=cid)).get("id", "")

    async def ig_post(self, url: str, caption: str) -> str:
        await self._ready()
        if not self._ig_id:
            raise MetaError("Facebook sahifaga Instagram biznes hisobi bog'lanmagan")
        cid = (await self._call("POST", f"{self._ig_id}/media", image_url=url, caption=caption))["id"]
        return await self._ig_publish(cid)

    async def ig_story(self, url: str) -> str:
        await self._ready()
        if not self._ig_id:
            raise MetaError("Facebook sahifaga Instagram biznes hisobi bog'lanmagan")
        cid = (await self._call("POST", f"{self._ig_id}/media", image_url=url, media_type="STORIES"))["id"]
        return await self._ig_publish(cid)

    async def ig_carousel(self, urls: list, caption: str) -> str:
        await self._ready()
        if not self._ig_id:
            raise MetaError("Facebook sahifaga Instagram biznes hisobi bog'lanmagan")
        kids = []
        for u in urls[:10]:
            c = (await self._call("POST", f"{self._ig_id}/media", image_url=u, is_carousel_item="true"))["id"]
            await self._ig_wait(c)
            kids.append(c)
        cid = (await self._call("POST", f"{self._ig_id}/media", media_type="CAROUSEL",
                                children=",".join(kids), caption=caption))["id"]
        return await self._ig_publish(cid)

    # Facebook sahifa
    async def fb_post(self, urls: list, caption: str) -> str:
        await self._ready()
        pt = self._page_token
        if len(urls) == 1:
            d = await self._call("POST", f"{self.page_id}/photos", url=urls[0], caption=caption, _token=pt)
            return d.get("post_id") or d.get("id", "")
        media = []
        for u in urls[:10]:
            d = await self._call("POST", f"{self.page_id}/photos", url=u, published="false", _token=pt)
            media.append({"media_fbid": d["id"]})
        d = await self._call("POST", f"{self.page_id}/feed", message=caption,
                             attached_media=json.dumps(media), _token=pt)
        return d.get("id", "")

    async def fb_story(self, url: str) -> str:
        await self._ready()
        pt = self._page_token
        d = await self._call("POST", f"{self.page_id}/photos", url=url, published="false", _token=pt)
        s = await self._call("POST", f"{self.page_id}/photo_stories", photo_id=d["id"], _token=pt)
        return s.get("post_id") or s.get("id", "") or "ok"


async def publish(meta: Meta, item: dict, public_url, caption: str) -> dict:
    """Bitta navbat elementini joylaydi. Har bir tarmoq alohida — biri xato bersa, boshqasi baribir chiqadi.
    Natija: {"ig_post": id | "xato: ...", "fb_post": ..., "ig_story": ..., "fb_story": ...}"""
    imgs = item["images"]  # [{"feed": "social/a.jpg", "story": "social/b.jpg"}, ...]
    out = {}

    async def run(key, coro):
        try:
            out[key] = await coro or "ok"
        except (MetaError, aiohttp.ClientError, asyncio.TimeoutError, KeyError) as e:
            out[key] = "xato: " + (str(e) or e.__class__.__name__)

    if item["kind"] in ("post", "both"):
        feed = [public_url(i["feed"]) for i in imgs]
        if len(feed) > 1:
            await run("ig_post", meta.ig_carousel(feed, caption))
        else:
            await run("ig_post", meta.ig_post(feed[0], caption))
        await run("fb_post", meta.fb_post(feed, caption))
    if item["kind"] == "carousel":
        feed = [public_url(i["feed"]) for i in imgs]
        await run("ig_post", meta.ig_carousel(feed, caption) if len(feed) > 1 else meta.ig_post(feed[0], caption))
        await run("fb_post", meta.fb_post(feed, caption))
    if item["kind"] in ("story", "both"):
        for n, i in enumerate(imgs):
            sfx = f"_{n + 1}" if len(imgs) > 1 else ""
            await run("ig_story" + sfx, meta.ig_story(public_url(i["story"])))
            await run("fb_story" + sfx, meta.fb_story(public_url(i["story"])))
    return out


NAMES = {"ig_post": "Instagram post", "fb_post": "Facebook post", "ig_story": "Instagram stories",
         "fb_story": "Facebook stories"}


def result_text(res: dict) -> str:
    lines = []
    for k, v in res.items():
        parts = k.split("_")
        name = NAMES.get("_".join(parts[:2]), k) + (f" {parts[2]}" if len(parts) > 2 else "")
        bad = str(v).startswith("xato")
        lines.append(("⚠️ " if bad else "✅ ") + name + (" — " + str(v)[5:].strip() if bad else ""))
    return "\n".join(lines)


def ok(res: dict) -> bool:
    return any(not str(v).startswith("xato") for v in res.values())
