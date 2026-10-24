"""
Mebel do'koni: Telegram bot + Mini App serveri (bitta jarayonda).
Ishga tushirish:  python app.py   (sozlamalar .env faylida)
"""
import asyncio
import hashlib
import hmac
import html
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

import aiohttp

import custom as cust
import social as soc
import sitepages
from offer import render_offer
from shop import (
    ACCEPT_ASK,
    ACCEPT_ASK_RU,
    ACTIONS,
    FLOW,
    ROLE_ACTIONS,
    awaiting_acceptance,
    next_statuses,
    role_text,
    STATUS_MESSAGES_RU,
    norm_lang,
    STATUS_MESSAGES,
    STATUSES,
    AuthError,
    Shop,
    ShopError,
    check_init_data,
    fmt_price,
    order_text,
)
from translate import translate, translate_many

BASE = Path(__file__).resolve().parent


def esc(s) -> str:
    return html.escape(str(s or ""), quote=False)


# ------------------------------------------------------------------ sozlamalar
def load_env(path: Path):
    """Oddiy .env o'quvchi (qo'shimcha kutubxonasiz)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env(BASE / ".env")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in re.findall(r"\d+", os.getenv("ADMIN_IDS", ""))}
# Buyurtmalar qo'shimcha yuboriladigan guruh (ixtiyoriy, masalan -1001234567890)
GROUP_ID = int(os.getenv("GROUP_ID") or 0)
# Buyurtmalar faqat guruhga keladi; guruh sozlanmagan bo'lsa — adminlarga
NOTIFY_CHATS = [GROUP_ID] if GROUP_ID else list(ADMIN_IDS)
# Render o'zi RENDER_EXTERNAL_URL beradi, shuning uchun u yerda WEBAPP_URL shart emas
WEBAPP_URL = (os.getenv("WEBAPP_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/") + "/"
# Telegram ichidagi ilova (Mini App) — /app; bosh sahifa (/) — hamma uchun ochiq veb-sayt
APP_URL = WEBAPP_URL + "app"
SHOP = {
    "name": os.getenv("SHOP_NAME", "iSofa"),
    "phone": os.getenv("SHOP_PHONE", ""),
    "address": os.getenv("SHOP_ADDRESS", ""),
    "bot": (os.getenv("BOT_USERNAME") or "Mebelixuz_bot").lstrip("@"),  # ishga tushganda botning o'zidan olinadi
    # Yandex Maps JavaScript API kaliti (ixtiyoriy). Bo'lsa — mijoz manzilni Yandex xaritada belgilaydi
    "ymaps_key": os.getenv("YANDEX_MAPS_KEY", ""),
    # Yandex HTTP Geokoder kaliti (ixtiyoriy) — xaritadagi nuqtaning aniq manzil nomi uchun
    "ygeo_key": os.getenv("YANDEX_GEOCODER_KEY", ""),
}
PORT = int(os.getenv("PORT", "8080"))
DB_PATH = os.getenv("DB_PATH", str(BASE / "data" / "shop.db"))
UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(BASE / "data" / "uploads"))
DEV = os.getenv("DEV") == "1"  # FAQAT sinov uchun: brauzerda Telegram'siz ochish

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("shop")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
shop = Shop(DB_PATH, UPLOAD_DIR)
cs = cust.CustomStore(shop)   # o'lchamga (individual) buyurtmalar
ss = soc.SocialStore(shop)    # Instagram / Facebook navbati
meta = soc.Meta()
CUSTOM_URL = WEBAPP_URL + "custom"
# Agar sozlamada karta bo'lmasa, .env/Render'dagi PAY_CARD dan olinadi (bir martalik)
if os.getenv("PAY_CARD") and not shop.settings()["pay_card"]:
    shop.save_settings({"pay_card": os.getenv("PAY_CARD"), "pay_owner": os.getenv("PAY_OWNER", ""),
                        "prepay_pct": os.getenv("PREPAY_PCT", "10")})
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) if BOT_TOKEN else None
dp = Dispatcher()


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# ------------------------------------------------------------------ saytdan (Telegram'siz) xaridorlar
# Ularga manfiy, juda katta ID beriladi (Telegram guruhlari ID'lari bilan to'qnashmaydi).
# Ularga botdan xabar yuborilmaydi — menejer telefon orqali bog'lanadi, holatni saytdagi «Buyurtmalarim»da ko'radi.
WEB_ID_BASE = 10 ** 15
_WEB_KEY = hashlib.sha256(b"mebelix-web:" + (BOT_TOKEN or "dev").encode()).digest()


def is_web(uid) -> bool:
    try:
        return int(uid) <= -WEB_ID_BASE
    except (TypeError, ValueError):
        return False


def web_token(uid: int) -> str:
    return f"{uid}.{hmac.new(_WEB_KEY, str(uid).encode(), hashlib.sha256).hexdigest()[:32]}"


def check_web_token(token: str) -> int:
    try:
        uid_s, sig = token.rsplit(".", 1)
        uid = int(uid_s)
    except (ValueError, AttributeError):
        return 0
    if not is_web(uid) or not hmac.compare_digest(web_token(uid), token):
        return 0
    return uid


_hits: dict = {}


def rate_ok(key: str, limit: int, per: int = 3600) -> bool:
    """Oddiy cheklov: bitta IP'dan soatiga `limit` martadan ko'p emas (spam va botlardan himoya)."""
    now = time.time()
    q = [t for t in _hits.get(key, []) if now - t < per]
    if len(q) >= limit:
        _hits[key] = q
        return False
    q.append(now)
    _hits[key] = q
    if len(_hits) > 5000:  # xotira o'smasin
        for k in [k for k, v in _hits.items() if not v or now - v[-1] > per]:
            _hits.pop(k, None)
    return True


def client_ip(request) -> str:
    return (request.headers.get("X-Forwarded-For") or request.remote or "").split(",")[0].strip()


# ------------------------------------------------------------------ mijoz tili (uz / ru)
TX = {
    "uz": {
        "hello": "Assalomu alaykum, <b>{name}</b>! 👋\n\n<b>{shop}</b> ga xush kelibsiz.\n"
                 "Tayyor mebellar katalogini ko'ring va bir necha bosishda buyurtma bering 👇",
        "ask": "\n\n❓ Savollaringiz bo'lsa, adminga yozing: {contact}",
        "no_chat": "Bu botga xabar yozib bo'lmaydi 🙏\n\n❓ Savollaringiz bo'lsa, adminga yozing: {contact}",
        "open": "🛋 Katalogni ochish",
        "open_ready": "🛋 Tayyor mebellar",
        "open_custom": "📐 O'lchamga buyurtma",
        "custom_hint": "\n\n🛋 <b>Tayyor mebellar</b> — katalogdan tanlab, tez olasiz.\n📐 <b>O'lchamga buyurtma</b> — xonangizga moslab, "
                       "o'zingiz xohlagan o'lcham va matoda yasab beramiz.",
        "custom_sent": "📐 <b>Arizangiz qabul qilindi!</b> №{id}\n\nMenejer tez orada qo'ng'iroq qilib, narx va "
                       "o'lchov vaqtini kelishadi. Ariza holatini «O'lchamga buyurtma» → «Arizalarim»da ko'rasiz.",
        "menu": "🛋 Do'kon",
        "sent": "Xabaringiz menejerga yuborildi. Tez orada javob beramiz 🙏",
        "manager": "💬 <b>Menejer:</b>",
        "lang_set": "✅ Til: O'zbekcha",
        "order_sent": "📨 <b>Buyurtmangiz va to'lov chekingiz yuborildi!</b>",
        "order_wait": "🧾 Chekingiz tekshirilgach, buyurtma qabul qilingani haqida shu yerga xabar keladi.",
        "auth": "Ruxsat yo'q. Ilovani bot orqali qayta oching.",
    },
    "ru": {
        "hello": "Здравствуйте, <b>{name}</b>! 👋\n\nДобро пожаловать в <b>{shop}</b>.\n"
                 "Смотрите каталог готовой мебели и оформляйте заказ в пару нажатий 👇",
        "ask": "\n\n❓ Если есть вопросы, пишите администратору: {contact}",
        "no_chat": "В этот бот нельзя писать сообщения 🙏\n\n❓ Если есть вопросы, пишите администратору: {contact}",
        "open": "🛋 Открыть каталог",
        "open_ready": "🛋 Готовая мебель",
        "open_custom": "📐 Мебель на заказ",
        "custom_hint": "\n\n🛋 <b>Готовая мебель</b> — выбираете в каталоге и быстро получаете.\n📐 <b>Мебель на заказ</b> — сделаем "
                       "под вашу комнату, в нужном размере и ткани.",
        "custom_sent": "📐 <b>Заявка принята!</b> №{id}\n\nМенеджер скоро позвонит, проконсультирует по цене "
                       "и согласует время замера. "
                       "Статус заявки — в разделе «Мебель на заказ» → «Мои заявки».",
        "menu": "🛋 Магазин",
        "sent": "Ваше сообщение отправлено менеджеру. Скоро ответим 🙏",
        "manager": "💬 <b>Менеджер:</b>",
        "lang_set": "✅ Язык: Русский",
        "order_sent": "📨 <b>Ваш заказ и чек об оплате отправлены!</b>",
        "order_wait": "🧾 После проверки чека сюда придёт сообщение о том, что заказ принят.",
        "auth": "Нет доступа. Откройте приложение заново через бота.",
    },
}
LANG_PICK = "🇺🇿 Tilni tanlang\n🇷🇺 Выберите язык"


def lang_of(uid: int) -> str:
    return shop.user_lang(uid) or "uz"


def tx(lang: str, key: str, **kw) -> str:
    return TX[norm_lang(lang)][key].format(**kw)


def admin_contact() -> str:
    """Mijozlar savol uchun yozadigan admin: @nik (sozlamalardan), bo'lmasa do'kon telefoni."""
    nick = shop.settings().get("admin_contact", "")
    if nick:
        return "@" + esc(nick)
    return esc(SHOP["phone"]) or "—"


# ------------------------------------------------------------------ bildirishnomalar
def chat_role(chat_id: int) -> str:
    """Qaysi chat qaysi rolga tegishli: kuryerlar va yig'uvchilar guruhi — sozlamalardan, qolgani — admin."""
    st = shop.settings()
    if st.get("courier_chat") and str(chat_id) == st["courier_chat"]:
        return "courier"
    if st.get("assembler_chat") and str(chat_id) == st["assembler_chat"]:
        return "assembler"
    return "admin"


