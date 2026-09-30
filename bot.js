const TelegramBot = require('node-telegram-bot-api');
const { createClient } = require('@supabase/supabase-js');
const express = require('express');

const SUPABASE_URL = 'https://avryabmbrowguthrvatf.supabase.co';
const SUPABASE_KEY = 'sb_publishable_KuReIRnnzOoTVD-vfIzeUA_9XE2AqCt';
const BOT_TOKEN = '8987783785:AAH3rHQJm8NxApCENm73iQgPOpY7GFVQeTM';

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);
const bot = new TelegramBot(BOT_TOKEN, { polling: true });

// Render port talabini qondirish uchun oddiy Express server
const app = express();
const PORT = process.env.PORT || 10000;

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Server is running on port ${PORT}`);
});

const adminState = {};

const CATEGORIES = [
  'Shkaflar',
  'Oyoq kiyim javoni',
  'Kitoblar javoni',
  'Krovatlar',
  'Yotoqxona to\'plami',
  'Yumshoq mebellar',
  'Tumbalar',
  'Mexmonxona uchun mebellar',
  'Oshxona uchun mebellar',
  'Bolalar uchun mebellar',
  'Stol va stullar',
  'Ofis uchun mebellar'
];

bot.onText(/\/start/, (msg) => {
  const chatId = msg.chat.id;
  bot.sendMessage(chatId, "Mebelix do'koniga xush kelibsiz!", {
    reply_markup: {
      inline_keyboard: [
        [{ text: "Mebelix Do'koni 🛒", web_app: { url: "https://ravshanmaksudoov3366.github.io/Mebelix-webapp/" } }]
      ]
    }
  });
});

// Yangi mahsulot qo'shishni boshlash
bot.onText(/\/add/, (msg) => {
  const chatId = msg.chat.id;
  adminState[chatId] = { step: 'TITLE', imageUrls: [] };
  bot.sendMessage(chatId, "Mebel nomini kiriting:");
});

// Mahsulotni o'chirish uchun ro'yxatni chaqirish
bot.onText(/\/delete/, async (msg) => {
  const chatId = msg.chat.id;

  // Bazadan oxirgi qo'shilgan 10 ta mahsulotni olib kelamiz
  const { data: products, error } = await supabase
    .from('products')
    .select('id, title, price')
    .order('created_at', { ascending: false })
    .limit(10);

  if (error || !products || products.length === 0) {
    return bot.sendMessage(chatId, "Hozircha o'chirish uchun mahsulotlar topilmadi.");
  }

  // Har bir mahsulot uchun o'chirish tugmasini yaratamiz
  const buttons = products.map(p => [
    { text: `❌ ${p.title} (${Number(p.price).toLocaleString()} so'm)`, callback_data: `del_${p.id}` }
  ]);

  bot.sendMessage(chatId, "O'chirmoqchi bo'lgan mahsulotni tanlang:", {
    reply_markup: { inline_keyboard: buttons }
  });
});

bot.on('message', async (msg) => {
  const chatId = msg.chat.id;
  const state = adminState[chatId];

  if (!state || msg.text === '/start' || msg.text === '/add' || msg.text === '/delete') return;

  try {
    if (state.step === 'TITLE') {
      state.title = msg.text;
      state.step = 'PRICE';
      bot.sendMessage(chatId, "Narxini kiriting (faqat raqam):");
    } else if (state.step === 'PRICE') {
      state.price = parseInt(msg.text.replace(/\D/g, '')) || 0;
      state.step = 'DESCRIPTION';
      bot.sendMessage(chatId, "Tavsifini kiriting:");
    } else if (state.step === 'DESCRIPTION') {
      state.description = msg.text;
      state.step = 'IMAGES';
      
      bot.sendMessage(chatId, "📸 Mahsulot rasmlarini birma-bir yuboring (yoki havolasini tashlang).\n\nBarcha rasmlarni yuborib bo'lgach, pastdagi tugmani bosing:", {
        reply_markup: {
          inline_keyboard: [
            [{ text: "✅ Rasmlarni kiritib bo'ldim", callback_data: 'done_photos' }]
          ]
        }
      });
    } else if (state.step === 'IMAGES') {
      let imageUrl = '';
      if (msg.photo) {
        const fileId = msg.photo[msg.photo.length - 1].file_id;
        imageUrl = await bot.getFileLink(fileId);
      } else if (msg.text && msg.text.startsWith('http')) {
        imageUrl = msg.text;
      }

      if (imageUrl) {
        state.imageUrls.push(imageUrl);
        bot.sendMessage(chatId, `✅ Rasm qo'shildi (${state.imageUrls.length} ta). Yana rasm yuborishingiz yoki tugmani bosishingiz mumkin.`);
      } else {
        bot.sendMessage(chatId, "Iltimos, rasm yoki to'g'ri rasm havolasini yuboring!");
      }
    }
  } catch (err) {
    bot.sendMessage(chatId, `Kutilmagan xatolik yuz berdi: ${err.message}`);
    delete adminState[chatId];
  }
});

bot.on('callback_query', async (query) => {
  const chatId = query.message.chat.id;
  const data = query.data;
  const state = adminState[chatId];

  // Mahsulotni o'chirish tugmasi bosilganda
  if (data.startsWith('del_')) {
    const productId = data.replace('del_', '');

    const { error } = await supabase
      .from('products')
      .delete()
      .eq('id', productId);

    if (error) {
      bot.answerCallbackQuery(query.id, { text: "Xatolik yuz berdi!" });
      return bot.sendMessage(chatId, `O'chirishda xatolik: ${error.message}`);
    }

    bot.answerCallbackQuery(query.id, { text: "Mahsulot o'chirildi!" });
    bot.editMessageText("✅ Tanlangan mahsulot Mebelix bazasidan va do'kondan muvaffaqiyatli o'chirildi.", {
      chat_id: chatId,
      message_id: query.message.message_id
    });
    return;
  }

  if (data === 'done_photos') {
    if (!state || state.imageUrls.length === 0) {
      bot.answerCallbackQuery(query.id, { text: "Kamida bitta rasm yuborishingiz kerak!" });
      return;
    }

    state.step = 'CATEGORY';
    const keyboard = CATEGORIES.map(cat => [{ text: cat, callback_data: `cat_${cat}` }]);
    
    bot.sendMessage(chatId, "Quyidagi kategoriyalardan birini tanlang:", {
      reply_markup: { inline_keyboard: keyboard }
    });
    bot.answerCallbackQuery(query.id);
  } 
  else if (data.startsWith('cat_')) {
    const category = data.replace('cat_', '');

    if (!state) {
      bot.answerCallbackQuery(query.id, { text: "Xatolik! Qaytadan /add buyrug'ini bering." });
      return;
    }

    state.category = category;

    // Supabase bazasiga saqlaymiz
    const { error } = await supabase.from('products').insert([
      {
        title: state.title,
        price: state.price,
        description: state.description,
        category: state.category,
        image_url: state.imageUrls[0],
        images: state.imageUrls
      }
    ]);

    if (error) {
      bot.sendMessage(chatId, `Xatolik yuz berdi: ${error.message}`);
    } else {
      bot.sendMessage(chatId, `✅ Mebel muvaffaqiyatli qo'shildi!\n\n📸 Rasmlar soni: ${state.imageUrls.length} ta\n🛋 Kategoriya: *${state.category}*`, { parse_mode: 'Markdown' });
    }

    delete adminState[chatId];
    bot.answerCallbackQuery(query.id);
  }
});
