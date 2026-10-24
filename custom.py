"""O'lchamga (individual) buyurtmalar: arizalar, bosqichlar, taxminiy narx.

Tayyor mebel buyurtmalaridan alohida jadvalda saqlanadi (custom_requests) va o'z bosqichlariga ega.
Bu fayl web-freymvorkka bog'liq emas — Shop bilan bitta SQLite bazadan foydalanadi.
"""
import html
import json
import math
import os
import re
import time

from shop import ShopError, normalize_phone, fmt_price

# ------------------------------------------------------------------ mebel turlari
# dims: o'lcham maydonlari (sm). main — narx hisoblanadigan asosiy uzunlik (metrda olinadi).
# unit: "m" — narx 1 metr uchun; "dona" — bitta mahsulot uchun.
KINDS = {
    "sofa": {"uz": "Divan", "ru": "Диван", "icon": "🛋", "unit": "m", "main": ["w"],
             "dims": [("w", "Uzunligi", "Длина"), ("d", "Chuqurligi", "Глубина"), ("h", "Balandligi", "Высота")]},
    "corner": {"uz": "Burchak divan", "ru": "Угловой диван", "icon": "🛋", "unit": "m", "main": ["w", "w2"],
               "dims": [("w", "Katta tomoni", "Длинная сторона"), ("w2", "Kichik tomoni", "Короткая сторона"),
                        ("d", "Chuqurligi", "Глубина")]},
    "armchair": {"uz": "Kreslo", "ru": "Кресло", "icon": "💺", "unit": "dona", "main": [],
                 "dims": [("w", "Eni", "Ширина"), ("d", "Chuqurligi", "Глубина"), ("h", "Balandligi", "Высота")]},
    "bed": {"uz": "Karavot", "ru": "Кровать", "icon": "🛏", "unit": "dona", "main": [],
            "dims": [("w", "Matras eni", "Ширина матраса"), ("l", "Matras bo'yi", "Длина матраса")]},
    "wardrobe": {"uz": "Shkaf", "ru": "Шкаф", "icon": "🚪", "unit": "m", "main": ["w"],
                 "dims": [("w", "Eni", "Ширина"), ("h", "Balandligi", "Высота"), ("d", "Chuqurligi", "Глубина")]},
    "kitchen": {"uz": "Oshxona mebeli", "ru": "Кухня", "icon": "🍳", "unit": "m", "main": ["w", "w2"],
                "dims": [("w", "1-devor uzunligi", "Длина 1-й стены"), ("w2", "2-devor (burchak bo'lsa)", "2-я стена (если угловая)"),
                         ("h", "Shift balandligi", "Высота потолка")]},
    "other": {"uz": "Boshqa mebel", "ru": "Другая мебель", "icon": "🪑", "unit": "dona", "main": [],
              "dims": [("w", "Eni", "Ширина"), ("d", "Chuqurligi", "Глубина"), ("h", "Balandligi", "Высота")]},
}
# Material darajalari — narx koeffitsienti
TIERS = {
    "econom": {"uz": "Ekonom", "ru": "Эконом", "k": 1.0,
               "d_uz": "Oddiy mato, LDSP — arzon va pishiq", "d_ru": "Простая ткань, ЛДСП — недорого и прочно"},
    "standard": {"uz": "Standart", "ru": "Стандарт", "k": 1.2,
                 "d_uz": "Velyur, rogojka, MDF fasad — eng ko'p tanlanadi", "d_ru": "Велюр, рогожка, фасады МДФ — выбирают чаще всего"},
    "premium": {"uz": "Premium", "ru": "Премиум", "k": 1.45,
                "d_uz": "Ekokoja, premium matolar, massiv yog'och", "d_ru": "Экокожа, премиум-ткани, массив дерева"},
}
STAGES = {
    "new": ("🆕 Yangi ariza", "🆕 Новая заявка"),
    "measure": ("📏 O'lchov", "📏 Замер"),
    "design": ("✏️ Eskiz va narx", "✏️ Эскиз и цена"),
    "contract": ("📝 Shartnoma va oldindan to'lov", "📝 Договор и предоплата"),
    "production": ("🔨 Ishlab chiqarishda", "🔨 В производстве"),
    "ready": ("✅ Tayyor", "✅ Готово"),
    "delivered": ("🚚 Yetkazildi", "🚚 Доставлено"),
    "done": ("🤝 Yakunlandi", "🤝 Завершено"),
    "cancelled": ("❌ Bekor qilindi", "❌ Отменено"),
}
STAGE_ORDER = ["new", "measure", "design", "contract", "production", "ready", "delivered", "done"]
ACTIVE = ("new", "measure", "design", "contract", "production", "ready", "delivered")
# Bosqich o'zgarganda mijozga boradigan xabar
STAGE_MSG = {
    "measure": ("📏 Ariza №{id}: o'lchov bosqichi. Usta yoki menejer siz bilan bog'lanib, o'lchash vaqtini kelishadi.",
                "📏 Заявка №{id}: этап замера. Мастер или менеджер свяжется с вами и согласует время замера."),
    "design": ("✏️ Ariza №{id}: eskiz va aniq narx tayyorlanmoqda. Tayyor bo'lishi bilan yuboramiz.",
               "✏️ Заявка №{id}: готовим эскиз и точную цену. Пришлём, как только будет готово."),
    "contract": ("📝 Ariza №{id}: narx kelishildi. Shartnoma va oldindan to'lovdan keyin ishlab chiqarishni boshlaymiz.",
                 "📝 Заявка №{id}: цена согласована. После договора и предоплаты начнём производство."),
    "production": ("🔨 Ariza №{id}: mebelingiz ishlab chiqarilmoqda!", "🔨 Заявка №{id}: ваша мебель в производстве!"),
    "ready": ("✅ Ariza №{id}: mebelingiz tayyor! Yetkazish vaqtini kelishish uchun bog'lanamiz.",
              "✅ Заявка №{id}: ваша мебель готова! Свяжемся, чтобы согласовать доставку."),
    "delivered": ("🚚 Ariza №{id}: mebel yetkazildi. Xaridingiz uchun rahmat!",
                  "🚚 Заявка №{id}: мебель доставлена. Спасибо за покупку!"),
    "cancelled": ("❌ Ariza №{id} bekor qilindi. Savollar bo'lsa, adminga yozing.",
                  "❌ Заявка №{id} отменена. Если есть вопросы, напишите администратору."),
}
MAX_PHOTOS = 6