def status_keyboard(o: dict, chat_id: int = 1, role: str = "admin") -> InlineKeyboardMarkup:
    nxt = next_statuses(o)
    if role == "assembler" and o["status"] not in ("assembled", "done", "cancelled", "rejected"):
        if not (o.get("assembler") or {}).get("id"):
            btns = [InlineKeyboardButton(text="🙋 Men yig'aman", callback_data=f"claim:{o['id']}")]
        else:
            labels = ROLE_ACTIONS[role]
            btns = [InlineKeyboardButton(text=labels[s], callback_data=f"st:{o['id']}:{s}") for s in nxt if s in labels]
            btns.append(InlineKeyboardButton(text="↩️ Voz kechish", callback_data=f"release:{o['id']}"))
    elif role in ROLE_ACTIONS:
        labels = ROLE_ACTIONS[role]
        btns = [InlineKeyboardButton(text=labels[s], callback_data=f"st:{o['id']}:{s}") for s in nxt if s in labels]
    else:
        btns = [InlineKeyboardButton(text=ACTIONS[s], callback_data=f"st:{o['id']}:{s}") for s in nxt]
    rows = [btns[i:i + 2] for i in range(0, len(btns), 2)]
    if chat_id > 0 and role == "admin":  # Mini App tugmasi guruhlarda ishlamaydi
        rows.append([InlineKeyboardButton(text="🗂 Admin panel", web_app=WebAppInfo(url=APP_URL + "?admin=1"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def act_key(oid: int) -> str:
    """Dalolatnoma havolasi uchun imzo (havolani taxmin qilib bo'lmasin)."""
    return hmac.new(BOT_TOKEN.encode() or b"dev", f"act:{oid}".encode(), hashlib.sha256).hexdigest()[:20]


def order_photos(o: dict, role: str = "admin") -> list:
    """Har bir mahsulotning asosiy rasmi va izohi: [[fayl yo'li, izoh], ...] (Telegram albomi — ko'pi bilan 10).
    Yig'uvchiga faqat yig'iladigan mahsulotlar, narxsiz."""
    out = []
    for i in o["items"]:
        img = i.get("image")
        if not img or (role == "assembler" and not i.get("assembly")):
            continue
        path = os.path.join(UPLOAD_DIR, os.path.basename(img))
        if os.path.isfile(path):
            if role == "assembler":
                cap = f"<b>{esc(i['name'])}</b>\n{i['qty']} ta"
            else:
                cap = f"<b>{esc(i['name'])}</b>\n{i['qty']} ta × {fmt_price(i['price'])} = {fmt_price(i['price'] * i['qty'])}"
                if i.get("delivery_days"):
                    cap += f"\n🚚 Yetkazish: {esc(i['delivery_days'])}"
            out.append([path, cap])
    return out[:10]


def _media(m: str):
    # birinchi yuborishda fayl, keyingi chatlarga Telegram file_id (qayta yuklamaslik uchun)
    return FSInputFile(m) if os.path.isfile(m) else m


async def send_order_to(chat_id: int, o: dict, media: dict, role: str = "admin") -> list:
    """Mahsulotlar rasmlari (albom) -> buyurtma ma'lumoti va tugmalar -> chek rasmi (faqat adminga)."""
    text = ("🔔 " + order_text(o, for_admin=True)) if role == "admin" else role_text(o, role)
    kb = status_keyboard(o, chat_id, role)
    photos = media.get("photos") or []
    if len(photos) == 1 and len(text) <= 1024:
        # bitta mahsulot: rasm + buyurtma ma'lumoti bitta xabarda
        m = await bot.send_photo(chat_id, _media(photos[0][0]), caption=text, reply_markup=kb)
        photos[0][0] = m.photo[-1].file_id
        entry = [chat_id, m.message_id, "photo"]
    else:
        if len(photos) == 1:
            sent = [await bot.send_photo(chat_id, _media(photos[0][0]), caption=photos[0][1])]
        elif photos:
            sent = await bot.send_media_group(
                chat_id, [InputMediaPhoto(media=_media(p), caption=c) for p, c in photos])
        else:
            sent = []
        for ph, sm in zip(photos, sent):
            if sm.photo:
                ph[0] = sm.photo[-1].file_id
        m = await bot.send_message(chat_id, text, reply_markup=kb)
        entry = [chat_id, m.message_id, "text"]
    entry.append(role)
    if media.get("receipt") and role == "admin":
        try:
            r = await bot.send_photo(chat_id, _media(media["receipt"]), reply_to_message_id=m.message_id,
                                     caption=f"🧾 Buyurtma #{o['id']} — oldindan to'lov cheki "
                                             f"({fmt_price(o['prepay'])})")
            media["receipt"] = r.photo[-1].file_id
        except TelegramAPIError as e:
            log.warning("chek yuborilmadi %s: %s", chat_id, e)
    return entry


async def notify_new_order(o: dict):
    if not bot:
        return
    msgs = []
    media = {"photos": order_photos(o), "receipt": shop.receipt_path(o)}
    for aid in NOTIFY_CHATS:
        try:
            msgs.append(await send_order_to(aid, o, media))
        except TelegramAPIError as e:
            log.warning("rasmli xabar yuborilmadi %s: %s", aid, e)
            try:  # rasm bilan muammo bo'lsa, hech bo'lmasa matn borsin
                m = await bot.send_message(aid, "🔔 " + order_text(o, for_admin=True),
                                           reply_markup=status_keyboard(o, aid))
                msgs.append([aid, m.message_id, "text"])
            except TelegramAPIError as e2:
                log.warning("adminga yuborilmadi %s: %s", aid, e2)
    if not msgs and GROUP_ID:
        # guruhga yetib bormadi (bot guruhdan chiqarilgan va h.k.) — buyurtma yo'qolmasin, adminlarga yuboramiz
        for aid in ADMIN_IDS:
            try:
                await bot.send_message(aid, "⚠️ Buyurtma guruhga yuborilmadi (bot guruhda a'zo ekanini tekshiring).")
                msgs.append(await send_order_to(aid, o, media))
            except TelegramAPIError as e:
                log.warning("zaxira: adminga yuborilmadi %s: %s", aid, e)
    st = shop.settings()
    for role, key, need in (("courier", "courier_chat", o["delivery"] == "delivery"),
                            ("assembler", "assembler_chat", bool(o.get("assembly")))):
        if not (need and st.get(key)):
            continue
        try:
            msgs.append(await send_order_to(int(st[key]), o, {"photos": order_photos(o, role)}, role))
        except (TelegramAPIError, ValueError) as e:
            log.warning("%s guruhiga yuborilmadi: %s", role, e)
            await alert_admins(f"⚠️ Buyurtma #{o['id']} {ROLE_NAMES[role]} guruhiga yuborilmadi: {esc(e)}\n"
                               "Bot o'sha guruhda a'zo ekanini tekshiring.")
    shop.set_admin_msgs(o["id"], msgs)
    if is_web(o["user_id"]):
        return
    try:
        await bot.send_message(
            o["user_id"],
            tx(lang_of(o["user_id"]), "order_sent") + "\n\n" + order_text(o, False, lang_of(o["user_id"]))
            + "\n\n" + tx(lang_of(o["user_id"]), "order_wait"))
    except TelegramAPIError as e:
        log.warning("mijozga yuborilmadi: %s", e)


async def notify_status(o: dict):
    if not bot:
        return
    await refresh_order_messages(o)
    await ping_next_role(o)
    if is_web(o["user_id"]):
        return
    lang = lang_of(o["user_id"])
    text = (STATUS_MESSAGES_RU if lang == "ru" else STATUS_MESSAGES).get(o["status"])
    if text:
        try:
            await bot.send_message(o["user_id"], text.format(id=o["id"]))
        except TelegramAPIError:
            pass
    if awaiting_acceptance(o):
        await ask_acceptance(o)


async def refresh_order_messages(o: dict):
    """Barcha guruhlardagi buyurtma xabarini (har biriga o'z matni va tugmalari bilan) yangilaydi."""
    if not bot:
        return
    for entry in o["admin_msgs"]:
        chat_id, msg_id = entry[0], entry[1]
        kind = entry[2] if len(entry) > 2 else "text"
        role = entry[3] if len(entry) > 3 else "admin"
        text = ("🔔 " + order_text(o, for_admin=True)) if role == "admin" else role_text(o, role)
        kb = status_keyboard(o, chat_id, role)
        try:
            if kind == "photo":
                await bot.edit_message_caption(chat_id=chat_id, message_id=msg_id, caption=text[:1024], reply_markup=kb)
            else:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=kb)
        except TelegramAPIError:
            pass


ROLE_NAMES = {"courier": "kuryerlar", "assembler": "yig'uvchilar", "admin": "admin"}


async def alert_admins(text: str):
    for aid in NOTIFY_CHATS:
        try:
            await bot.send_message(aid, text)
        except TelegramAPIError:
            pass


async def ping_next_role(o: dict):
    """Keyingi bosqich egasiga qisqa xabar (tahrirlangan xabar Telegram'da bildirishnoma bermaydi)."""
    target = None
    if o["status"] == "confirmed" and o["delivery"] == "delivery":
        target, text = "courier", f"✅ Buyurtma #{o['id']} tasdiqlandi — olib ketishga tayyor."
    elif o["status"] == "delivered" and o.get("assembly"):
        target, text = "assembler", f"📦 Buyurtma #{o['id']} mijozga yetkazildi — yig'ishga boring."
    if not target:
        return
    for entry in o["admin_msgs"]:
        if len(entry) > 3 and entry[3] == target:
            try:
                await bot.send_message(entry[0], text, reply_to_message_id=entry[1])
            except TelegramAPIError:
                pass


async def ask_acceptance(o: dict):
    if is_web(o["user_id"]):
        return
    lang = lang_of(o["user_id"])
    ru = lang == "ru"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Проверил, принимаю" if ru else "✅ Tekshirdim, qabul qildim",
                              callback_data=f"acc:{o['id']}:ok")],
        [InlineKeyboardButton(text="⚠️ Есть проблема" if ru else "⚠️ Muammo bor", callback_data=f"acc:{o['id']}:bad")]])
    head = f"<b>{'Заказ' if ru else 'Buyurtma'} #{o['id']}</b>\n\n"
    try:
        await bot.send_message(o["user_id"], head + (ACCEPT_ASK_RU if ru else ACCEPT_ASK), reply_markup=kb)
    except TelegramAPIError as e:
        log.warning("qabul savoli yuborilmadi: %s", e)


async def register_user(user: dict):
    """Mijozni bazaga yozadi; yangi bo'lsa — adminlarga xabar (sozlamada o'chirib qo'yish mumkin)."""
    if not shop.touch_user(user) or not bot or shop.settings().get("notify_new_users") != "1":
        return
    name = esc(" ".join(x for x in (user.get("first_name"), user.get("last_name")) if x) or "—")
    uname = f" (@{esc(user['username'])})" if user.get("username") else ""
    if is_web(user["id"]):
        uname = " (🌐 saytdan, Telegram'siz)"
    st = shop.customer_stats()
    text = (f"👤 <b>Yangi mijoz qo'shildi</b>\n{name}{uname}\nID: <code>{user['id']}</code>\n\n"
            f"👥 Jami mijozlar: <b>{st['total']}</b> · bugun: {st['today']}")
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid, text)
        except TelegramAPIError:
            pass


# ------------------------------------------------------------------ bot
def shop_button(text="", suffix="", lang="uz") -> InlineKeyboardMarkup:
    lang = norm_lang(lang)
    sep = "&" if "?" in suffix else "?"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=text or tx(lang, "open"), web_app=WebAppInfo(url=f"{APP_URL}{suffix}{sep}lang={lang}"))]])


def two_doors(lang="uz") -> InlineKeyboardMarkup:
    """Ikki eshik: tayyor mebellar katalogi va o'lchamga buyurtma — mijoz chalkashmasligi uchun alohida ilovalar."""
    lang = norm_lang(lang)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tx(lang, "open_ready"), web_app=WebAppInfo(url=f"{APP_URL}?lang={lang}"))],
        [InlineKeyboardButton(text=tx(lang, "open_custom"), web_app=WebAppInfo(url=f"{CUSTOM_URL}?lang={lang}"))]])


def lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang:uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru")]])


_start_args: dict = {}   # til tanlanguncha saqlab turiladigan /start parametri (masalan saytdan p12)


def start_suffix(arg: str) -> str:
    """Saytdagi «Telegram orqali buyurtma» havolasi: /start p12 — ilova shu mahsulot bilan ochiladi."""
    return f"?p={arg[1:]}" if re.fullmatch(r"p\d{1,9}", arg or "") else ""


async def send_welcome(chat_id: int, user, lang: str, suffix: str = ""):
    text = tx(lang, "hello", name=esc(user.first_name or ""), shop=esc(SHOP["name"]))
    if SHOP["phone"]:
        text += f"\n\n📞 {esc(SHOP['phone'])}"
    if SHOP["address"]:
        text += f"\n📍 {esc(SHOP['address'])}"
    text += tx(lang, "custom_hint") + tx(lang, "ask", contact=admin_contact())
    await bot.send_message(chat_id, text, reply_markup=two_doors(lang))
    if suffix:
        try:
            p = shop.localize_product(shop.product(int(suffix.split("=")[1])), lang)
            await bot.send_message(chat_id, f"🛋 <b>{esc(p['name'])}</b>\n{fmt_price(p['price'], lang)}",
                                   reply_markup=shop_button(tx(lang, "open"), suffix, lang))
        except (ShopError, ValueError, TelegramAPIError):
            pass
    try:  # pastdagi menyu tugmasi ham mijoz tilida
        await bot.set_chat_menu_button(chat_id=chat_id, menu_button=MenuButtonWebApp(
            text=tx(lang, "menu"), web_app=WebAppInfo(url=f"{APP_URL}?lang={lang}")))
    except TelegramAPIError:
        pass
    if is_admin(user.id):
        await bot.send_message(chat_id, "Siz adminsiz. Mahsulot va buyurtmalarni boshqarish:",
                               reply_markup=shop_button("🗂 Admin panel", "?admin=1"))


@dp.message(CommandStart())
async def cmd_start(m: Message):
    await register_user(m.from_user.model_dump())
    lang = shop.user_lang(m.from_user.id)
    parts = (m.text or "").split(maxsplit=1)
    suffix = start_suffix(parts[1].strip() if len(parts) > 1 else "")
    if not lang:  # birinchi marta — avval tilni tanlaydi
        if suffix:
            _start_args[m.from_user.id] = suffix
        return await m.answer(LANG_PICK, reply_markup=lang_keyboard())
    await send_welcome(m.chat.id, m.from_user, lang, suffix)


@dp.message(Command("lang", "til", "language"))
async def cmd_lang(m: Message):
    await m.answer(LANG_PICK, reply_markup=lang_keyboard())


@dp.callback_query(F.data.startswith("lang:"))
async def cb_lang(c: CallbackQuery):
    lang = shop.set_user_lang(c.from_user.id, c.data.split(":", 1)[1])
    await c.answer(tx(lang, "lang_set"))
    try:
        await c.message.edit_text(tx(lang, "lang_set"))
    except TelegramAPIError:
        pass
    await send_welcome(c.message.chat.id, c.from_user, lang, _start_args.pop(c.from_user.id, ""))


@dp.message(Command("admin"))
async def cmd_admin(m: Message):
    if is_admin(m.from_user.id):
        await m.answer("🗂 Admin panel:\n\n📲 Instagram/Facebook: shu yerga rasm yuboring (matnini rasm ostiga yozing).\n"
                       "/meta — ulanish va sozlamalar · /navbat — navbatdagi postlar",
                       reply_markup=shop_button("🗂 Admin panelni ochish", "?admin=1"))
    else:
        await m.answer(f"Sizning ID: <code>{m.from_user.id}</code>\nAdmin emassiz.")


@dp.message(Command("id"))
async def cmd_id(m: Message):
    await m.answer(f"Sizning Telegram ID: <code>{m.from_user.id}</code>")


@dp.callback_query(F.data.startswith("cs:"))
async def cb_custom_stage(c: CallbackQuery):
    """Guruhdagi individual ariza tugmalari (faqat admin)."""
    if not is_admin(c.from_user.id):
        return await c.answer("Ruxsat yo'q", show_alert=True)
    _, rid, status = c.data.split(":")
    try:
        r = cs.set_status(int(rid), status, who=f"admin: {c.from_user.full_name}")
    except ShopError as e:
        return await c.answer(str(e), show_alert=True)
    await notify_custom_status(r)
    await c.answer(cust.stage_name(status))


@dp.callback_query(F.data.startswith("st:"))
async def cb_status(c: CallbackQuery):
    role = chat_role(c.message.chat.id) if c.message else "admin"
    if role == "admin" and not is_admin(c.from_user.id):
        return await c.answer("Ruxsat yo'q", show_alert=True)
    _, oid, status = c.data.split(":")
    who = c.from_user.full_name + (f" (@{c.from_user.username})" if c.from_user.username else "")
    try:
        o = shop.set_status(int(oid), status, role=role, who=f"{ROLE_NAMES[role]}: {who}", actor_id=c.from_user.id)
    except ShopError as e:
        return await c.answer(str(e), show_alert=True)
    await notify_status(o)
    if role != "admin":
        await alert_admins(f"{o['status_text']} — buyurtma #{o['id']} ({esc(who)})")
    await c.answer(o["status_text"])


@dp.callback_query(F.data.startswith("claim:") | F.data.startswith("release:"))
async def cb_claim(c: CallbackQuery):
    """Yig'uvchilar guruhida: «Men yig'aman» / «Voz kechish»."""
    if chat_role(c.message.chat.id) != "assembler":
        return await c.answer("Bu tugma faqat yig'uvchilar guruhida ishlaydi", show_alert=True)
    kind, oid = c.data.split(":")
    name = c.from_user.full_name + (f" (@{c.from_user.username})" if c.from_user.username else "")
    try:
        if kind == "claim":
            o = shop.claim_assembly(int(oid), c.from_user.id, name)
        else:
            o = shop.release_assembly(int(oid), c.from_user.id)
    except ShopError as e:
        return await c.answer(str(e), show_alert=True)
    await refresh_order_messages(o)
    if kind == "claim":
        await alert_admins(f"👷 <b>{esc(name)}</b> buyurtma #{o['id']} ni yig'ishni oldi.")
        await c.answer("✅ Buyurtma sizga biriktirildi")
    else:
        await alert_admins(f"↩️ {esc(name)} buyurtma #{o['id']} ni yig'ishdan voz kechdi — boshqa yig'uvchi kerak.")
        await c.answer("Voz kechdingiz")


@dp.callback_query(F.data.startswith("acc:"))
async def cb_accept(c: CallbackQuery):
    """Mijoz: «Tekshirdim, qabul qildim» yoki «Muammo bor»."""
    _, oid, ans = c.data.split(":")
    lang = lang_of(c.from_user.id)
    ru = lang == "ru"
    if ans == "ok":
        try:
            o = shop.accept_by_user(c.from_user.id, int(oid))
        except ShopError as e:
            return await c.answer(e.text(lang), show_alert=True)
        try:
            await c.message.edit_text(c.message.html_text + "\n\n" + ("✅ Вы подтвердили приёмку. Спасибо!" if ru
                                                                        else "✅ Qabul qilganingiz tasdiqlandi. Rahmat!"))
        except TelegramAPIError:
            pass
        await notify_status(o)
        await alert_admins(f"🤝 Mijoz buyurtma #{o['id']} ni tekshirib qabul qildi (botda tasdiqladi).")
        return await c.answer("✅")
    try:
        o = shop.order(int(oid))
    except ShopError:
        return await c.answer()
    if o["user_id"] != c.from_user.id:
        return await c.answer()
    await alert_admins(f"⚠️ <b>Mijoz buyurtma #{o['id']} bo'yicha muammo bildirdi!</b>\n"
                       f"👤 {esc(o['name'])}, 📞 {esc(o['phone'])}\nTezda bog'laning.")
    try:
        await c.message.edit_reply_markup(reply_markup=None)
        await c.message.answer(("Менеджер скоро свяжется с вами. Опишите проблему и отправьте фото администратору: "
                                if ru else "Menejer tez orada siz bilan bog'lanadi. Muammoni yozib, suratini adminga "
                                           "yuboring: ") + admin_contact())
    except TelegramAPIError:
        pass
    await c.answer()


@dp.message(Command("kuryer_guruhi", "yiguvchi_guruhi"))
async def cmd_link_group(m: Message):
    """Admin kuryerlar/yig'uvchilar guruhida shu buyruqni yozsa — guruh ulanadi."""
    role = "courier" if m.text.lstrip("/").startswith("kuryer") else "assembler"
    if m.chat.type == "private":
        return await m.answer("Bu buyruqni kuryerlar yoki yig'uvchilar <b>guruhining o'zida</b> yozing "
                              "(avval botni o'sha guruhga qo'shing).")
    if not is_admin(m.from_user.id):
        return await m.answer("Guruhni faqat do'kon admini ulay oladi.")
    if GROUP_ID and m.chat.id == GROUP_ID:
        return await m.answer("Bu asosiy (admin) guruh. Kuryerlar va yig'uvchilar uchun alohida guruh oching.")
    other = "assembler_chat" if role == "courier" else "courier_chat"
    if shop.settings().get(other) == str(m.chat.id):
        shop.set_setting(other, "")
        shop.set_setting(other + "_title", "")
    shop.set_setting(f"{role}_chat", str(m.chat.id))
    shop.set_setting(f"{role}_chat_title", m.chat.title or "")
    what = ("🚚 Kuryerlar guruhi ulandi. Yangi buyurtmalar shu yerga keladi: mijoz, manzil, xarita, "
            "qayerdan olish va mijozdan olinadigan summa. Tugmalar: «Yo'lga chiqdim», «Yetkazib berdim».")
    if role == "assembler":
        what = ("🔧 Yig'uvchilar guruhi ulandi. Yig'ib berish so'ralgan buyurtmalar shu yerga keladi: mijoz, manzil "
                "va yig'iladigan mahsulotlar (narxlarsiz). Tugma: «Yig'ib bo'ldim».")
    await m.answer(what + "\n\n📷 Ish suratini buyurtma xabariga «Reply» qilib yuborsangiz, adminga boradi.")


@dp.message(F.photo, F.reply_to_message, F.chat.type.in_({"group", "supergroup"}))
async def group_proof_photo(m: Message):
    """Kuryer/yig'uvchi buyurtma xabariga javoban surat yuborsa — buyurtmaga biriktiriladi va adminga boradi."""
    o = shop.order_by_message(m.chat.id, m.reply_to_message.message_id)
    if not o:
        return
    role = chat_role(m.chat.id)
    who = m.from_user.full_name if m.from_user else ""
    file_id = m.photo[-1].file_id
    shop.add_proof(o["id"], file_id, f"{ROLE_NAMES[role]}: {who}")
    if role != "admin":
        for aid in NOTIFY_CHATS:
            try:
                await bot.send_photo(aid, file_id, caption=f"📷 Buyurtma #{o['id']} — {ROLE_NAMES[role]} ({esc(who)})")
            except TelegramAPIError:
                pass
    try:
        await m.reply("📷 Surat buyurtma #%d ga biriktirildi ✓" % o["id"])
    except TelegramAPIError:
        pass


