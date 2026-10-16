const { Telegraf, Markup } = require('telegraf');
const express = require('express');
const path = require('path');
const { createClient } = require('@supabase/supabase-js');

// Token mavjudligini tekshirish
if (!process.env.BOT_TOKEN) {
    console.error("DIQQAT XATOLIK: BOT_TOKEN topilmadi!");
}

const bot = new Telegraf(process.env.BOT_TOKEN);
const app = express();

app.use(express.json());

// Telegram Webhook
app.use(bot.webhookCallback('/telegram-webhook'));

// ------------------- SUPABASE ULANISHI -------------------
const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_KEY;
const supabase = createClient(supabaseUrl, supabaseKey);

// ------------------- XOTIRA VA HOLATLAR -------------------
// Botga kirgan foydalanuvchilar ro'yxati
const usersSet = new Set();

// Admin buyurtma/mahsulot qo'shish holatlari
const userState = {};

// Admin huquqini tekshirish
function isAdmin(ctx) {
    const adminId = process.env.ADMIN_CHAT_ID;
    return ctx.from && String(ctx.from.id) === String(adminId);
}

// ------------------- BOT BUYRUQLARI -------------------

// /start buyrug'i
bot.start((ctx) => {
    if (ctx.from && ctx.from.id) {
        usersSet.add(ctx.from.id);
    }

    ctx.reply(
        "Assalomu alaykum! Mebelix do'koniga xush kelibsiz! Quyidagi tugmani bosing:",
        Markup.keyboard([
            [Markup.button.webApp("🛋 Do'konni ochish", "https://mebelix-webapp.onrender.com")]
        ]).resize()
    );
});

// /admin buyrug'i
bot.command('admin', (ctx) => {
    if (!isAdmin(ctx)) {
        return ctx.reply("❌ Sizda admin huquqlari yo'q!");
    }

    ctx.reply(
        "⚙️ *Mebelix Admin Paneli*\n\nKerakli bo'limni tanlang:",
        {
            parse_mode: 'Markdown',
            ...Markup.inlineKeyboard([
                [Markup.button.callback("📊 Mijozlar soni", "stat_users")],
                [Markup.button.callback("➕ Yangi mebel qo'shish", "add_product")]
            ])
        }
    );
});

// ------------------- ADMIN AMALLARI -------------------

// Mijozlar statistikasi
bot.action('stat_users', (ctx) => {
    if (!isAdmin(ctx)) return;
    ctx.answerCbQuery();
    ctx.reply("👥 *Mebelix botidan foydalangan mijozlar soni:* " + usersSet.size + " ta", { parse_mode: 'Markdown' });
});

// Yangi mebel qo'shishni boshlash
bot.action('add_product', (ctx) => {
    if (!isAdmin(ctx)) return;
    ctx.answerCbQuery();

    userState[ctx.from.id] = {
        step: 'WAIT_NAME',
        photos: []
    };

    ctx.reply("📝 *1-Qadam:* Yangi mebel nomini kiriting (masalan: *Klassik burchakli divan*):", { parse_mode: 'Markdown' });
});

// Rasmlarni saqlash (Supabase bazasiga yozish)
bot.action('save_photos', async (ctx) => {
    if (!isAdmin(ctx)) return;
    ctx.answerCbQuery();

    const state = userState[ctx.from.id];
    if (!state || state.photos.length === 0) {
        return ctx.reply("⚠️ Kamida 1 ta rasm yuborishingiz kerak!");
    }

    try {
        const { data, error } = await supabase
            .from('products')
            .insert([
                {
                    title: state.name,
                    description: state.description,
                    price: state.price,
                    photos: state.photos
                }
            ])
            .select();

        if (error) throw error;

        const savedProduct = data[0];
        delete userState[ctx.from.id];

        ctx.reply(
            "✅ *Yangi mebel muvaffaqiyatli saqlandi va do'konga qo'shildi!*\n\n" +
            "📌 *Nomi:* " + savedProduct.title + "\n" +
            "📝 *Tavsif:* " + savedProduct.description + "\n" +
            "💵 *Narxi:* " + Number(savedProduct.price).toLocaleString() + " so'm\n" +
            "🖼 *Rasmlar soni:* " + (savedProduct.photos ? savedProduct.photos.length : 0) + " ta",
            { parse_mode: 'Markdown' }
        );
    } catch (err) {
        console.error("Supabase'ga saqlashda xato:", err);
        ctx.reply("❌ Bazaga saqlashda xatolik yuz berdi!");
    }
});

