"""
Mebel do'koni: Telegram bot + Mini App serveri (bitta jarayonda).
Ishga tushirish:  python app.py   (sozlamalar .env faylida)
"""
import asyncio
import html
import json
import logging
import os
import re
from pathlib import Path

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

from shop import (
    ACTIONS,
    STATUS_MESSAGES,
    STATUSES,
    AuthError,
    Shop,
    ShopError,
    check_init_data,
    order_text,
)

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
NOTIFY_CHATS = list(ADMIN_IDS) + ([GROUP_ID] if GROUP_ID else [])
# Render o'zi RENDER_EXTERNAL_URL beradi, shuning uchun u yerda WEBAPP_URL shart emas
WEBAPP_URL = (os.getenv("WEBAPP_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/") + "/"
SHOP = {
    "name": os.getenv("SHOP_NAME", "Mebel Do'koni"),
    "phone": os.getenv("SHOP_PHONE", ""),
    "address": os.getenv("SHOP_ADDRESS", ""),
}
PORT = int(os.getenv("PORT", "8080"))
DB_PATH = os.getenv("DB_PATH", str(BASE / "data" / "shop.db"))
UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(BASE / "data" / "uploads"))
DEV = os.getenv("DEV") == "1"  # FAQAT sinov uchun: brauzerda Telegram'siz ochish

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("shop")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
shop = Shop(DB_PATH, UPLOAD_DIR)
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) if BOT_TOKEN else None
dp = Dispatcher()


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# ------------------------------------------------------------------ bildirishnomalar
def status_keyboard(o: dict, chat_id: int = 1) -> InlineKeyboardMarkup:
    flow = {"new": ["confirmed", "cancelled"], "confirmed": ["delivering", "cancelled"],
            "delivering": ["done", "cancelled"], "done": [], "cancelled": ["new"]}
    btns = [InlineKeyboardButton(text=ACTIONS[s], callback_data=f"st:{o['id']}:{s}")
            for s in flow.get(o["status"], [])]
    rows = [btns[i:i + 2] for i in range(0, len(btns), 2)]
    if chat_id > 0:  # Mini App tugmasi guruhlarda ishlamaydi
        rows.append([InlineKeyboardButton(text="🗂 Admin panel", web_app=WebAppInfo(url=WEBAPP_URL + "?admin=1"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def notify_new_order(o: dict):
    if not bot:
        return
    msgs = []
    for aid in NOTIFY_CHATS:
        try:
            m = await bot.send_message(aid, "🔔 " + order_text(o, for_admin=True),
                                       reply_markup=status_keyboard(o, aid))
            msgs.append([aid, m.message_id])
        except TelegramAPIError as e:
            log.warning("adminga yuborilmadi %s: %s", aid, e)
    shop.set_admin_msgs(o["id"], msgs)
    try:
        await bot.send_message(
            o["user_id"],
            "✅ <b>Buyurtmangiz qabul qilindi!</b>\n\n" + order_text(o, for_admin=False)
            + "\n\nMenejerimiz tez orada siz bilan bog'lanadi.")
    except TelegramAPIError as e:
        log.warning("mijozga yuborilmadi: %s", e)


async def notify_status(o: dict):
    if not bot:
        return
    for chat_id, msg_id in o["admin_msgs"]:
        try:
            await bot.edit_message_text(order_text(o, for_admin=True), chat_id=chat_id, message_id=msg_id,
                                        reply_markup=status_keyboard(o, chat_id))
        except TelegramAPIError:
            pass
    text = STATUS_MESSAGES.get(o["status"])
    if text:
        try:
            await bot.send_message(o["user_id"], text.format(id=o["id"]))
        except TelegramAPIError:
            pass


# ------------------------------------------------------------------ bot
def shop_button(text="🛋 Katalogni ochish", suffix="") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=text, web_app=WebAppInfo(url=WEBAPP_URL + suffix))]])


