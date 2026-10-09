const TelegramBot = require('node-telegram-bot-api');
const express = require('express');

const token = '8987783785:AAH3rHQJm8NxApCENm73iQgPOpY7GFVQeTM';
const adminId = '1027326101';
const webAppUrl = 'https://ravshanmaksudoov3366.github.io/Mebelix-webapp/';

const bot = new TelegramBot(token, { polling: true });
const app = express();

app.use(express.json());

// /start komandasi
bot.onText(/\/start/, (msg) => {
  const chatId = msg.chat.id;
  bot.sendMessage(chatId, "Mebelix mebellar do'koniga xush kelibsiz! Katalog va buyurtma berish uchun quyidagi tugmani bosing:", {
    reply_markup: {
      inline_keyboard: [
        [{ text: "🛍 Do'konni ochish", web_app: { url: webAppUrl } }]
      ]
    }
  });
});

// WebApp'dan buyurtma kelganda
bot.on('message', async (msg) => {
  if (msg.web_app_data) {
    try {
      const data = JSON.parse(msg.web_app_data.data);
      
      let text = `🛒 **Yangi buyurtma!**\n\n`;
      text += `👤 **Mijoz:** ${msg.from.first_name} (@${msg.from.username || 'username yo\'q'})\n`;
      text += `🆔 **ID:** ${msg.from.id}\n\n`;
      text += `📦 **Mahsulotlar:**\n`;

      if (Array.isArray(data.items)) {
        data.items.forEach((item, index) => {
          text += `${index + 1}. ${item.name} - ${item.price} x ${item.quantity || 1}\n`;
        });
      } else {
        text += `${JSON.stringify(data)}\n`;
      }

      if (data.totalPrice) {
        text += `\n💰 **Jami summa:** ${data.totalPrice}`;
      }

      // 1. Mijozga tasdiq
      await bot.sendMessage(msg.chat.id, `Rahmat! Buyurtmangiz qabul qilindi. Tez orada siz bilan bog'lanamiz.`);

      // 2. Adminga xabar
      await bot.sendMessage(adminId, text, { parse_mode: 'Markdown' });

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
