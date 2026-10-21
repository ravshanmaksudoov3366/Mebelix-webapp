"""
Do'kon mantig'i: baza (SQLite), buyurtmalar, mahsulotlar, Telegram initData tekshiruvi.
Bu fayl hech qanday web-freymvorkka bog'liq emas.
"""
import hashlib
import hmac
import html
import io
import json
import math
import os
import re
import sqlite3
import time
import uuid
from urllib.parse import parse_qsl

STATUSES = {
    "new": "🧾 Chek tekshirilmoqda",
    "confirmed": "✅ Qabul qilindi",
    "delivering": "🚚 Yo'lda",
    "done": "📦 Yetkazildi",
    "rejected": "⛔ Chek rad etildi",
    "cancelled": "❌ Bekor qilindi",
}
ACTIONS = {
    "new": "🔄 Qayta tekshirish",
    "confirmed": "✅ Chekni tasdiqlash",
    "delivering": "🚚 Yo'lga chiqarish",
    "done": "📦 Yetkazildi",
    "rejected": "⛔ Chekni rad etish",
    "cancelled": "❌ Bekor qilish",
}
# Har bir holatdan qaysi holatlarga o'tish mumkin (admin tugmalari)
FLOW = {
    "new": ["confirmed", "rejected"],
    "confirmed": ["delivering", "cancelled"],
    "delivering": ["done", "cancelled"],
    "done": [],
    "rejected": ["confirmed", "cancelled"],
    "cancelled": ["new"],
}
ACTIVE = ("new", "confirmed", "delivering")
DELIVERY = {"delivery": "🚚 Yetkazib berish", "pickup": "🏬 Do'kondan olib ketish"}
# Qolgan summani to'lash usullari (naqd olib tashlangan)
PAYMENTS = ["Karta orqali (qabul qilganda)", "Click / Payme"]
LANGS = ("uz", "ru")
STATUSES_RU = {
    "new": "🧾 Чек проверяется",
    "confirmed": "✅ Принят",
    "delivering": "🚚 В пути",
    "done": "📦 Доставлен",
    "rejected": "⛔ Чек отклонён",
    "cancelled": "❌ Отменён",
}
PAYMENTS_RU = {"Karta orqali (qabul qilganda)": "Картой (при получении)", "Click / Payme": "Click / Payme",
               "Naqd (qabul qilganda)": "Наличными (при получении)"}
DEFAULT_SETTINGS = {"pay_card": "", "pay_owner": "", "prepay_pct": "10", "notify_new_users": "1"}


class ShopError(Exception):
    """Mijozga ko'rsatiladigan xato (o'zbekcha va ixtiyoriy ruscha matn)."""

    def __init__(self, uz: str, ru: str = ""):
        super().__init__(uz)
        self.ru = ru

    def text(self, lang: str = "uz") -> str:
        return self.ru if lang == "ru" and self.ru else str(self)


def norm_lang(lang) -> str:
    return "ru" if str(lang or "").lower().startswith("ru") else "uz"


class AuthError(Exception):
    pass


# ---------------------------------------------------------------- yordamchi
def fmt_price(n, lang: str = "uz") -> str:
    return f"{int(n):,}".replace(",", " ") + (" сум" if lang == "ru" else " so'm")


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:
        digits = "998" + digits
    if len(digits) < 9 or len(digits) > 15:
        raise ShopError("Telefon raqamni to'g'ri kiriting", "Введите правильный номер телефона")
    return "+" + digits


def check_init_data(init_data: str, bot_token: str, max_age: int = 86400) -> dict:
    """Telegram Mini App initData imzosini tekshiradi va foydalanuvchini qaytaradi."""
    if not init_data:
        raise AuthError("initData yo'q")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", "")
    check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise AuthError("imzo noto'g'ri")
    if max_age and time.time() - int(pairs.get("auth_date", 0)) > max_age:
        raise AuthError("sessiya eskirgan")
    user = json.loads(pairs.get("user", "{}"))
    if "id" not in user:
        raise AuthError("foydalanuvchi yo'q")
    return user


# ---------------------------------------------------------------- baza
SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, emoji TEXT DEFAULT '', sort INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY, cat_id INTEGER, name TEXT NOT NULL,
    price INTEGER NOT NULL, old_price INTEGER DEFAULT 0,
    description TEXT DEFAULT '', specs TEXT DEFAULT '[]', images TEXT DEFAULT '[]',
    emoji TEXT DEFAULT '🪑', in_stock INTEGER DEFAULT 1, active INTEGER DEFAULT 1,
    created INTEGER
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY, user_id INTEGER, username TEXT,
    name TEXT, phone TEXT, delivery TEXT, city TEXT, address TEXT, pay TEXT, note TEXT,
    items TEXT, total INTEGER, status TEXT DEFAULT 'new',
    admin_msgs TEXT DEFAULT '[]', created INTEGER, updated INTEGER
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, first_name TEXT, username TEXT, created INTEGER
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""
# Eski bazaga qo'shiladigan ustunlar
# *_ru — avtomatik (yoki admin tuzatgan) ruscha tarjima; tr_src — tarjima qilingan o'zbekcha matn "izi"
PRODUCT_COLUMNS = {"delivery_days": "TEXT DEFAULT ''", "name_ru": "TEXT DEFAULT ''", "description_ru": "TEXT DEFAULT ''",
                   "specs_ru": "TEXT DEFAULT '[]'", "delivery_days_ru": "TEXT DEFAULT ''", "tr_src": "TEXT DEFAULT ''"}