@dp.message(CommandStart())
async def cmd_start(m: Message):
    shop.touch_user(m.from_user.model_dump())
    text = (f"Assalomu alaykum, <b>{esc(m.from_user.first_name or '')}</b>! 👋\n\n"
            f"<b>{esc(SHOP['name'])}</b> ga xush kelibsiz.\n"
            "Tayyor mebellar katalogini ko'ring va bir necha bosishda buyurtma bering 👇")
    if SHOP["phone"]:
        text += f"\n\n📞 {esc(SHOP['phone'])}"
    if SHOP["address"]:
        text += f"\n📍 {esc(SHOP['address'])}"
    text += "\n\nSavolingiz bo'lsa, shu yerga yozing, menejer javob beradi."
    await m.answer(text, reply_markup=shop_button())
    if is_admin(m.from_user.id):
        await m.answer("Siz adminsiz. Mahsulot va buyurtmalarni boshqarish:",
                       reply_markup=shop_button("🗂 Admin panel", "?admin=1"))


@dp.message(Command("admin"))
async def cmd_admin(m: Message):
    if is_admin(m.from_user.id):
        await m.answer("🗂 Admin panel:", reply_markup=shop_button("🗂 Admin panelni ochish", "?admin=1"))
    else:
        await m.answer(f"Sizning ID: <code>{m.from_user.id}</code>\nAdmin emassiz.")


@dp.message(Command("id"))
async def cmd_id(m: Message):
    await m.answer(f"Sizning Telegram ID: <code>{m.from_user.id}</code>")


@dp.callback_query(F.data.startswith("st:"))
async def cb_status(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        return await c.answer("Ruxsat yo'q", show_alert=True)
    _, oid, status = c.data.split(":")
    try:
        o = shop.set_status(int(oid), status)
    except ShopError as e:
        return await c.answer(str(e), show_alert=True)
    await notify_status(o)
    await c.answer(o["status_text"])


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
        await bot.send_message(int(found.group(1)), f"💬 <b>Menejer:</b>\n{esc(m.text)}")
        await m.answer("✅ Yuborildi")
    except TelegramAPIError as e:
        await m.answer(f"Yuborilmadi: {e}")


@dp.message(F.chat.type == "private", F.text)
async def user_message(m: Message):
    """Mijozning oddiy xabarini adminlarga uzatadi."""
    if is_admin(m.from_user.id):
        return await m.answer("Mijozga javob berish uchun uning xabariga «Reply» qiling.",
                              reply_markup=shop_button("🗂 Admin panel", "?admin=1"))
    shop.touch_user(m.from_user.model_dump())
    u = m.from_user
    who = esc(u.full_name) + (f" (@{u.username})" if u.username else "")
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid, f"💬 <b>{who}</b> #u{u.id}\n\n{esc(m.text)}\n\n"
                                        "<i>Javob berish uchun shu xabarga «Reply» qiling.</i>")
        except TelegramAPIError:
            pass
    await m.answer("Xabaringiz menejerga yuborildi. Tez orada javob beramiz 🙏", reply_markup=shop_button())


# ------------------------------------------------------------------ web API
def get_user(request: web.Request) -> dict:
    init_data = request.headers.get("X-Init-Data", "")
    if DEV and not init_data:
        return {"id": int(os.getenv("DEV_USER_ID") or next(iter(ADMIN_IDS), 1)), "first_name": "Test",
                "username": "test"}
    return check_init_data(init_data, BOT_TOKEN)


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
        return web.json_response({"error": str(e)}, status=400)
    except AuthError as e:
        return web.json_response({"error": "Ruxsat yo'q. Ilovani bot orqali qayta oching.", "detail": str(e)},
                                 status=401)


async def page_index(request):
    return web.FileResponse(BASE / "webapp" / "index.html", headers={"Cache-Control": "no-cache"})


async def api_catalog(request):
    return web.json_response({"shop": SHOP, **shop.catalog()})