@dp.message(F.chat.type == "private", F.text, F.reply_to_message)
async def admin_reply(m: Message):
    """Admin mijoz xabariga «Reply» qilsa, javob mijozga boradi."""
    if not is_admin(m.from_user.id):
        return await user_message(m)
    src = m.reply_to_message.text or m.reply_to_message.caption or ""
    found = re.search(r"#u(\d+)", src)
    if not found:
        return await m.answer("Javob berish uchun mijoz xabariga «Reply» qiling.")
    try:
        uid = int(found.group(1))
        await bot.send_message(uid, f"{tx(lang_of(uid), 'manager')}\n{esc(m.text)}")
        await m.answer("✅ Yuborildi")
    except TelegramAPIError as e:
        await m.answer(f"Yuborilmadi: {e}")


# Admin botga oddiy matn yozsa — tasdiqlagach barcha mijozlarga yuboriladi
_pending_bc: dict = {}   # admin xabari id -> matn


@dp.message(F.chat.type == "private", F.text)
async def user_message(m: Message):
    if not is_admin(m.from_user.id):
        return await refuse_user(m)
    text = (m.text or "").strip()
    if not text or text.startswith("/"):
        return await m.answer("Mijozlarga xabar yuborish uchun matnni shu yerga yozing.",
                              reply_markup=shop_button("🗂 Admin panel", "?admin=1"))
    _pending_bc[m.message_id] = text
    n = len(shop.user_ids())
    await m.reply(f"📣 Shu xabar barcha mijozlarga (<b>{n}</b> ta) yuborilsinmi?",
                  reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                      InlineKeyboardButton(text="✅ Yuborish", callback_data=f"bc:yes:{m.message_id}"),
                      InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"bc:no:{m.message_id}")]]))


@dp.callback_query(F.data.startswith("bc:"))
async def cb_broadcast(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        return await c.answer("Ruxsat yo'q", show_alert=True)
    _, ans, mid = c.data.split(":")
    text = _pending_bc.pop(int(mid), None)
    if ans != "yes":
        await c.message.edit_text("❌ Bekor qilindi. Xabar hech kimga yuborilmadi.")
        return await c.answer()
    if not text:
        await c.message.edit_text("Bu xabar eskirgan. Matnni qaytadan yozing.")
        return await c.answer()
    n = start_broadcast(text)
    await c.message.edit_text(f"⏳ Xabar {n} ta mijozga yuborilmoqda… Tugagach shu yerga xabar keladi.")
    await c.answer("✅")


# ------------------------------------------------------------------ Instagram / Facebook (admin rasm yuboradi)
_albums: dict = {}          # media_group_id -> {"chat", "files", "caption"}
_social_pending: dict = {}  # kalit -> {"files": [file_id], "caption": str}


def social_url(rel: str) -> str:
    return WEBAPP_URL + "uploads/" + rel


def social_footer() -> str:
    lines = [f"✨ {SHOP['name']} — mebel o'lchamingizga moslab", "📏 Usta uyingizga kelib o'lchaydi"]
    if cs.call_phone():
        lines.append(f"📞 {cs.call_phone()}")
    lines.append(f"🛋 Katalog va buyurtma: t.me/{SHOP['bot']}")
    return "\n".join(lines)


async def social_ask(chat_id: int, files: list, caption: str):
    key = uuid.uuid4().hex[:8]
    _social_pending[key] = {"files": files[:10], "caption": caption}
    n = len(files[:10])
    rows = [[InlineKeyboardButton(text="📸 Post", callback_data=f"so:{key}:post"),
             InlineKeyboardButton(text="⭕ Stories", callback_data=f"so:{key}:story")],
            [InlineKeyboardButton(text="📸 Post + ⭕ Stories", callback_data=f"so:{key}:both")]]
    if n > 1:
        rows.append([InlineKeyboardButton(text="🖼 Karusel — bitta postda hammasi", callback_data=f"so:{key}:carousel")])
    rows.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"so:{key}:no")])
    text = f"📲 <b>{n} ta rasm.</b> Instagram va Facebook'ga qanday joylaymiz?"
    text += f"\n\n📝 Matn: {esc(caption[:300])}" if caption else "\n\n📝 Matn yozilmagan — standart matn va heshteglar qo'yiladi."
    if not soc.configured():
        text += "\n\n⚠️ Meta hali ulanmagan (META_TOKEN, FB_PAGE_ID). Navbatga qo'yaveraman — ulangach chiqadi."
    await bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def _album_done(gid: str):
    await asyncio.sleep(1.5)
    a = _albums.pop(gid, None)
    if a:
        await social_ask(a["chat"], a["files"], a["caption"])


@dp.message(F.chat.type == "private", F.photo | F.document.mime_type.startswith("image/"))
async def admin_photo(m: Message):
    """Admin rasm yuborsa — Instagram/Facebook'ga joylashni taklif qilamiz (albom bo'lsa, birga)."""
    if not is_admin(m.from_user.id):
        return await refuse_user(m)
    fid = m.photo[-1].file_id if m.photo else m.document.file_id
    cap = (m.caption or "").strip()
    if m.media_group_id:
        a = _albums.setdefault(m.media_group_id, {"chat": m.chat.id, "files": [], "caption": ""})
        a["files"].append(fid)
        a["caption"] = a["caption"] or cap
        if len(a["files"]) == 1:
            asyncio.create_task(_album_done(m.media_group_id))
        return
    await social_ask(m.chat.id, [fid], cap)


@dp.callback_query(F.data.startswith("so:"))
async def cb_social_kind(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        return await c.answer("Ruxsat yo'q", show_alert=True)
    _, key, kind = c.data.split(":")
    if kind == "no":
        _social_pending.pop(key, None)
        await c.message.edit_text("❌ Bekor qilindi.")
        return await c.answer()
    if key not in _social_pending:
        await c.message.edit_text("Bu so'rov eskirgan. Rasmni qaytadan yuboring.")
        return await c.answer()
    p = _social_pending[key]
    split = kind != "carousel" and len(p["files"]) > 1
    slot = soc.local_str(ss.next_slot())
    q = (f"Har bir rasm alohida kunga, {ss.post_time()} da" if split else f"{slot} da")
    await c.message.edit_text(f"{soc.KINDS[kind]} · {len(p['files'])} ta rasm\n\nQachon joylaymiz?",
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                  [InlineKeyboardButton(text="⚡ Hozir", callback_data=f"sw:{key}:{kind}:now")],
                                  [InlineKeyboardButton(text=f"🗓 Navbatga ({q})", callback_data=f"sw:{key}:{kind}:queue")],
                                  [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"so:{key}:no")]]))
    await c.answer()


def _prepare(datas: list, kind: str, fixed: bool) -> list:
    folder = ss.folder
    out = []
    for d in datas:
        it = {}
        if kind in ("post", "both", "carousel"):
            it["feed"] = "social/" + soc.save_jpeg(soc.prepare_feed(d, fixed), folder)
        if kind in ("story", "both"):
            it["story"] = "social/" + soc.save_jpeg(soc.prepare_story(d), folder)
        out.append(it)
    return out


async def social_publish(item: dict) -> dict:
    ss.set(item["id"], status="posting")
    res = await soc.publish(meta, item, social_url, ss.full_caption(item["caption"], social_footer()))
    good = soc.ok(res)
    ss.set(item["id"], status="posted" if good else "failed", posted_at=int(time.time()), result=res,
           error="" if good else "; ".join(str(v) for v in res.values())[:500])
    return res


