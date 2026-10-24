"""O'lchamga (individual) buyurtmalar: uslublar (Hi-Tech / Neoklassika / Klassika), namuna rasmlar,
uslub bo'yicha narxlar (oshxona — 1 pogon metr; shkaf, garderob, komod — 1 m²), arizalar va bosqichlar.
Mijozdan o'lcham so'ralmaydi: usta uyiga borib o'lchaydi va shu yerda shartnoma tuziladi.

Tayyor mebel buyurtmalaridan alohida jadvallarda saqlanadi va o'z bosqichlariga ega.
Bu fayl web-freymvorkka bog'liq emas — Shop bilan bitta SQLite bazadan foydalanadi.
"""
import html
import json
import math
import os
import re
import time

from shop import ShopError, normalize_phone, fmt_price

# ------------------------------------------------------------------ dizayn uslublari
# tag — kirish kartasidagi qisqa shior; f — uslub ichidagi xususiyatlar ro'yxati
STYLE_INFO = {
    "modern": {"tag": ("Zamonaviy va minimal", "Современно и минималистично"),
               "f": [("🪞", "Yaltiroq yoki mat fasadlar (MDF, akril)", "Глянцевые или матовые фасады (МДФ, акрил)"),
                     ("✋", "Tutqichsiz eshiklar yoki yashirin tutqichlar", "Фасады без ручек или скрытые ручки"),
                     ("💡", "Metall, shisha va LED yoritish", "Металл, стекло и LED-подсветка"),
                     ("🎨", "Ranglar: oq, kulrang, grafit, qora", "Цвета: белый, серый, графит, чёрный"),
                     ("🏙", "Zamonaviy kvartira va minimalizm uchun", "Для современных квартир и минимализма")]},
    "newclassic": {"tag": ("Nafis va yorug'", "Изящно и светло"),
                   "f": [("🖼", "Ramkali fasadlar, yengil karnizlar", "Рамочные фасады, лёгкие карнизы"),
                         ("✨", "Oltin yoki bronza tutqichlar, nozik patina", "Золотые или бронзовые ручки, лёгкая патина"),
                         ("🎨", "Ranglar: oq, krem, bej, och kulrang", "Цвета: белый, крем, беж, светло-серый"),
                         ("🌿", "Klassika chiroyi + zamonaviy qulaylik", "Красота классики + современный комфорт"),
                         ("🏠", "Yorug' va keng xonadonlar uchun", "Для светлых и просторных квартир")]},
    "classic": {"tag": ("Hashamatli va an'anaviy", "Роскошно и традиционно"),
                "f": [("🌳", "Tabiiy yog'och yoki shpon", "Натуральное дерево или шпон"),
                      ("🏛", "O'yma naqshlar, karniz, balyasinalar", "Резьба, карнизы, балясины"),
                      ("✨", "Patina, oltin bezaklar", "Патина, золотой декор"),
                      ("🎨", "Ranglar: yong'oq, olcha, fil suyagi", "Цвета: орех, вишня, слоновая кость"),
                      ("🏡", "Katta xonadon va hovli uylar uchun", "Для больших квартир и частных домов")]},
}
STYLES = {
    # id "modern" eski arizalar va namunalar uchun saqlanadi — mijozga "Hi-Tech" deb ko'rinadi
    "modern": {"uz": "Hi-Tech", "ru": "Хай-тек",
               "d_uz": "Tekis chiziqlar, yaltiroq yuzalar, metall va shisha detallar. Ortiqcha bezaksiz — zamonaviy "
                       "va keng ko'rinadi.",
               "d_ru": "Чёткие линии, глянцевые поверхности, металл и стекло. Без лишнего декора — современно и "
                       "просторно."},
    "newclassic": {"uz": "Neoklassika", "ru": "Неоклассика",
                   "d_uz": "Klassikaning nafisligi va zamonaviy qulaylik: yengil naqshlar, och ranglar, oltin yoki "
                           "bronza detallar.",
                   "d_ru": "Изящество классики и современный комфорт: лёгкий декор, светлые тона, золотые или "
                           "бронзовые детали."},
    "classic": {"uz": "Klassika", "ru": "Классика",
                "d_uz": "Boy naqshlar, o'yma bezaklar, tabiiy yog'och va hashamatli matolar — an'anaviy chiroy.",
                "d_ru": "Богатый декор, резьба, натуральное дерево и роскошные ткани — традиционная красота."},
}

