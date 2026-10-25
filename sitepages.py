"""iSofa veb-sayti: server tomonda tayyorlanadigan sahifalar (Google/Yandex uchun ham ko'rinadi).

Bu modul faqat matn (HTML/XML) yasaydi — aiohttp va botga bog'liq emas, shuning uchun alohida sinab ko'rsa bo'ladi.
Ma'lumotlar Shop.catalog() dan keladi: u yerda ta'minotchi, kirim narxi kabi ichki maydonlar allaqachon olib tashlangan.
"""
import html
import json
import re

e = html.escape

T = {
    "uz": {
        "tagline": "Onlayn mebel do'koni",
        "nav_catalog": "Katalog", "nav_how": "Qanday buyurtma beriladi", "nav_info": "Yetkazish va to'lov",
        "nav_contact": "Aloqa", "nav_orders": "Buyurtmalarim", "cart": "Savatcha",
        "hero_eyebrow": "Tayyor mebel · yetkazib berish · yig'ib berish",
        "hero_title": "Uyingizga mos mebel&nbsp;—<br><em>bir necha bosishda</em>",
        "hero_text": "Divanlar, yotoqxona, oshxona va bolalar mebellari. Tanlang, buyurtma bering — "
                     "uyingizgacha yetkazib, kerak bo'lsa yig'ib beramiz.",
        "hero_cta": "Katalogni ko'rish", "hero_tg": "Telegram orqali",
        "f_delivery": "Uyingizgacha yetkazish", "f_delivery_t": "Manzilni xaritada belgilaysiz",
        "f_asm": "Yig'ib berish", "f_asm_t": "Usta uyingizda yig'ib beradi",
        "f_prepay": "Oldindan atigi {pct}%", "f_prepay_t": "Qolgani — mebelni olganingizda",
        "f_check": "Tekshirib qabul qilasiz", "f_check_t": "Hammasi joyida bo'lsagina tasdiqlaysiz",
        "cats_title": "Bo'limlar", "all": "Hammasi", "items_n": "{n} ta mahsulot",
        "cat_title": "Katalog", "search_ph": "Qidirish: divan, shkaf, stol…",
        "sort_new": "Avval yangilari", "sort_cheap": "Avval arzonlari", "sort_exp": "Avval qimmatlari",
        "nothing": "Hech narsa topilmadi. Boshqa so'z bilan qidirib ko'ring.",
        "empty_catalog": "Katalog tez orada to'ldiriladi. Yangi mahsulotlarni Telegram botimizda birinchi bo'lib ko'ring.",
        "som": "so'm", "add": "Savatchaga", "added": "Savatchada ✓", "out": "Omborda yo'q", "in_stock": "Omborda bor",
        "buy_now": "Hozir buyurtma berish", "tg_order": "Telegram orqali buyurtma",
        "delivery_days": "Yetkazish muddati", "asm_ok": "Yig'ib berish xizmati mavjud",
        "specs": "Xususiyatlari", "about": "Tavsif", "related": "Shu bo'limdan yana",
        "how_title": "Buyurtma berish oson",
        "how_1": "Tanlang", "how_1t": "Katalogdan mebelni tanlab, savatchaga qo'shing.",
        "how_2": "Rasmiylashtiring", "how_2t": "Ism, telefon va manzilni yozing — xaritada belgilang.",
        "how_3": "Oldindan to'lang", "how_3t": "Summaning {pct}% ini kartaga o'tkazib, chek rasmini yuklang.",
        "how_4": "Qabul qiling", "how_4t": "Yetkazamiz, xohlasangiz yig'amiz. Tekshirib, qolganini to'laysiz.",
        "tg_title": "Telegram'da qulayroqmi?",
        "tg_text": "Xuddi shu katalog Telegram botimizda ham bor: buyurtma holati haqidagi xabarlar to'g'ridan-to'g'ri "
                   "Telegram'ga keladi.",
        "tg_btn": "Botni ochish",
        "info_title": "Yetkazish va to'lov",
        "q_pay": "Qanday to'layman?",
        "a_pay": "Buyurtma berishda summaning {pct}% ini do'kon kartasiga oldindan o'tkazasiz va chek rasmini yuklaysiz. "
                 "Qolgan summani mebelni qabul qilganingizda karta yoki Click / Payme orqali to'laysiz.",
        "q_when": "Qachon yetkazasiz?",
        "a_when": "Har bir mahsulot sahifasida yetkazish muddati ko'rsatilgan. Aniq kun va vaqtni siz bilan telefonda "
                  "kelishamiz. Do'kondan o'zingiz olib ketishingiz ham mumkin.",
        "q_asm": "Yig'ib berasizmi?",
        "a_asm": "Ha. Yig'iladigan mebellar uchun buyurtmada «Yig'ib beraylikmi?» degan savol chiqadi. Xizmat narxi — "
                 "shu mahsulotlar narxining {asm}%.",
        "q_check": "Mebel shikastlangan bo'lsa-chi?",
        "a_check": "Mebelni kuryer yoki usta huzurida ko'zdan kechirasiz. Hammasi joyida bo'lsa «Qabul qildim» deysiz, "
                   "muammo bo'lsa — darhol bizga xabar qilasiz.",
        "q_ask": "Savolim bor",
        "a_ask": "Telegram'da adminga yozing: {contact}",
        "a_ask_phone": " yoki qo'ng'iroq qiling: {phone}",
        "contact_title": "Aloqa", "write_admin": "Adminga yozish", "call": "Qo'ng'iroq qilish",
        "offer": "Ommaviy oferta", "rights": "Barcha huquqlar himoyalangan.",
        "cart_empty": "Savatcha hozircha bo'sh", "total": "Jami", "checkout": "Rasmiylashtirish",
        "checkout_hint": "Keyingi bosqichda manzil va oldindan to'lov chekini kiritasiz.",
        "remove": "O'chirish", "close": "Yopish", "back_catalog": "← Katalogga qaytish",
        "not_found": "Sahifa topilmadi", "not_found_t": "Bu mahsulot sotuvdan olingan yoki havola noto'g'ri.",
        "install": "Telefonga o'rnatish", "discount": "Chegirma",
        "home_title": "{shop} — mebel do'koni: divan, yotoqxona, oshxona mebellari",
        "home_desc": "{shop} — onlayn mebel do'koni. Divanlar, yotoqxona to'plamlari, oshxona garniturlari, shkaflar. "
                     "Uyingizgacha yetkazish va yig'ib berish. Oldindan atigi {pct}% to'lov.",
        "prod_title": "{name} — narxi {price} | {shop}",
        "nav_custom": "O'lchamga buyurtma",
        "door_ready": "Tayyor mebellar", "door_ready_t": "Katalogdan tanlang — narxi aniq, tez yetkazamiz.",
        "door_custom": "O'lchamga buyurtma", "door_custom_t": "Xonangizga moslab, o'zingiz xohlagan o'lcham, mato va rangda yasab beramiz.",
        "door_custom_btn": "Ariza qoldirish", "door_ready_btn": "Katalogni ko'rish",
        "my_size": "Shu modelni o'z o'lchamimda buyurtma qilish",
        "ch_t": "O'lchami, rangi yoki matosi to'g'ri kelmadimi?",
        "ch_p": "Shu mebelni xohishingizga moslab o'zgartirib yasab beramiz. Admin bilan bog'laning va modelni ayting:",
        "ch_call": "Qo'ng'iroq qilish", "ch_write": "Telegramda yozish",
    },
    "ru": {
        "tagline": "Онлайн-магазин мебели",
        "nav_catalog": "Каталог", "nav_how": "Как заказать", "nav_info": "Доставка и оплата",
        "nav_contact": "Контакты", "nav_orders": "Мои заказы", "cart": "Корзина",
        "hero_eyebrow": "Готовая мебель · доставка · сборка",
        "hero_title": "Мебель для вашего дома&nbsp;—<br><em>в пару нажатий</em>",
        "hero_text": "Диваны, спальни, кухни и детская мебель. Выберите, оформите заказ — доставим до двери "
                     "и при желании соберём.",
        "hero_cta": "Смотреть каталог", "hero_tg": "Через Telegram",
        "f_delivery": "Доставка до двери", "f_delivery_t": "Адрес отмечаете на карте",
        "f_asm": "Сборка", "f_asm_t": "Мастер соберёт у вас дома",
        "f_prepay": "Предоплата всего {pct}%", "f_prepay_t": "Остальное — при получении",
        "f_check": "Проверяете при приёмке", "f_check_t": "Подтверждаете, только если всё в порядке",
        "cats_title": "Разделы", "all": "Все", "items_n": "товаров: {n}",
        "cat_title": "Каталог", "search_ph": "Поиск: диван, шкаф, стол…",
        "sort_new": "Сначала новые", "sort_cheap": "Сначала дешёвые", "sort_exp": "Сначала дорогие",
        "nothing": "Ничего не найдено. Попробуйте другое слово.",
        "empty_catalog": "Каталог скоро пополнится. Новинки первыми появляются в нашем Telegram-боте.",
        "som": "сум", "add": "В корзину", "added": "В корзине ✓", "out": "Нет в наличии", "in_stock": "В наличии",
        "buy_now": "Заказать сейчас", "tg_order": "Заказать через Telegram",
        "delivery_days": "Срок доставки", "asm_ok": "Доступна услуга сборки",
        "specs": "Характеристики", "about": "Описание", "related": "Ещё из этого раздела",
        "how_title": "Заказать просто",
        "how_1": "Выберите", "how_1t": "Найдите мебель в каталоге и добавьте в корзину.",
        "how_2": "Оформите", "how_2t": "Укажите имя, телефон и адрес — отметьте его на карте.",
        "how_3": "Внесите предоплату", "how_3t": "Переведите {pct}% суммы на карту и загрузите фото чека.",
        "how_4": "Получите", "how_4t": "Доставим и при желании соберём. Проверите и оплатите остаток.",
        "tg_title": "Удобнее в Telegram?",
        "tg_text": "Тот же каталог есть в нашем Telegram-боте: уведомления о статусе заказа приходят прямо в Telegram.",
        "tg_btn": "Открыть бота",
        "info_title": "Доставка и оплата",
        "q_pay": "Как оплатить?",
        "a_pay": "При оформлении вы переводите {pct}% суммы на карту магазина и загружаете фото чека. "
                 "Остаток оплачиваете при получении — картой или через Click / Payme.",
        "q_when": "Когда доставите?",
        "a_when": "Срок доставки указан на странице каждого товара. Точные день и время согласуем по телефону. "
                  "Можно забрать и самовывозом из магазина.",
        "q_asm": "Собираете мебель?",
        "a_asm": "Да. Для мебели, которая требует сборки, при заказе появится вопрос «Собрать?». "
                 "Стоимость услуги — {asm}% от цены этих товаров.",
        "q_check": "А если мебель повреждена?",
        "a_check": "Вы осматриваете мебель при курьере или мастере. Если всё в порядке — подтверждаете приёмку, "
                   "если есть проблема — сразу сообщаете нам.",
        "q_ask": "У меня вопрос",
        "a_ask": "Напишите администратору в Telegram: {contact}",
        "a_ask_phone": " или позвоните: {phone}",
        "contact_title": "Контакты", "write_admin": "Написать админу", "call": "Позвонить",
        "offer": "Публичная оферта", "rights": "Все права защищены.",
        "cart_empty": "Корзина пока пуста", "total": "Итого", "checkout": "Оформить заказ",
        "checkout_hint": "На следующем шаге укажете адрес и загрузите чек предоплаты.",
        "remove": "Удалить", "close": "Закрыть", "back_catalog": "← Вернуться в каталог",
        "not_found": "Страница не найдена", "not_found_t": "Товар снят с продажи или ссылка неверна.",
        "install": "Установить на телефон", "discount": "Скидка",
        "home_title": "{shop} — магазин мебели: диваны, спальни, кухни",
        "home_desc": "{shop} — онлайн-магазин мебели. Диваны, спальные гарнитуры, кухни, шкафы. "
                     "Доставка до двери и сборка. Предоплата всего {pct}%.",
        "prod_title": "{name} — цена {price} | {shop}",
        "nav_custom": "Мебель на заказ",
        "door_ready": "Готовая мебель", "door_ready_t": "Выберите в каталоге — цена известна, доставим быстро.",
        "door_custom": "Мебель на заказ", "door_custom_t": "Сделаем под вашу комнату — в нужном размере, ткани и цвете.",
        "door_custom_btn": "Оставить заявку", "door_ready_btn": "Смотреть каталог",
        "my_size": "Заказать эту модель в моём размере",
        "ch_t": "Не подошёл размер, цвет или ткань?",
        "ch_p": "Изменим эту модель под ваши пожелания. Свяжитесь с администратором и назовите модель:",
        "ch_call": "Позвонить", "ch_write": "Написать в Telegram",
    },
}