@dp.callback_query(F.data.startswith("sw:"))
async def cb_social_when(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        return await c.answer("Ruxsat yo'q", show_alert=True)
    _, key, kind, when = c.data.split(":")
    p = _social_pending.pop(key, None)
    if not p:
        await c.message.edit_text("Bu so'rov eskirgan. Rasmni qaytadan yuboring.")
        return await c.answer()
    await c.answer("⏳")
    await c.message.edit_text("⏳ Rasmlar tayyorlanmoqda…")
    try:
        datas = [(await bot.download(f)).read() for f in p["files"]]
        multi = len(datas) > 1
        if multi and kind != "carousel" and when == "queue":
            groups = [[d] for d in datas]  # navbatda — har kuni bittadan
        else:
            groups = [datas]
        items = []
        for g in groups:
            fixed = len(g) > 1  # karuselda hamma rasm bir xil 4:5
            imgs = await asyncio.to_thread(_prepare, g, kind, fixed)
            items.append(ss.add(kind, imgs, p["caption"], when))
    except Exception as e:  # noqa: BLE001 — admin xatoni ko'rsin
        log.exception("social prepare")
        return await c.message.edit_text(f"⚠️ Rasmni tayyorlab bo'lmadi: {esc(str(e))}")
    if when == "queue":
        lines = [f"🗓 #{it['id']} — {soc.local_str(it['scheduled_at'])}" for it in items]
        return await c.message.edit_text(f"✅ Navbatga qo'yildi ({soc.KINDS[kind]}):\n" + "\n".join(lines)
                                         + "\n\nNavbat: /navbat")
    if not soc.configured():
        return await c.message.edit_text("⚠️ Meta hali ulanmagan — rasm navbatda turibdi va ulangan zahoti chiqadi.\n"
                                         "Tekshirish: /meta")
    await c.message.edit_text("⏳ Instagram va Facebook'ga joylanmoqda…")
    texts = []
    for it in items:
        res = await social_publish(ss.get(it["id"]))
        texts.append(soc.result_text(res))
    await c.message.edit_text("📲 Natija:\n" + "\n".join(texts))


@dp.message(Command("meta"))
async def cmd_meta(m: Message):
    if not is_admin(m.from_user.id):
        return
    q = ss.queued()
    tail = (f"\n\n🕖 Kunlik post vaqti: <b>{ss.post_time()}</b> (/post_vaqti 19:00)\n🗓 Navbatda: {len(q)} ta (/navbat)"
            f"\n#️⃣ Heshteglar: {esc(ss.tags()) or '—'} (/heshteg ...)"
            f"\n\n🔗 Instagram bio uchun havola:\n{WEBAPP_URL}custom?src=ig\n🔗 Facebook uchun:\n{WEBAPP_URL}custom?src=fb")
    if not soc.configured():
        return await m.answer("⚠️ Meta ulanmagan. Render → Environment ga META_TOKEN va FB_PAGE_ID ni yozing." + tail)
    try:
        info = await meta.connect()
        await m.answer(f"✅ Ulangan\n📘 Facebook: <b>{esc(info['page'])}</b>\n📸 Instagram: "
                       + (f"<b>@{esc(info['instagram'])}</b>" if info["instagram"] else "⚠️ bog'lanmagan") + tail)
    except (soc.MetaError, aiohttp.ClientError, asyncio.TimeoutError) as e:
        await m.answer(f"⚠️ Ulanishda xato: {esc(str(e))}" + tail)


@dp.message(Command("navbat"))
async def cmd_queue(m: Message):
    if not is_admin(m.from_user.id):
        return
    q = ss.queued()
    if not q:
        return await m.answer("🗓 Navbat bo'sh. Rasm yuborsangiz, joylashni taklif qilaman.")
    lines, rows = [], []
    for it in q[:20]:
        cap = (it["caption"] or "standart matn")[:40]
        lines.append(f"#{it['id']} · {soc.local_str(it['scheduled_at'])} · {soc.KINDS[it['kind']]} · "
                     f"{len(it['images'])} rasm · {esc(cap)}")
        rows.append([InlineKeyboardButton(text=f"⚡ #{it['id']} hozir", callback_data=f"sq:{it['id']}:now"),
                     InlineKeyboardButton(text=f"❌ #{it['id']}", callback_data=f"sq:{it['id']}:del")])
    await m.answer("🗓 <b>Navbat</b>\n" + "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows[:20]))


@dp.callback_query(F.data.startswith("sq:"))
async def cb_social_queue(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        return await c.answer("Ruxsat yo'q", show_alert=True)
    _, pid, act = c.data.split(":")
    try:
        it = ss.get(int(pid))
    except KeyError:
        return await c.answer("Topilmadi", show_alert=True)
    if it["status"] != "queued":
        return await c.answer(f"#{pid}: {soc.STATUS.get(it['status'], it['status'])}", show_alert=True)
    if act == "del":
        ss.cancel(it["id"])
        await c.answer("❌ Bekor qilindi")
        return await c.message.answer(f"❌ #{pid} navbatdan olindi.")
    if not soc.configured():
        return await c.answer("Meta hali ulanmagan", show_alert=True)
    await c.answer("⏳")
    res = await social_publish(it)
    await c.message.answer(f"📲 #{pid}:\n" + soc.result_text(res))


@dp.message(Command("post_vaqti"))
async def cmd_post_time(m: Message):
    if not is_admin(m.from_user.id):
        return
    arg = (m.text or "").split(maxsplit=1)
    try:
        v = ss.set_post_time(arg[1] if len(arg) > 1 else "")
    except ValueError as e:
        return await m.answer(f"{e}\nHozir: {ss.post_time()}")
    ss.reschedule()
    await m.answer(f"✅ Kunlik post vaqti: <b>{v}</b>. Navbatdagilar shu vaqtga ko'chirildi.")


@dp.message(Command("heshteg"))
async def cmd_tags(m: Message):
    if not is_admin(m.from_user.id):
        return
    arg = (m.text or "").split(maxsplit=1)
    if len(arg) < 2:
        return await m.answer(f"#️⃣ Hozirgi heshteglar:\n{esc(ss.tags()) or '—'}\n\n"
                              "O'zgartirish: /heshteg #isofa #mebel ...\nO'chirish: /heshteg -")
    v = ss.set_tags("" if arg[1].strip() == "-" else arg[1])
    await m.answer("✅ Heshteglar saqlandi:\n" + (esc(v) or "— (heshtegsiz)"))


async def social_loop():
    """Navbatdagi postlarni vaqti kelganda joylaydi va natijani adminlarga yozadi."""
    while True:
        await asyncio.sleep(60)
        if not soc.configured():
            continue
        for it in ss.due():
            try:
                res = await social_publish(it)
                text = f"📲 Navbatdagi #{it['id']} ({soc.KINDS[it['kind']]}):\n" + soc.result_text(res)
            except Exception as e:  # noqa: BLE001
                log.exception("social_loop")
                ss.set(it["id"], status="failed", error=str(e)[:500])
                text = f"⚠️ Navbatdagi #{it['id']} joylanmadi: {esc(str(e))}"
            for aid in ADMIN_IDS:
                try:
                    await bot.send_message(aid, text)
                except TelegramAPIError:
                    pass


@dp.message(F.chat.type == "private")
async def refuse_user(m: Message):
    """Mijozlar botga yoza olmaydi — savollar uchun admin nikini ko'rsatamiz."""
    if is_admin(m.from_user.id):
        return
    await register_user(m.from_user.model_dump())
    lang = lang_of(m.from_user.id)
    await m.answer(tx(lang, "no_chat", contact=admin_contact()), reply_markup=shop_button(lang=lang))


# ------------------------------------------------------------------ web API
def get_user(request: web.Request) -> dict:
    init_data = request.headers.get("X-Init-Data", "")
    if not init_data and request.headers.get("X-Web-Token"):
        uid = check_web_token(request.headers["X-Web-Token"])
        if not uid:
            raise AuthError("web token noto'g'ri")
        return {"id": uid, "first_name": "", "username": "", "web": True}
    if DEV and not init_data:
        return {"id": int(os.getenv("DEV_USER_ID") or next(iter(ADMIN_IDS), 1)), "first_name": "Test",
                "username": "test"}
    return check_init_data(init_data, BOT_TOKEN)


async def api_web_session(request):
    """Saytdan buyurtma beruvchi uchun maxfiy kalit (Telegram'siz). Faqat buyurtma berish paytida so'raladi."""
    if not rate_ok("ws:" + client_ip(request), 20):
        raise ShopError("Juda ko'p urinish. Birozdan keyin qayta urinib ko'ring.",
                        "Слишком много попыток. Попробуйте чуть позже.")
    uid = -(WEB_ID_BASE + int.from_bytes(os.urandom(6), "big"))
    return web.json_response({"token": web_token(uid)})


def get_admin(request: web.Request) -> dict:
    u = get_user(request)
    if not is_admin(u["id"]):
        raise AuthError("admin emas")
    return u


@web.middleware
async def errors(request, handler):
    try:
        return await handler(request)
    except ShopError as e:
        return web.json_response({"error": e.text(norm_lang(request.headers.get("X-Lang")))}, status=400)
    except AuthError as e:
        return web.json_response({"error": tx(norm_lang(request.headers.get("X-Lang")), "auth"), "detail": str(e)},
                                 status=401)


async def page_index(request):
    return web.FileResponse(BASE / "webapp" / "index.html", headers={"Cache-Control": "no-cache"})


async def api_catalog(request):
    info = {**SHOP, "admin": shop.settings().get("admin_contact", "")}
    return web.json_response({"shop": info, **shop.catalog(norm_lang(request.query.get("lang")))})


# ------------------------------------------------------------------ o'lchamga buyurtma (/custom)
CUSTOM_PHOTO_MAX = 15 * 1024 * 1024


async def page_custom(request):
    return web.FileResponse(BASE / "webapp" / "custom.html", headers={"Cache-Control": "no-cache"})


async def api_custom_config(request):
    lang = norm_lang(request.query.get("lang"))
    model = None
    try:
        mid = int(request.query.get("model") or 0)
    except ValueError:
        mid = 0
    if mid:
        try:
            p = shop.localize_product(shop.product(mid), lang)
            if p.get("active"):
                model = {"id": p["id"], "name": p["name"], "price": p["price"], "cat_id": p.get("cat_id"),
                         "image": sitepages.first_image(p), "specs": p.get("specs") or []}
        except ShopError:
            pass
    cats = {c["id"]: c["name"] for c in shop.categories()}
    return web.json_response({"shop": {**SHOP, "admin": shop.settings().get("admin_contact", "")},
                              "model": model, "model_cat": cats.get((model or {}).get("cat_id"), ""),
                              **cs.config(lang)})


async def read_custom_form(request) -> tuple:
    payload, photos = {}, []
    if not request.content_type.startswith("multipart/"):
        return await request.json(), []
    reader = await request.multipart()
    async for part in reader:
        if part.name == "data":
            payload = json.loads(await part.text() or "{}")
        elif part.name == "photo" and len(photos) < cust.MAX_PHOTOS:
            buf = bytearray()
            while True:
                chunk = await part.read_chunk(256 * 1024)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > CUSTOM_PHOTO_MAX:
                    raise ShopError("Rasm juda katta (15 MB dan oshmasin)", "Фото слишком большое (не более 15 МБ)")
            if buf:
                photos.append(bytes(buf))
    return payload, photos


async def api_custom_request(request):
    u = get_user(request)
    lang = norm_lang(request.headers.get("X-Lang"))
    payload, photos = await read_custom_form(request)
    if u.get("web"):
        if not rate_ok("wc:" + client_ip(request), 6):
            raise ShopError("Juda ko'p ariza yuborildi. Iltimos, adminga yozing.",
                            "Слишком много заявок. Пожалуйста, напишите администратору.")
        u = {**u, "first_name": (payload.get("name") or "").strip()[:80] or "Sayt mijozi"}
    r = cs.create(u, payload, photos, lang)
    if u.get("web"):
        await register_user(u)
    asyncio.create_task(notify_custom_new(r))
    return web.json_response({"request": cust.public(r, lang)})


async def api_custom_mine(request):
    u = get_user(request)
    lang = norm_lang(request.headers.get("X-Lang"))
    return web.json_response({"requests": [cust.public(r, lang) for r in cs.user_list(u["id"])],
                              "is_admin": is_admin(u["id"])})


def custom_admin(r: dict) -> dict:
    out = {k: v for k, v in r.items() if k != "admin_msgs"}
    out["photos"] = len(r.get("photos") or [])
    out["next"] = cust.next_stages(r["status"])
    out["tier_name"] = cust.TIERS.get(r.get("tier"), {}).get("uz", "")
    out["style_name"] = cust.style_name(r.get("style") or "")
    out["sample_image"] = "/" + r["sample_image"] if r.get("sample_image") else ""
    out["dims_text"] = cust.dims_text(r)
    out["visit_text"] = cust.visit_text(r)
    out["lead"] = cust.lead(r)
    out["source_text"] = cust.source_text(r)
    out["lead_name"] = cust.lead_name(r)
    out["need_text"] = cust.NEED_WHEN.get(r.get("need_when"), ("",))[0]
    out["repair_text"] = cust.REPAIR.get(r.get("repair"), ("",))[0]
    return out


async def api_admin_custom(request):
    get_admin(request)
    return web.json_response({"requests": [custom_admin(r) for r in cs.list(request.query.get("status", "active"))],
                              "counts": cs.counts(), "rates": cs.rates(), "gallery": gallery_admin(),
                              "measure_fee": cs.measure_fee(), "call_phone": cs.call_phone(),
                              "kinds_admin": cs.kinds_admin()})


def gallery_admin() -> list:
    return [{**g, "image": "/" + g["image"]} for g in cs.gallery()]


async def api_admin_gallery_add(request):
    """Namuna rasmlar: multipart — style, kind, caption va bir nechta photo."""
    get_admin(request)
    fields, images = {}, []
    reader = await request.multipart()
    async for part in reader:
        if part.name == "photo" and len(images) < 20:
            buf = bytearray()
            while True:
                chunk = await part.read_chunk(256 * 1024)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > CUSTOM_PHOTO_MAX:
                    raise ShopError("Rasm juda katta (15 MB dan oshmasin)")
            if buf:
                images.append(bytes(buf))
        elif part.name:
            fields[part.name] = (await part.text())[:200]
    cs.gallery_add(fields.get("style", ""), fields.get("kind", ""), fields.get("caption", ""), images)
    return web.json_response({"gallery": gallery_admin()})


async def api_admin_gallery_update(request):
    get_admin(request)
    cs.gallery_update(int(request.match_info["gid"]), await request.json())
    return web.json_response({"gallery": gallery_admin()})


async def api_admin_gallery_delete(request):
    get_admin(request)
    cs.gallery_delete(int(request.match_info["gid"]))
    return web.json_response({"gallery": gallery_admin()})


async def api_admin_custom_status(request):
    u = get_admin(request)
    body = await request.json()
    r = cs.set_status(int(request.match_info["id"]), body.get("status", ""), who=f"admin: {u.get('first_name', '')}")
    asyncio.create_task(notify_custom_status(r))
    return web.json_response({"request": custom_admin(r)})


async def api_admin_custom_update(request):
    get_admin(request)
    r = cs.update_admin(int(request.match_info["id"]), await request.json())
    asyncio.create_task(refresh_custom_messages(r))
    return web.json_response({"request": custom_admin(r)})


async def api_admin_custom_kinds(request):
    get_admin(request)
    data = await request.json()
    return web.json_response({"kinds_admin": cs.save_kinds(data.get("kinds")),
                              "config": cs.config(norm_lang(request.headers.get("X-Lang")))})


async def api_admin_custom_rates(request):
    get_admin(request)
    data = await request.json()
    fee = cs.save_measure_fee(data.pop("measure_fee")) if "measure_fee" in data else cs.measure_fee()
    phone = cs.save_call_phone(data.pop("call_phone")) if "call_phone" in data else cs.call_phone()
    return web.json_response({"rates": cs.save_rates(data), "measure_fee": fee, "call_phone": phone})


async def api_admin_custom_photo(request):
    get_admin(request)
    path = cs.photo_path(int(request.match_info["id"]), int(request.match_info["i"]))
    if not os.path.isfile(path):
        raise ShopError("Rasm topilmadi")
    return web.FileResponse(path, headers={"Cache-Control": "private, no-store"})


def custom_kb(r: dict) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=("❌ Bekor qilish" if s == "cancelled" else "🔄 Qayta ochish" if s == "new"
                                        else "➡️ " + cust.stage_name(s)), callback_data=f"cs:{r['id']}:{s}")]
            for s in cust.next_stages(r["status"])]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def notify_custom_new(r: dict):
    if not bot:
        return
    msgs = []
    for chat in NOTIFY_CHATS:
        try:
            photos = [os.path.join(cs.photo_dir, p) for p in r["photos"]]
            if r.get("sample_image"):  # mijoz tanlagan namuna — birinchi rasm
                photos.insert(0, os.path.join(UPLOAD_DIR, os.path.basename(r["sample_image"])))
            photos = [p for p in photos if os.path.isfile(p)]
            if len(photos) == 1:
                await bot.send_photo(chat, FSInputFile(photos[0]))
            elif photos:
                await bot.send_media_group(chat, [InputMediaPhoto(media=FSInputFile(p)) for p in photos[:10]])
            m = await bot.send_message(chat, cust.admin_text(r), reply_markup=custom_kb(r))
            msgs.append([chat, m.message_id])
        except TelegramAPIError as e:
            log.warning("individual ariza guruhga yuborilmadi: %s", e)
    cs.set_admin_msgs(r["id"], msgs)
    if is_web(r["user_id"]):
        return
    try:
        lang = r.get("lang") or lang_of(r["user_id"])
        await bot.send_message(r["user_id"], tx(lang, "custom_sent", id=r["id"]))
    except TelegramAPIError as e:
        log.warning("mijozga yuborilmadi: %s", e)