CUSTOM_SCHEMA = """
CREATE TABLE IF NOT EXISTS custom_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT DEFAULT '', name TEXT, phone TEXT,
    city TEXT DEFAULT '', address TEXT DEFAULT '', kind TEXT, model_id INTEGER, model_name TEXT DEFAULT '',
    dims TEXT DEFAULT '{}', measure_visit INTEGER DEFAULT 0, tier TEXT DEFAULT '', color TEXT DEFAULT '',
    note TEXT DEFAULT '', photos TEXT DEFAULT '[]', estimate_min INTEGER DEFAULT 0, estimate_max INTEGER DEFAULT 0,
    price INTEGER DEFAULT 0, prepay INTEGER DEFAULT 0, due TEXT DEFAULT '', admin_note TEXT DEFAULT '',
    status TEXT DEFAULT 'new', events TEXT DEFAULT '[]', admin_msgs TEXT DEFAULT '[]', lang TEXT DEFAULT 'uz',
    created INTEGER, updated INTEGER
);
"""


def kind_name(kind: str, lang: str = "uz") -> str:
    k = KINDS.get(kind) or KINDS["other"]
    return k["ru" if lang == "ru" else "uz"]


def stage_name(st: str, lang: str = "uz") -> str:
    return STAGES.get(st, (st, st))[1 if lang == "ru" else 0]


def default_rates() -> dict:
    """Boshlang'ich holatda narx kiritilmagan: mijozga taxminiy narx ko'rsatilmaydi, menejer o'zi hisoblaydi."""
    return {k: 0 for k in KINDS}