# ------------------------------------------------------------------ mebel turlari
# price: qaysi narx bilan ko'rsatiladi — "kitchen" (1 pogon metr), "wardrobe" (1 m²), None — kelishiladi
# dims: eski arizalardagi o'lchamlar (yangi ariza formasida o'lcham so'ralmaydi — usta o'lchaydi).
# BASE_KINDS — standart turlar; admin «🪑 Turlar» bo'limida nomini, belgisini, narx turini, tartibini o'zgartiradi,
# yangi tur qo'shadi yoki yashiradi. Natija sozlamalarda saqlanadi va KINDS ga qo'llanadi (apply_kinds).
BASE_KINDS = {
    "kitchen": {"uz": "Oshxona mebeli", "ru": "Кухня", "icon": "🍳", "price": "kitchen",
                "dims": [("w", "1-devor uzunligi", "Длина 1-й стены"), ("w2", "2-devor (burchak bo'lsa)", "2-я стена (если угловая)")]},
    "wardrobe": {"uz": "Shkaf / garderob", "ru": "Шкаф / гардероб", "icon": "🚪", "price": "wardrobe",
                 "dims": [("w", "Eni", "Ширина"), ("h", "Balandligi", "Высота")]},
    "komod": {"uz": "Komod", "ru": "Комод", "icon": "🗄", "price": "wardrobe",
              "dims": [("w", "Eni", "Ширина"), ("h", "Balandligi", "Высота")]},
    "sofa": {"uz": "Divan", "ru": "Диван", "icon": "🛋", "price": None,
             "dims": [("w", "Uzunligi", "Длина")]},
    "corner": {"uz": "Burchak divan", "ru": "Угловой диван", "icon": "🛋", "price": None,
               "dims": [("w", "Katta tomoni", "Длинная сторона"), ("w2", "Kichik tomoni", "Короткая сторона")]},
    "other": {"uz": "Boshqa mebel", "ru": "Другая мебель", "icon": "🪑", "price": None, "dims": []},
    # eski arizalar uchun (tanlovda ko'rsatilmaydi)
    "armchair": {"uz": "Kreslo", "ru": "Кресло", "icon": "💺", "price": None, "hidden": True,
                 "dims": [("w", "Eni", "Ширина")]},
    "bed": {"uz": "Karavot", "ru": "Кровать", "icon": "🛏", "price": None, "hidden": True,
            "dims": [("w", "Matras eni", "Ширина матраса"), ("l", "Matras bo'yi", "Длина матраса")]},
}
KINDS = {k: dict(v) for k, v in BASE_KINDS.items()}
KIND_PRICES = ("kitchen", "wardrobe")  # admin tanlaydigan narx turlari; None — kelishiladi
DIMS_BY_PRICE = {"kitchen": BASE_KINDS["kitchen"]["dims"], "wardrobe": BASE_KINDS["wardrobe"]["dims"], None: []}
MAX_KINDS = 30


def apply_kinds(items: list):
    """Admin saqlagan turlar ro'yxatini KINDS ga qo'llaydi (tartib saqlanadi). Standart turlar hech qachon
    yo'qolmaydi — ro'yxatda bo'lmasa yashirin holda qo'shiladi (eski arizalar nomi buzilmasin)."""
    new = {}
    for it in items or []:
        kid = str(it.get("id") or "")
        if not kid or kid in new:
            continue
        base = BASE_KINDS.get(kid, {})
        price = it.get("price") if it.get("price") in KIND_PRICES else None
        new[kid] = {"uz": str(it.get("uz") or base.get("uz") or kid), "ru": str(it.get("ru") or it.get("uz") or base.get("ru") or kid),
                    "icon": str(it.get("icon") or base.get("icon") or "🪑"), "price": price, "hidden": bool(it.get("hidden")),
                    "dims": base.get("dims") if base and base.get("price") == price else DIMS_BY_PRICE[price]}
    for kid, v in BASE_KINDS.items():
        if kid not in new:
            new[kid] = {**v, "hidden": True}
    KINDS.clear()
    KINDS.update(new)