async def refresh_custom_messages(r: dict):
    if not bot:
        return
    for entry in r.get("admin_msgs") or []:
        try:
            await bot.edit_message_text(cust.admin_text(r), chat_id=entry[0], message_id=entry[1],
                                        reply_markup=custom_kb(r))
        except TelegramAPIError:
            pass


async def notify_custom_status(r: dict):
    if not bot:
        return
    await refresh_custom_messages(r)
    msg = cust.STAGE_MSG.get(r["status"])
    if not msg or is_web(r["user_id"]):
        return
    lang = r.get("lang") or lang_of(r["user_id"])
    text = msg[1 if lang == "ru" else 0].format(id=r["id"])
    if r["status"] == "contract" and r.get("price"):
        text += (f"\n\n💰 {'Цена' if lang == 'ru' else 'Narx'}: <b>{fmt_price(r['price'], lang)}</b>"
                 + (f"\n💵 {'Предоплата' if lang == 'ru' else 'Oldindan to‘lov'}: {fmt_price(r['prepay'], lang)}"
                    if r.get("prepay") else ""))
    try:
        await bot.send_message(r["user_id"], text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📐 " + ("Мои заявки" if lang == "ru" else "Arizalarim"),
                                 web_app=WebAppInfo(url=f"{CUSTOM_URL}?go=mine&lang={lang}"))]]))
    except TelegramAPIError:
        pass


# ------------------------------------------------------------------ veb-sayt (/, /p/..., /oferta)
SITE_DIR = BASE / "webapp" / "site"


def _asset_version() -> str:
    h = hashlib.sha1()
    for f in ("site.css", "site.js"):
        try:
            h.update((SITE_DIR / f).read_bytes())
        except OSError:
            pass
    return h.hexdigest()[:10]


ASSET_V = _asset_version()


def site_base(request) -> str:
    proto = (request.headers.get("X-Forwarded-Proto") or request.scheme or "https").split(",")[0].strip()
    return f"{proto}://{request.host}"


def site_ctx(request) -> dict:
    lang = norm_lang(request.query.get("lang"))
    st = shop.settings()
    products = []
    for p in shop.products():
        lp = shop.localize_product(p, lang)  # ichki maydonlar (kirim narxi, ta'minotchi) shu yerda olib tashlanadi
        lp["name_uz"] = p["name"]
        products.append(lp)
    return {"lang": lang, "shop": SHOP, "settings": {"admin_contact": st.get("admin_contact", "")},
            "categories": shop.categories(lang), "products": products, "bot": SHOP.get("bot", ""),
            "prepay_pct": shop.prepay_info()["pct"], "assembly_pct": int(st.get("assembly_pct") or 0),
            "base": site_base(request), "v": ASSET_V, "path": request.path, "year": time.gmtime().tm_year}


def html_page(text: str, status: int = 200) -> web.Response:
    return web.Response(text=text, status=status, content_type="text/html",
                        headers={"Cache-Control": "public, max-age=60"})


async def page_site(request):
    return html_page(sitepages.page_home(site_ctx(request)))


async def page_product(request):
    ctx = site_ctx(request)
    m = re.match(r"(\d+)", request.match_info.get("slug", ""))
    pid = int(m.group(1)) if m else 0
    p = next((x for x in ctx["products"] if x["id"] == pid), None)
    if not p:
        return html_page(sitepages.page_404(ctx), 404)
    return html_page(sitepages.page_product(ctx, p))


async def page_offer(request):
    ctx = site_ctx(request)
    return html_page(sitepages.page_offer(ctx, render_offer(shop.seller(), ctx["assembly_pct"], ctx["lang"])))


async def page_not_found(request):
    return html_page(sitepages.page_404(site_ctx(request)), 404)


async def page_sitemap(request):
    return web.Response(text=sitepages.sitemap_xml(site_base(request), site_ctx(request)["products"]),
                        content_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})


async def page_robots(request):
    return web.Response(text=sitepages.robots_txt(site_base(request)), content_type="text/plain")


async def page_manifest(request):
    return web.Response(text=sitepages.manifest(SHOP["name"]), content_type="application/manifest+json")


async def page_sw(request):
    return web.FileResponse(SITE_DIR / "sw.js", headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/",
                                                          "Content-Type": "application/javascript"})


async def api_lang(request):
    u = get_user(request)
    lang = shop.set_user_lang(u["id"], (await request.json()).get("lang"))
    if bot:
        try:
            await bot.set_chat_menu_button(chat_id=u["id"], menu_button=MenuButtonWebApp(
                text=tx(lang, "menu"), web_app=WebAppInfo(url=f"{APP_URL}?lang={lang}")))
        except TelegramAPIError:
            pass
    return web.json_response({"lang": lang})


def public(o: dict, admin: bool = False) -> dict:
    """Javobga ichki maydonlarni (chek fayli, admin xabarlari) qo'shmaymiz.
    Mijozga ta'minotchi, kirim narxi va kodi ham yuborilmaydi (admin=False)."""
    o = dict(o)
    o["has_receipt"] = bool(o.pop("receipt", ""))
    o.pop("admin_msgs", None)
    if not admin:
        o["items"] = [{k: v for k, v in i.items() if k != "sup"} for i in o.get("items") or []]
        o.pop("proofs", None)
        o.pop("events", None)
    else:
        o["next"] = next_statuses(o)
        o["act_key"] = act_key(o["id"])
        o["proofs"] = len(o.get("proofs") or [])
    return o


async def api_me(request):
    u = get_user(request)
    if not u.get("web"):  # saytdagi xaridor buyurtma paytida ro'yxatga olinadi (ismi bilan)
        await register_user(u)
    lang = shop.user_lang(u["id"])
    show = lang or norm_lang(request.headers.get("X-Lang") or u.get("language_code"))
    return web.json_response({"user": u, "is_admin": is_admin(u["id"]), "profile": shop.last_profile(u["id"]),
                              "lang": lang, "orders": [public(shop.localize_order(o, show))
                                                       for o in shop.user_orders(u["id"])]})


async def api_order(request):
    """Buyurtma: multipart — "data" (JSON) va "receipt" (chek rasmi)."""
    u = get_user(request)
    payload, receipt = {}, b""
    if request.content_type.startswith("multipart/"):
        reader = await request.multipart()
        async for part in reader:
            if part.name == "data":
                payload = json.loads(await part.text() or "{}")
            elif part.name == "receipt":
                receipt = bytes(await part.read(decode=False))
    else:
        payload = await request.json()
    if u.get("web"):
        if not rate_ok("wo:" + client_ip(request), 8):
            raise ShopError("Juda ko'p buyurtma yuborildi. Iltimos, do'konga qo'ng'iroq qiling.",
                            "Слишком много заказов. Пожалуйста, позвоните в магазин.")
        c = payload.get("customer") or {}
        u = {**u, "first_name": (c.get("name") or "").strip()[:80] or "Sayt mijozi"}
    o = shop.create_order(u, payload, receipt)
    if u.get("web"):
        await register_user(u)
    asyncio.create_task(notify_new_order(o))
    return web.json_response({"order": public(shop.localize_order(o, norm_lang(request.headers.get("X-Lang"))))})


async def api_order_accept(request):
    """Mijoz ilovada «Tekshirdim, qabul qildim» tugmasini bosdi."""
    u = get_user(request)
    o = shop.accept_by_user(u["id"], int(request.match_info["id"]))
    asyncio.create_task(notify_status(o))
    asyncio.create_task(alert_admins(f"🤝 Mijoz buyurtma #{o['id']} ni tekshirib qabul qildi (ilovada tasdiqladi)."))
    return web.json_response({"order": public(shop.localize_order(o, norm_lang(request.headers.get("X-Lang"))))})


async def api_order_cancel(request):
    u = get_user(request)
    o = shop.cancel_by_user(u["id"], int(request.match_info["id"]))
    asyncio.create_task(notify_status(o))
    return web.json_response({"order": public(o)})


