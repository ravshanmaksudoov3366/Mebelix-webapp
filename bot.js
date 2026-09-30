const TelegramBot = require('node-telegram-bot-api');
const { createClient } = require('@supabase/supabase-js');
const express = require('express');

const token = '8987783785:AAH3rHQJm8NxApCENm73iQgPOpY7GFVQeTM';
// Polling o'chirildi, Webhook ishlatiladi
const bot = new TelegramBot(token);

const SUPABASE_URL = 'https://avryabmbrowguthrvatf.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable_KuReIRnnzOoTVD-vfIzeUA_9XE2AqCt';
const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

const ADMIN_ID = 1027326101;
const userStates = {};

const app = express();
app.use(express.json());
const PORT = process.env.PORT || 3000;

// Render URL orqali Webhook'ni avtomatik sozlash
const RENDER_URL = process.env.RENDER_EXTERNAL_URL;
if (RENDER_URL) {
    bot.setWebHook(`${RENDER_URL}/bot${token}`);
    console.log(`Webhook ulandi: ${RENDER_URL}/bot${token}`);
}

app.get('/', (req, res) => {
    res.send('Mebelix Bot ishlayapti!');
});

// Telegram'dan keladigan xabarlarni qabul qilish nuqtasi
app.post(`/bot${token}`, (req, res) => {
    bot.processUpdate(req.body);
    res.sendStatus(200);
});

app.listen(PORT, () => {
    console.log(`Server ${PORT}-portda ishga tushdi.`);
});

const categories = [
    "Shkaflar", "Oyoq kiyim javoni", "Kitoblar javoni", "Krovatlar",
    "Yotoqxona to'plami", "Yumshoq mebellar", "Tumbalar",
    "Mexmonxona uchun mebellar", "Oshxona uchun mebellar",
    "Bolalar uchun mebellar", "Stol va stullar", "Ofis uchun mebellar"
];

// /start buyrug'i (Reply Keyboard - pastdagi tugma, sendData ishlashi uchun shart)
bot.onText(/\/start/, (msg) => {
    const chatId = msg.chat.id;
    
    let keyboard = {
        keyboard: [
            [{ text: "Mebelix Do'koni 🛒", web_app: { url: "https://ravshanmaksudoov3366.github.io/Mebelix-webapp/" } }]
        ],
        resize_keyboard: true
    };

    if (chatId === ADMIN_ID) {
        keyboard.keyboard.push([{ text: "➕ Mebel qo'shish" }]);
    }

    bot.sendMessage(chatId, "Assalomu alaykum! Mebelix botiga xush kelibsiz. Quyidagi tugmani bosing:", {
        reply_markup: keyboard
    });
});

// Admin uchun "➕ Mebel qo'shish" matnli tugmasi
bot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    const userId = msg.from.id;
    const text = msg.text;

    if (userId !== ADMIN_ID || !text) return;

    if (text === "➕ Mebel qo'shish") {
        userStates[userId] = { step: 'waiting_for_name', images: [] };
        return bot.sendMessage(chatId, "Mebel nomini kiriting:");
    }

    if (text.startsWith('/')) return;

    const state = userStates[userId];
    if (!state) return;

    if (state.step === 'waiting_for_name') {
        state.title = text;
        state.step = 'waiting_for_price';
        bot.sendMessage(chatId, "Narxini kiriting (faqat raqam):");
    } else if (state.step === 'waiting_for_price') {
        const price = parseFloat(text);
        if (isNaN(price)) {
            return bot.sendMessage(chatId, "Iltimos, narxni faqat raqamlarda kiriting!");
        }
        state.price = price;
        state.step = 'waiting_for_description';
        bot.sendMessage(chatId, "Mebel haqida qisqacha ma'lumot (tavsif) kiriting:");
    } else if (state.step === 'waiting_for_description') {
        state.description = text;
        state.step = 'waiting_for_images';

        const keyboard = categories.map(cat => [{ text: cat, callback_data: `cat_${cat}` }]);
        bot.sendMessage(chatId, "Kategoriyani tanlang:", {
            reply_markup: { inline_keyboard: keyboard }
        });
    }
});

