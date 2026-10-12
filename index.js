require('dotenv').config();
const TelegramBot = require('node-telegram-bot-api');
const express = require('express');

const token = process.env.BOT_TOKEN;
const adminId = process.env.ADMIN_ID;

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());

// Mebellarni saqlash uchun xotira
const products = [];
const adminStates = {};

// Web App uchun mahsulotlar API'si
app.get('/api/products', (req, res) => {
  res.json(products);
});

// Web App do'konining HTML sahifasi
app.get('/', (req, res) => {
  res.send(`
    <!DOCTYPE html>
    <html lang="uz">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Mebelix Do'koni</title>
      <script src="https://telegram.org/js/telegram-web-app.js"></script>
      <style>
        body { font-family: sans-serif; background: #f4f4f9; margin: 0; padding: 15px; color: #333; }
        h1 { text-align: center; font-size: 20px; color: #2c3e50; }
        .grid { display: grid; grid-template-columns: 1fr; gap: 15px; margin-top: 15px; }
        .card { background: #fff; border-radius: 12px; padding: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .card img { width: 100%; height: 200px; object-fit: cover; border-radius: 8px; }
        .card h3 { margin: 10px 0 5px 0; font-size: 16px; }
        .price { color: #27ae60; font-weight: bold; font-size: 15px; }
        .empty { text-align: center; color: #7f8c8d; margin-top: 40px; }
      </style>
    </head>
    <body>
      <h1>🛋 Mebelix Katalogi</h1>
      <div id="product-list" class="grid"></div>

      <script>
        const tg = window.Telegram.WebApp;
        tg.expand();

        async function loadProducts() {
          const res = await fetch('/api/products');
          const data = await res.json();
          const list = document.getElementById('product-list');

          if (data.length === 0) {
            list.innerHTML = '<div class="empty">Hozircha katalogda mebellar yo\'q.</div>';
            return;
          }

          list.innerHTML = data.map(p => \`
            <div class="card">
              <img src="https://api.telegram.org/file/bot${token}/\${p.images[0]}" alt="\${p.title}" onerror="this.src='https://via.placeholder.com/300x200?text=Mebel'"/>
              <h3>\${p.title}</h3>
              <div class="price">\${p.price}</div>
            </div>
          \`).join('');
        }

        loadProducts();
      </script>
    </body>
    </html>
  `);
});

app.listen(PORT, () => {
  console.log(`Server ${PORT}-portda ishga tushdi`);
});

const bot = new TelegramBot(token, { polling: true });

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

// Admin callback query'lari
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
  else if (data === "delete_list") {
    if (products.length === 0) {
      bot.sendMessage(chatId, "O'chirish uchun mahsulot yo'q.");
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

// Xabarlar
bot.on('message', async (msg) => {
  const chatId = msg.chat.id;
  const text = msg.text;

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

  // Admin ketma-ketlik ma'lumot kiritishi
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
      bot.sendMessage(chatId, "🖼 **Mebel rasmlarini yuboring (1 dan 10 tagacha):**\n\nRasmlarni yuborib bo'lgach, pastdagi **'✅ Rasmlarni yuklashni tugatish'** tugmasini bosing.", {
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

console.log('Mebelix Bot va Web App ishga tushdi...');