class CustomStore:
    def __init__(self, shop):
        self.shop = shop
        self.db = shop.db
        self.db.executescript(CUSTOM_SCHEMA)
        self.db.commit()
        self.photo_dir = os.path.join(os.path.dirname(shop.upload_dir.rstrip("/")), "custom")
        os.makedirs(self.photo_dir, exist_ok=True)

    # ------------------------------------------------ narx
    def rates(self) -> dict:
        try:
            saved = json.loads(self.shop.settings().get("custom_rates") or "{}")
        except ValueError:
            saved = {}
        r = default_rates()
        for k in r:
            try:
                r[k] = max(0, int(saved.get(k) or 0))
            except (TypeError, ValueError):
                pass
        return r

    def save_rates(self, data: dict) -> dict:
        r = default_rates()
        for k in r:
            raw = re.sub(r"\D", "", str((data or {}).get(k) or ""))
            r[k] = int(raw) if raw else 0
            if r[k] > 10 ** 10:
                raise ShopError("Narx juda katta")
        self.shop.set_setting("custom_rates", json.dumps(r))
        return r

    def estimate(self, kind: str, dims: dict, tier: str) -> tuple:
        """Taxminiy narx oralig'i (min, max). Narx kiritilmagan yoki o'lcham yo'q bo'lsa (0, 0)."""
        k = KINDS.get(kind)
        rate = self.rates().get(kind, 0)
        if not k or not rate:
            return 0, 0
        coef = TIERS.get(tier, TIERS["standard"])["k"]
        if k["unit"] == "m":
            length_cm = sum(float(dims.get(f) or 0) for f in k["main"])
            if length_cm <= 0:
                return 0, 0
            base = rate * length_cm / 100
        else:
            base = rate
        mid = base * coef
        lo = int(math.floor(mid * 0.9 / 10000) * 10000)
        hi = int(math.ceil(mid * 1.1 / 10000) * 10000)
        return lo, hi

    def config(self, lang: str = "uz") -> dict:
        ru = lang == "ru"
        rates = self.rates()
        return {
            "kinds": [{"id": k, "name": v["ru" if ru else "uz"], "icon": v["icon"], "unit": v["unit"],
                       "rate": rates.get(k, 0), "main": v["main"],
                       "dims": [{"id": f, "label": (lr if ru else lu)} for f, lu, lr in v["dims"]]}
                      for k, v in KINDS.items()],
            "tiers": [{"id": k, "name": v["ru" if ru else "uz"], "desc": v["d_ru" if ru else "d_uz"], "k": v["k"]}
                      for k, v in TIERS.items()],
            "stages": [{"id": s, "name": stage_name(s, lang)} for s in STAGE_ORDER],
            "max_photos": MAX_PHOTOS,
        }

    # ------------------------------------------------ arizalar
    @staticmethod
    def _row(r) -> dict:
        d = dict(r)
        for f, dflt in (("dims", "{}"), ("photos", "[]"), ("events", "[]"), ("admin_msgs", "[]")):
            d[f] = json.loads(d.get(f) or dflt)
        d["kind_name"] = kind_name(d["kind"], d.get("lang") or "uz")
        d["status_text"] = stage_name(d["status"])
        return d

    def get(self, rid: int) -> dict:
        r = self.db.execute("SELECT * FROM custom_requests WHERE id=?", (rid,)).fetchone()
        if not r:
            raise ShopError("Ariza topilmadi", "Заявка не найдена")
        return self._row(r)

    def list(self, status: str = "", limit: int = 200) -> list:
        if status == "active":
            q, a = f"SELECT * FROM custom_requests WHERE status IN ({','.join('?' * len(ACTIVE))}) ORDER BY id DESC LIMIT ?", (*ACTIVE, limit)
        elif status in STAGES:
            q, a = "SELECT * FROM custom_requests WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit)
        else:
            q, a = "SELECT * FROM custom_requests ORDER BY id DESC LIMIT ?", (limit,)
        return [self._row(r) for r in self.db.execute(q, a).fetchall()]

    def user_list(self, user_id: int, limit: int = 30) -> list:
        rows = self.db.execute("SELECT * FROM custom_requests WHERE user_id=? ORDER BY id DESC LIMIT ?",
                               (user_id, limit)).fetchall()
        return [self._row(r) for r in rows]

    def counts(self) -> dict:
        out = {s: 0 for s in STAGES}
        for r in self.db.execute("SELECT status, COUNT(*) c FROM custom_requests GROUP BY status").fetchall():
            out[r["status"]] = r["c"]
        out["active"] = sum(out[s] for s in ACTIVE)
        return out

    def create(self, user: dict, payload: dict, photos: list, lang: str = "uz") -> dict:
        kind = payload.get("kind")
        if kind not in KINDS:
            raise ShopError("Mebel turini tanlang", "Выберите тип мебели")
        visit = bool(payload.get("measure_visit"))
        dims = {}
        raw_dims = payload.get("dims") or {}
        for f, _, _ in KINDS[kind]["dims"]:
            v = str(raw_dims.get(f) or "").replace(",", ".").strip()
            if not v:
                continue
            try:
                n = float(v)
            except ValueError:
                raise ShopError("O'lchamni raqam bilan yozing (santimetrda)", "Укажите размер числом (в сантиметрах)")
            if not 10 <= n <= 2000:
                raise ShopError("O'lcham 10 dan 2000 sm gacha bo'lishi kerak", "Размер должен быть от 10 до 2000 см")
            dims[f] = round(n, 1)
        first = KINDS[kind]["dims"][0][0]
        if not visit and kind != "other" and first not in dims:
            raise ShopError("Asosiy o'lchamni kiriting yoki «Usta kelib o'lchasin»ni tanlang",
                            "Укажите основной размер или выберите «Нужен замер»")
        tier = payload.get("tier") if payload.get("tier") in TIERS else "standard"
        color = (payload.get("color") or "").strip()[:80]
        note = (payload.get("note") or "").strip()[:1000]
        if kind == "other" and len(note) < 5:
            raise ShopError("Qanday mebel kerakligini qisqacha yozing", "Коротко опишите, какая мебель нужна")
        name = (payload.get("name") or "").strip()[:80]
        if len(name) < 2:
            raise ShopError("Ismingizni kiriting", "Введите ваше имя")
        phone = normalize_phone(payload.get("phone"))
        city = (payload.get("city") or "").strip()[:120]
        address = (payload.get("address") or "").strip()[:300]
        model_id, model_name = None, ""
        try:
            mid = int(payload.get("model_id") or 0)
        except (TypeError, ValueError):
            mid = 0
        if mid:
            r = self.db.execute("SELECT name FROM products WHERE id=?", (mid,)).fetchone()
            if r:
                model_id, model_name = mid, r["name"]
        saved = []
        for data in photos[:MAX_PHOTOS]:
            name_ = self.shop._save_jpeg(data, self.photo_dir, 1600, 82)
            saved.append(name_)
        lo, hi = self.estimate(kind, dims, tier)
        now = int(time.time())
        cur = self.db.execute(
            "INSERT INTO custom_requests(user_id,username,name,phone,city,address,kind,model_id,model_name,dims,"
            "measure_visit,tier,color,note,photos,estimate_min,estimate_max,status,events,lang,created,updated)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (user["id"], user.get("username") or "", name, phone, city, address, kind, model_id, model_name,
             json.dumps(dims), 1 if visit else 0, tier, color, note, json.dumps(saved), lo, hi, "new",
             json.dumps([["new", now, "mijoz"]]), "ru" if lang == "ru" else "uz", now, now))
        self.db.commit()
        return self.get(cur.lastrowid)

    def set_status(self, rid: int, status: str, who: str = "") -> dict:
        if status not in STAGES:
            raise ShopError("Noto'g'ri bosqich")
        r = self.get(rid)
        if r["status"] == status:
            return r
        now = int(time.time())
        events = r["events"] + [[status, now, who]]
        self.db.execute("UPDATE custom_requests SET status=?, updated=?, events=? WHERE id=?",
                        (status, now, json.dumps(events, ensure_ascii=False), rid))
        self.db.commit()
        return self.get(rid)

    def update_admin(self, rid: int, data: dict) -> dict:
        r = self.get(rid)
        def num(k):
            raw = re.sub(r"\D", "", str(data.get(k, r[k]) or ""))
            return int(raw) if raw else 0
        price, prepay = num("price"), num("prepay")
        if prepay and price and prepay > price:
            raise ShopError("Oldindan to'lov narxdan katta bo'lishi mumkin emas")
        due = str(data.get("due", r["due"]) or "").strip()[:60]
        note = str(data.get("admin_note", r["admin_note"]) or "").strip()[:1000]
        self.db.execute("UPDATE custom_requests SET price=?, prepay=?, due=?, admin_note=?, updated=? WHERE id=?",
                        (price, prepay, due, note, int(time.time()), rid))
        self.db.commit()
        return self.get(rid)

    def set_admin_msgs(self, rid: int, msgs: list):
        self.db.execute("UPDATE custom_requests SET admin_msgs=? WHERE id=?", (json.dumps(msgs), rid))
        self.db.commit()

    def photo_path(self, rid: int, idx: int) -> str:
        r = self.get(rid)
        if not 0 <= idx < len(r["photos"]):
            raise ShopError("Rasm topilmadi")
        return os.path.join(self.photo_dir, os.path.basename(r["photos"][idx]))


