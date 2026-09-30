const TelegramBot = require('node-telegram-bot-api');
const { createClient } = require('@supabase/supabase-js');
const express = require('express');

const SUPABASE_URL = 'https://avryabmbrowguthrvatf.supabase.co';
const SUPABASE_KEY = 'sb_publishable_KuReIRnnzOoTVD-vfIzeUA_9XE2AqCt'; // O'zingizning uzun anon public kalitingizni yozing
const BOT_TOKEN = '8987783785:AAH3rHQJm8NxApCENm73iQgPOpY7GFVQeTM';

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);
const bot = new TelegramBot(BOT_TOKEN, { polling: true });

// Render port talabini qondirish uchun oddiy Express server
const app = express();
const PORT = process.env.PORT || 3000;

app.get('/', (req, res) => {
  res.send('Mebelix Bot is running!');
});

app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});

const adminState = {};

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

bot.onText(/\/add/, (msg) => {
  const chatId = msg.chat.id;
  adminState[chatId] = { step: 'TITLE' };
  bot.sendMessage(chatId, "Mebel nomini kiriting:");
});

bot.on('message', async (msg) => {
  const chatId = msg.chat.id;
  const state = adminState[chatId];

  if (!state || msg.text === '/start' || msg.text === '/add') return;

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
      state.step = 'IMAGE';
      bot.sendMessage(chatId, "Rasm havolasini (linkini) yuboring yoki rasm joylang:");
    } else if (state.step === 'IMAGE') {
      let imageUrl = '';
      if (msg.photo) {
        const fileId = msg.photo[msg.photo.length - 1].file_id;
        imageUrl = await bot.getFileLink(fileId);
      } else {
        imageUrl = msg.text;
      }

      const { data, error } = await supabase.from('products').insert([
        {
          title: state.title,
          price: state.price,
          description: state.description,
          image_url: imageUrl
        }
      ]);

      if (error) {
        bot.sendMessage(chatId, `Xatolik yuz berdi: ${error.message}`);
      } else {
        bot.sendMessage(chatId, "✅ Mebel do'konga muvaffaqiyatli qo'shildi!");
      }

      delete adminState[chatId];
    }
  } catch (err) {
    bot.sendMessage(chatId, `Kutilmagan xatolik yuz berdi: ${err.message}`);
    delete adminState[chatId];
  }
});