async def api_admin_data(request):
    get_admin(request)
    return web.json_response({"stats": shop.stats(),
                              "orders": [public(o, admin=True) for o in shop.orders(request.query.get("status", ""))],
                              "products": shop.products(include_hidden=True), "categories": shop.categories(),
                              "suppliers": shop.suppliers(),
                              "statuses": STATUSES, "actions": ACTIONS, "flow": FLOW, "settings": shop.settings(),
                              "custom": cs.counts()})


async def api_admin_receipt(request):
    get_admin(request)
    path = shop.receipt_path(shop.order(int(request.match_info["id"])))
    if not path:
        raise ShopError("Chek topilmadi")
    return web.FileResponse(path, headers={"Cache-Control": "private, no-store"})


async def api_admin_customers(request):
    get_admin(request)
    q = request.query
    data = shop.customers(q.get("q", ""), int(q.get("offset") or 0), int(q.get("limit") or 50))
    return web.json_response({"stats": shop.customer_stats(), **data})


async def api_admin_settings(request):
    get_admin(request)
    return web.json_response({"settings": shop.save_settings(await request.json())})


VIDEO_MAX_BYTES = 400 * 1024 * 1024   # yuklanadigan asl video (telefondan) — 400 MB gacha
VIDEO_MAX_SECONDS = 90                 # mijozga ko'rsatiladigan uzunlik
TMP_DIR = os.path.join(os.path.dirname(UPLOAD_DIR.rstrip("/")), "tmp")
_ffmpeg_lock = asyncio.Semaphore(1)    # bir vaqtda bitta video siqiladi (server kuchi kichik)


# Xotira tugasa, server bot jarayonini emas, aynan ffmpeg'ni to'xtatsin
# (video «xato» bo'ladi, lekin bot va Mini App ishlashda davom etadi).
_OOM_FIRST = ("sh", "-c", 'echo 1000 > /proc/self/oom_score_adj 2>/dev/null; exec "$@"', "sh")


