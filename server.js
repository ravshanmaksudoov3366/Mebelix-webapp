Const express = require('express');
const cors = require('cors');
const TelegramBot = require('node-telegram-bot-api');
const { createClient } = require('@supabase/supabase-js');

const app = express();
app.use(cors());
app.use(express.json({ limit: '50mb' }));
app.use(express.static('public'));

// Konfiguratsiya ma'lumotlari
const BOT_TOKEN = '8987783785:AAHZSdAP7ex4dQO7jMBDtmMIU2oNfgCrJ2I';
const ADMIN_ID = 1027326101;
const GROUP_ID = -1004481485199;
const ADMIN_PHONE = '993333366';
const ADMIN_NIK = '@MRS3366';

// Supabase ulanishi (Siz bergan URL va API key)
const SUPABASE_URL = 'https://avryabmbrowguthrvatf.supabase.co';
const SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF2cnlhYm1icm93Z3V0aHJ2YXRmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTA1MTY3NjUsImV4cCI6MjEwNjA5Mjc2NX0.s99c6MuuJzYIQ5LMxvlUBirq8_YX3x7HMsmU8ymGyP8'; // Baza uchun anon/public kalit
const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

const bot = new TelegramBot(BOT_TOKEN, { polling: true });

// Matnlar lug'ati (O'zbek va Rus)
const i18n = {
    uz: {
        welcome: `Xush kelibsiz! Mebelix onlayn do'koniga hush kelibsiz.\n\n📞 Admin tel: +${ADMIN_PHONE}\n💬 Telegram: ${ADMIN_NIK}`,
        select_lang: "Iltimos, xizmat ko'rsatish tilini tanlang / Пожалуйста, выберите язык:",
        shop_btn: "🛍 Mebelix Do'koni",
        contact_btn: "📞 Admin bilan bog'lanish",
        approved_msg: "✅ Xaridingiz va to'lovingiz qabul qilindi! Mahsulotni ko'rsatilgan muddatda yetkazib beramiz."
    },
    ru: {
        welcome: `Добро пожаловать в онлайн-магазин Mebelix!\n\n📞 Тел. админа: +${ADMIN_PHONE}\n💬 Telegram: ${ADMIN_NIK}`,
        select_lang: "Пожалуйста, выберите язык обслуживания:",
        shop_btn: "🛍 Магазин Mebelix",
        contact_btn: "📞 Связаться с админом",
        approved_msg: "✅ Ваш заказ и оплата приняты! Мы доставим товар в указанный срок."
    }
};

// BOT LOGIKASI
bot.onText(/\/start/, async (msg) => {
    const chatId = msg.chat.id;
    const langKeyboard = {
        reply_markup: {
            inline_keyboard: [
                [{ text: "🇺🇿 O'zbekcha", callback_data: "lang_uz" }],
                [{ text: "🇷🇺 Русский", callback_data: "lang_ru" }]
            ]
        }
    };
    bot.sendMessage(chatId, i18n.uz.select_lang, langKeyboard);
});

// Admin uchun /admin buyrug'i
bot.onText(/\/admin/, (msg) => {
    const chatId = msg.chat.id;
    if (msg.from.id === ADMIN_ID) {
        const adminKeyboard = {
            reply_markup: {
                inline_keyboard: [
                    [{ text: "🛠 Admin Panelni Ochish", web_app: { url: `https://${process.env.RENDER_EXTERNAL_HOSTNAME || 'localhost:3000'}/admin.html` } }]
                ]
            }
        };
        bot.sendMessage(chatId, "Assalomu alaykum, Admin! Quyidagi tugma orqali panelga kiring:", adminKeyboard);
    } else {
        bot.sendMessage(chatId, "Kechirasiz, bu buyruq faqat admin uchun.");
    }
});

bot.on('callback_query', async (query) => {
    const chatId = query.message.chat.id;
    const data = query.data;

    if (data.startsWith('lang_')) {
        const lang = data.split('_')[1];
        await supabase.from('users').upsert({
            telegram_id: query.from.id,
            first_name: query.from.first_name || '',
            last_name: query.from.last_name || '',
            username: query.from.username || '',
            language: lang
        });

        const txt = i18n[lang];
        const mainKeyboard = {
            reply_markup: {
                keyboard: [
                    [{ text: txt.shop_btn, web_app: { url: `https://${process.env.RENDER_EXTERNAL_HOSTNAME || 'localhost:3000'}` } }],
                    [{ text: txt.contact_btn }]
                ],
                resize_keyboard: true
            }
        };
        bot.sendMessage(chatId, txt.welcome, mainKeyboard);
    }

    // Admin to'lovni tasdiqlashi
    if (data.startsWith('approve_order_')) {
        const orderId = data.split('_')[2];
        const { data: order } = await supabase.from('orders').select('*').eq('id', orderId).single();
        
        if (order) {
            await supabase.from('orders').update({ status: 'approved' }).eq('id', orderId);
            const { data: user } = await supabase.from('users').select('language').eq('telegram_id', order.user_id).single();
            const lang = user ? user.language : 'uz';

            bot.sendMessage(order.user_id, i18n[lang].approved_msg);
            bot.answerCallbackQuery(query.id, { text: "To'lov tasdiqlandi!" });
            bot.editMessageReplyMarkup({ inline_keyboard: [] }, {
                chat_id: query.message.chat.id,
                message_id: query.message.message_id
            });
            bot.sendMessage(GROUP_ID, `✅ Buyurtma #${orderId} to'lovi tasdiqlandi!`);
        }
    }
});