def tr(lang: str, key: str, **kw) -> str:
    s = T.get(lang, T["uz"]).get(key) or T["uz"][key]
    return s.format(**kw) if kw else s


def money(n, lang: str = "uz") -> str:
    return f"{int(n or 0):,}".replace(",", " ") + " " + tr(lang, "som")


def slug(s: str) -> str:
    table = str.maketrans({"ʻ": "", "'": "", "’": "", "ʼ": "", "`": ""})
    s = (s or "").translate(table).lower()
    cyr = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюяўқғҳ",
                   ["a", "b", "v", "g", "d", "e", "yo", "j", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                    "u", "f", "x", "ts", "ch", "sh", "sh", "", "i", "", "e", "yu", "ya", "o", "q", "g", "h"]))
    s = "".join(cyr.get(c, c) for c in s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60] or "mebel"


def product_url(p: dict) -> str:
    return f"/p/{p['id']}-{slug(p.get('name_uz') or p['name'])}"


def img_url(path: str) -> str:
    if not path:
        return ""
    return path if path.startswith(("http://", "https://", "/")) else "/" + path


def first_image(p: dict) -> str:
    return img_url((p.get("images") or [None])[0] or (p.get("video") or {}).get("poster") or "")


def discount_pct(p: dict) -> int:
    old, price = int(p.get("old_price") or 0), int(p.get("price") or 0)
    return round((old - price) * 100 / old) if old > price > 0 else 0


