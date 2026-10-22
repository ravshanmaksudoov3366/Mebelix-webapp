# Oltin savdo boti (XAUUSD / GOLD)

MT5 hisobida (XM) oltin bilan avtomatik savdo qiladi. Broker hisobiga MetaApi bulut xizmati orqali ulanadi,
egasi esa iPad'dan Telegram orqali boshqaradi. Render'da alohida xizmat sifatida ishlaydi (`goldbot/Dockerfile`).

## Strategiyalar
Uchta mustaqil usul bor. Ularni Telegram'da `strategiya ABC` deb yozib birga yoki alohida yoqasiz.

- **A «Qaytish»:** katta trend bo'yicha, narx EMA21 ga qaytgandan keyin kirish (batafsil pastda).
- **B «Osiyo diapazoni»:** kechasi 00:00–07:00 UTC da oltin tor oraliqda yuradi.
  London ochilgach (07:00–11:00 UTC) narx shu oraliqdan H1 trend tomonga birinchi marta chiqsa, bot kiradi.
  Stop diapazon o'rtasi orqasiga qo'yiladi.
- **C «Siqilish→portlash»:** narx 8 sham davomida odatdagidan ancha tor qutida yursa, keyin trend tomonga
  katta tanali sham bilan qutidan chiqsa, bot kiradi. Stop qutining narigi tomoniga qo'yiladi.
- **Ishonch bali (0.5–1.5):** bot riskni shu balga ko'paytiradi, lekin bir savdoda 10% dan oshirmaydi.
  - ball oshadi: ADX ≥ 30 bo'lsa, London–Nyu-York kesishuvida (12–16 UTC) va bir nechta usul bir yo'nalishni ko'rsatsa;
  - ball kamayadi: kech soatlarda va usullar bir-biriga zid bo'lsa.
  - Telegram'da `balli risk yo'q` deb yozsangiz, risk o'zgarmas bo'ladi.
- **🧪 Sinov:** XM narxlarining oxirgi 365 kunida har bir usul alohida va birga tekshiriladi.
  Davr ikkiga bo'linadi: birinchi 2/3 qismi «o'rganish», oxirgi 1/3 qismi «tekshiruv».
  Faqat bot ko'rmagan tekshiruv davrida ham foyda bergan usul tavsiya qilinadi.

### A usuli batafsil
- **Trend (H1):** EMA50 EMA200 dan yuqori, narx EMA50 dan yuqori va ADX ≥ 20 bo'lsa, bot faqat sotib oladi.
  Teskari holatda faqat sotadi. Trend aniq bo'lmasa, savdo qilmaydi.
- **Kirish (M15):** narx EMA21 ga qaytib tekkandan keyin trend tomonga kuchli yopilganda.
- **Stop-loss:** oxirgi 5 shamning past/baland nuqtasi orqasida, 1–2.5 ATR oralig'ida.
  **Take-profit:** stop masofasining 2 baravari.
- **Himoya:**
  - foyda 1R ga yetsa, stop zararsiz nuqtaga suriladi; 1.5R da 0.5R foyda qulflanadi;
  - bir vaqtda faqat bitta savdo ochiq turadi;
  - savdo vaqti: ish kunlari 07:00–20:00 UTC;
  - juma kuni 20:30 UTC da hamma savdolar yopiladi;
  - bir kunda ketma-ket N marta yutqazsa (standart 5), o'sha kuni boshqa savdo ochmaydi;
  - hisob eng yuqori nuqtasidan `MAX_DRAWDOWN_PCT` foizga tushsa, bot pauzaga o'tadi;
  - spred katta bo'lsa, savdo ochmaydi.
- **Lot hajmi:** stopga tegsa hisobning aynan «risk %» qismi yo'qotiladigan qilib hisoblanadi.

## Muhit o'zgaruvchilari (Render → Environment)
| Nomi | Majburiy | Izoh |
|---|---|---|
| `METAAPI_TOKEN` | ha | app.metaapi.cloud → API tokens |
| `METAAPI_ACCOUNT_ID` | ha | MetaApi'ga qo'shilgan MT5 hisobining ID raqami |
| `TELEGRAM_TOKEN` | ha | @BotFather bergan yangi bot tokeni |
| `OWNER_ID` | ha | Botni boshqaradigan yagona Telegram foydalanuvchi ID raqami |
| `RISK_PERCENT` | yo'q | Har savdodagi risk, %. Standart: 5 |
| `MAX_CONSEC_LOSSES` | yo'q | Kunlik ketma-ket yutqazishlar chegarasi. Standart: 5 |
| `MAX_TRADES_PER_DAY` | yo'q | Bir kundagi savdolar chegarasi. Standart: 10 |
| `MAX_DRAWDOWN_PCT` | yo'q | Shuncha % pasayishda bot pauzaga o'tadi. Standart: 50 |
| `AUTO_START` | yo'q | `1` bo'lsa, qayta ishga tushganda savdo darhol davom etadi. Standart: `0` (pauza) |
| `SYMBOL` | yo'q | Bo'sh bo'lsa, bot GOLD/XAUUSD belgisini o'zi topadi |
| `BACKTEST_DAYS` | yo'q | Sinov uchun olinadigan kunlar soni. Standart: 365 |
| `STRATEGIES` | yo'q | Yoqilgan usullar. Standart: `ABC` |
| `DYNAMIC_RISK` | yo'q | `1` bo'lsa, risk ishonch baliga qarab o'zgaradi. Standart: `1` |

Telegram'dan o'zgartirilgan risk va seriya sozlamalari server qayta ishga tushguncha amal qiladi.
Doimiy qilish uchun ularni muhit o'zgaruvchilarida ham o'zgartiring.

## Telegram buyruqlari
- 📊 Holat
- 📜 Tarix
- ▶️ Boshlash
- ⏸ To'xtatish
- ⚙️ Risk — `risk 3`, `seriya 5`, `strategiya AB`, `balli risk ha` yoki `balli risk yo'q` deb yozib o'zgartiriladi
- 🧪 Sinov — strategiyani o'tgan narxlarda tekshiradi
- ❌ Hammasini yopish — tasdiqlash uchun `ha yopish` deb yoziladi

## Testlar
```
cd goldbot && python3 -m unittest discover -s tests
```