CATEGORY_COLUMNS = {"name_ru": "TEXT DEFAULT ''", "tr_src": "TEXT DEFAULT ''"}
USER_COLUMNS = {"last_name": "TEXT DEFAULT ''", "last_seen": "INTEGER", "lang": "TEXT DEFAULT ''"}
ORDER_COLUMNS = {"lat": "REAL", "lon": "REAL", "prepay": "INTEGER DEFAULT 0", "receipt": "TEXT DEFAULT ''"}

SEED_CATEGORIES = [("Divanlar", "🛋"), ("Yotoqxona", "🛏"), ("Oshxona", "🍳"),
                   ("Stol-stullar", "🪑"), ("Shkaflar", "🚪"), ("Bolalar", "🧸")]
SEED_CATEGORIES_RU = {"Divanlar": "Диваны", "Yotoqxona": "Спальня", "Oshxona": "Кухня",
                      "Stol-stullar": "Столы и стулья", "Shkaflar": "Шкафы", "Bolalar": "Детская"}
SEED_PRODUCTS = [
    (1, "Burchak divan «Milano»", 7490000, 8900000, "🛋",
     "Yumshoq velyur matoli burchak divan. Yoyiladi, ichida choyshab qutisi bor.",
     [["O'lcham", "280×180 sm"], ["Material", "Velyur, yog'och karkas"], ["Kafolat", "18 oy"]]),
    (1, "Divan-kreslo to'plami 3+1+1", 9800000, 0, "🛋",
     "Mehmonxona uchun klassik to'plam: 3 o'rinli divan va 2 ta kreslo.",
     [["Material", "Ekokoja"], ["Rang", "Jigarrang"], ["Kafolat", "24 oy"]]),
    (2, "Yotoqxona to'plami «Venetsiya»", 18500000, 21000000, "🛏",
     "Karavot, 2 ta tumbochka, 4 eshikli shkaf, tualet stoli va ko'zgu.",
     [["Karavot", "180×200 sm"], ["Material", "MDF, LDSP"], ["Kafolat", "24 oy"]]),
    (2, "Ortopedik matras", 2450000, 0, "🛌",
     "Mustaqil prujinali blok, o'rta qattiqlik.", [["O'lcham", "160×200 sm"], ["Balandlik", "24 sm"]]),
    (3, "Oshxona garnituri 2.4 m", 11900000, 0, "🍳",
     "Yuqori va pastki shkaflar, stoleshnitsa bilan. O'lchamga moslab ham yasaladi.",
     [["Uzunlik", "240 sm"], ["Fasad", "MDF bo'yalgan"]]),
    (4, "Ovqat stoli + 6 stul", 6700000, 7400000, "🪑",
     "Yoyiladigan stol va yumshoq o'rindiqli 6 ta stul.",
     [["Stol", "160(200)×90 sm"], ["Material", "Bukovaya yog'och"]]),
    (5, "Kupe shkaf 3 eshikli", 5300000, 0, "🚪",
     "Oynali kupe eshiklar, ichki javonlar va ilgich.", [["O'lcham", "210×240×60 sm"]]),
    (6, "Ikki qavatli bolalar karavoti", 4200000, 0, "🧸",
     "Zinali, xavfsiz to'siqlar bilan. Matrassiz.", [["O'lcham", "190×90 sm"], ["Material", "Massiv qarag'ay"]]),
]