# ------------------------------------------------------------------ qismlar
LOGO = ('<svg class="logo-mark" viewBox="0 0 40 40" aria-hidden="true"><rect width="40" height="40" rx="11" fill="currentColor"/>'
        '<path d="M10 27v-7.5a3.5 3.5 0 0 1 7 0V22h6v-2.5a3.5 3.5 0 0 1 7 0V27M10 27h20M12.5 27v3M27.5 27v3" '
        'fill="none" stroke="#f6efe6" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>')

ICONS = {
    "cart": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 4h2l2.2 10.2a2 2 0 0 0 2 1.6h7.6a2 2 0 0 0 2-1.5L20.5 8H6.2" '
            'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
            '<circle cx="10" cy="20" r="1.4" fill="currentColor"/><circle cx="17" cy="20" r="1.4" fill="currentColor"/></svg>',
    "tg": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21.5 4.3 2.9 11.5c-1 .4-1 1.8.1 2.1l4.6 1.4 1.8 5.6c.3.9 1.4 '
          '1.1 2 .4l2.6-2.6 4.7 3.4c.8.6 1.9.1 2.1-.8l3.1-14.7c.2-1.1-.9-2-1.9-1.6ZM9.6 14.6l8.3-7.4-6.4 8.6-.3 3-1.6-4.2Z" '
          'fill="currentColor"/></svg>',
    "truck": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h11v10H3zM14 9h4l3 3.5V16h-7M7 19a2 2 0 1 0 0-.01M17 19a2 2 0 1 0 0-.01" '
             'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
    "tool": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14.5 5.5a4 4 0 0 0 5 5L12 18l-3 3-3-3 3-3 7.5-7.5Zm0 0L17 3l4 4-2.5 2.5" '
            'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "card": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5.5" width="18" height="13" rx="2.5" fill="none" '
            'stroke="currentColor" stroke-width="1.6"/><path d="M3 10h18M7 15h4" stroke="currentColor" stroke-width="1.6" '
            'stroke-linecap="round"/></svg>',
    "check": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 4.5 6v5.5c0 4.5 3.2 8 7.5 9.5 4.3-1.5 7.5-5 7.5-9.5V6L12 3Z" '
             'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="m8.5 12 2.5 2.5 4.5-5" '
             'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "phone": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h3.5l1.5 4.5-2 1.5a12 12 0 0 0 6 6l1.5-2L20 15.5V19a1 1 0 0 1-1 '
             '1A16 16 0 0 1 4 5a1 1 0 0 1 1-1Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
    "pin": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s7-6.1 7-11.5a7 7 0 0 0-14 0C5 14.9 12 21 12 21Z" fill="none" '
           'stroke="currentColor" stroke-width="1.6"/><circle cx="12" cy="9.5" r="2.5" fill="none" stroke="currentColor" '
           'stroke-width="1.6"/></svg>',
    "search": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" '
              'stroke-width="1.8"/><path d="m16 16 4.5 4.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    "menu": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-width="1.8" '
            'stroke-linecap="round"/></svg>',
    "x": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" stroke="currentColor" stroke-width="1.8" '
         'stroke-linecap="round"/></svg>',
    "box": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 4 7v10l8 4 8-4V7l-8-4Zm0 0v0M4 7l8 4 8-4M12 11v10" fill="none" '
           'stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
}

# Rasm yo'q mahsulotlar uchun chiroyli o'rinbosar (emoji o'rniga chiziqli rasm)
SOFA_ART = ('<svg class="ph-art" viewBox="0 0 200 120" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-width="2.4" '
            'stroke-linecap="round" stroke-linejoin="round"><path d="M38 58V44c0-8 6-14 14-14h96c8 0 14 6 14 14v14"/>'
            '<path d="M30 60c-6 0-10 4-10 10v18h160V70c0-6-4-10-10-10s-10 4-10 10v6H50v-6c0-6-4-10-10-10Z"/>'
            '<path d="M50 76V64c0-3 2-5 5-5h40v17M105 76V59h40c3 0 5 2 5 5v12M32 88v8M168 88v8"/></g></svg>')