# Narx turlari (admin har uslub uchun kiritadi). hidden — mijozga va admin formaga chiqmaydi (eski ma'lumot).
PRICE_UNITS = {
    "kitchen": {"uz": "Oshxona mebeli — 1 pogon metr", "ru": "Кухня — 1 погонный метр", "short_uz": "1 pogon metr",
                "short_ru": "1 пог. метр", "hint_uz": "devor bo'ylab uzunligi (pastki va yuqori shkaflar bilan)",
                "hint_ru": "длина вдоль стены (с нижними и верхними шкафами)"},
    "wardrobe": {"uz": "Shkaf, garderob, komod — 1 m²", "ru": "Шкаф, гардероб, комод — 1 м²", "short_uz": "1 m²",
                 "short_ru": "1 м²", "hint_uz": "old tomoni: eni × balandligi (masalan 2 m × 2,5 m = 5 m²)",
                 "hint_ru": "фасад: ширина × высота (например 2 м × 2,5 м = 5 м²)"},
    "sofa": {"uz": "Divan — 1 metr", "ru": "Диван — 1 метр", "short_uz": "1 metr", "short_ru": "1 метр",
             "hint_uz": "divan uzunligi bo'yicha", "hint_ru": "по длине дивана", "hidden": True},
}
# O'lchov va konsultatsiya narxi (admin o'zgartiradi; shartnoma tuzilsa narxdan chegiriladi)
MEASURE_FEE_DEFAULT = 1_000_000
# «Qo'ng'iroq qilish» tugmasidagi admin raqami (admin paneldan o'zgartiriladi)
CALL_PHONE_DEFAULT = "+998 99 333 33 66"
# Saralash savollari: mijoz qanchalik tayyor (usta avval 🔥 issiq arizalarga boradi)
NEED_WHEN = {"month": ("Shu oy ichida", "В этом месяце"), "quarter": ("1–3 oy ichida", "В ближайшие 1–3 месяца"),
             "price": ("Hozircha narx bilmoqchiman", "Пока хочу узнать цену")}
REPAIR = {"done": ("Ta'mir tugagan", "Ремонт закончен"), "going": ("Ta'mir ketyapti", "Идёт ремонт"),
          "none": ("Hali boshlanmagan", "Ещё не начат")}
LEADS = {"hot": ("🔥 Issiq", "🔥 Горячая"), "warm": ("🌤 Iliq", "🌤 Тёплая"), "cold": ("❄️ Sovuq", "❄️ Холодная")}
# Usta o'lchovga qachon kelsin (mijoz tanlaydi)
VISIT_DAYS = {"today": ("Bugun", "Сегодня"), "tomorrow": ("Ertaga", "Завтра"),
              "week": ("Shu hafta ichida", "На этой неделе"), "call": ("Qo'ng'iroq qilib kelishamiz", "Договоримся по телефону")}
VISIT_TIMES = {"morning": ("ertalab (9–12)", "утром (9–12)"), "day": ("tushdan keyin (12–17)", "днём (12–17)"),
               "evening": ("kechqurun (17–20)", "вечером (17–20)")}
# Eski arizalardagi material darajasi (faqat ko'rsatish uchun)
TIERS = {"econom": {"uz": "Ekonom", "ru": "Эконом"}, "standard": {"uz": "Standart", "ru": "Стандарт"},
         "premium": {"uz": "Premium", "ru": "Премиум"}}
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
GALLERY_MAX = 300

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
CREATE TABLE IF NOT EXISTS custom_gallery (
    id INTEGER PRIMARY KEY AUTOINCREMENT, style TEXT NOT NULL, kind TEXT DEFAULT '', image TEXT NOT NULL,
    caption TEXT DEFAULT '', caption_ru TEXT DEFAULT '', sort INTEGER DEFAULT 0, created INTEGER
);
"""
REQUEST_COLUMNS = {"style": "TEXT DEFAULT ''", "sample_id": "INTEGER", "sample_image": "TEXT DEFAULT ''",
                   "visit_day": "TEXT DEFAULT ''", "visit_time": "TEXT DEFAULT ''",
                   "need_when": "TEXT DEFAULT ''", "repair": "TEXT DEFAULT ''", "fee_ok": "INTEGER DEFAULT 0",
                   "kinds": "TEXT DEFAULT '[]'"}  # bir arizada bir nechta mebel turi (kind — birinchisi)


def kinds_of(r: dict) -> list:
    """Arizadagi mebel turlari ro'yxati (eski arizalarda faqat bitta — kind)."""
    ks = r.get("kinds")
    if isinstance(ks, str):
        try:
            ks = json.loads(ks or "[]")
        except ValueError:
            ks = []
    return [k for k in (ks or []) if k in KINDS] or [r.get("kind") or "other"]