// Callback tugmalar (Kategoriyalar va rasmlarni yakunlash)
bot.on('callback_query', async (query) => {
    const chatId = query.message.chat.id;
    const data = query.data;
    const userId = query.from.id;

    if (data.startsWith('cat_')) {
        if (userId !== ADMIN_ID) return;
        const category = data.replace('cat_', '');
        const state = userStates[userId];
        if (!state) return;

        state.category = category;
        state.step = 'collecting_photos';

        bot.answerCallbackQuery(query.id);
        bot.sendMessage(chatId, `Kategoriya tanlandi: ${category}\n\nEndi ushbu mebel uchun **1 tadan 5 tagacha rasm** yuboring. Rasmlarni yuborib bo'lib, pastdagi tugmani bosing.`, {
            parse_mode: 'Markdown',
            reply_markup: {
                inline_keyboard: [[{ text: "✅ Rasmlarni tugatish", callback_data: "finish_photos" }]]
            }
        });
    } else if (data === 'finish_photos') {
        if (userId !== ADMIN_ID) return;
        const state = userStates[userId];
        if (!state || state.images.length === 0) {
            return bot.answerCallbackQuery(query.id, { text: "Kamida 1 ta rasm yuborishingiz kerak!" });
        }

        bot.answerCallbackQuery(query.id);

        const { error } = await supabase.from('products').insert([
            {
                title: state.title,
                price: state.price,
                description: state.description,
                category: state.category,
                images: state.images,
                image_url: state.images[0]
            }
        ]);

        if (error) {
            console.error(error);
            bot.sendMessage(chatId, "❌ Bazaga saqlashda xatolik yuz berdi!");
        } else {
            bot.sendMessage(chatId, `✅ Mebel muvaffaqiyatli qo'shildi!\n\n📷 Rasmlar soni: ${state.images.length} ta\n📁 Kategoriya: ${state.category}`);
        }

        delete userStates[userId];
    }
});

// Rasmlarni qabul qilish
bot.on('photo', async (msg) => {
    const chatId = msg.chat.id;
    const userId = msg.from.id;
    if (userId !== ADMIN_ID) return;

    const state = userStates[userId];
    if (!state || state.step !== 'collecting_photos') return;

    const photo = msg.photo;
    const fileId = photo[photo.length - 1].file_id;

    const fileLink = await bot.getFileLink(fileId);
    state.images.push(fileLink);

    bot.sendMessage(chatId, `Rasm qabul qilindi! Jami rasmlar: ${state.images.length} ta. Yana rasm yuborishingiz yoki tugmani bosishingiz mumkin.`, {
        reply_markup: {
            inline_keyboard: [[{ text: "✅ Rasmlarni tugatish", callback_data: "finish_photos" }]]
        }
    });
});

// WebApp orqali kelgan buyurtmalarni qabul qilish (tg.sendData)
bot.on('web_app_data', (msg) => {
    const chatId = msg.chat.id;
    try {
        const data = JSON.parse(msg.web_app_data.data);
        
        bot.sendMessage(chatId, "✅ Buyurtmangiz qabul qilindi! Tez orada operatorlarimiz siz bilan bog'lanishadi.");

        let adminMessage = `🎉 <b>Yangi buyurtma tushdi!</b>\n\n` +
                           `🛋 <b>Mebel:</b> ${data.product}\n` +
                           `💰 <b>Narxi:</b> ${Number(data.price).toLocaleString()} so'm\n\n` +
                           `👤 <b>Mijoz:</b> ${data.clientName}\n` +
                           `📞 <b>Telefon:</b> ${data.clientPhone}\n` +
                           `📍 <b>Manzil:</b> ${data.clientAddress}`;

        if (data.geoLink && data.geoLink.trim() !== '') {
            adminMessage += `\n\n🗺 <b>Lokatsiya:</b> <a href="${data.geoLink}">Xaritada ko'rish</a>`;
        }

        bot.sendMessage(ADMIN_ID, adminMessage, { parse_mode: 'HTML', disable_web_page_preview: true });

    } catch (e) {
        bot.sendMessage(chatId, "Buyurtmangiz qabul qilindi.");
    }
});
