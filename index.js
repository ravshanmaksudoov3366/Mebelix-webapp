require('dotenv').config();
const TelegramBot = require('node-telegram-bot-api');
const express = require('express');

const token = process.env.BOT_TOKEN;
const adminId = process.env.ADMIN_ID;

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());

app.get('/', (req, res) => {
  res.send('Mebelix Bot serveri ishlamoqda!');
});

app.listen(PORT, () => {
  console.log(`Server ${PORT}-portda ishga tushdi`);
});

const bot = new TelegramBot(token, { polling: true });

// Mebellarni saqlash uchun massiv (operativ xotirada)
const products = [];

// Admin mahsulot qo'shish jarayonini kuzatish uchun holat (state)
const adminStates = {};

// /start buyrug'i
bot.onText(/\/start/, (msg) => {
  const chatId = msg.chat.id;
  const isAdmin = chatId.toString() === adminId.toString();

  let welcomeText = `Assalomu aleykum! **Mebelix** mebel do'konining rasmiy botiga xush kelibsiz! ✨\n\nKatalogimizdan sifatli mebellarni tanlashingiz mumkin.`;

  const keyboard = [
    [{ text: "🛋 Mebellar katalogi" }],
    [{ text: "📞 Biz bilan bog'lanish" }]
  ];

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

// Admin tugmalari va hodisalari
bot.on('callback_query', async (query) => {
  const chatId = query.message.chat.id;
  const data = query.data;

  if (chatId.toString() !== adminId.toString()) return;

  if (data === "add_product") {
    adminStates[chatId] = { step: 'awaiting_title', images: [] };
    bot.sendMessage(chatId, "📝 **Yangi mebel nomini kiritishingiz mumkin:**", { parse_mode: 'Markdown' });
  } 
  else if (data === "finish_images") {
    const state = adminStates[chatId];
    if (state && state.step === 'awaiting_images') {
      if (state.images.length === 0) {
        bot.sendMessage(chatId, "⚠️ Kamida 1 ta rasm yuborishingiz kerak!");
        return;
      }
      // Yangi mahsulotni saqlash
      const newProduct = {
        id: Date.now(),
        title: state.title,
        price: state.price,
        images: state.images
      };
      products.push(newProduct);
      delete adminStates[chatId];

      bot.sendMessage(chatId, `✅ **Mebel muvaffaqiyatli qo'shildi!**\n\n🛋 Nom: ${newProduct.title}\n💰 Narx: ${newProduct.price}\n🖼 Rasmlar soni: ${newProduct.images.length}`, {
        parse_mode: 'Markdown'
      });
    }
  }
  else if (data.startsWith("del_")) {
    const productId = parseInt(data.replace("del_", ""));
    const index = products.findIndex(p => p.id === productId);
    if (index !== -1) {
      const removed = products.splice(index, 1)[0];
      bot.sendMessage(chatId, `🗑 **"${removed.title}"** bazadan o'chirildi!`);
    } else {
      bot.sendMessage(chatId, "❌ Mahsulot topilmadi.");
    }
  }

  bot.answerCallbackQuery(query.id);
});

// Xabarlarni ushlash
bot.on('message', async (msg) => {
  const chatId = msg.chat.id;
  const text = msg.text;

  // 1. Matnli buyruqlar
  if (text === "🛋 Mebellar katalogi") {
    if (products.length === 0) {
      bot.sendMessage(chatId, "🛋 Hozircha katalogda mebellar yo'q.");
      return;
    }

    for (let product of products) {
      const caption = `🛋 **${product.title}**\n💰 Narx: ${product.price}\n\n🔍 *Rasmni bosing va kattalashtirib (zoom) ko'ring!*`;
      
      if (product.images.length === 1) {
        await bot.sendPhoto(chatId, product.images[0], { caption, parse_mode: 'Markdown' });
      } else {
        const mediaGroup = product.images.map((imgId, idx) => ({
          type: 'photo',
          media: imgId,
          caption: idx === 0 ? caption : '',
          parse_mode: 'Markdown'
        }));
        await bot.sendMediaGroup(chatId, mediaGroup);
      }
    }
    return;
  }

  if (text === "📞 Biz bilan bog'lanish") {
    bot.sendMessage(chatId, "📞 **Murojaat va buyurtmalar uchun:**\n Telegram: @MebelixAdmin\n Telefon: +998 90 123 45 67", { parse_mode: 'Markdown' });
    return;
  }

  if (text === "⚙️ Admin Panel" && chatId.toString() === adminId.toString()) {
    bot.sendMessage(chatId, "⚙️ **Admin Panel**\n\nQuyidagi tugmalar orqali mebellarni boshqarishingiz mumkin:", {
      parse_mode: 'Markdown',
      reply_markup: {
        inline_keyboard: [
          [{ text: "➕ Yangi mebel qo'shish", callback_data: "add_product" }],
          [{ text: "🗑 Mebelni o'chirish", callback_data: "delete_list" }]
        ]
      }
    });
    return;
  }

  // Admin o'chirish ro'yxatini so'rasa
  if (text === "⚙️ Admin Panel") return;

  // 2. Admin qadamma-qadam mahsulot qo'shishi
  const state = adminStates[chatId];
  if (state) {
    if (state.step === 'awaiting_title' && text) {
      state.title = text;
      state.step = 'awaiting_price';
      bot.sendMessage(chatId, "💰 **Mebel narxini kiriting (masalan: 2,500,000 so'm):**", { parse_mode: 'Markdown' });
    } 
    else if (state.step === 'awaiting_price' && text) {
      state.price = text;
      state.step = 'awaiting_images';
      bot.sendMessage(chatId, "🖼 **Mebel rasmlarini yuboring (1 dan 10 tagacha):**\n\nRasmlarni yuborib bo'lgach, pastdagi **'✅ Tugatish'** tugmasini bosing.", {
        parse_mode: 'Markdown',
        reply_markup: {
          inline_keyboard: [
            [{ text: "✅ Rasmlarni yuklashni tugatish", callback_data: "finish_images" }]
          ]
        }
      });
    } 
    else if (state.step === 'awaiting_images' && msg.photo) {
      if (state.images.length >= 10) {
        bot.sendMessage(chatId, "⚠️ Maksimal 10 ta rasm yuklashingiz mumkin!");
        return;
      }
      const photoId = msg.photo[msg.photo.length - 1].file_id;
      state.images.push(photoId);
      bot.sendMessage(chatId, `📸 Rasm qabul qilindi! (${state.images.length}/10)`);
    }
  }
});

// Admin mahsulot o'chirish menyusini ko'rishi uchun
bot.on('callback_query', (query) => {
  const chatId = query.message.chat.id;
  if (query.data === "delete_list" && chatId.toString() === adminId.toString()) {
    if (products.length === 0) {
      bot.sendMessage(chatId, "O'chirish uchun hechnarsa yo'q.");
      return;
    }
    const buttons = products.map(p => ([{
      text: `🗑 ${p.title} (${p.price})`,
      callback_data: `del_${p.id}`
    }]));

    bot.sendMessage(chatId, "🗑 **O'chirmoqchi bo'lgan mebelingizni tanlang:**", {
      parse_mode: 'Markdown',
      reply_markup: { inline_keyboard: buttons }
    });
  }
});

console.log('Mebelix Bot to\'liq funksiyalar bilan ishlamoqda...');
