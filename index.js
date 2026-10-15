const { Telegraf } = require('telegraf');
const express = require('express');
const cors = require('cors');

const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_CHAT_ID = process.env.ADMIN_CHAT_ID;
const WEBAPP_URL = "https://ravshanmaksudoov3366.github.io/Mebelix-webapp/";

if (!BOT_TOKEN) {
  console.error("BOT_TOKEN ko'rsatilmadi!");
  process.exit(1);
}

const bot = new Telegraf(BOT_TOKEN);
const app = express();

app.use(cors());
app.use(express.json());

// /start buyrug'i
bot.start((ctx) => {
  ctx.reply("MQ Mebelix do'koniga xush kelibsiz!\n\nQuyidagi tugmani bosib tayyor mebellar katalogini ko'rishingiz mumkin:", {
    reply_markup: {
      keyboard: [
        [{ text: "🛋 Do'konni ochish", web_app: { url: WEBAPP_URL } }]
      ],
      resize_keyboard: true
    }
  });
});

// Zaxira: tg.sendData orqali kelganda
bot.on('web_app_data', async (ctx) => {
  try {
    const rawData = ctx.web_app_data && ctx.web_app_data.data;
    if (!rawData) return;
    const data = JSON.parse(rawData);
    await processOrder(ctx.from, data.items, data.totalPrice);
    await ctx.reply(`✅ Buyurtmangiz qabul qilindi!\n\nJami summa: ${data.totalPrice} $`);
  } catch (err) {
    console.error("sendData xatoligi:", err);
  }
});

// Asosiy usul: WebApp'dan keladigan HTTP API so'rovini qabul qilish
app.post('/api/order', async (req, res) => {
  try {
    const { user, items, totalPrice } = req.body;

    if (!items || items.length === 0) {
      return res.status(400).json({ error: "Savat bo'sh" });
    }

    await processOrder(user, items, totalPrice);

    // Mijozga botdan xabar yuborish (agar user.id mavjud bo'lsa)
    if (user && user.id) {
      try {
        await bot.telegram.sendMessage(user.id, `✅ **Buyurtmangiz muvaffaqiyatli qabul qilindi!**\n\n💰 Jami summa: **${totalPrice} $**\n\nTez orada menejerimiz siz bilan bog'lanadi!`, { parse_mode: 'Markdown' });
      } catch (e) {
        console.log("Mijozga xabar yuborib bo'lmadi:", e.message);
      }
    }

    res.json({ success: true });
  } catch (err) {
    console.error("API Buyurtma xatosi:", err);
    res.status(500).json({ error: "Server xatosi" });
  }
});

// Buyurtmani shakllantirish va Adminga yuborish
async function processOrder(user, items, totalPrice) {
  let itemsText = "";
  if (items && Array.isArray(items)) {
    items.forEach((item, index) => {
      itemsText += `${index + 1}. *${item.title}* — ${item.count} ta x ${item.price} $ = ${item.subtotal} $\n`;
    });
  }

  const userInfo = user ? `${user.first_name || ''} ${user.last_name || ''} (@${user.username || 'username_yoq'})` : "Nomalum";
  const userId = user && user.id ? user.id : "Korsatilmagan";

  const adminMessage = `🛒 *YANGI BUYURTMA!*

👤 *Mijoz:* ${userInfo}
🆔 *ID:* \`${userId}\`

📦 *Buyurtma qilingan mebellar:*
${itemsText}
💰 *Jami summa:* ${totalPrice} $`;

  if (ADMIN_CHAT_ID) {
    await bot.telegram.sendMessage(ADMIN_CHAT_ID, adminMessage, { parse_mode: 'Markdown' });
  }
}

bot.launch().then(() => console.log("Mebelix Boti muvaffaqiyatli ishga tushdi!"));

const PORT = process.env.PORT || 10000;
app.get('/', (req, res) => res.send('Mebelix Bot Server is Active!'));
app.listen(PORT, () => console.log(`Server listening on port ${PORT}`));