def placeholder(p: dict) -> str:
    return f'<div class="ph">{SOFA_ART}<span class="ph-emoji">{e(p.get("emoji") or "")}</span></div>'


def picture(p: dict, cls: str = "", eager: bool = False) -> str:
    src = first_image(p)
    if not src:
        return placeholder(p)
    load = 'fetchpriority="high"' if eager else 'loading="lazy"'
    return f'<img class="{cls}" src="{e(src)}" alt="{e(p["name"])}" {load} decoding="async">'


def product_card(p: dict, lang: str, cats: dict) -> str:
    d = discount_pct(p)
    badge = f'<span class="badge sale">−{d}%</span>' if d else ""
    if not p.get("in_stock"):
        badge = f'<span class="badge out">{e(tr(lang, "out"))}</span>'
    old = f'<s>{money(p["old_price"], lang)}</s>' if d else ""
    cat = cats.get(p.get("cat_id"), {})
    btn = (f'<button class="add" data-add="{p["id"]}" aria-label="{e(tr(lang, "add"))}">{ICONS["cart"]}'
           f'<span>{e(tr(lang, "add"))}</span></button>' if p.get("in_stock") else "")
    return (f'<article class="card" data-cat="{p.get("cat_id") or 0}" data-price="{int(p["price"])}" '
            f'data-new="{int(p.get("created") or 0)}" data-name="{e((p["name"] + " " + cat.get("name", "")).lower())}">'
            f'<a class="card-img" href="{product_url(p)}?lang={lang}">{picture(p)}{badge}</a>'
            f'<div class="card-body"><div class="card-cat">{e(cat.get("name", ""))}</div>'
            f'<h3><a href="{product_url(p)}?lang={lang}">{e(p["name"])}</a></h3>'
            f'<div class="card-foot"><div class="price">{money(p["price"], lang)}{old}</div>{btn}</div></div></article>')


def header(ctx: dict, active: str = "") -> str:
    lang, shop = ctx["lang"], ctx["shop"]
    home = "/" if lang == "uz" else "/?lang=ru"
    path = ctx.get("path", "/")
    sw = "".join(f'<a href="{e(path)}?lang={l}" class="{"on" if l == lang else ""}" data-lang="{l}" hreflang="{l}">'
                 f'{l.upper()}</a>' for l in ("uz", "ru"))
    links = (f'<a href="{home}#katalog">{e(tr(lang, "nav_catalog"))}</a>'
             f'<a href="/custom?lang={lang}">{e(tr(lang, "nav_custom"))}</a>'
             f'<a href="{home}#qanday">{e(tr(lang, "nav_how"))}</a>'
             f'<a href="{home}#tolov">{e(tr(lang, "nav_info"))}</a>'
             f'<a href="{home}#aloqa">{e(tr(lang, "nav_contact"))}</a>')
    return f"""<header class="top" id="top">
  <div class="wrap top-in">
    <a class="logo" href="{home}" aria-label="{e(shop['name'])}">{LOGO}<span><b>{e(shop['name'])}</b><small>{e(tr(lang, 'tagline'))}</small></span></a>
    <nav class="menu" id="menu">{links}<a href="/app?go=orders&lang={lang}" class="menu-orders">{e(tr(lang, 'nav_orders'))}</a></nav>
    <div class="top-r">
      <div class="langsw">{sw}</div>
      <button class="icon-btn cart-btn" id="cartBtn" aria-label="{e(tr(lang, 'cart'))}">{ICONS['cart']}<span class="cnt" id="cartCnt" hidden>0</span></button>
      <button class="icon-btn burger" id="burger" aria-label="Menu">{ICONS['menu']}</button>
    </div>
  </div>
</header>"""


def footer(ctx: dict) -> str:
    lang, shop, st = ctx["lang"], ctx["shop"], ctx["settings"]
    nick = st.get("admin_contact") or ""
    rows = []
    if nick:
        rows.append(f'<a href="https://t.me/{e(nick)}" target="_blank" rel="noopener">{ICONS["tg"]}@{e(nick)}</a>')
    if shop.get("phone"):
        rows.append(f'<a href="tel:{e(re.sub(r"[^0-9+]", "", shop["phone"]))}">{ICONS["phone"]}{e(shop["phone"])}</a>')
    if shop.get("address"):
        rows.append(f'<span>{ICONS["pin"]}{e(shop["address"])}</span>')
    bot = ctx.get("bot") or ""
    if bot:
        rows.append(f'<a href="https://t.me/{e(bot)}" target="_blank" rel="noopener">{ICONS["tg"]}@{e(bot)}</a>')
    home = "/" if lang == "uz" else "/?lang=ru"
    return f"""<footer class="foot" id="aloqa">
  <div class="wrap foot-in">
    <div class="foot-brand"><a class="logo light" href="{home}">{LOGO}<span><b>{e(shop['name'])}</b><small>{e(tr(lang, 'tagline'))}</small></span></a>
      <p>{e(tr(lang, 'hero_text'))}</p></div>
    <div><h4>{e(tr(lang, 'contact_title'))}</h4><div class="foot-links">{''.join(rows)}</div></div>
    <div><h4>{e(shop['name'])}</h4><div class="foot-links">
      <a href="{home}#katalog">{e(tr(lang, 'nav_catalog'))}</a><a href="{home}#tolov">{e(tr(lang, 'nav_info'))}</a>
      <a href="/app?go=orders&lang={lang}">{e(tr(lang, 'nav_orders'))}</a><a href="/oferta?lang={lang}">{e(tr(lang, 'offer'))}</a>
      <button class="linkish" id="installBtn" hidden>{e(tr(lang, 'install'))}</button></div></div>
  </div>
  <div class="wrap foot-copy">© {ctx.get('year', '')} {e(shop['name'])}. {e(tr(lang, 'rights'))}</div>
</footer>"""


def cart_drawer(lang: str) -> str:
    return f"""<div class="shade" id="shade" hidden></div>
<aside class="drawer" id="drawer" aria-hidden="true" aria-label="{e(tr(lang, 'cart'))}">
  <div class="drawer-h"><h3>{e(tr(lang, 'cart'))}</h3><button class="icon-btn" id="drawerClose" aria-label="{e(tr(lang, 'close'))}">{ICONS['x']}</button></div>
  <div class="drawer-b" id="cartList"></div>
  <div class="drawer-f" id="cartFoot"></div>
</aside>
<div class="toast" id="toast" role="status"></div>"""


