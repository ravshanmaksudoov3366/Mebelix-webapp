require('dotenv').config();
const TelegramBot = require('node-telegram-bot-api');
const express = require('express');

const token = process.env.BOT_TOKEN;
const adminId = process.env.ADMIN_ID;

// Express serverini sozlash (Render to'g'ri ishlashi uchun)
const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());

app.get('/', (req, res) => {
  res.send('Mebelix Bot serveri ishlamoqda!');
});

app.listen(PORT, () => {
  console.log(`Server ${PORT}-portda ishga tushdi`);
});

// Botni ishga tushirish (Polling rejimida)
const bot = new TelegramBot(token, { polling: true });

// Mebel mahsulotlarini vaqtincha saqlash uchun xotira (database o'rnida)
const products = [];

// /start buyrug'ini ushlash
bot.onText(/\/start/, (msg) => {
  const chatId = msg.chat.id;
  const isAdmin = chatId.toString() === adminId.toString();

  let welcomeText = `Assalomu aleykum! **Mebelix** mebel do'konining rasmiy botiga xush kelibsiz! ✨\n\nKatalogimizdan sifatli mebellarni tanlashingiz mumkin.`;
  
  const keyboard = [
    [{ text: "🛋 Mebellar katalogi" }],
    [{ text: "📞 Biz bilan bog'lanish" }]
  ];

  // Agar foydalanuvchi Admin bo'lsa, Admin tugmasini qo'shamiz
  if (isAdmin) {
    welcomeText += `\n\n👑 *Xush kelibsiz, Admin!*`;
    keyboard.push([{ text: "⚙️ Admin Panel" }]);
  }

  bot.sendMessage(chatId, welcomeText, {
    parse_mode: 'Markdown',
    reply_markup: {
      keyboard: keyboard,
      resize_keyboard: true
    }
  });
});

// Tugmalarni ushlash
bot.on('message', (msg) => {
  const chatId = msg.chat.id;
  const text = msg.text;

  if (text === "🛋 Mebellar katalogi") {
    if (products.length === 0) {
      bot.sendMessage(chatId, "Hozircha katalogda mebellar yo'q.");
    } else {
      bot.sendMessage(chatId, "Mebellar ro'yxati tez orada taqdim etiladi.");
    }
  } else if (text === "📞 Biz bilan bog'lanish") {
    bot.sendMessage(chatId, "Murojaat uchun: @MebelixAdmin yoki +998 90 123 45 67");
  } else if (text === "⚙️ Admin Panel" && chatId.toString() === adminId.toString()) {
    bot.sendMessage(chatId, "⚙️ **Admin Panel**\n\nBu yerdan mahsulot qo'shishingiz yoki o'chirishingiz mumkin.", {
      parse_mode: 'Markdown',
      reply_markup: {
        inline_keyboard: [
          [{ text: "➕ Yangi mebel qo'shish", callback_data: "add_product" }],
          [{ text: "🗑 Mebelni o'chirish", callback_data: "delete_product" }]
        ]
      }
    });
  }
});

console.log('Mebelix Bot muvaffaqiyatli ishga tushdi...');