async def _run(*cmd) -> tuple:
    proc = await asyncio.create_subprocess_exec(*_OOM_FIRST, *cmd,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    return proc.returncode, err.decode(errors="ignore")[-600:]


async def process_video(pid: int, src_path: str, prev: dict = None):
    """Telefondan kelgan videoni 720p H.264 ga siqadi (taxminan 3–6 MB/daqiqa) va poster rasm yaratadi."""
    name = uuid.uuid4().hex[:16]
    out_mp4 = os.path.join(UPLOAD_DIR, name + ".mp4")
    out_jpg = os.path.join(UPLOAD_DIR, name + ".jpg")
    try:
        async with _ffmpeg_lock:
            # Oqimlar soni cheklangan: aks holda ffmpeg Render serveridagi barcha yadrolarni ko'rib
            # o'nlab oqim ochadi va 4K videoda 1.5 GB+ xotira oladi (Starter tarifda 512 MB).
            code, err = await _run(
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-threads", "1",
                "-i", src_path, "-t", str(VIDEO_MAX_SECONDS), "-filter_threads", "1",
                "-vf", "scale='min(1280,iw)':'min(1280,ih)':force_original_aspect_ratio=decrease,"
                       "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p", "-r", "30",
                "-threads", "2", "-x264-params", "rc-lookahead=10",
                "-c:a", "aac", "-b:a", "96k", "-ac", "2", "-movflags", "+faststart", out_mp4)
            if code != 0 or not os.path.isfile(out_mp4):
                raise RuntimeError(f"ffmpeg: {err}")
            for ss in ("1", "0"):  # poster: 1-soniya (juda qisqa videoda — boshidan)
                code, _ = await _run("ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-threads", "1",
                                     "-ss", ss, "-i", out_mp4,
                                     "-frames:v", "1", "-q:v", "4", out_jpg)
                if code == 0 and os.path.isfile(out_jpg):
                    break
        size = os.path.getsize(out_mp4)
        shop.set_product_video(pid, {"status": "ready", "src": "uploads/" + name + ".mp4",
                                     "poster": "uploads/" + name + ".jpg" if os.path.isfile(out_jpg) else "",
                                     "size": size})
        log.info("video tayyor: mahsulot #%s, %.1f MB", pid, size / 1e6)
    except Exception as e:  # noqa: BLE001
        log.warning("video siqilmadi (#%s): %s", pid, e)
        for f in (out_mp4, out_jpg):
            if os.path.isfile(f):
                os.remove(f)
        try:  # avvalgi tayyor video bo'lsa — uni saqlab qolamiz, aks holda «xato»
            shop.set_product_video(pid, {**prev, "status": "ready", "last_error": 1} if prev and prev.get("src")
                                   else {"status": "error"})
        except ShopError:
            pass
    finally:
        if os.path.isfile(src_path):
            os.remove(src_path)


async def api_admin_product(request):
    get_admin(request)
    data, images, video_tmp = {}, [], ""
    reader = await request.multipart()
    async for part in reader:
        if part.name == "images" and part.filename:
            raw = await part.read(decode=False)
            if raw:
                images.append(shop.save_image(bytes(raw)))
        elif part.name == "video" and part.filename:
            # katta faylni xotiraga emas, to'g'ridan-to'g'ri diskka yozamiz
            os.makedirs(TMP_DIR, exist_ok=True)
            video_tmp = os.path.join(TMP_DIR, uuid.uuid4().hex)
            size = 0
            with open(video_tmp, "wb") as f:
                while chunk := await part.read_chunk(1024 * 1024):
                    size += len(chunk)
                    if size > VIDEO_MAX_BYTES:
                        f.close()
                        os.remove(video_tmp)
                        raise ShopError("Video juda katta (400 MB dan oshmasin). Qisqaroq video tanlang.")
                    f.write(chunk)
            if not size:
                os.remove(video_tmp)
                video_tmp = ""
        elif part.name:
            data[part.name] = await part.text()
    p = shop.save_product(data, images)
    if video_tmp:
        prev = p["video"] if p["video"].get("status") == "ready" else {}
        shop.set_product_video(p["id"], {**prev, "status": "processing"} if prev.get("src") else {"status": "processing"})
        app_tasks.append(asyncio.create_task(process_video(p["id"], video_tmp, prev)))
        p = shop.product(p["id"])
    try:  # ruscha tarjimani darhol qilamiz (bo'lmasa fon jarayoni keyinroq qayta urinadi)
        await asyncio.wait_for(translate_products([p]), 15)
        p = shop.product(p["id"])
    except Exception as e:  # noqa: BLE001
        log.warning("tarjima kechiktirildi: %s", e)
    return web.json_response({"product": p})


async def api_admin_product_delete(request):
    get_admin(request)
    shop.delete_product(int(request.match_info["id"]))
    return web.json_response({"ok": True})


async def api_admin_category(request):
    get_admin(request)
    c = shop.save_category(await request.json())
    try:
        await asyncio.wait_for(translate_categories(), 10)
    except Exception as e:  # noqa: BLE001
        log.warning("kategoriya tarjimasi kechiktirildi: %s", e)
    return web.json_response({"category": c})


async def api_admin_release(request):
    get_admin(request)
    o = shop.release_assembly(int(request.match_info["id"]), 0, by_admin=True)
    asyncio.create_task(refresh_order_messages(o))
    return web.json_response({"order": public(o, admin=True)})


async def api_admin_group_unlink(request):
    get_admin(request)
    role = request.match_info["role"]
    if role not in ("courier", "assembler"):
        raise ShopError("Noma'lum guruh")
    shop.set_setting(f"{role}_chat", "")
    shop.set_setting(f"{role}_chat_title", "")
    return web.json_response({"settings": shop.settings()})


def _act_html(o: dict) -> str:
    """Qabul qilish-topshirish dalolatnomasi — chop etishga tayyor sahifa (brauzerda «Chop etish → PDF»)."""
    sel = shop.seller()
    blank = "________________"
    rows = "".join(f"<tr><td>{n}</td><td>{esc(i['name'])}</td><td class='c'>{i['qty']}</td>"
                   f"<td class='r'>{fmt_price(i['price'])}</td><td class='r'>{fmt_price(i['price'] * i['qty'])}</td></tr>"
                   for n, i in enumerate(o["items"], 1))
    if o.get("assembly"):
        rows += (f"<tr><td></td><td>Yig'ib berish xizmati</td><td class='c'>1</td>"
                 f"<td class='r'></td><td class='r'>{fmt_price(o['assembly_fee'])}</td></tr>")
    import time as _t
    date = _t.strftime("%d.%m.%Y", _t.gmtime(o["created"] + 5 * 3600))
    addr = "Do'kondan olib ketish" if o["delivery"] != "delivery" else ", ".join(x for x in (o.get("city"), o.get("address")) if x)
    checks = ["Mahsulotlar to'liq komplektda topshirildi", "Tashqi ko'rinishida shikast, tirnalish va dog' yo'q",
              "Rang va o'lchamlar buyurtmaga mos"] + (["Mebel yig'ib, o'rnatib berildi"] if o.get("assembly") else [])
    return f"""<!doctype html><html lang="uz"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Dalolatnoma #{o['id']}</title>
<style>
 body {{ font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; color:#111; max-width: 800px; margin: 24px auto; padding: 0 16px; font-size: 14px; }}
 h1 {{ font-size: 18px; text-align: center; margin: 0 0 4px; }} .sub {{ text-align:center; color:#555; margin-bottom: 18px; }}
 table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }} td, th {{ border: 1px solid #999; padding: 6px; vertical-align: top; }}
 th {{ background: #f1f1f1; }} .c {{ text-align: center; }} .r {{ text-align: right; white-space: nowrap; }}
 .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px 24px; }} .box {{ border: 1px solid #999; padding: 10px; min-height: 60px; }}
 .sign {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 28px; }} .line {{ border-bottom: 1px solid #111; height: 28px; }}
 .btn {{ display:block; margin: 0 auto 16px; padding: 10px 18px; font-size: 15px; border-radius: 10px; border: 0; background: #b4692f; color: #fff; }}
 @media print {{ .btn {{ display: none; }} body {{ margin: 0; }} }}
</style></head><body>
<button class="btn" onclick="window.print()">🖨 Chop etish / PDF saqlash</button>
<h1>QABUL QILISH-TOPSHIRISH DALOLATNOMASI</h1>
<div class="sub">Buyurtma № {o['id']} · {date}</div>
<div class="grid">
 <div><b>Sotuvchi:</b> {esc(sel['name']) or blank}<br>STIR: {esc(sel['tin']) or blank}<br>Manzil: {esc(sel['address']) or blank}<br>Tel: {esc(sel['phone']) or blank}</div>
 <div><b>Xaridor:</b> {esc(o['name'])}<br>Tel: {esc(o['phone'])}<br>Manzil: {esc(addr) or blank}</div>
</div>
<table><tr><th>№</th><th>Mahsulot</th><th>Soni</th><th>Narxi</th><th>Summa</th></tr>{rows}
<tr><td colspan="4" class="r"><b>Jami</b></td><td class="r"><b>{fmt_price(o['total'])}</b></td></tr>
<tr><td colspan="4" class="r">Oldindan to'langan</td><td class="r">{fmt_price(o.get('prepay') or 0)}</td></tr>
<tr><td colspan="4" class="r">Topshirishda to'landi</td><td class="r">{fmt_price(o['total'] - (o.get('prepay') or 0))}</td></tr></table>
<p><b>Xaridor mahsulotni Sotuvchi vakili huzurida ko'zdan kechirdi va quyidagilarni tasdiqlaydi</b> (☑ belgilang):</p>
{''.join(f"<div>☐ {c}</div>" for c in checks)}
<p><b>E'tirozlar (bo'lsa):</b></p><div class="box"></div>
<p class="sub" style="text-align:left">Ushbu dalolatnoma mahsulotning ko'rinadigan nuqsonlari va komplektligi bo'yicha tuzildi va Xaridorning
qonunchilikda belgilangan yashirin nuqsonlar bo'yicha huquqlarini cheklamaydi. Ikki nusxada tuzildi.</p>
<div class="sign">
 <div>Topshirdi (Sotuvchi vakili):<div class="line"></div>F.I.Sh., imzo</div>
 <div>Qabul qildi (Xaridor):<div class="line"></div>{esc(o['name'])}, imzo</div>
</div>
<p style="margin-top:18px">Sana: ____.____.20____ &nbsp;&nbsp; Vaqt: ____:____</p>
</body></html>"""


async def page_act(request):
    oid = int(request.match_info["id"])
    if not hmac.compare_digest(request.query.get("k", ""), act_key(oid)):
        raise web.HTTPForbidden(text="Havola noto'g'ri")
    try:
        o = shop.order(oid)
    except ShopError:
        raise web.HTTPNotFound(text="Buyurtma topilmadi")
    return web.Response(text=_act_html(o), content_type="text/html", headers={"Cache-Control": "no-store"})


async def api_admin_supplier(request):
    get_admin(request)
    return web.json_response({"supplier": shop.save_supplier(await request.json()), "suppliers": shop.suppliers()})


async def api_admin_supplier_delete(request):
    get_admin(request)
    shop.delete_supplier(int(request.match_info["id"]))
    return web.json_response({"ok": True, "suppliers": shop.suppliers()})


async def api_admin_category_delete(request):
    get_admin(request)
    shop.delete_category(int(request.match_info["id"]))
    return web.json_response({"ok": True})


async def api_admin_status(request):
    get_admin(request)
    body = await request.json()
    u = get_user(request)
    o = shop.set_status(int(request.match_info["id"]), body.get("status", ""), role="admin",
                        who=f"admin: {u.get('first_name', '')}")
    asyncio.create_task(notify_status(o))
    return web.json_response({"order": public(o, admin=True)})


def start_broadcast(text: str) -> int:
    """Matnni barcha mijozlarga (ruslarga tarjima bilan) fon rejimida yuboradi; nechta mijozga navbatga qo'yilganini qaytaradi."""
    groups = shop.user_ids_by_lang()
    ids = groups["uz"] + groups["ru"]
    ru_set = set(groups["ru"])

    async def run():
        sent = 0
        text_ru = ""
        if groups["ru"]:
            try:
                text_ru = await translate(http(), text)
            except Exception as e:  # noqa: BLE001
                log.warning("xabar tarjima qilinmadi: %s", e)
        for uid in ids:
            lang = "ru" if uid in ru_set else "uz"
            try:
                await bot.send_message(uid, esc(text_ru if lang == "ru" and text_ru else text),
                                       reply_markup=shop_button(lang=lang))
                sent += 1
            except TelegramAPIError:
                pass
            await asyncio.sleep(0.05)  # Telegram limitlari uchun
        for aid in ADMIN_IDS:
            try:
                await bot.send_message(aid, f"📣 Xabar {sent}/{len(ids)} mijozga yetkazildi.")
            except TelegramAPIError:
                pass

    if bot:
        asyncio.create_task(run())
    return len(ids)


async def api_admin_broadcast(request):
    get_admin(request)
    text = ((await request.json()).get("text") or "").strip()
    if not text:
        raise ShopError("Xabar matnini yozing")
    return web.json_response({"queued": start_broadcast(text)})


# ------------------------------------------------------------------ avtomatik tarjima (uz -> ru)
_http: aiohttp.ClientSession = None


def http() -> aiohttp.ClientSession:
    global _http
    if _http is None or _http.closed:
        _http = aiohttp.ClientSession()
    return _http


async def translate_products(products: list = None):
    for p in (products if products is not None else shop.products_to_translate()):
        p = shop.product(p["id"])
        src = shop.product_src(p)
        if p.get("tr_src") == src:
            continue
        specs = p["specs"]
        texts = [p["name"], p["description"], p.get("delivery_days") or ""] + [x for kv in specs for x in kv]
        out = await translate_many(http(), texts)
        if p["name"] and not out[0]:
            raise RuntimeError("bo'sh tarjima")
        specs_ru = [[out[3 + 2 * i] or k, out[4 + 2 * i] or v] for i, (k, v) in enumerate(specs)]
        shop.set_product_ru(p["id"], out[0], out[1], specs_ru, out[2], src)
        log.info("tarjima qilindi: #%s %s -> %s", p["id"], p["name"], out[0])


async def translate_categories():
    for c in shop.categories_to_translate():
        ru = await translate(http(), c["name"])
        if ru:
            shop.set_category_ru(c["id"], ru)


async def translation_loop():
    """Tarjimasi yo'q yoki eskirgan mahsulot/kategoriyalarni vaqti-vaqti bilan tarjima qiladi."""
    try:  # ishga tushganda tarjima xizmati ishlayotganini tekshiramiz (loglarda ko'rinadi)
        log.info("tarjima tekshiruvi: 'Yumshoq divan' -> %r", await translate(http(), "Yumshoq divan"))
    except Exception as e:  # noqa: BLE001
        log.warning("tarjima xizmatiga ulanib bo'lmadi: %s", e)
    while True:
        try:
            await translate_categories()
            await translate_products()
        except Exception as e:  # noqa: BLE001
            log.warning("fon tarjimasi: %s", e)
        await asyncio.sleep(600)


async def api_admin_translate(request):
    """Admin: «Qayta tarjima qilish» — avtomatik tarjimani majburan yangilash."""
    get_admin(request)
    p = shop.product(int(request.match_info["id"]))
    shop.set_product_ru(p["id"], p["name_ru"], p["description_ru"], p["specs_ru"], p["delivery_days_ru"], "")
    await asyncio.wait_for(translate_products([p]), 15)
    return web.json_response({"product": shop.product(p["id"])})


async def upload_headers(request, response):
    # Rasmlar: uzoq keshlash (nomlari takrorlanmaydi) va Telegram'dan yuklab olishga ruxsat
    if request.path.startswith("/uploads/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        response.headers["Access-Control-Allow-Origin"] = "*"
    elif request.path.startswith("/s/"):
        # sayt fayllari: manzilda ?v=... versiyasi bor, shuning uchun uzoq keshlasa bo'ladi
        response.headers["Cache-Control"] = "public, max-age=2592000"


def make_app() -> web.Application:
    app = web.Application(middlewares=[errors], client_max_size=450 * 1024 * 1024)
    app.on_response_prepare.append(upload_headers)
    app.router.add_get("/", page_site)
    app.router.add_get("/app", page_index)
    app.router.add_get("/p/{slug}", page_product)
    app.router.add_get("/oferta", page_offer)
    app.router.add_get("/sitemap.xml", page_sitemap)
    app.router.add_get("/robots.txt", page_robots)
    app.router.add_get("/manifest.webmanifest", page_manifest)
    app.router.add_get("/sw.js", page_sw)
    app.router.add_static("/s/", SITE_DIR)
    app.router.add_post("/api/web/session", api_web_session)
    app.router.add_get("/custom", page_custom)
    app.router.add_get("/api/custom/config", api_custom_config)
    app.router.add_post("/api/custom/request", api_custom_request)
    app.router.add_post("/api/custom/mine", api_custom_mine)
    app.router.add_get("/api/admin/custom", api_admin_custom)
    app.router.add_post("/api/admin/custom/rates", api_admin_custom_rates)
    app.router.add_post("/api/admin/custom/kinds", api_admin_custom_kinds)
    app.router.add_post("/api/admin/custom/gallery", api_admin_gallery_add)
    app.router.add_post("/api/admin/custom/gallery/{gid}/delete", api_admin_gallery_delete)
    app.router.add_post("/api/admin/custom/gallery/{gid}", api_admin_gallery_update)
    app.router.add_post("/api/admin/custom/{id}/status", api_admin_custom_status)
    app.router.add_post("/api/admin/custom/{id}", api_admin_custom_update)
    app.router.add_get("/api/admin/custom/{id}/photo/{i}", api_admin_custom_photo)
    app.router.add_static("/uploads/", UPLOAD_DIR)
    app.router.add_get("/api/catalog", api_catalog)
    app.router.add_post("/api/me", api_me)
    app.router.add_post("/api/order", api_order)
    app.router.add_post("/api/order/{id}/cancel", api_order_cancel)
    app.router.add_post("/api/order/{id}/accept", api_order_accept)
    app.router.add_get("/api/admin/data", api_admin_data)
    app.router.add_post("/api/admin/product", api_admin_product)
    app.router.add_post("/api/admin/product/{id}/delete", api_admin_product_delete)
    app.router.add_post("/api/admin/category", api_admin_category)
    app.router.add_post("/api/admin/category/{id}/delete", api_admin_category_delete)
    app.router.add_post("/api/admin/supplier", api_admin_supplier)
    app.router.add_post("/api/admin/group/{role}/unlink", api_admin_group_unlink)
    app.router.add_post("/api/admin/order/{id}/release", api_admin_release)
    app.router.add_get("/act/{id}", page_act)
    app.router.add_post("/api/admin/supplier/{id}/delete", api_admin_supplier_delete)
    app.router.add_post("/api/admin/order/{id}/status", api_admin_status)
    app.router.add_post("/api/admin/broadcast", api_admin_broadcast)
    app.router.add_get("/api/admin/receipt/{id}", api_admin_receipt)
    app.router.add_post("/api/admin/settings", api_admin_settings)
    app.router.add_get("/api/admin/customers", api_admin_customers)
    app.router.add_post("/api/lang", api_lang)
    app.router.add_post("/api/admin/product/{id}/translate", api_admin_translate)
    return app


app_tasks: list = []


async def main():
    runner = web.AppRunner(make_app())
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    log.info("Web server: http://0.0.0.0:%s", PORT)
    app_tasks.append(asyncio.create_task(translation_loop()))
    if bot:
        app_tasks.append(asyncio.create_task(social_loop()))
    shop.reset_stuck_videos()  # havolani saqlaymiz (GC o'chirib yubormasin)
    if not bot:
        log.warning("BOT_TOKEN yo'q — faqat web server ishlayapti (sinov rejimi).")
        await asyncio.Event().wait()
    if not ADMIN_IDS:
        log.warning("ADMIN_IDS bo'sh — buyurtmalar hech kimga yuborilmaydi!")
    try:
        SHOP["bot"] = (await bot.get_me()).username or SHOP["bot"]
    except TelegramAPIError as e:
        log.warning("bot nomini olib bo'lmadi: %s", e)
    try:  # botning ko'rinadigan nomi do'kon nomi bilan bir xil bo'lsin (masalan «iSofa»)
        if (await bot.get_my_name()).name != SHOP["name"]:
            await bot.set_my_name(SHOP["name"])
    except TelegramAPIError as e:
        log.warning("bot nomini o'zgartirib bo'lmadi: %s", e)
    await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="🛋 Do'kon", web_app=WebAppInfo(url=APP_URL)))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