def boot_json(ctx: dict) -> str:
    lang = ctx["lang"]
    data = {
        "lang": lang, "bot": ctx.get("bot") or "",
        "products": {str(p["id"]): {"name": p["name"], "price": int(p["price"]), "img": first_image(p),
                                    "url": product_url(p) + f"?lang={lang}", "stock": bool(p.get("in_stock"))}
                     for p in ctx["products"]},
        "t": {k: tr(lang, k) for k in ("som", "add", "added", "cart_empty", "total", "checkout", "checkout_hint",
                                        "remove", "nothing")},
    }
    # </script> ichida xavfsiz bo'lishi uchun
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def layout(ctx: dict, title: str, desc: str, body: str, canonical: str, og_image: str = "", jsonld=None,
           og_type: str = "website", noindex: bool = False) -> str:
    lang, base, v = ctx["lang"], ctx["base"], ctx.get("v", "1")
    alt_path = canonical.split("?")[0]
    alts = "".join(f'<link rel="alternate" hreflang="{l}" href="{e(base + alt_path + ("?lang=ru" if l == "ru" else ""))}">'
                   for l in ("uz", "ru"))
    alts += f'<link rel="alternate" hreflang="x-default" href="{e(base + alt_path)}">'
    ld = "".join(f'<script type="application/ld+json">{json.dumps(j, ensure_ascii=False).replace("</", "<\\/")}</script>'
                 for j in (jsonld or []))
    og_img = f'<meta property="og:image" content="{e(base + og_image)}">' if og_image else ""
    robots = '<meta name="robots" content="noindex">' if noindex else ""
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
{robots}
<link rel="canonical" href="{e(base + canonical)}">
{alts}
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="{e(ctx['shop']['name'])}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(base + canonical)}">
<meta property="og:locale" content="{'ru_RU' if lang == 'ru' else 'uz_UZ'}">
{og_img}
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#f6f1ea">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" href="/s/icon-192.png" type="image/png">
<link rel="apple-touch-icon" href="/s/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="{e(ctx['shop']['name'])}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&family=Playfair+Display:ital,wght@0,500;0,600;1,500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/s/site.css?v={v}">
<script>/* Telegram ichida ochilsa — ilovaga (Mini App) o'tamiz */
(function(){{var h=location.hash||"",s=location.search||"";if(h.indexOf("tgWebApp")>=0||/[?&](admin|tgWebAppStartParam)=/.test(s)){{location.replace("/app"+s+h);return;}}
/* avval ruscha tanlagan bo'lsa (saytda yoki ilovada) — ruscha sahifani ochamiz */
try{{if(!/[?&]lang=/.test(s)&&document.documentElement.lang==="uz"&&JSON.parse(localStorage.getItem("lang"))==="ru"){{location.replace(location.pathname+(s?s+"&":"?")+"lang=ru"+h);}}}}catch(e){{}}}})();</script>
{ld}
{pixel_head(ctx)}
</head>
<body>
{header(ctx)}
<main>{body}</main>
{footer(ctx)}
{cart_drawer(lang)}
<script id="boot" type="application/json">{boot_json(ctx)}</script>
<script src="/s/site.js?v={v}" defer></script>
</body>
</html>"""


def _cats_index(ctx) -> dict:
    return {c["id"]: c for c in ctx["categories"]}


def store_jsonld(ctx: dict) -> dict:
    shop, base = ctx["shop"], ctx["base"]
    j = {"@context": "https://schema.org", "@type": "FurnitureStore", "name": shop["name"], "url": base + "/",
         "logo": base + "/s/icon-512.png", "image": base + "/s/icon-512.png", "currenciesAccepted": "UZS"}
    if shop.get("phone"):
        j["telephone"] = shop["phone"]
    if shop.get("address"):
        j["address"] = {"@type": "PostalAddress", "streetAddress": shop["address"], "addressCountry": "UZ"}
    nick = ctx["settings"].get("admin_contact")
    same = [f"https://t.me/{x}" for x in (ctx.get("bot"), nick) if x]
    if same:
        j["sameAs"] = same
    return j


# ------------------------------------------------------------------ sahifalar
def page_home(ctx: dict) -> str:
    lang, shop, st = ctx["lang"], ctx["shop"], ctx["settings"]
    pct = int(ctx.get("prepay_pct") or 10)
    asm = int(ctx.get("assembly_pct") or 0)
    cats = _cats_index(ctx)
    products = ctx["products"]
    counts = {}
    for p in products:
        counts[p.get("cat_id")] = counts.get(p.get("cat_id"), 0) + 1
    bot = ctx.get("bot") or ""
    tg_link = f"https://t.me/{bot}" if bot else ""

    # Bosh rasm: suratli mahsulotlardan kollaj, bo'lmasa — chizilgan rasm
    with_img = [p for p in products if first_image(p)][:3]
    if with_img:
        tiles = "".join(f'<a class="hero-tile t{i}" href="{product_url(p)}?lang={lang}">{picture(p, eager=i == 0)}'
                        f'<span class="hero-tag"><span>{e(p["name"])}</span><b>{money(p["price"], lang)}</b></span></a>'
                        for i, p in enumerate(with_img))
        visual = f'<div class="hero-collage n{len(with_img)}">{tiles}</div>'
    else:
        visual = f'<div class="hero-art">{SOFA_ART}<div class="hero-sun"></div></div>'

    feats = [("truck", "f_delivery", "f_delivery_t"), ("tool", "f_asm", "f_asm_t"),
             ("card", "f_prepay", "f_prepay_t"), ("check", "f_check", "f_check_t")]
    feats_html = "".join(f'<div class="feat"><span class="feat-ic">{ICONS[ic]}</span><div><b>{e(tr(lang, a, pct=pct))}</b>'
                         f'<small>{e(tr(lang, b))}</small></div></div>' for ic, a, b in feats)

    cat_cards = "".join(
        f'<button class="cat" data-pick="{c["id"]}"><span class="cat-emoji">{e(c.get("emoji") or "🪑")}</span>'
        f'<b>{e(c["name"])}</b><small>{e(tr(lang, "items_n", n=counts.get(c["id"], 0)))}</small></button>'
        for c in ctx["categories"] if counts.get(c["id"]))
    chips = f'<button class="chip on" data-cat="0">{e(tr(lang, "all"))}</button>' + "".join(
        f'<button class="chip" data-cat="{c["id"]}">{e(c["name"])}</button>' for c in ctx["categories"] if counts.get(c["id"]))

    grid = "".join(product_card(p, lang, cats) for p in products)
    if not products:
        grid_html = (f'<div class="empty">{e(tr(lang, "empty_catalog"))}'
                     + (f'<br><a class="btn" href="{tg_link}" target="_blank" rel="noopener">{ICONS["tg"]}'
                        f'{e(tr(lang, "tg_btn"))}</a>' if tg_link else "") + '</div>')
    else:
        grid_html = f'<div class="grid" id="grid">{grid}</div><div class="empty" id="nothing" hidden>{e(tr(lang, "nothing"))}</div>'

    steps = "".join(f'<li><span class="step-n">0{i}</span><h3>{e(tr(lang, f"how_{i}"))}</h3>'
                    f'<p>{e(tr(lang, f"how_{i}t", pct=pct))}</p></li>' for i in range(1, 5))

    nick = st.get("admin_contact") or ""
    contact = (f'<a href="https://t.me/{e(nick)}" target="_blank" rel="noopener">@{e(nick)}</a>' if nick
               else e(shop.get("phone") or "—"))
    ask = e(tr(lang, "a_ask", contact="{c}")).replace("{c}", contact)
    if shop.get("phone") and nick:
        ask += e(tr(lang, "a_ask_phone", phone="{p}")).replace(
            "{p}", f'<a href="tel:{e(re.sub(r"[^0-9+]", "", shop["phone"]))}">{e(shop["phone"])}</a>')
    faq = [("q_pay", e(tr(lang, "a_pay", pct=pct))), ("q_when", e(tr(lang, "a_when"))),
           ("q_check", e(tr(lang, "a_check"))), ("q_ask", ask)]
    if asm:
        faq.insert(2, ("q_asm", e(tr(lang, "a_asm", asm=asm))))
    faq_html = "".join(f'<details{" open" if i == 0 else ""}><summary>{e(tr(lang, q))}</summary><p>{a}</p></details>'
                       for i, (q, a) in enumerate(faq))

    tg_band = ""
    if tg_link:
        tg_band = f"""<section class="band"><div class="wrap band-in">
  <div class="band-ic">{ICONS['tg']}</div>
  <div><h2>{e(tr(lang, 'tg_title'))}</h2><p>{e(tr(lang, 'tg_text'))}</p></div>
  <a class="btn light" href="{tg_link}" target="_blank" rel="noopener">{e(tr(lang, 'tg_btn'))} · @{e(bot)}</a>
