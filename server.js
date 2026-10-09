const TelegramBot = require('node-telegram-bot-api');
const express = require('express');

const token = '8987783785:AAH3rHQJm8NxApCENm73iQgPOpY7GFVQeTM';
const adminId = '1027326101';
const webAppUrl = 'https://ravshanmaksudoov3366.github.io/Mebelix-webapp/';

const bot = new TelegramBot(token, { polling: true });
const app = express();

app.use(express.json());

// Main keyboard menu button sozlash
bot.setChatMenuButton({
  menu_button: JSON.stringify({
    type: "web_app",
    text: "🛍 Do'konni ochish",
    web_app: { url: webAppUrl }
  })
});

// /start komandasi
bot.onText(/\/start/, (msg) => {
  const chatId = msg.chat.id;
  const isAdmin = msg.from.id.toString() === adminId;

  let replyMarkup = {
    keyboard: [
      [{ text: "🛍 Do'konni ochish", web_app: { url: webAppUrl } }]
    ],
    resize_keyboard: true
  };

  // Admin bo'lsa boshqaruv tugmalarini qo'shamiz
  if (isAdmin) {
    replyMarkup.keyboard.push(
      [{ text: "➕ Mahsulot qo'shish" }, { text: "🗑 Mahsulot o'chirish" }]
    );
  }

  bot.sendMessage(chatId, "Mebelix mebellar do'koniga xush kelibsiz!\n\nPastdagi tugma orqali katalog bilan tanishishingiz mumkin:", {
    reply_markup: replyMarkup
  });
});

// Admin tugmalariga javob
bot.on('message', async (msg) => {
  const chatId = msg.chat.id;
  const text = msg.text;
  const isAdmin = msg.from.id.toString() === adminId;

  if (isAdmin && text === "➕ Mahsulot qo'shish") {
    bot.sendMessage(chatId, "Yangi mahsulot qo'shish bo'limi:\nIltimos, mahsulot nomini va narxini kiriting.");
    return;
  }

  if (isAdmin && text === "🗑 Mahsulot o'chirish") {
    bot.sendMessage(chatId, "Mahsulotni o'chirish uchun `products.json` faylidan mahsulot ID'sini tanlang yoki o'chiriladigan nomni kiriting.");
    return;
  }

  // WebApp'dan buyurtma kelganda
  if (msg.web_app_data) {
    try {
      const data = JSON.parse(msg.web_app_data.data);
      
      let orderText = `🛒 **Yangi buyurtma!**\n\n`;
      orderText += `👤 **Mijoz:** ${msg.from.first_name} (@${msg.from.username || 'username yo\'q'})\n`;
      orderText += `🆔 **ID:** ${msg.from.id}\n\n`;
      orderText += `📦 **Mahsulotlar:**\n`;

      if (Array.isArray(data.items)) {
        data.items.forEach((item, index) => {
          orderText += `${index + 1}. ${item.name} - ${item.price} $ x ${item.quantity || 1}\n`;
        });
      }

      if (data.totalPrice) {
        orderText += `\n💰 **Jami summa:** ${data.totalPrice}`;
      }

      // 1. Mijozga tasdiq
      await bot.sendMessage(msg.chat.id, `✅ Rahmat! Buyurtmangiz qabul qilindi. Tez orada siz bilan bog'lanamiz.`);

      // 2. Adminga xabar
      await bot.sendMessage(adminId, orderText, { parse_mode: 'Markdown' });

    } catch (e) {
      console.error('Xatolik:', e);
      bot.sendMessage(msg.chat.id, 'Buyurtmani qayta ishlashda xatolik yuz berdi.');
    }
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server ${PORT}-portda ishlamoqda...`);
});
