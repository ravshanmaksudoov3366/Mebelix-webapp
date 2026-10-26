"""Ommaviy oferta matni (o'zbekcha va ruscha).

DIQQAT: bu loyiha. Do'kon ishga tushishidan oldin yurist ko'rib chiqishi kerak.
Sotuvchi rekvizitlari admin paneldagi «Sozlamalar»dan olinadi (bo'sh bo'lsa — «____» chiqadi).
Matn o'zgarsa OFFER_VERSION ni yangilang: har buyurtmada mijoz qaysi versiyaga rozi bo'lgani saqlanadi.
"""
import html

OFFER_VERSION = "2026-10-26.1"

_BLANK = "____________"

OFFER_UZ = """<h2>Ommaviy oferta</h2>
<p class="muted">Mebel sotish va yetkazib berish shartnomasi · Tahrir: {ver}</p>

<h3>1. Umumiy qoidalar</h3>
<p>1.1. Ushbu hujjat {name} (STIR: {tin}, manzil: {address}, telefon: {phone}; bundan buyon — «Sotuvchi») tomonidan
Telegram'dagi «iSofa» do'koni (bot va ilova) hamda uning veb-sayti orqali mebel sotish bo'yicha istalgan shaxsga (bundan buyon — «Xaridor»)
qaratilgan ommaviy oferta hisoblanadi.</p>
<p>1.2. Xaridor ilovada «Ommaviy oferta shartlariga roziman» belgisini qo'yib, buyurtma berganida ushbu oferta
to'liq qabul qilingan (aksept) va shartnoma tuzilgan hisoblanadi («Elektron tijorat to'g'risida»gi Qonun).</p>

<h3>2. Buyurtma va to'lov</h3>
<p>2.1. Mahsulot nomi, rasmi, o'lchamlari, narxi va yetkazib berish muddati ilovada ko'rsatiladi.</p>
<p>2.2. Buyurtma uchun Xaridor ilovada ko'rsatilgan foizda oldindan to'lov qiladi va to'lov chekini yuklaydi.
Sotuvchi chekni tekshirib, buyurtmani tasdiqlaydi yoki rad etadi.</p>
<p>2.3. Qolgan summa mahsulot topshirilganda ilovada tanlangan usulda to'lanadi.</p>

<h3>3. Yetkazib berish</h3>
<p>3.1. Mahsulot Xaridor ilovada xaritada belgilagan manzilga ko'rsatilgan muddatda yetkaziladi.
Aniq vaqt Xaridor bilan telefon orqali kelishiladi.</p>

<h3>4. Yig'ib berish xizmati</h3>
<p>4.1. Yig'iladigan mahsulotlar uchun Xaridor buyurtma paytida yig'ib berish xizmatini tanlashi mumkin.</p>
<p>4.2. Xizmat narxi yig'iladigan mahsulotlar narxining {pct}% ini tashkil etadi va buyurtma summasiga qo'shiladi.
Xizmat faqat yetkazib berishda ko'rsatiladi.</p>

<h3>5. Mahsulotni qabul qilish</h3>
<p>5.1. Mahsulot topshirilayotganda Xaridor uni Sotuvchi vakili (kuryer yoki yig'uvchi) huzurida ko'zdan kechiradi:
komplektligi, tashqi ko'rinishi (shikast, tirnalish, dog'), rangi va o'lchami buyurtmaga mosligi.</p>
<p>5.2. Tekshiruv natijasi qabul qilish-topshirish dalolatnomasida qayd etiladi va ikki tomon imzolaydi.
Xaridor bundan tashqari botda «Tekshirdim, qabul qildim» tugmasi orqali qabulni tasdiqlaydi.</p>
<p>5.3. Ko'rinadigan nuqsonlar yoki komplekt yetishmasligi haqidagi e'tirozlar topshirish paytida dalolatnomada
yozilishi lozim.</p>

<h3>6. Qaytarish va almashtirish</h3>
<p>6.1. Mahsulot ilovadagi tavsif yoki rasmga mos kelmasa, yoki ishlab chiqarish nuqsoni aniqlansa, Xaridor
qonunchilikda belgilangan tartibda uni almashtirish yoki pulini qaytarishni talab qilishga haqli.</p>
<p>6.2. Sifati lozim darajadagi mebel to'plamlari qonunchilikka muvofiq qaytarilmaydi va almashtirilmaydi.</p>
<p>6.3. Ushbu oferta Xaridorning qonunchilikda belgilangan huquqlarini cheklamaydi.</p>

<h3>7. Shaxsiy ma'lumotlar</h3>
<p>7.1. Xaridor buyurtmani bajarish uchun o'z ismi, telefon raqami va manzilini Sotuvchiga, kuryer va yig'uvchiga
berilishiga rozilik bildiradi. Ma'lumotlar boshqa maqsadda uchinchi shaxslarga berilmaydi.</p>

<h3>8. Sotuvchi rekvizitlari</h3>
<p>{name}<br>STIR: {tin}<br>Manzil: {address}<br>Telefon: {phone}</p>
"""

