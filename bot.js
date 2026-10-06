const { Telegraf } = require('telegraf');
const express = require('express');
const cors = require('cors');
const path = require('path');

// Atrof-muhit o'zgaruvchilari
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_CHAT_ID = process.env.ADMIN_CHAT_ID;
const PORT = process.env.PORT || 3000;
const WEBHOOK_URL = process.env.RENDER_EXTERNAL_URL;

if (!BOT_TOKEN) {
  console.error("Xatolik: BOT_TOKEN ko'rsatilmagan!");
  process.exit(1);
}

const bot = new Telegraf(BOT_TOKEN);
const app = express();

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// 1. /start buyrug'i
bot.start((ctx) => {
  const webAppUrl = WEBHOOK_URL || 'https://your-domain.com';
  
  return ctx.reply("Salom! Mebelix mebel do'koniga xush kelibsiz. Katalog va buyurtma berish uchun quyidagi tugmani bosing:", {
    reply_markup: {
      inline_keyboard: [
        [{ text: "🛍 Mebelix Do'konini Ochish", web_app: { url: webAppUrl } }]
      ]
    }
  });
});

// Helper: Textlarni HTML xatolaridan tozalash
function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// 2. Buyurtma va 10% To'lovni adminga yuborish (API Endpoint)
app.post('/api/order', async (req, res) => {
  try {
    const { customerName, username, phone, address, transaction, cartItems, totalPrice, advancePrice } = req.body;

    if (!cartItems || cartItems.length === 0) {
      return res.status(400).json({ success: false, message: "Savat bo'sh!" });
    }

    let message = `📥 <b>YANGI BUYURTMA + 10% TO'LOV | MEBELIX</b>\n\n`;
    message += `👤 <b>Mijoz:</b> ${escapeHtml(customerName)}\n`;
    message += `💬 <b>Telegram:</b> ${escapeHtml(username)}\n`;
    message += `📞 <b>Tel:</b> ${escapeHtml(phone)}\n`;
    message += `📍 <b>Manzil:</b> ${escapeHtml(address)}\n\n`;
    
    message += `💳 <b>TO'LOV MA'LUMOTI (10% Avans):</b>\n`;
    message += `└ <b>10% Avans summasi:</b> ${advancePrice.toLocaleString('uz-UZ')} so'm\n`;
    message += `└ <b>Chek / Tranzaksiya:</b> ${escapeHtml(transaction)}\n\n`;

    message += `📦 <b>Buyurtma qilingan mebellar:</b>\n`;
    cartItems.forEach((item, index) => {
      const itemTotal = (item.price * item.quantity).toLocaleString('uz-UZ');
      message += `${index + 1}. <b>${escapeHtml(item.name)}</b> (${item.quantity} ta) - ${itemTotal} so'm\n`;
    });

    message += `\n💵 <b>UMUMIY SHARTNOMA SUMMASI:</b> ${totalPrice.toLocaleString('uz-UZ')} so'm`;

    // Admin Telegramiga xabar yuborish
    if (ADMIN_CHAT_ID) {
      await bot.telegram.sendMessage(ADMIN_CHAT_ID, message, { parse_mode: 'HTML' });
    } else {
      console.warn("ADMIN_CHAT_ID o'rnatilmagan!");
    }

    return res.status(200).json({ success: true, message: "Buyurtma va to'lov qabul qilindi!" });
  } catch (error) {
    console.error("Buyurtma yuborishda xatolik:", error);
    return res.status(500).json({ success: false, message: "Serverda xatolik yuz berdi" });
  }
});

// Health-check
app.get('/', (req, res) => res.send('Mebelix Bot Server Ishlamoqda!'));

// Render Webhook sozlamasi
if (WEBHOOK_URL) {
  app.use(bot.webhookCallback('/webhook'));
  bot.telegram.setWebhook(`${WEBHOOK_URL}/webhook`);
  console.log(`Webhook o'rnatildi: ${WEBHOOK_URL}/webhook`);
} else {
  bot.launch();
  console.log("Bot Polling rejimida ishga tushdi...");
}

app.listen(PORT, () => {
  console.log(`Server ${PORT}-portda ishlamoqda`);
});

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