</div></section>"""

    body = f"""
<section class="hero"><div class="wrap hero-in">
  <div class="hero-txt">
    <div class="eyebrow">{e(tr(lang, 'hero_eyebrow'))}</div>
    <h1>{tr(lang, 'hero_title')}</h1>
    <p class="lead">{e(tr(lang, 'hero_text'))}</p>
    <div class="hero-cta"><a class="btn" href="#katalog">{e(tr(lang, 'hero_cta'))}</a>
      {f'<a class="btn ghost" href="{tg_link}" target="_blank" rel="noopener">{ICONS["tg"]}{e(tr(lang, "hero_tg"))}</a>' if tg_link else ''}</div>
  </div>
  {visual}
</div>
<div class="wrap feats">{feats_html}</div></section>

<section class="sec doors-sec"><div class="wrap doors">
  <a class="door" href="#katalog"><span class="door-ic">🛋</span><div><h2>{e(tr(lang, 'door_ready'))}</h2><p>{e(tr(lang, 'door_ready_t'))}</p>
    <span class="door-go">{e(tr(lang, 'door_ready_btn'))} →</span></div></a>
  <a class="door dark" href="/custom?lang={lang}"><span class="door-ic">📐</span><div><h2>{e(tr(lang, 'door_custom'))}</h2><p>{e(tr(lang, 'door_custom_t'))}</p>
    <span class="door-go">{e(tr(lang, 'door_custom_btn'))} →</span></div></a>
</div></section>

{f'<section class="sec" id="bolimlar"><div class="wrap"><h2 class="sec-t">{e(tr(lang, "cats_title"))}</h2><div class="cats">{cat_cards}</div></div></section>' if cat_cards else ''}

<section class="sec" id="katalog"><div class="wrap">
  <div class="sec-head"><h2 class="sec-t">{e(tr(lang, 'cat_title'))}</h2>
    {f'''<div class="tools"><label class="search">{ICONS['search']}<input id="q" type="search" placeholder="{e(tr(lang, 'search_ph'))}" autocomplete="off"></label>
    <select id="sort" aria-label="sort"><option value="new">{e(tr(lang, 'sort_new'))}</option><option value="cheap">{e(tr(lang, 'sort_cheap'))}</option><option value="exp">{e(tr(lang, 'sort_exp'))}</option></select></div>''' if products else ''}</div>
  {f'<div class="chips" id="chips">{chips}</div>' if products else ''}
  {grid_html}
</div></section>

<section class="sec how" id="qanday"><div class="wrap"><h2 class="sec-t">{e(tr(lang, 'how_title'))}</h2><ol class="steps">{steps}</ol></div></section>

{tg_band}