OFFER_RU = """<h2>Публичная оферта</h2>
<p class="muted">Договор купли-продажи и доставки мебели · Редакция: {ver}</p>

<h3>1. Общие положения</h3>
<p>1.1. Настоящий документ является публичной офертой {name} (ИНН: {tin}, адрес: {address}, телефон: {phone};
далее — «Продавец») любому лицу (далее — «Покупатель») о продаже мебели через магазин «iSofa» в Telegram (бот и приложение) и его веб-сайт.</p>
<p>1.2. Оферта считается принятой (акцепт), а договор — заключённым, когда Покупатель отмечает
«Принимаю условия публичной оферты» и оформляет заказ (Закон «Об электронной коммерции»).</p>

<h3>2. Заказ и оплата</h3>
<p>2.1. Название, фото, размеры, цена и срок доставки товара указаны в приложении.</p>
<p>2.2. Для оформления заказа Покупатель вносит предоплату в размере, указанном в приложении, и загружает чек.
Продавец проверяет чек и подтверждает или отклоняет заказ.</p>
<p>2.3. Остаток оплачивается при получении товара выбранным в приложении способом.</p>

<h3>3. Доставка</h3>
<p>3.1. Товар доставляется по адресу, отмеченному Покупателем на карте, в указанный срок.
Точное время согласовывается по телефону.</p>

<h3>4. Услуга сборки</h3>
<p>4.1. Для товаров, требующих сборки, Покупатель может заказать сборку при оформлении заказа.</p>
<p>4.2. Стоимость услуги — {pct}% от цены собираемых товаров, она добавляется к сумме заказа.
Услуга оказывается только при доставке.</p>

<h3>5. Приёмка товара</h3>
<p>5.1. При передаче товара Покупатель осматривает его в присутствии представителя Продавца (курьера или сборщика):
комплектность, внешний вид (повреждения, царапины, пятна), соответствие цвета и размеров заказу.</p>
<p>5.2. Результат осмотра фиксируется в акте приёма-передачи, который подписывают обе стороны.
Дополнительно Покупатель подтверждает приёмку кнопкой «Проверил, принимаю» в боте.</p>
<p>5.3. Претензии по видимым дефектам и комплектности указываются в акте в момент передачи.</p>

<h3>6. Возврат и обмен</h3>
<p>6.1. Если товар не соответствует описанию или фото в приложении либо обнаружен производственный дефект,
Покупатель вправе потребовать замену или возврат денег в порядке, установленном законодательством.</p>
<p>6.2. Мебельные гарнитуры надлежащего качества в соответствии с законодательством возврату и обмену не подлежат.</p>
<p>6.3. Настоящая оферта не ограничивает права Покупателя, установленные законодательством.</p>

<h3>7. Персональные данные</h3>
<p>7.1. Покупатель соглашается на передачу своего имени, телефона и адреса Продавцу, курьеру и сборщику для
выполнения заказа. Данные не передаются третьим лицам в иных целях.</p>

<h3>8. Реквизиты Продавца</h3>
<p>{name}<br>ИНН: {tin}<br>Адрес: {address}<br>Телефон: {phone}</p>
"""


def render_offer(seller: dict, assembly_pct: int, lang: str = "uz", warranty_years: int = 3) -> str:
    f = {k: html.escape((seller.get(k) or "").strip()) or _BLANK for k in ("name", "tin", "address", "phone")}
    tpl = OFFER_RU if lang == "ru" else OFFER_UZ
    return tpl.format(ver=OFFER_VERSION, pct=assembly_pct, wy=warranty_years, **f)
