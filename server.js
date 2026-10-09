const TelegramBot = require('node-telegram-bot-api');
const fs = require('fs');

const TOKEN = '8987783785:AAH3rHQJm8NxApCENm73iQgPOpY7GFVQeTM';
const ADMIN_ID = 1027326101;
const WEBAPP_URL = 'https://ravshanmaksudoov3366.github.io/Mebelix-webapp/';

const bot = new TelegramBot(TOKEN, { polling: true });

let userSteps = {};
let userOrders = {};

// /start komandasi
bot.onText(/\/start/, (msg) => {
  const chatId = msg.chat.id;
  
  const opts = {
    reply_markup: {
      inline_keyboard: [
        [{ text: "🛍 Do'konni ochish", web_app: { url: WEBAPP_URL } }]
      ]
    }
  };

  if (chatId === ADMIN_ID) {
    opts.reply_markup.inline_keyboard.push([
      { text: "➕ Yangi mahsulot qo'shish", callback_data: "add_product" },
      { text: "🗑 Mahsulotni o'chirish", callback_data: "delete_product" }
    ]);
  }

  bot.sendMessage(chatId, "Hush kelibsiz! Mebelix do'konimizdan mebellarni tanlash uchun tugmani bosing:", opts);
});

// WebApp'dan buyurtma kelganda
bot.on('message', async (msg) => {
  const chatId = msg.chat.id;

  if (msg.web_app_data) {
    try {
      const cart = JSON.parse(msg.web_app_data.data);
      userOrders[chatId] = cart;
      userSteps[chatId] = 'WAITING_NAME';

      bot.sendMessage(chatId, "Buyurtmangiz qabul qilindi!\n\nIltimos, to'liq **ism va familiyangizni** kiriting:");
    } catch (e) {
      console.error(e);
    }
    return;
  }

  // Bosqichma-bosqich ma'lumot yig'ish
  if (userSteps[chatId] === 'WAITING_NAME') {
    userOrders[chatId].name = msg.text;
    userSteps[chatId] = 'WAITING_PHONE';
    
    bot.sendMessage(chatId, "Telefon raqamingizni yuboring:", {
      reply_markup: {
        keyboard: [[{ text: "📱 Raqamni yuborish", request_contact: true }]],
        resize_keyboard: true,
        one_time_keyboard: true
      }
    });
  } else if (userSteps[chatId] === 'WAITING_PHONE') {
    userOrders[chatId].phone = msg.contact ? msg.contact.phone_number : msg.text;
    userSteps[chatId] = 'WAITING_ADDRESS';
    
    bot.sendMessage(chatId, "Yetkazib berish **yozma manzilini** kiriting (masalan: Toshkent, Chilonzor 10-daha, 12-uy):", {
      reply_markup: { remove_keyboard: true }
    });
  } else if (userSteps[chatId] === 'WAITING_ADDRESS') {
    userOrders[chatId].address = msg.text;
    userSteps[chatId] = 'WAITING_LOCATION';

    bot.sendMessage(chatId, "Anqroq yetkazib berish uchun **GPS geolokatsiyangizni** yuboring:", {
      reply_markup: {
        keyboard: [[{ text: "📍 Geolokatsiyani yuborish", request_location: true }]],
        resize_keyboard: true,
        one_time_keyboard: true
      }
    });
  } else if (userSteps[chatId] === 'WAITING_LOCATION') {
    if (msg.location) {
      userOrders[chatId].location = msg.location;
      
      // Buyurtmani yakunlash va Adminga yuborish
      const order = userOrders[chatId];
      let jami = 0;
      let orderText = `🛒 **YANGI BUYURTMA!**\n\n`;
      orderText += `👤 **Mijoz:** ${order.name}\n`;
      orderText += `📞 **Tel:** ${order.phone}\n`;
      orderText += `🏠 **Manzil:** ${order.address}\n\n`;
      orderText += `📦 **Mahsulotlar:**\n`;

      order.forEach(item => {
        orderText += `- ${item.title} (${item.count} ta) = ${(item.price * item.count).toLocaleString()} so'm\n`;
        jami += item.price * item.count;
      });

      const prepay = jami * 0.1;
      orderText += `\n💰 **Jami:** ${jami.toLocaleString()} so'm\n`;
      orderText += `⚠️ **10% Oldindan to'lov:** ${prepay.toLocaleString()} so'm\n`;

      // Mijozga xabar
      bot.sendMessage(chatId, `Rahmat! Buyurtmangiz qabul qilindi.\n\n⚠️ **Eslatib o'tamiz:** Buyurtmani tasdiqlash uchun 10% oldindan to'lov (${prepay.toLocaleString()} so'm) qilish lozim. Tez orada siz bilan bog'lanamiz!`, {
        reply_markup: { remove_keyboard: true }
      });

      // Adminga xabar va geolokatsiya
      await bot.sendMessage(ADMIN_ID, orderText, { parse_mode: 'Markdown' });
      await bot.sendLocation(ADMIN_ID, msg.location.latitude, msg.location.longitude);

      delete userSteps[chatId];
      delete userOrders[chatId];
    }
  }
});

// Admin tugmalari (Mahsulot o'chirish / qo'shish)
bot.on('callback_query', (query) => {
  const chatId = query.message.chat.id;

  if (chatId !== ADMIN_ID) return;

  if (query.data === 'delete_product') {
    let products = JSON.parse(fs.readFileSync('products.json'));
    let buttons = products.map(p => [{ text: `❌ ${p.title}`, callback_data: `del_${p.id}` }]);
    
    bot.sendMessage(ADMIN_ID, "O'chirmoqchi bo'lgan mahsulotni tanlang:", {
      reply_markup: { inline_keyboard: buttons }
    });
  } else if (query.data.startsWith('del_')) {
    const id = parseInt(query.data.split('_')[1]);
    let products = JSON.parse(fs.readFileSync('products.json'));
    products = products.filter(p => p.id !== id);
    fs.writeFileSync('products.json', JSON.stringify(products, null, 2));

    bot.sendMessage(ADMIN_ID, "✅ Mahsulot muvaffaqiyatli o'chirildi!");
  }
});