class Shop:
    def __init__(self, db_path: str, upload_dir: str, receipt_dir: str = ""):
        self.upload_dir = upload_dir
        # cheklar ommaga ochiq emas: alohida papkada, faqat admin ko'ra oladi
        self.receipt_dir = receipt_dir or os.path.join(os.path.dirname(upload_dir.rstrip("/")), "receipts")
        os.makedirs(upload_dir, exist_ok=True)
        os.makedirs(self.receipt_dir, exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        for table, cols in (("orders", ORDER_COLUMNS), ("products", PRODUCT_COLUMNS),
                            ("categories", CATEGORY_COLUMNS), ("users", USER_COLUMNS)):
            have = {r[1] for r in self.db.execute(f"PRAGMA table_info({table})").fetchall()}
            for col, typ in cols.items():
                if col not in have:
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
        self.db.commit()
        if not self.db.execute("SELECT 1 FROM categories LIMIT 1").fetchone():
            self._seed()
        # standart kategoriyalarning ruscha nomlari (tarmoqsiz)
        for c in self.categories():
            if not c.get("name_ru") and c["name"] in SEED_CATEGORIES_RU:
                self.set_category_ru(c["id"], SEED_CATEGORIES_RU[c["name"]])

    def _seed(self):
        for i, (name, emoji) in enumerate(SEED_CATEGORIES):
            self.db.execute("INSERT INTO categories(name, emoji, sort) VALUES (?,?,?)", (name, emoji, i))
        now = int(time.time())
        for i, (cat, name, price, old, emoji, desc, specs) in enumerate(SEED_PRODUCTS):
            self.db.execute(
                "INSERT INTO products(cat_id,name,price,old_price,emoji,description,specs,created)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (cat, name, price, old, emoji, desc, json.dumps(specs, ensure_ascii=False), now - i))
        self.db.commit()

    # ------------------------------------------------ obyektlar
    @staticmethod
    def _product(r) -> dict:
        d = dict(r)
        d["specs"] = json.loads(d["specs"] or "[]")
        d["specs_ru"] = json.loads(d.get("specs_ru") or "[]")
        d["images"] = json.loads(d["images"] or "[]")
        d["in_stock"] = bool(d["in_stock"])
        d["active"] = bool(d["active"])
        return d

    @staticmethod
    def _order(r) -> dict:
        d = dict(r)
        d["items"] = json.loads(d["items"] or "[]")
        d["admin_msgs"] = json.loads(d["admin_msgs"] or "[]")
        d["status_text"] = STATUSES.get(d["status"], d["status"])
        return d

    # ------------------------------------------------ katalog
    def categories(self, lang: str = "") -> list:
        rows = [dict(r) for r in self.db.execute("SELECT * FROM categories ORDER BY sort, id").fetchall()]
        if lang == "ru":
            for c in rows:
                c["name"] = c.get("name_ru") or c["name"]
        return rows

    @staticmethod
    def localize_product(p: dict, lang: str) -> dict:
        """Mijozga ko'rsatish uchun: ruscha tanlangan bo'lsa, tarjima qilingan maydonlar."""
        if lang != "ru":
            return p
        p = dict(p)
        p["name"] = p.get("name_ru") or p["name"]
        p["description"] = p.get("description_ru") or p["description"]
        p["specs"] = p.get("specs_ru") or p["specs"]
        p["delivery_days"] = p.get("delivery_days_ru") or p.get("delivery_days") or ""
        return p

    @staticmethod
    def localize_order(o: dict, lang: str) -> dict:
        o = dict(o)
        if lang == "ru":
            o["status_text"] = STATUSES_RU.get(o["status"], o["status"])
            o["pay"] = PAYMENTS_RU.get(o.get("pay"), o.get("pay"))
            o["items"] = [{**i, "name": i.get("name_ru") or i["name"],
                           "delivery_days": i.get("delivery_days_ru") or i.get("delivery_days", "")} for i in o["items"]]
        return o

    def products(self, include_hidden=False) -> list:
        q = "SELECT * FROM products" + ("" if include_hidden else " WHERE active=1") + " ORDER BY created DESC"
        return [self._product(r) for r in self.db.execute(q).fetchall()]

    def product(self, pid: int) -> dict:
        r = self.db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if not r:
            raise ShopError("Mahsulot topilmadi", "Товар не найден")
        return self._product(r)

    # ------------------------------------------------ sozlamalar
    def settings(self) -> dict:
        d = dict(DEFAULT_SETTINGS)
        d.update({r[0]: r[1] for r in self.db.execute("SELECT key, value FROM settings").fetchall()})
        return d

    def save_settings(self, data: dict) -> dict:
        card = re.sub(r"\D", "", str(data.get("pay_card") or ""))
        if card and not 12 <= len(card) <= 19:
            raise ShopError("Karta raqamini to'g'ri kiriting (16 ta raqam)")
        owner = str(data.get("pay_owner") or "").strip()[:60]
        try:
            pct = int(re.sub(r"\D", "", str(data.get("prepay_pct") or "10")) or 10)
        except ValueError:
            pct = 10
        if not 1 <= pct <= 100:
            raise ShopError("Oldindan to'lov foizi 1 dan 100 gacha bo'lishi kerak")
        cur = self.settings()
        notify = data.get("notify_new_users", cur["notify_new_users"])
        notify = "1" if str(notify).lower() in ("1", "true", "on") else "0"
        for k, v in {"pay_card": card, "pay_owner": owner, "prepay_pct": str(pct),
                     "notify_new_users": notify}.items():
            self.db.execute("INSERT INTO settings(key, value) VALUES (?,?) "
                            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
        self.db.commit()
        return self.settings()

    def prepay_info(self) -> dict:
        st = self.settings()
        card = st["pay_card"]
        return {"card": " ".join(card[i:i + 4] for i in range(0, len(card), 4)), "owner": st["pay_owner"],
                "pct": int(st["prepay_pct"] or 10)}

    @staticmethod
    def prepay_amount(total: int, pct: int) -> int:
        """Oldindan to'lov: foiz, yuqoriga 1000 so'mgacha yaxlitlangan."""
        return int(math.ceil(total * pct / 100 / 1000) * 1000)

    def catalog(self, lang: str = "uz") -> dict:
        return {"categories": self.categories(lang), "products": [self.localize_product(p, lang) for p in self.products()],
                "payments": PAYMENTS, "payments_ru": PAYMENTS_RU, "prepay": self.prepay_info(), "lang": lang}

    # ------------------------------------------------ tarjima (uz -> ru)
    @staticmethod
    def _src_hash(*parts) -> str:
        return hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:16]

    def product_src(self, p: dict) -> str:
        return self._src_hash(p["name"], p["description"], p["specs"], p.get("delivery_days") or "")

    def products_to_translate(self) -> list:
        """Ruscha tarjimasi yo'q yoki o'zbekcha matni o'zgargan mahsulotlar."""
        return [p for p in self.products(include_hidden=True) if p.get("tr_src") != self.product_src(p)]

    def set_product_ru(self, pid: int, name: str, description: str, specs: list, delivery_days: str, src: str):
        self.db.execute("UPDATE products SET name_ru=?, description_ru=?, specs_ru=?, delivery_days_ru=?, tr_src=? "
                        "WHERE id=?", (name, description, json.dumps(specs, ensure_ascii=False), delivery_days, src, pid))
        self.db.commit()

    def categories_to_translate(self) -> list:
        return [c for c in self.categories() if c.get("tr_src") != self._src_hash(c["name"])]

    def set_category_ru(self, cid: int, name_ru: str, src: str = ""):
        row = self.db.execute("SELECT name FROM categories WHERE id=?", (cid,)).fetchone()
        if row:
            self.db.execute("UPDATE categories SET name_ru=?, tr_src=? WHERE id=?",
                            (name_ru, src or self._src_hash(row["name"]), cid))
            self.db.commit()

    # ------------------------------------------------ admin: mahsulotlar
    @staticmethod
    def _save_jpeg(data: bytes, folder: str, max_side: int, quality: int) -> str:
        from PIL import Image, ImageOps
        try:
            img = Image.open(io.BytesIO(data))
            img = ImageOps.exif_transpose(img).convert("RGB")
        except Exception:
            raise ShopError("Rasm faylini o'qib bo'lmadi. Iltimos, rasm (JPG/PNG) yuklang.",
                            "Не удалось прочитать файл. Загрузите изображение (JPG/PNG).")
        img.thumbnail((max_side, max_side))
        name = uuid.uuid4().hex[:16] + ".jpg"
        img.save(os.path.join(folder, name), "JPEG", quality=quality, optimize=True)
        return name

    def save_image(self, data: bytes) -> str:
        """Mahsulot rasmini siqib (max 1280px, JPEG) saqlaydi va URL yo'lini qaytaradi."""
        return "uploads/" + self._save_jpeg(data, self.upload_dir, 1280, 82)

    def receipt_path(self, o: dict) -> str:
        if not o.get("receipt"):
            return ""
        path = os.path.join(self.receipt_dir, os.path.basename(o["receipt"]))
        return path if os.path.isfile(path) else ""

    def save_product(self, data: dict, new_images: list = ()) -> dict:
        name = (data.get("name") or "").strip()
        if not name:
            raise ShopError("Mahsulot nomini kiriting")
        try:
            price = int(re.sub(r"\D", "", str(data.get("price") or "")))
        except ValueError:
            raise ShopError("Narxni kiriting")
        old_raw = re.sub(r"\D", "", str(data.get("old_price") or ""))
        old_price = int(old_raw) if old_raw else 0
        if old_price and old_price <= price:
            old_price = 0
        cat_id = int(data.get("cat_id") or 0) or None
        specs = []
        for line in str(data.get("specs") or "").splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                if k.strip() and v.strip():
                    specs.append([k.strip(), v.strip()])
        keep = data.get("keep_images")
        keep = json.loads(keep) if isinstance(keep, str) and keep else (keep or [])
        keep = [p for p in keep if isinstance(p, str) and p.startswith("uploads/")]
        new_images = list(new_images)
        # "order": rasmlar tartibi, masalan ["k:uploads/a.jpg", "n:0", "n:1"] (k — eski, n — yangi yuklangan)
        order = data.get("order")
        order = json.loads(order) if isinstance(order, str) and order else (order or [])
        images = []
        for ref in order:
            if not isinstance(ref, str):
                continue
            if ref.startswith("k:") and ref[2:] in keep:
                images.append(ref[2:])
            elif ref.startswith("n:") and ref[2:].isdigit() and int(ref[2:]) < len(new_images):
                images.append(new_images[int(ref[2:])])
        # tartibda ko'rsatilmaganlarini oxiriga qo'shamiz
        images += [p for p in keep + new_images if p not in images]
        fields = dict(
            cat_id=cat_id, name=name, price=price, old_price=old_price,
            description=(data.get("description") or "").strip(),
            specs=json.dumps(specs, ensure_ascii=False), images=json.dumps(images[:10]),
            emoji=(data.get("emoji") or "🪑").strip()[:4] or "🪑",
            delivery_days=(data.get("delivery_days") or "").strip()[:40],
            in_stock=1 if str(data.get("in_stock", "1")) in ("1", "true", "on") else 0,
            active=1 if str(data.get("active", "1")) in ("1", "true", "on") else 0,
        )
        pid = int(data.get("id") or 0)
        ru_edited = str(data.get("ru_edited", "")) in ("1", "true")
        if pid:
            old = self.product(pid)
            sets = ",".join(f"{k}=?" for k in fields)
            self.db.execute(f"UPDATE products SET {sets} WHERE id=?", (*fields.values(), pid))
            self._remove_unused_files(set(old["images"]) - set(images[:10]))
        else:
            fields["created"] = int(time.time())
            cols = ",".join(fields)
            cur = self.db.execute(f"INSERT INTO products({cols}) VALUES ({','.join('?' * len(fields))})",
                                  tuple(fields.values()))
            pid = cur.lastrowid
        self.db.commit()
        if ru_edited:  # admin ruscha tarjimani o'zi tuzatdi — avtomatik tarjima ustidan yozmaydi
            specs_ru = []
            for line in str(data.get("specs_ru") or "").splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    if k.strip() and v.strip():
                        specs_ru.append([k.strip(), v.strip()])
            p = self.product(pid)
            self.set_product_ru(pid, (data.get("name_ru") or "").strip()[:200], (data.get("description_ru") or "").strip(),
                                specs_ru, (data.get("delivery_days_ru") or "").strip()[:40], self.product_src(p))
        return self.product(pid)

    def delete_product(self, pid: int):
        p = self.product(pid)
        self.db.execute("DELETE FROM products WHERE id=?", (pid,))
        self.db.commit()
        self._remove_unused_files(set(p["images"]))

    def _remove_unused_files(self, paths):
        for p in paths:
            fn = os.path.join(self.upload_dir, os.path.basename(p))
            if os.path.isfile(fn):
                os.remove(fn)

    # ------------------------------------------------ admin: kategoriyalar
    def save_category(self, data: dict) -> dict:
        name = (data.get("name") or "").strip()
        if not name:
            raise ShopError("Kategoriya nomini kiriting")
        emoji = (data.get("emoji") or "").strip()[:4]
        cid = int(data.get("id") or 0)
        name_ru = (data.get("name_ru") or "").strip()[:80]
        if cid:
            self.db.execute("UPDATE categories SET name=?, emoji=? WHERE id=?", (name, emoji, cid))
        else:
            sort = self.db.execute("SELECT COALESCE(MAX(sort),0)+1 FROM categories").fetchone()[0]
            cid = self.db.execute("INSERT INTO categories(name,emoji,sort) VALUES (?,?,?)",
                                  (name, emoji, sort)).lastrowid
        self.db.commit()
        if name_ru:
            self.set_category_ru(cid, name_ru)
        return dict(self.db.execute("SELECT * FROM categories WHERE id=?", (cid,)).fetchone())

    def delete_category(self, cid: int):
        n = self.db.execute("SELECT COUNT(*) FROM products WHERE cat_id=?", (cid,)).fetchone()[0]
        if n:
            raise ShopError(f"Bu kategoriyada {n} ta mahsulot bor. Avval ularni boshqa kategoriyaga o'tkazing.")
        self.db.execute("DELETE FROM categories WHERE id=?", (cid,))
        self.db.commit()

    # ------------------------------------------------ foydalanuvchilar
    def touch_user(self, user: dict) -> bool:
        """Mijozni saqlaydi/yangilaydi. Birinchi marta qo'shilgan bo'lsa True qaytaradi."""
        now = int(time.time())
        is_new = not self.db.execute("SELECT 1 FROM users WHERE id=?", (user["id"],)).fetchone()
        self.db.execute(
            "INSERT INTO users(id, first_name, last_name, username, created, last_seen) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET first_name=excluded.first_name, last_name=excluded.last_name, "
            "username=excluded.username, last_seen=excluded.last_seen",
            (user["id"], user.get("first_name") or "", user.get("last_name") or "", user.get("username") or "",
             now, now))
        self.db.commit()
        return is_new

    def user_lang(self, user_id: int) -> str:
        r = self.db.execute("SELECT lang FROM users WHERE id=?", (user_id,)).fetchone()
        return r["lang"] if r and r["lang"] in LANGS else ""

    def set_user_lang(self, user_id: int, lang: str):
        lang = norm_lang(lang)
        self.db.execute("INSERT INTO users(id, lang, created, last_seen) VALUES (?,?,?,?) "
                        "ON CONFLICT(id) DO UPDATE SET lang=excluded.lang", (user_id, lang, int(time.time()), int(time.time())))
        self.db.commit()
        return lang

    def user_ids_by_lang(self) -> dict:
        out = {"uz": [], "ru": []}
        for r in self.db.execute("SELECT id, lang FROM users").fetchall():
            out["ru" if r["lang"] == "ru" else "uz"].append(r["id"])
        return out

    def customer_stats(self, tz_offset_hours: int = 5) -> dict:
        import calendar
        off = tz_offset_hours * 3600
        t = time.gmtime(time.time() + off)
        day = calendar.timegm((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0)) - off
        q = lambda sql, *a: self.db.execute(sql, a).fetchone()[0]
        return {
            "total": q("SELECT COUNT(*) FROM users"),
            "today": q("SELECT COUNT(*) FROM users WHERE created>=?", day),
            "week": q("SELECT COUNT(*) FROM users WHERE created>=?", day - 6 * 86400),
            "month": q("SELECT COUNT(*) FROM users WHERE created>=?", day - 29 * 86400),
            "active7": q("SELECT COUNT(*) FROM users WHERE COALESCE(last_seen, created)>=?", int(time.time()) - 7 * 86400),
            "buyers": q("SELECT COUNT(DISTINCT user_id) FROM orders WHERE status NOT IN ('cancelled','rejected')"),
            "ru": q("SELECT COUNT(*) FROM users WHERE lang='ru'"),
        }

    def customers(self, query: str = "", offset: int = 0, limit: int = 50) -> dict:
        where, args = "", []
        query = (query or "").strip().lstrip("@")
        if query:
            like = f"%{query}%"
            where = ("WHERE u.first_name LIKE ? OR u.last_name LIKE ? OR u.username LIKE ? OR CAST(u.id AS TEXT) LIKE ? "
                     "OR u.id IN (SELECT user_id FROM orders WHERE phone LIKE ? OR name LIKE ?)")
            args = [like, like, like, like, f"%{re.sub(chr(92) + 'D', '', query) or query}%", like]
        total = self.db.execute(f"SELECT COUNT(*) FROM users u {where}", args).fetchone()[0]
        rows = self.db.execute(f"""
            SELECT u.id, u.first_name, u.last_name, u.username, u.lang, u.created, COALESCE(u.last_seen, u.created) AS last_seen,
              (SELECT COUNT(*) FROM orders o WHERE o.user_id=u.id) AS orders,
              (SELECT COALESCE(SUM(total),0) FROM orders o WHERE o.user_id=u.id
                 AND o.status NOT IN ('cancelled','rejected')) AS spent,
              (SELECT phone FROM orders o WHERE o.user_id=u.id ORDER BY o.id DESC LIMIT 1) AS phone
            FROM users u {where} ORDER BY u.created DESC LIMIT ? OFFSET ?""",
            [*args, max(1, min(200, limit)), max(0, offset)]).fetchall()
        return {"total": total, "items": [dict(r) for r in rows]}

    def user_ids(self) -> list:
        return [r[0] for r in self.db.execute("SELECT id FROM users").fetchall()]

    def last_profile(self, user_id: int) -> dict:
        r = self.db.execute("SELECT name, phone, city, address, delivery, pay, lat, lon FROM orders "
                            "WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
        return dict(r) if r else {}

    # ------------------------------------------------ buyurtmalar
    def create_order(self, user: dict, payload: dict, receipt: bytes = b"") -> dict:
        raw_items = payload.get("items") or []
        if not raw_items:
            raise ShopError("Savatcha bo'sh", "Корзина пуста")
        items, total = [], 0
        for it in raw_items[:50]:
            try:
                pid, qty = int(it["id"]), int(it["qty"])
            except (KeyError, TypeError, ValueError):
                raise ShopError("Savatchada xato bor", "Ошибка в корзине")
            if not 1 <= qty <= 99:
                raise ShopError("Miqdor noto'g'ri", "Неверное количество")
            r = self.db.execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
            if not r:
                raise ShopError("Savatchadagi ba'zi mahsulotlar endi sotuvda yo'q. Savatchani yangilang.",
                                "Некоторых товаров из корзины больше нет в продаже. Обновите корзину.")
            if not r["in_stock"]:
                raise ShopError(f"«{r['name']}» hozir omborda yo'q", f"«{r['name_ru'] or r['name']}» сейчас нет в наличии")
            items.append({"id": pid, "name": r["name"], "name_ru": r["name_ru"] or "", "price": r["price"], "qty": qty,
                          "image": (json.loads(r["images"]) or [None])[0], "emoji": r["emoji"],
                          "delivery_days": r["delivery_days"] or "", "delivery_days_ru": r["delivery_days_ru"] or ""})
            total += r["price"] * qty

        c = payload.get("customer") or {}
        name = (c.get("name") or "").strip()[:80]
        if len(name) < 2:
            raise ShopError("Ismingizni kiriting", "Введите ваше имя")
        phone = normalize_phone(c.get("phone"))
        delivery = c.get("delivery") if c.get("delivery") in DELIVERY else "delivery"
        city = (c.get("city") or "").strip()[:200]
        address = (c.get("address") or "").strip()[:300]
        lat = lon = None
        if delivery == "delivery":
            try:
                lat, lon = float(c.get("lat")), float(c.get("lon"))
            except (TypeError, ValueError):
                raise ShopError("Yetkazib berish manzilini xaritada belgilang", "Отметьте адрес доставки на карте")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ShopError("Joylashuv noto'g'ri. Xaritada qayta belgilang.", "Неверная геолокация. Отметьте адрес на карте заново.")
        pay = c.get("pay") if c.get("pay") in PAYMENTS else PAYMENTS[0]
        note = (c.get("note") or "").strip()[:500]

        info = self.prepay_info()
        if not info["card"]:
            raise ShopError("Do'kon hali to'lov kartasini kiritmagan. Iltimos, keyinroq urinib ko'ring "
                            "yoki do'konga qo'ng'iroq qiling.",
                            "Магазин ещё не указал карту для оплаты. Попробуйте позже или позвоните в магазин.")
        prepay = self.prepay_amount(total, info["pct"])
        if not receipt:
            raise ShopError(f"Oldindan to'lov ({fmt_price(prepay)}) chekining rasmini yuklang",
                            f"Загрузите фото чека предоплаты ({fmt_price(prepay, 'ru')})")
        receipt_name = self._save_jpeg(receipt, self.receipt_dir, 1600, 85)

        now = int(time.time())
        cur = self.db.execute(
            "INSERT INTO orders(user_id,username,name,phone,delivery,city,address,pay,note,items,total,"
            "status,created,updated,lat,lon,prepay,receipt) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (user["id"], user.get("username", ""), name, phone, delivery, city, address, pay, note,
             json.dumps(items, ensure_ascii=False), total, "new", now, now, lat, lon, prepay, receipt_name))
        self.db.commit()
        return self.order(cur.lastrowid)

    def order(self, oid: int) -> dict:
        r = self.db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        if not r:
            raise ShopError("Buyurtma topilmadi", "Заказ не найден")
        return self._order(r)

    def user_orders(self, user_id: int, limit=30) -> list:
        rows = self.db.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT ?",
                               (user_id, limit)).fetchall()
        return [self._order(r) for r in rows]

    def orders(self, status: str = "", limit=200) -> list:
        if status in STATUSES:
            rows = self.db.execute("SELECT * FROM orders WHERE status=? ORDER BY id DESC LIMIT ?",
                                   (status, limit)).fetchall()
        elif status == "active":
            rows = self.db.execute(f"SELECT * FROM orders WHERE status IN {ACTIVE} "
                                   "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self._order(r) for r in rows]

    def set_status(self, oid: int, status: str) -> dict:
        if status not in STATUSES:
            raise ShopError("Noma'lum holat")
        self.order(oid)
        self.db.execute("UPDATE orders SET status=?, updated=? WHERE id=?", (status, int(time.time()), oid))
        self.db.commit()
        return self.order(oid)

    def cancel_by_user(self, user_id: int, oid: int) -> dict:
        o = self.order(oid)
        if o["user_id"] != user_id:
            raise ShopError("Buyurtma topilmadi", "Заказ не найден")
        raise ShopError("Oldindan to'lov qilingan buyurtmani bekor qilish uchun do'konga qo'ng'iroq qiling.",
                        "Чтобы отменить заказ с предоплатой, позвоните в магазин.")

    def set_admin_msgs(self, oid: int, msgs: list):
        self.db.execute("UPDATE orders SET admin_msgs=? WHERE id=?", (json.dumps(msgs), oid))
        self.db.commit()

    def stats(self, tz_offset_hours: int = 5) -> dict:
        import calendar
        off = tz_offset_hours * 3600
        t = time.gmtime(time.time() + off)  # mahalliy vaqt
        day_start = calendar.timegm((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0)) - off
        month_start = calendar.timegm((t.tm_year, t.tm_mon, 1, 0, 0, 0)) - off
        q = lambda sql, *a: self.db.execute(sql, a).fetchone()[0]
        ok = "status NOT IN ('cancelled','rejected')"
        return {
            "new": q("SELECT COUNT(*) FROM orders WHERE status='new'"),
            "active": q(f"SELECT COUNT(*) FROM orders WHERE status IN {ACTIVE}"),
            "today_orders": q(f"SELECT COUNT(*) FROM orders WHERE created>=? AND {ok}", day_start),
            "today_sum": q(f"SELECT COALESCE(SUM(total),0) FROM orders WHERE created>=? AND {ok}", day_start),
            "month_orders": q(f"SELECT COUNT(*) FROM orders WHERE created>=? AND {ok}", month_start),
            "month_sum": q(f"SELECT COALESCE(SUM(total),0) FROM orders WHERE created>=? AND {ok}", month_start),
            "products": q("SELECT COUNT(*) FROM products WHERE active=1"),
            "customers": q("SELECT COUNT(*) FROM users"),
        }


# ---------------------------------------------------------------- xabar matnlari
def order_text(o: dict, for_admin: bool, lang: str = "uz") -> str:
    e = lambda s: html.escape(str(s), quote=False)
    if not for_admin and lang == "ru":
        o = Shop.localize_order(o, "ru")
        lines = "\n".join(f"• {e(i['name'])} × {i['qty']} = {fmt_price(i['price'] * i['qty'], 'ru')}"
                          + (f"\n   🚚 Доставка: {e(i['delivery_days'])}" if i.get("delivery_days") else "")
                          for i in o["items"])
        return (f"<b>Заказ #{o['id']}</b>\nСтатус: {o['status_text']}\n\n{lines}\n\n"
                f"<b>Итого: {fmt_price(o['total'], 'ru')}</b>"
                + (f"\nПредоплата: {fmt_price(o['prepay'], 'ru')}\nОстаток: {fmt_price(o['total'] - o['prepay'], 'ru')}"
                   if o.get("prepay") else ""))
    lines = "\n".join(f"• {e(i['name'])} × {i['qty']} = {fmt_price(i['price'] * i['qty'])}"
                      + (f"\n   🚚 Yetkazish: {e(i['delivery_days'])}" if i.get("delivery_days") else "")
                      for i in o["items"])
    when = time.strftime("%d.%m.%Y %H:%M", time.gmtime(o["created"] + 5 * 3600))
    if for_admin:
        user = f"@{e(o['username'])}" if o.get("username") else f"<a href=\"tg://user?id={o['user_id']}\">profil</a>"
        place = DELIVERY.get(o["delivery"], "")
        if o["delivery"] == "delivery":
            addr = ", ".join(e(x) for x in (o.get("city"), o.get("address")) if x)
            if addr:
                place += f"\n🏠 {addr}"
            if o.get("lat") is not None:
                g, y = (html.escape(u) for u in map_links(o))  # & -> &amp; (Telegram HTML talabi)
                place += f"\n📍 Xaritada: <a href=\"{g}\">Google</a> · <a href=\"{y}\">Yandex</a>"
        return (f"<b>Buyurtma #{o['id']}</b> — {o['status_text']}\n🕒 {when}\n\n"
                f"👤 {e(o['name'])} ({user})\n📞 {e(o['phone'])}\n{place}\n💳 Qolgan summa: {e(o['pay'])}\n"
                + (f"📝 {e(o['note'])}\n" if o.get("note") else "")
                + f"\n{lines}\n\n<b>Jami: {fmt_price(o['total'])}</b>"
                + (f"\n💰 Oldindan to'lov: <b>{fmt_price(o['prepay'])}</b> (chek ilova qilingan)"
                   f"\n💵 Qolgan: {fmt_price(o['total'] - o['prepay'])}" if o.get("prepay") else ""))
    return (f"<b>Buyurtma #{o['id']}</b>\nHolati: {o['status_text']}\n\n{lines}\n\n"
            f"<b>Jami: {fmt_price(o['total'])}</b>"
            + (f"\nOldindan to'langan: {fmt_price(o['prepay'])}\nQolgan: {fmt_price(o['total'] - o['prepay'])}"
               if o.get("prepay") else ""))


def map_links(o: dict) -> tuple:
    lat, lon = o["lat"], o["lon"]
    return (f"https://www.google.com/maps?q={lat:.6f},{lon:.6f}",
            f"https://yandex.uz/maps/?pt={lon:.6f},{lat:.6f}&z=17&l=map")


STATUS_MESSAGES_RU = {
    "confirmed": "✅ Ваш чек проверен, заказ #{id} принят! Скоро мы свяжемся с вами, чтобы согласовать время доставки.",
    "rejected": "⛔ Чек об оплате по заказу #{id} не подтверждён. Пожалуйста, свяжитесь с магазином или напишите в этот бот.",
    "delivering": "🚚 Ваш заказ #{id} в пути.",
    "done": "📦 Ваш заказ #{id} доставлен. Спасибо за покупку! 🙏",
    "cancelled": "❌ Ваш заказ #{id} отменён. Если есть вопросы, свяжитесь с нами.",
}

STATUS_MESSAGES = {
    "confirmed": "✅ To'lov chekingiz tekshirildi va buyurtmangiz #{id} qabul qilindi! "
                 "Tez orada yetkazib berish vaqtini kelishib olamiz.",
    "rejected": "⛔ Buyurtma #{id} uchun yuborilgan to'lov cheki tasdiqlanmadi. "
                "Iltimos, do'kon bilan bog'laning yoki shu botga yozing.",
    "delivering": "🚚 Buyurtmangiz #{id} yo'lga chiqdi.",
    "done": "📦 Buyurtmangiz #{id} yetkazib berildi. Xaridingiz uchun rahmat! 🙏",
    "cancelled": "❌ Buyurtmangiz #{id} bekor qilindi. Savollar bo'lsa, biz bilan bog'laning.",
}