# ------------------------------------------------------------------ matnlar
def dims_text(r: dict, lang: str = "uz") -> str:
    k = KINDS.get(r["kind"]) or KINDS["other"]
    parts = []
    for f, lu, lr in k["dims"]:
        if f in r["dims"]:
            v = r["dims"][f]
            parts.append(f"{lr if lang == 'ru' else lu}: {int(v) if float(v).is_integer() else v} sm")
    return "\n".join(parts)


def public(r: dict, lang: str = "uz") -> dict:
    """Mijozga: ichki izoh, guruh xabarlari va rasmlar yo'li yuborilmaydi."""
    out = {k: v for k, v in r.items() if k not in ("admin_msgs", "admin_note", "photos", "user_id", "username")}
    out["photos"] = len(r.get("photos") or [])
    out["kind_name"] = kind_name(r["kind"], lang)
    out["status_text"] = stage_name(r["status"], lang)
    out["tier_name"] = TIERS.get(r.get("tier"), {}).get("ru" if lang == "ru" else "uz", "")
    return out


def admin_text(r: dict) -> str:
    e = html.escape
    when = time.strftime("%d.%m.%Y %H:%M", time.gmtime(r["created"] + 5 * 3600))
    if r["user_id"] < 0:
        who = "🌐 saytdan — Telegram'i yo'q, telefon qiling"
    elif r.get("username"):
        who = "@" + e(r["username"])
    else:
        who = f"<a href=\"tg://user?id={r['user_id']}\">profil</a>"
    lines = [f"📐 <b>Individual ariza #{r['id']}</b> — {stage_name(r['status'])}", f"🕒 {when}", "",
             f"👤 {e(r['name'])} ({who})", f"📞 {e(r['phone'])}"]
    place = ", ".join(e(x) for x in (r.get("city"), r.get("address")) if x)
    if place:
        lines.append(f"🏠 {place}")
    lines += ["", f"{(KINDS.get(r['kind']) or KINDS['other'])['icon']} <b>{e(kind_name(r['kind']))}</b>"
              + (f" — asos: {e(r['model_name'])}" if r.get("model_name") else "")]
    d = dims_text(r)
    if d:
        lines.append("📏 " + e(d).replace("\n", "\n📏 "))
    if r.get("measure_visit"):
        lines.append("📏 <b>Usta borib o'lchashi kerak</b>")
    tier = TIERS.get(r.get("tier"), {}).get("uz")
    if tier:
        lines.append(f"🧵 Material: {e(tier)}" + (f", rang: {e(r['color'])}" if r.get("color") else ""))
    elif r.get("color"):
        lines.append(f"🎨 Rang: {e(r['color'])}")
    if r.get("note"):
        lines.append(f"📝 {e(r['note'])}")
    if r.get("photos"):
        lines.append(f"🖼 Rasmlar: {len(r['photos'])} ta")
    if r.get("estimate_min"):
        lines.append(f"\n💡 Saytdagi taxminiy narx: {fmt_price(r['estimate_min'])} – {fmt_price(r['estimate_max'])}")
    if r.get("price"):
        lines.append(f"💰 <b>Kelishilgan narx: {fmt_price(r['price'])}</b>"
                     + (f"\n💵 Oldindan to'lov: {fmt_price(r['prepay'])}" if r.get("prepay") else ""))
    if r.get("due"):
        lines.append(f"📅 Muddat: {e(r['due'])}")
    if r.get("admin_note"):
        lines.append(f"🗒 Izoh (ichki): {e(r['admin_note'])}")
    return "\n".join(lines)


def next_stages(status: str) -> list:
    """Keyingi bosqich va bekor qilish (yakunlangan/bekor qilinganda — qayta ochish)."""
    if status in ("done",):
        return []
    if status == "cancelled":
        return ["new"]
    i = STAGE_ORDER.index(status)
    return [STAGE_ORDER[i + 1], "cancelled"]