bot.on('message', async (msg) => {
    if (msg.text && (msg.text.includes("Admin bilan bog'lanish") || msg.text.includes("Связаться с админом"))) {
        bot.sendMessage(msg.chat.id, `📞 Admin tel: +${ADMIN_PHONE}\n💬 Telegram: ${ADMIN_NIK}`);
    }
});

// API ROUTE'LAR (WEBAPP UCHUN)

// 1. Mahsulotlar ro'yxatini olish
app.get('/api/products', async (req, res) => {
    const { data, error } = await supabase.from('products').select('*').order('id', { ascending: false });
    if (error) return res.status(500).json({ error: error.message });
    res.json(data);
});

// 2. Yangi mahsulot qo'shish (Admin)
app.post('/api/products', async (req, res) => {
    const { name_uz, name_ru, categories, price, dimensions, delivery_days, description_uz, description_ru, images } = req.body;
    const { data, error } = await supabase.from('products').insert([{
        name_uz, name_ru, categories, price, dimensions, delivery_days, description_uz, description_ru, images
    }]).select();

    if (error) return res.status(500).json({ error: error.message });
    res.json({ success: true, product: data[0] });
});

// 3. Mahsulotni o'chirish (Admin)
app.delete('/api/products/:id', async (req, res) => {
    const { id } = req.params;
    const { error } = await supabase.from('products').delete().eq('id', id);
    if (error) return res.status(500).json({ error: error.message });
    res.json({ success: true });
});

// 4. Foydalanuvchilar ro'yxati (Admin)
app.get('/api/users', async (req, res) => {
    const { data, error } = await supabase.from('users').select('*').order('created_at', { ascending: false });
    if (error) return res.status(500).json({ error: error.message });
    res.json(data);
});

// 5. Buyurtma berish va telegram guruhga chek bilan yuborish
app.post('/api/orders', async (req, res) => {
    try {
        const { user_id, full_name, phone_number, address, latitude, longitude, notes, cart_items, total_price, advance_price, receipt_image_base64 } = req.body;

        // Buyurtmani bazaga saqlash
        const { data: order, error } = await supabase.from('orders').insert([{
            user_id, full_name, phone_number, address, latitude, longitude, notes, cart_items, total_price, advance_price, status: 'pending_approval'
        }]).select().single();

        if (error) throw error;

        // Chek rasmini Telegram guruhiga yuborish
        const itemsList = cart_items.map(item => `• ${item.name} x ${item.qty} = ${item.price * item.qty} so'm`).join('\n');
        const caption = `📦 <b>Yangi Buyurtma #${order.id}</b>\n\n` +
            `👤 <b>Mijoz:</b> ${full_name}\n` +
            `📞 <b>Tel:</b> ${phone_number}\n` +
            `🏠 <b>Manzil:</b> ${address}\n` +
            `📝 <b>Izoh:</b> ${notes || 'Yo\'q'}\n\n` +
            `🛍 <b>Mahsulotlar:</b>\n${itemsList}\n\n` +
            `💰 <b>Umumiy summa:</b> ${total_price} so'm\n` +
            `💳 <b>10% Avans:</b> ${advance_price} so'm\n` +
            `📍 <b>Geolokatsiya:</b> https://maps.google.com/?q=${latitude},${longitude}`;

        const inline_keyboard = {
            inline_keyboard: [
                [{ text: "✅ To'lovni tasdiqlash", callback_data: `approve_order_${order.id}` }]
            ]
        };

        if (receipt_image_base64) {
            const buffer = Buffer.from(receipt_image_base64.split(',')[1], 'base64');
            await bot.sendPhoto(GROUP_ID, buffer, { caption, parse_mode: 'HTML', reply_markup: inline_keyboard });
        } else {
            await bot.sendMessage(GROUP_ID, caption, { parse_mode: 'HTML', reply_markup: inline_keyboard });
        }

        res.json({ success: true, order_id: order.id });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Render Keep-Alive (Uxlab qolmaslik uchun avto-ping)
setInterval(() => {
    const hostname = process.env.RENDER_EXTERNAL_HOSTNAME;
    if (hostname) {
        require('https').get(`https://${hostname}`);
    }
}, 10 * 60 * 1000); // Har 10 daqiqada bir marta

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
});