def kinds_name(r: dict, lang: str = "uz") -> str:
    return ", ".join(kind_name(k, lang) for k in kinds_of(r))


def kind_name(kind: str, lang: str = "uz") -> str:
    k = KINDS.get(kind) or KINDS["other"]
    return k["ru" if lang == "ru" else "uz"]


def style_name(style: str, lang: str = "uz") -> str:
    s = STYLES.get(style)
    return s["ru" if lang == "ru" else "uz"] if s else ""


def stage_name(st: str, lang: str = "uz") -> str:
    return STAGES.get(st, (st, st))[1 if lang == "ru" else 0]


def num(v) -> float:
    try:
        return float(str(v or "").replace(",", ".").strip() or 0)
    except ValueError:
        return 0.0


def quantity(kind: str, dims: dict) -> float:
    """Narx hisoblanadigan miqdor: divan — metr, shkaf — m², oshxona — pogon metr. O'lcham bo'lmasa 0."""
    k = KINDS.get(kind) or {}
    unit = k.get("price")
    if unit == "sofa" or unit == "kitchen":
        return (num(dims.get("w")) + num(dims.get("w2"))) / 100
    if unit == "wardrobe":
        return num(dims.get("w")) / 100 * num(dims.get("h")) / 100
    return 0.0


class CustomStore:
    def __init__(self, shop):
        self.shop = shop
        self.db = shop.db
        self.db.executescript(CUSTOM_SCHEMA)
        have = {r[1] for r in self.db.execute("PRAGMA table_info(custom_requests)").fetchall()}
        for col, typ in REQUEST_COLUMNS.items():
            if col not in have:
                self.db.execute(f"ALTER TABLE custom_requests ADD COLUMN {col} {typ}")
        self.db.commit()
        try:
            saved = json.loads(shop.settings().get("custom_kinds") or "null")
        except ValueError:
            saved = None
        if isinstance(saved, list) and saved:
            apply_kinds(saved)
        self.photo_dir = os.path.join(os.path.dirname(shop.upload_dir.rstrip("/")), "custom")
        os.makedirs(self.photo_dir, exist_ok=True)

    # ------------------------------------------------ narxlar: {uslub: {sofa, wardrobe, kitchen}}
    def rates(self) -> dict:
        try:
            saved = json.loads(self.shop.settings().get("custom_style_rates") or "{}")
        except ValueError:
            saved = {}
        out = {}
        for s in STYLES:
            out[s] = {}
            for u in PRICE_UNITS:
                try:
                    out[s][u] = max(0, int((saved.get(s) or {}).get(u) or 0))
                except (TypeError, ValueError, AttributeError):
                    out[s][u] = 0
        return out

    def save_rates(self, data: dict) -> dict:
        old = self.rates()
        out = {}
        for s in STYLES:
            out[s] = {}
            for u, uv in PRICE_UNITS.items():
                if uv.get("hidden"):
                    out[s][u] = old[s][u]
                    continue
                raw = re.sub(r"\D", "", str(((data or {}).get(s) or {}).get(u) or ""))
                out[s][u] = int(raw) if raw else 0
                if out[s][u] > 10 ** 10:
                    raise ShopError("Narx juda katta")
        self.shop.set_setting("custom_style_rates", json.dumps(out))
        return out

    def measure_fee(self) -> int:
        try:
            v = self.shop.settings().get("custom_measure_fee")
            return MEASURE_FEE_DEFAULT if v in (None, "") else max(0, int(v))
        except (TypeError, ValueError):
            return MEASURE_FEE_DEFAULT

    def save_measure_fee(self, raw) -> int:
        v = re.sub(r"\D", "", str(raw or ""))
        self.shop.set_setting("custom_measure_fee", str(int(v) if v else 0))
        return self.measure_fee()

    # ------------------------------------------------ mebel turlari (admin boshqaradi)
    def _kind_used(self, kid: str) -> bool:
        q = ("SELECT 1 FROM custom_requests WHERE kind=? OR kinds LIKE ? LIMIT 1")
        if self.db.execute(q, (kid, f'%"{kid}"%')).fetchone():
            return True
        return bool(self.db.execute("SELECT 1 FROM custom_gallery WHERE kind=? LIMIT 1", (kid,)).fetchone())

    def kinds_admin(self) -> list:
        return [{"id": k, "uz": v["uz"], "ru": v["ru"], "icon": v["icon"], "price": v.get("price") or "",
                 "hidden": bool(v.get("hidden")), "builtin": k in BASE_KINDS} for k, v in KINDS.items()]

    def save_kinds(self, data: list) -> list:
        if not isinstance(data, list):
            raise ShopError("Noto'g'ri ma'lumot")
        items, seen = [], set()
        for i, it in enumerate(data[:MAX_KINDS]):
            if not isinstance(it, dict):
                continue
            uz = re.sub(r"\s+", " ", str(it.get("uz") or "")).strip()[:40]
            ru = re.sub(r"\s+", " ", str(it.get("ru") or "")).strip()[:40]
            if not uz:
                raise ShopError(f"{i + 1}-turning nomini yozing")
            kid = str(it.get("id") or "")
            if kid not in KINDS or kid in seen:
                kid = "t" + str(int(time.time() * 1000))[-9:] + str(i)
            seen.add(kid)
            icon = str(it.get("icon") or "").strip()[:8] or "🪑"
            items.append({"id": kid, "uz": uz, "ru": ru or uz, "icon": icon,
                          "price": it.get("price") if it.get("price") in KIND_PRICES else "",
                          "hidden": bool(it.get("hidden"))})
        for kid, v in KINDS.items():  # ro'yxatdan olib tashlanganlar: ishlatilgan bo'lsa yashiramiz, aks holda o'chadi
            if kid not in seen and (kid in BASE_KINDS or self._kind_used(kid)):
                items.append({"id": kid, "uz": v["uz"], "ru": v["ru"], "icon": v["icon"], "price": v.get("price") or "",
                              "hidden": True})
        if not any(not it["hidden"] for it in items):
            raise ShopError("Kamida bitta tur mijozga ko'rinishi kerak")
        self.shop.set_setting("custom_kinds", json.dumps(items, ensure_ascii=False))
        apply_kinds(items)
        return self.kinds_admin()

    def call_phone(self) -> str:
        v = self.shop.settings().get("custom_call_phone")
        return CALL_PHONE_DEFAULT if v is None else str(v)

    def save_call_phone(self, raw) -> str:
        v = re.sub(r"[^\d+ ()-]", "", str(raw or "")).strip()[:25]
        if v and len(re.sub(r"\D", "", v)) < 9:
            raise ShopError("Telefon raqamni to'g'ri kiriting")
        self.shop.set_setting("custom_call_phone", v)
        return self.call_phone()

    def estimate(self, kind: str, dims: dict, style: str) -> tuple:
        """Taxminiy narx oralig'i (min, max): narx × miqdor ±10%. Narx yoki o'lcham bo'lmasa (0, 0)."""
        unit = (KINDS.get(kind) or {}).get("price")
        rate = self.rates().get(style, {}).get(unit, 0) if unit else 0
        q = quantity(kind, dims)
        if not rate or q <= 0:
            return 0, 0
        mid = rate * q
        return int(math.floor(mid * 0.9 / 10000) * 10000), int(math.ceil(mid * 1.1 / 10000) * 10000)

    # ------------------------------------------------ namuna rasmlar
    def gallery(self, style: str = "") -> list:
        q = "SELECT * FROM custom_gallery" + (" WHERE style=?" if style else "") + " ORDER BY sort, id"
        return [dict(r) for r in self.db.execute(q, (style,) if style else ()).fetchall()]

    def gallery_add(self, style: str, kind: str, caption: str, images: list) -> list:
        if style not in STYLES:
            raise ShopError("Uslubni tanlang")
        if kind and kind not in KINDS:
            kind = ""
        if not images:
            raise ShopError("Rasm tanlang")
        if self.db.execute("SELECT COUNT(*) FROM custom_gallery").fetchone()[0] + len(images) > GALLERY_MAX:
            raise ShopError(f"Namuna rasmlar soni {GALLERY_MAX} tadan oshmasin. Eskilarini o'chiring.")
        now = int(time.time())
        for data in images:
            path = self.shop.save_image(data)  # "uploads/..." — ommaviy (namunalar hamma uchun)
            self.db.execute("INSERT INTO custom_gallery(style, kind, image, caption, sort, created) VALUES (?,?,?,?,?,?)",
                            (style, kind, path, (caption or "").strip()[:120], now, now))
        self.db.commit()
        return self.gallery()

    def gallery_update(self, gid: int, data: dict) -> list:
        r = self.db.execute("SELECT * FROM custom_gallery WHERE id=?", (gid,)).fetchone()
        if not r:
            raise ShopError("Rasm topilmadi")
        style = data.get("style") if data.get("style") in STYLES else r["style"]
        kind = data.get("kind", r["kind"])
        kind = kind if kind in KINDS else ""
        caption = str(data.get("caption", r["caption"]) or "").strip()[:120]
        self.db.execute("UPDATE custom_gallery SET style=?, kind=?, caption=? WHERE id=?", (style, kind, caption, gid))
        self.db.commit()
        return self.gallery()

    def gallery_delete(self, gid: int) -> list:
        r = self.db.execute("SELECT image FROM custom_gallery WHERE id=?", (gid,)).fetchone()
        if r:
            self.db.execute("DELETE FROM custom_gallery WHERE id=?", (gid,))
            self.db.commit()
            used = self.db.execute("SELECT 1 FROM custom_requests WHERE sample_image=? LIMIT 1", (r["image"],)).fetchone()
            if not used:
                self.shop._remove_unused_files([r["image"]])
        return self.gallery()

    # ------------------------------------------------ ilova uchun sozlamalar
    def config(self, lang: str = "uz") -> dict:
        ru = lang == "ru"
        rates = self.rates()
        gal = self.gallery()
        styles = []
        for sid, s in STYLES.items():
            items = [{"id": g["id"], "kind": g["kind"], "image": "/" + g["image"], "caption": g["caption"]}
                     for g in gal if g["style"] == sid]
            info = STYLE_INFO.get(sid, {"tag": ("", ""), "f": []})
            styles.append({"id": sid, "name": s["ru" if ru else "uz"], "desc": s["d_ru" if ru else "d_uz"],
                           "tag": info["tag"][1 if ru else 0],
                           "features": [{"icon": i, "text": (r_ if ru else u)} for i, u, r_ in info["f"]],
                           "rates": rates[sid], "gallery": items, "cover": items[0]["image"] if items else ""})
        return {
            "styles": styles,
            "units": [{"id": u, "name": v["ru" if ru else "uz"], "short": v["short_ru" if ru else "short_uz"],
                       "hint": v["hint_ru" if ru else "hint_uz"]} for u, v in PRICE_UNITS.items() if not v.get("hidden")],
            "kinds": [{"id": k, "name": v["ru" if ru else "uz"], "icon": v["icon"], "price": v["price"],
                       "dims": [{"id": f, "label": (lr if ru else lu)} for f, lu, lr in v["dims"]]}
                      for k, v in KINDS.items() if not v.get("hidden")],
            "stages": [{"id": s, "name": stage_name(s, lang)} for s in STAGE_ORDER],
            "max_photos": MAX_PHOTOS,
            "measure_fee": self.measure_fee(),
            "call_phone": self.call_phone(),
            "need_when": [{"id": k, "name": v[1 if ru else 0]} for k, v in NEED_WHEN.items()],
            "repair": [{"id": k, "name": v[1 if ru else 0]} for k, v in REPAIR.items()],
            "visit_days": [{"id": k, "name": v[1 if ru else 0]} for k, v in VISIT_DAYS.items()],
            "visit_times": [{"id": k, "name": v[1 if ru else 0]} for k, v in VISIT_TIMES.items()],
        }

    # ------------------------------------------------ arizalar
    @staticmethod
    def _row(r) -> dict:
        d = dict(r)
        for f, dflt in (("dims", "{}"), ("photos", "[]"), ("events", "[]"), ("admin_msgs", "[]")):
            d[f] = json.loads(d.get(f) or dflt)
        d["kinds"] = kinds_of(d)
        d["kind_name"] = kinds_name(d, d.get("lang") or "uz")
        d["status_text"] = stage_name(d["status"])
        return d

    def get(self, rid: int) -> dict:
        r = self.db.execute("SELECT * FROM custom_requests WHERE id=?", (rid,)).fetchone()
        if not r:
            raise ShopError("Ariza topilmadi", "Заявка не найдена")
        return self._row(r)

    def list(self, status: str = "", limit: int = 200) -> list:
        if status == "active":
            q, a = (f"SELECT * FROM custom_requests WHERE status IN ({','.join('?' * len(ACTIVE))}) "
                    "ORDER BY id DESC LIMIT ?", (*ACTIVE, limit))
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
        style = payload.get("style") if payload.get("style") in STYLES else ""
        raw_kinds = payload.get("kinds")
        if not isinstance(raw_kinds, list):
            raw_kinds = [payload.get("kind")]
        kinds = []
        for k in raw_kinds:
            if k in KINDS and not KINDS[k].get("hidden") and k not in kinds:
                kinds.append(k)
        if not kinds:
            raise ShopError("Qanday mebel kerakligini tanlang", "Выберите, какая мебель нужна")
        kind = kinds[0]
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
        need_when = payload.get("need_when") if payload.get("need_when") in NEED_WHEN else ""
        repair = payload.get("repair") if payload.get("repair") in REPAIR else ""
        if not need_when:
            raise ShopError("Mebel qachon kerakligini tanlang", "Выберите, когда нужна мебель")
        price_only = need_when == "price"
        fee_ok = bool(payload.get("fee_ok"))
        if not price_only and self.measure_fee() and not fee_ok:
            raise ShopError("O'lchov shartlariga rozilikni belgilang", "Отметьте согласие с условиями замера")
        visit = not price_only and (bool(payload.get("measure_visit")) or not dims)
        visit_day = payload.get("visit_day") if payload.get("visit_day") in VISIT_DAYS and not price_only else ""
        visit_time = payload.get("visit_time") if payload.get("visit_time") in VISIT_TIMES and visit_day != "call" else ""
        color = (payload.get("color") or "").strip()[:80]
        note = (payload.get("note") or "").strip()[:1000]
        sample_id, sample_image = None, ""
        try:
            sid = int(payload.get("sample_id") or 0)
        except (TypeError, ValueError):
            sid = 0
        if sid:
            g = self.db.execute("SELECT * FROM custom_gallery WHERE id=?", (sid,)).fetchone()
            if g:
                sample_id, sample_image = sid, g["image"]
                style = style or g["style"]
        if kinds == ["other"] and len(note) < 5 and not sample_id:
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
        saved = [self.shop._save_jpeg(data, self.photo_dir, 1600, 82) for data in photos[:MAX_PHOTOS]]
        lo, hi = self.estimate(kind, dims, style)
        now = int(time.time())
        cur = self.db.execute(
            "INSERT INTO custom_requests(user_id,username,name,phone,city,address,kind,model_id,model_name,dims,"
            "measure_visit,tier,color,note,photos,estimate_min,estimate_max,status,events,lang,created,updated,"
            "style,sample_id,sample_image,visit_day,visit_time,need_when,repair,fee_ok,kinds) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (user["id"], user.get("username") or "", name, phone, city, address, kind, model_id, model_name,
             json.dumps(dims), 1 if visit else 0, "", color, note, json.dumps(saved), lo, hi, "new",
             json.dumps([["new", now, "mijoz"]]), "ru" if lang == "ru" else "uz", now, now,
             style, sample_id, sample_image, visit_day, visit_time, need_when, repair, 1 if fee_ok and not price_only else 0,
             json.dumps(kinds)))
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

        def money_field(k):
            raw = re.sub(r"\D", "", str(data.get(k, r[k]) or ""))
            return int(raw) if raw else 0
        price, prepay = money_field("price"), money_field("prepay")
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
    q = quantity(r["kind"], r["dims"])
    unit = k.get("price")
    if q and unit:
        u = PRICE_UNITS[unit]["short_ru" if lang == "ru" else "short_uz"].replace("1 ", "")
        parts.append(f"= {round(q, 2)} {u}")
    return "\n".join(parts)