async def api_me(request):
    u = get_user(request)
    shop.touch_user(u)
    return web.json_response({"user": u, "is_admin": is_admin(u["id"]),
                              "profile": shop.last_profile(u["id"]), "orders": shop.user_orders(u["id"])})


async def api_order(request):
    u = get_user(request)
    o = shop.create_order(u, await request.json())
    asyncio.create_task(notify_new_order(o))
    return web.json_response({"order": o})


async def api_order_cancel(request):
    u = get_user(request)
    o = shop.cancel_by_user(u["id"], int(request.match_info["id"]))
    asyncio.create_task(notify_status(o))
    return web.json_response({"order": o})


async def api_admin_data(request):
    get_admin(request)
    return web.json_response({"stats": shop.stats(), "orders": shop.orders(request.query.get("status", "")),
                              "products": shop.products(include_hidden=True), "categories": shop.categories(),
                              "statuses": STATUSES})


async def api_admin_product(request):
    get_admin(request)
    data, images = {}, []
    reader = await request.multipart()
    async for part in reader:
        if part.name == "images" and part.filename:
            raw = await part.read(decode=False)
            if raw:
                images.append(shop.save_image(bytes(raw)))
        elif part.name:
            data[part.name] = await part.text()
    return web.json_response({"product": shop.save_product(data, images)})


async def api_admin_product_delete(request):
    get_admin(request)
    shop.delete_product(int(request.match_info["id"]))
    return web.json_response({"ok": True})


async def api_admin_category(request):
    get_admin(request)
    return web.json_response({"category": shop.save_category(await request.json())})


async def api_admin_category_delete(request):
    get_admin(request)
    shop.delete_category(int(request.match_info["id"]))
    return web.json_response({"ok": True})


async def api_admin_status(request):
    get_admin(request)
    body = await request.json()
    o = shop.set_status(int(request.match_info["id"]), body.get("status", ""))
    asyncio.create_task(notify_status(o))
    return web.json_response({"order": o})


async def api_admin_broadcast(request):
    get_admin(request)
    text = ((await request.json()).get("text") or "").strip()
    if not text:
        raise ShopError("Xabar matnini yozing")
    ids = shop.user_ids()

    async def run():
        sent = 0
        for uid in ids:
            try:
                await bot.send_message(uid, esc(text), reply_markup=shop_button())
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
    return web.json_response({"queued": len(ids)})


def make_app() -> web.Application:
    app = web.Application(middlewares=[errors], client_max_size=60 * 1024 * 1024)
    app.router.add_get("/", page_index)
    app.router.add_static("/uploads/", UPLOAD_DIR)
    app.router.add_get("/api/catalog", api_catalog)
    app.router.add_post("/api/me", api_me)
    app.router.add_post("/api/order", api_order)
    app.router.add_post("/api/order/{id}/cancel", api_order_cancel)
    app.router.add_get("/api/admin/data", api_admin_data)
    app.router.add_post("/api/admin/product", api_admin_product)
    app.router.add_post("/api/admin/product/{id}/delete", api_admin_product_delete)
    app.router.add_post("/api/admin/category", api_admin_category)
    app.router.add_post("/api/admin/category/{id}/delete", api_admin_category_delete)
    app.router.add_post("/api/admin/order/{id}/status", api_admin_status)
    app.router.add_post("/api/admin/broadcast", api_admin_broadcast)
    return app


async def main():
    runner = web.AppRunner(make_app())
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    log.info("Web server: http://0.0.0.0:%s", PORT)
    if not bot:
        log.warning("BOT_TOKEN yo'q — faqat web server ishlayapti (sinov rejimi).")
        await asyncio.Event().wait()
    if not ADMIN_IDS:
        log.warning("ADMIN_IDS bo'sh — buyurtmalar hech kimga yuborilmaydi!")
    await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="🛋 Do'kon", web_app=WebAppInfo(url=WEBAPP_URL)))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