// Matnli xabarlarni qabul qilish (Nomi -> Tavsifi -> Narxi)
bot.on('text', (ctx) => {
    const userId = ctx.from.id;
    const state = userState[userId];

    if (!isAdmin(ctx) || !state) return;

    if (state.step === 'WAIT_NAME') {
        state.name = ctx.message.text;
        state.step = 'WAIT_DESC';
        return ctx.reply("📝 *2-Qadam:* Mebel haqida batafsil ma'lumot (tavsif) kiritib yuboring:");
    }

    if (state.step === 'WAIT_DESC') {
        state.description = ctx.message.text;
        state.step = 'WAIT_PRICE';
        return ctx.reply("💰 *3-Qadam:* Mebel narxini kiriting (faqat raqamlarda, masalan: *4500000*):");
    } if (state.step === 'WAIT_PRICE') {
        const price = parseInt(ctx.message.text.replace(/\D/g, ''));
        if (isNaN(price) || price <= 0) {
            return ctx.reply("⚠️ Iltimos, narxni faqat raqamlarda to'g'ri kiriting!");
        }
        state.price = price;
        state.step = 'WAIT_PHOTOS';
        return ctx.reply(
            "🖼 *4-Qadam:* Mebel rasmlarini yuboring (1 tadan 10 tagacha foto yuborishingiz mumkin).\n\n" +
            "Rasmlarni yuborib bo'lgach, pastdagi *'✅ Saqlash'* tugmasini bosing:",
            Markup.inlineKeyboard([
                [Markup.button.callback("✅ Saqlash", "save_photos")]
            ])
        );
    }
});

// Rasmlarni qabul qilish (10 tagacha)
bot.on('photo', (ctx) => {
    const userId = ctx.from.id;
    const state = userState[userId];

    if (!isAdmin(ctx) || !state || state.step !== 'WAIT_PHOTOS') return;

    if (state.photos.length >= 10) {
        return ctx.reply("⚠️ Maksimal 10 ta rasm yuklay olasiz! Endi '✅ Saqlash' tugmasini bosing.");
    }

    const photoArray = ctx.message.photo;
    const fileId = photoArray[photoArray.length - 1].file_id;

    state.photos.push(fileId);

    ctx.reply(
        "📸 Rasm qabul qilindi! (" + state.photos.length + "/10)\n" +
        "Yana rasm yuborishingiz yoki saqlashingiz mumkin:",
        Markup.inlineKeyboard([
            [Markup.button.callback("✅ Saqlash", "save_photos")]
        ])
    );
});

// ------------------- SERVER VA BUYURTMA QISMI -------------------

async function sendOrderToAdmin(orderData) {
    const adminGroupId = process.env.ADMIN_GROUP_ID;
    let caption = "📦 YANGI BUYURTMA!\n\n";
    caption += "👤 Mijoz: " + orderData.fullName + "\n";
    caption += "📞 Tel: " + orderData.phone + "\n";
    caption += "💰 Jami: " + (orderData.total ? orderData.total.toLocaleString() : 0) + " so'm\n\n";
    caption += "🛒 Buyurtmalar:\n";

    if (orderData.cart && orderData.cart.length > 0) {
        orderData.cart.forEach(item => {
            caption += "• " + item.name + " - " + item.price.toLocaleString() + " so'm\n";
        });
    }

    if (adminGroupId) {
        await bot.telegram.sendMessage(adminGroupId, caption);
    }
}

// Web App (do'kon) mahsulotlarni Supabase bazasidan olishi uchun API
app.get('/api/products', async (req, res) => {
    try {
        const { data, error } = await supabase
            .from('products')
            .select('*')
            .order('id', { ascending: false });

        if (error) throw error;
        res.json(data);
    } catch (err) {
        console.error("Mahsulotlarni olishda xatolik:", err);
        res.status(500).json({ error: "Server xatoligi" });
    }
});

app.post('/api/order', async (req, res) => {
    try {
        const { orderData } = req.body;
        await sendOrderToAdmin(orderData);
        res.status(200).send({ success: true, message: "Buyurtma qabul qilindi" });
    } catch (error) {
        console.error(error);
        res.status(500).send({ success: false, error: error.message });
    }
});

app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// Xatoliklarni ushlab qolish (server o'chib qolmasligi uchun)
bot.catch((err, ctx) => {
    console.error("Xatolik yuz berdi:", err);
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log("Server " + PORT + "-portda ishga tushdi");
});
