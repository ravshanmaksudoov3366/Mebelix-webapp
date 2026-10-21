# 🛋 Mebel do'koni — Telegram bot + Mini App

Tayyor mebellar sotish uchun Telegram ichida ishlaydigan to'liq do'kon.

## Nimalar bor

**Mijoz uchun**
- Rasmli katalog, kategoriyalar, qidiruv, saralash (arzon / qimmat / chegirma)
- Mahsulot sahifasi: bir nechta rasm (surib ko'rish), xususiyatlar, tavsif, chegirma foizi
- Savatcha (ilova yopilsa ham saqlanib qoladi)
- Tez buyurtma: yetkazib berish yoki olib ketish, telefonni 📱 bitta tugma bilan yuborish,
  to'lov usuli tanlash. Ikkinchi buyurtmada ism, telefon, manzil avtomatik to'ldiriladi
- «Buyurtmalarim»: holati (Yangi → Tasdiqlandi → Yo'lda → Yetkazildi), bekor qilish, qayta buyurtma
- Holat o'zgarganda bot orqali xabar keladi
- Botga oddiy xabar yozsa, u menejerga boradi

**Admin uchun** (telefondan, kod yozmasdan)
- Statistika: yangi buyurtmalar, bugungi va oylik savdo
- Buyurtmalar ro'yxati, filtrlar, mijozga bir bosishda qo'ng'iroq
- Yangi buyurtma darhol Telegram'ga keladi; holatni xabar ostidagi tugmalar bilan o'zgartirasiz
- Mahsulot qo'shish/tahrirlash: telefondan rasm yuklash (avtomatik siqiladi), narx, eski narx,
  tavsif, xususiyatlar, «omborda yo'q», «yashirish»
- Kategoriyalarni boshqarish
- Barcha mijozlarga xabar (aksiya, chegirma) yuborish
- Mijoz xabariga «Reply» qilib javob berish

## Fayllar
```
app.py            — bot + web server (bitta dastur)
shop.py           — baza va do'kon mantig'i
webapp/index.html — Mini App interfeysi
data/             — baza (shop.db) va rasmlar (avtomatik yaratiladi)
.env.example      — sozlamalar namunasi
```

## O'rnatish

### 1. Bot yaratish
1. Telegramda **@BotFather** → `/newbot` → nom bering → **token**ni nusxalang.
2. O'z Telegram ID raqamingizni **@userinfobot** orqali bilib oling.

### 2. Server
Mini App faqat **HTTPS** manzil orqali ishlaydi, shuning uchun dastur internetdagi serverda turishi kerak.

**A) VPS (tavsiya etiladi)** — Ubuntu server + domen:
```bash
sudo apt update && sudo apt install -y python3-pip python3-venv caddy
git clone <repo> mebel-bot   # yoki fayllarni yuklang
cd mebel-bot
python3 -m venv venv && . venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env      # qiymatlarni to'ldiring
python app.py
```
HTTPS uchun `/etc/caddy/Caddyfile`:
```
mebel.example.uz {
    reverse_proxy localhost:8080
}
```
so'ng `sudo systemctl reload caddy`. Caddy SSL sertifikatni o'zi oladi.

Dastur doim ishlab turishi uchun systemd xizmati (`/etc/systemd/system/mebel.service`):
```
[Unit]
Description=Mebel bot
After=network.target

[Service]
WorkingDirectory=/root/mebel-bot
ExecStart=/root/mebel-bot/venv/bin/python app.py
Restart=always

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now mebel
```

**B) Render (eng oson)** — `render.yaml` tayyor:
1. render.com → **New** → **Blueprint** → shu GitHub repo'ni tanlang.
2. So'ralganda faqat `BOT_TOKEN` ni kiriting (qolganlari `render.yaml` da yozilgan).
3. **Apply** — Render Starter tarifi (~7$/oy) va 1 GB disk bilan xizmat yaratadi.
   `WEBAPP_URL` kerak emas, Render manzilni o'zi beradi.
4. Agar shu token bilan ishlaydigan eski xizmat bo'lsa, uni **Suspend** yoki o'chiring
   (bitta botni ikki joyda ishlatib bo'lmaydi).

**C) Railway** — `Dockerfile` tayyor. Loyihani yuklang, `.env` dagi qiymatlarni
«Variables» bo'limiga kiriting, `/app/data` papkasiga **doimiy disk (Volume)** ulang
(aks holda qayta ishga tushganda mahsulot va buyurtmalar o'chib ketadi).
Berilgan `https://...` manzilni `WEBAPP_URL` ga yozing.

### 3. Tekshirish
1. Botga `/start` yozing → «🛋 Katalogni ochish».
2. Admin sifatida «🗂 Admin panel» tugmasi ham chiqadi (yoki `/admin`).
3. Namuna mahsulotlar bor — ularni o'chirib, o'zingiznikini qo'shing.

### Qo'shimcha: BotFather'da chiroyli havola
`@BotFather` → `/newapp` → botingizni tanlang → manzil sifatida `WEBAPP_URL` ni bering.
Shunda `t.me/botingiz/app` havolasi orqali do'kon to'g'ridan-to'g'ri ochiladi.
Ma'lum mahsulotga havola: `t.me/botingiz/app?startapp=p5` (5 — mahsulot ID).

## Sozlamalar (.env)
| Nomi | Ma'nosi |
|---|---|
| `BOT_TOKEN` | BotFather tokeni |
| `ADMIN_IDS` | Adminlar ID si, vergul bilan |
| `WEBAPP_URL` | Server HTTPS manzili |
| `SHOP_NAME`, `SHOP_PHONE`, `SHOP_ADDRESS` | Do'kon ma'lumotlari |
| `PORT` | Port (standart 8080) |

To'lov usullari ro'yxatini `shop.py` dagi `PAYMENTS` da o'zgartirish mumkin.

## Zaxira nusxa
Barcha ma'lumot `data/` papkasida. Vaqti-vaqti bilan shu papkani nusxalab qo'ying.