<section class="sec" id="tolov"><div class="wrap info"><h2 class="sec-t">{e(tr(lang, 'info_title'))}</h2><div class="faq">{faq_html}</div></div></section>
"""
    title = tr(lang, "home_title", shop=shop["name"])
    desc = tr(lang, "home_desc", shop=shop["name"], pct=pct)
    og = first_image(with_img[0]) if with_img else "/s/og.png"
    ld = [store_jsonld(ctx), {"@context": "https://schema.org", "@type": "WebSite", "name": shop["name"],
                              "url": ctx["base"] + "/", "inLanguage": ["uz", "ru"]}]
    return layout(ctx, title, desc, body, "/" + ("?lang=ru" if lang == "ru" else ""), og, ld)


def page_product(ctx: dict, p: dict) -> str:
    lang, shop = ctx["lang"], ctx["shop"]
    cats = _cats_index(ctx)
    cat = cats.get(p.get("cat_id"), {})
    imgs = [img_url(x) for x in (p.get("images") or [])]
    video = p.get("video") or {}
    yt = p.get("youtube") or ""
    slides = []
    if imgs:
        slides += [f'<img src="{e(u)}" alt="{e(p["name"])}" {"fetchpriority=high" if i == 0 else "loading=lazy"}>'
                   for i, u in enumerate(imgs)]
    if video.get("src"):
        slides.append(f'<video src="{e(img_url(video["src"]))}" poster="{e(img_url(video.get("poster") or ""))}" '
                      f'controls playsinline preload="none"></video>')
    if yt:
        slides.append(f'<iframe src="https://www.youtube-nocookie.com/embed/{e(yt)}" title="YouTube" loading="lazy" '
                      f'allow="encrypted-media; picture-in-picture" allowfullscreen></iframe>')
    if not slides:
        slides = [placeholder(p)]
    thumbs = ""
    if len(slides) > 1:
        tlist = []
        for i, u in enumerate(imgs):
            tlist.append(f'<button class="thumb{" on" if i == 0 else ""}" data-go="{i}"><img src="{e(u)}" alt="" loading="lazy"></button>')
        if video.get("src"):
            poster = img_url(video.get("poster") or "")
            inner = f'<img src="{e(poster)}" alt="" loading="lazy">' if poster else ""
            tlist.append(f'<button class="thumb vid{" on" if not imgs else ""}" data-go="{len(imgs)}">{inner}<span>▶</span></button>')
        if yt:
            tlist.append(f'<button class="thumb vid" data-go="{len(slides) - 1}"><img src="https://i.ytimg.com/vi/{e(yt)}/mqdefault.jpg" '
                         f'alt="" loading="lazy"><span>▶</span></button>')
        thumbs = f'<div class="thumbs">{"".join(tlist)}</div>'
    gallery = (f'<div class="gallery"><div class="g-track" id="gTrack">'
               + "".join(f'<div class="g-slide">{s}</div>' for s in slides) + f'</div>{thumbs}</div>')

    d = discount_pct(p)
    price = (f'<div class="p-price">{money(p["price"], lang)}'
             + (f'<s>{money(p["old_price"], lang)}</s><span class="badge sale">−{d}%</span>' if d else "") + '</div>')
    stock = (f'<span class="pill ok">● {e(tr(lang, "in_stock"))}</span>' if p.get("in_stock")
             else f'<span class="pill no">● {e(tr(lang, "out"))}</span>')
    meta = [stock]
    if p.get("delivery_days"):
        meta.append(f'<span class="pill">{ICONS["truck"]}{e(tr(lang, "delivery_days"))}: {e(p["delivery_days"])}</span>')
    if p.get("assembly"):
        meta.append(f'<span class="pill">{ICONS["tool"]}{e(tr(lang, "asm_ok"))}</span>')
    bot = ctx.get("bot") or ""
    buttons = ""
    if p.get("in_stock"):
        buttons = (f'<button class="btn big" data-add="{p["id"]}">{ICONS["cart"]}<span>{e(tr(lang, "add"))}</span></button>'
                   f'<button class="btn big ghost" data-buy="{p["id"]}">{e(tr(lang, "buy_now"))}</button>')
    nick = (ctx.get("settings") or {}).get("admin_contact") or ""
    phone = (ctx.get("shop") or {}).get("phone") or ""
    acts = ""
    if phone:
        acts += (f'<a class="ch-call" href="tel:{e(re.sub(r"[^0-9+]", "", phone))}">{ICONS["phone"]}'
                 f'{e(tr(lang, "ch_call"))}</a>')
    if nick:
        acts += (f'<a class="ch-write" href="https://t.me/{e(nick)}" target="_blank" rel="noopener">{ICONS["tg"]}'
                 f'{e(tr(lang, "ch_write"))}</a>')
    if acts:
        buttons += (f'<div class="change-box"><b>✏️ {e(tr(lang, "ch_t"))}</b><p>{e(tr(lang, "ch_p"))} '
                    f'<b>{e(p["name"])} (№ {p["id"]})</b></p><div class="ch-acts">{acts}</div>'
                    + (f'<div class="ch-phone">{e(phone)}</div>' if phone else "") + '</div>')
    if bot:
        buttons += (f'<a class="tg-link" href="https://t.me/{e(bot)}?start=p{p["id"]}" target="_blank" rel="noopener">'
                    f'{ICONS["tg"]}{e(tr(lang, "tg_order"))}</a>')
    specs = p.get("specs") or []
    specs_html = ("<h2>" + e(tr(lang, "specs")) + '</h2><dl class="specs">'
                  + "".join(f"<div><dt>{e(k)}</dt><dd>{e(v)}</dd></div>" for k, v in specs) + "</dl>") if specs else ""
    desc_html = (f'<h2>{e(tr(lang, "about"))}</h2><p class="p-desc">{e(p.get("description") or "")}</p>'
                 if p.get("description") else "")
    related = [x for x in ctx["products"] if x["id"] != p["id"] and x.get("cat_id") == p.get("cat_id")][:4]
    rel_html = (f'<section class="sec"><div class="wrap"><h2 class="sec-t">{e(tr(lang, "related"))}</h2>'
                f'<div class="grid">{"".join(product_card(x, lang, cats) for x in related)}</div></div></section>'
                if related else "")
    home = "/" if lang == "uz" else "/?lang=ru"
    crumbs = (f'<nav class="crumbs"><a href="{home}">{e(shop["name"])}</a><span>/</span>'
              f'<a href="{home}#katalog" data-cat-link="{p.get("cat_id") or 0}">{e(cat.get("name") or tr(lang, "nav_catalog"))}</a>'
              f'<span>/</span><b>{e(p["name"])}</b></nav>')
    body = f"""<section class="product"><div class="wrap">
  {crumbs}
  <div class="p-grid">
    {gallery}
    <div class="p-info">
      <div class="card-cat">{e(cat.get('name', ''))}</div>
      <h1>{e(p['name'])}</h1>
      {price}
      <div class="pills">{''.join(meta)}</div>
      <div class="p-buy">{buttons}</div>
      {specs_html}
      {desc_html}
    </div>
  </div>
