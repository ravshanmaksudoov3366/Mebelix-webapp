const { Telegraf } = require('telegraf');
const express = require('express');
const cors = require('cors');
const path = require('path');

// Environment variables
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_CHAT_ID = process.env.ADMIN_CHAT_ID;
const PORT = process.env.PORT || 3000;
const WEBHOOK_URL = process.env.RENDER_EXTERNAL_URL; // Render avto beradigan URL

if (!BOT_TOKEN) {
  console.error("Xatolik: BOT_TOKEN aniqlanmadi!");
  process.exit(1);
}

const bot = new Telegraf(BOT_TOKEN);
const app = express();

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public'))); // Front-end fayllar uchun

// 1. /start buyrug'i
bot.start((ctx) => {
  const webAppUrl = WEBHOOK_URL || 'https://your-domain.com';
  
  return ctx.reply('Salom! Mebelix mebel do\'koniga xush kelibsiz. Do\'konni ochish uchun pastdagi tugmani bosing:', {
    reply_markup: {
      inline_keyboard: [
        [{ text: "🛍 Do'konni ochish", web_app: { url: webAppUrl } }]
      ]
    }
  });
});

// 2. WebApp orqali kelgan buyurtmani adminga yuborish (API endpoint)
app.post('/api/order', async (req, res) => {
  try {
    const { customerName, phone, cartItems, totalPrice } = req.body;

    if (!cartItems || cartItems.length === 0) {
      return res.status(400).json({ success: false, message: "Savat bo'sh!" });
    }

    let message = `🛒 **Yangi buyurtma (Mebelix)**\n\n`;
    message += `👤 **Mijoz:** ${customerName || 'Ko\'rsatilmagan'}\n`;
    message += `📞 **Tel:** ${phone || 'Ko\'rsatilmagan'}\n\n`;
    message += `📦 **Mahsulotlar:**\n`;

    cartItems.forEach((item, index) => {
      message += `${index + 1}. ${item.name} - ${item.quantity} шт. (${item.price} so'm)\n`;
    });

    message += `\n💰 **Jami summasi:** ${totalPrice} so'm`;

    // Adminga xabar yuborish
    if (ADMIN_CHAT_ID) {
      await bot.telegram.sendMessage(ADMIN_CHAT_ID, message, { parse_mode: 'Markdown' });
    } else {
      console.warn("ADMIN_CHAT_ID o'rnatilmagan!");
    }

    return res.status(200).json({ success: true, message: "Buyurtma qabul qilindi!" });
  } catch (error) {
    console.error("Buyurtma yuborishda xatolik:", error);
    return res.status(500).json({ success: false, message: "Serverda xatolik yuz berdi" });
  }
});

// 3. Health-check va Webhook yo'laklari
app.get('/', (req, res) => res.send('Mebelix Bot Server Ishlamoqda!'));

// Render Webhook sozlamasi
if (WEBHOOK_URL) {
  app.use(bot.webhookCallback('/webhook'));
  bot.telegram.setWebhook(`${WEBHOOK_URL}/webhook`);
  console.log(`Webhook o'rnatildi: ${WEBHOOK_URL}/webhook`);
} else {
  // Mahalliy test qilish uchun Polling rejimida ishga tushirish
  bot.launch();
  console.log("Bot Polling rejimida ishga tushdi...");
}

app.listen(PORT, () => {
  console.log(`Server ${PORT}-portda ishlamoqda`);
});

// Serverni xavfsiz to'xtatish
process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