def visit_text(r: dict, lang: str = "uz") -> str:
    """Usta kelish vaqti: «Ertaga, ertalab (9–12)»."""
    i = 1 if lang == "ru" else 0
    parts = [VISIT_DAYS[r["visit_day"]][i]] if r.get("visit_day") in VISIT_DAYS else []
    if r.get("visit_time") in VISIT_TIMES:
        parts.append(VISIT_TIMES[r["visit_time"]][i])
    return ", ".join(parts)


def lead(r: dict) -> str:
    """🔥 issiq: shu oy kerak va ta'mir tugagan/ketyapti, o'lchovga rozi. ❄️ sovuq: faqat narx so'raydi."""
    if r.get("need_when") == "price":
        return "cold"
    if r.get("need_when") == "month" and r.get("repair") in ("done", "going") and r.get("fee_ok"):
        return "hot"
    return "warm" if r.get("need_when") else ""


def lead_name(r: dict, lang: str = "uz") -> str:
    k = lead(r)
    return LEADS[k][1 if lang == "ru" else 0] if k else ""


def public(r: dict, lang: str = "uz") -> dict:
    """Mijozga: ichki izoh, guruh xabarlari va rasmlar yo'li yuborilmaydi."""
    out = {k: v for k, v in r.items() if k not in ("admin_msgs", "admin_note", "photos", "user_id", "username")}
    out["photos"] = len(r.get("photos") or [])
    out["kind_name"] = kinds_name(r, lang)
    out["status_text"] = stage_name(r["status"], lang)
    out["style_name"] = style_name(r.get("style") or "", lang)
    out["sample_image"] = "/" + r["sample_image"] if r.get("sample_image") else ""
    out["visit_text"] = visit_text(r, lang)
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
    ln = lead_name(r)
    lines = [f"📐 <b>Individual ariza #{r['id']}</b> — {stage_name(r['status'])}" + (f"\n<b>{ln}</b>" if ln else ""),
             f"🕒 {when}", "",
             f"👤 {e(r['name'])} ({who})", f"📞 {e(r['phone'])}"]
    place = ", ".join(e(x) for x in (r.get("city"), r.get("address")) if x)
    if place:
        lines.append(f"🏠 {place}")
    lines += ["", " ".join(KINDS[k]["icon"] for k in kinds_of(r)) + f" <b>{e(kinds_name(r))}</b>"
              + (f" — uslub: <b>{e(style_name(r.get('style') or ''))}</b>" if r.get("style") else "")
              + (f"\n🛋 Asos: {e(r['model_name'])}" if r.get("model_name") else "")]
    if r.get("sample_image"):
        lines.append("🖼 Namuna rasmlardan birini tanladi (yuqorida)")
    d = dims_text(r)
    if d:
        lines.append("📏 " + e(d).replace("\n", "\n📏 "))
    if r.get("need_when") in NEED_WHEN:
        lines.append(f"⏳ Kerak: {NEED_WHEN[r['need_when']][0]}" + (f" · 🧱 {REPAIR[r['repair']][0]}" if r.get("repair") in REPAIR else ""))
    if r.get("need_when") == "price":
        lines.append("☎️ <b>Faqat narx so'ramoqda — usta emas, menejer qo'ng'iroq qilsin</b>")
    if r.get("fee_ok"):
        lines.append("💳 O'lchov pulli ekaniga rozi (shartnomada chegiriladi)")
    if r.get("measure_visit"):
        vt = visit_text(r)
        lines.append("📏 <b>Usta borib o'lchashi kerak</b>" + (f"\n🗓 Qulay vaqt: <b>{e(vt)}</b>" if vt else ""))
    tier = TIERS.get(r.get("tier"), {}).get("uz")
    if tier:
        lines.append(f"🧵 Material: {e(tier)}")
    if r.get("color"):
        lines.append(f"🎨 Rang: {e(r['color'])}")
    if r.get("note"):
        lines.append(f"📝 {e(r['note'])}")
    if r.get("photos"):
        lines.append(f"📷 Mijoz rasmlari: {len(r['photos'])} ta")
    if r.get("estimate_min"):
        lines.append(f"\n💡 Ko'rsatilgan taxminiy narx: {fmt_price(r['estimate_min'])} – {fmt_price(r['estimate_max'])}")
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
    if status == "done":
        return []
    if status == "cancelled":
        return ["new"]
    i = STAGE_ORDER.index(status)
    return [STAGE_ORDER[i + 1], "cancelled"]