</div></section>
{rel_html}"""
    title = tr(lang, "prod_title", name=p["name"], price=money(p["price"], lang), shop=shop["name"])
    desc = (p.get("description") or "").strip().replace("\n", " ")[:155] or f'{p["name"]} — {money(p["price"], lang)}'
    url = product_url(p) + ("?lang=ru" if lang == "ru" else "")
    offer = {"@type": "Offer", "price": int(p["price"]), "priceCurrency": "UZS", "url": ctx["base"] + url,
             "availability": "https://schema.org/" + ("InStock" if p.get("in_stock") else "OutOfStock"),
             "seller": {"@type": "Organization", "name": shop["name"]}}
    ld = {"@context": "https://schema.org", "@type": "Product", "name": p["name"], "sku": str(p["id"]),
          "description": (p.get("description") or p["name"])[:500], "offers": offer,
          "brand": {"@type": "Brand", "name": shop["name"]}}
    if imgs:
        ld["image"] = [ctx["base"] + u for u in imgs[:5]]
    if cat.get("name"):
        ld["category"] = cat["name"]
    crumbs_ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": shop["name"], "item": ctx["base"] + home},
        {"@type": "ListItem", "position": 2, "name": p["name"], "item": ctx["base"] + url}]}
    if (shop or {}).get("pixel"):
        body += ("<script>window.fbq&&fbq('track','ViewContent',"
                 + json.dumps({"content_ids": [str(p["id"])], "content_type": "product", "value": int(p.get("price") or 0),
                               "currency": "UZS", "content_name": p["name"]}, ensure_ascii=False) + ")</script>")
    return layout(ctx, title, desc, body, url, first_image(p) or "/s/og.png", [ld, crumbs_ld], og_type="product")


def page_offer(ctx: dict, offer_html: str) -> str:
    lang = ctx["lang"]
    body = f'<section class="sec"><div class="wrap doc">{offer_html}</div></section>'
    return layout(ctx, f'{tr(lang, "offer")} — {ctx["shop"]["name"]}', tr(lang, "offer"), body,
                  "/oferta" + ("?lang=ru" if lang == "ru" else ""))


def page_404(ctx: dict) -> str:
    lang = ctx["lang"]
    home = "/" if lang == "uz" else "/?lang=ru"
    body = (f'<section class="sec"><div class="wrap nf"><div class="nf-art">{SOFA_ART}</div><h1>{e(tr(lang, "not_found"))}</h1>'
            f'<p>{e(tr(lang, "not_found_t"))}</p><a class="btn" href="{home}#katalog">{e(tr(lang, "back_catalog"))}</a></div></section>')
    return layout(ctx, tr(lang, "not_found"), tr(lang, "not_found_t"), body, "/", noindex=True)


def meta_feed_csv(base: str, products: list, categories: list, brand: str) -> str:
    """Meta katalogi: id, title, description, availability, condition, price, sale_price, link, image_link, brand..."""
    import csv
    import io
    cats = {c["id"]: c["name"] for c in categories}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "title", "description", "availability", "condition", "price", "sale_price", "link", "image_link",
                "additional_image_link", "brand", "product_type"])
    for p in products:
        imgs = [img_url(x) for x in (p.get("images") or []) if x]
        if not imgs or not p.get("price"):
            continue  # Meta rasmsiz yoki narxsiz mahsulotni qabul qilmaydi
        price, old = int(p["price"]), int(p.get("old_price") or 0)
        desc = re.sub(r"\s+", " ", p.get("description") or "").strip() or p["name"]
        w.writerow([p["id"], p["name"][:150], desc[:5000], "in stock" if p.get("in_stock") else "out of stock", "new",
                    f"{old if old > price else price} UZS", f"{price} UZS" if old > price else "",
                    base + product_url({**p, "name_uz": p["name"]}), base + imgs[0],
                    ",".join(base + x for x in imgs[1:10]), brand, cats.get(p.get("cat_id"), "")])
    return buf.getvalue()


def pixel_head(ctx: dict) -> str:
    pid = (ctx.get("shop") or {}).get("pixel") or ""
    if not pid:
        return ""
    return ("<script>!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?n.callMethod.apply(n,arguments)"
            ":n.queue.push(arguments)};if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);"
            "t.async=!0;t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,document,'script',"
            f"'https://connect.facebook.net/en_US/fbevents.js');fbq('init','{pid}');fbq('track','PageView');</script>")


def sitemap_xml(base: str, products: list) -> str:
    urls = [("/", "daily"), ("/oferta", "monthly")] + [(product_url(p), "weekly") for p in products]
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for path, freq in urls:
        uz, ru = base + path, base + path + "?lang=ru"
        for loc in (uz, ru):
            out.append(f"<url><loc>{e(loc)}</loc><changefreq>{freq}</changefreq>"
                       f'<xhtml:link rel="alternate" hreflang="uz" href="{e(uz)}"/>'
                       f'<xhtml:link rel="alternate" hreflang="ru" href="{e(ru)}"/></url>')
    out.append("</urlset>")
    return "\n".join(out)


def robots_txt(base: str) -> str:
    return ("User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /app\nDisallow: /act/\n"
            f"\nSitemap: {base}/sitemap.xml\n")


def manifest(shop_name: str) -> str:
    return json.dumps({
        "name": shop_name, "short_name": shop_name, "start_url": "/?source=pwa", "scope": "/",
        "display": "standalone", "background_color": "#f6f1ea", "theme_color": "#f6f1ea", "lang": "uz",
        "description": T["uz"]["tagline"],
        "icons": [{"src": "/s/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/s/icon-512.png", "sizes": "512x512", "type": "image/png"},
                  {"src": "/s/icon-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}],
    }, ensure_ascii=False)
