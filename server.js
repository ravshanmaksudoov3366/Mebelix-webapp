const { Telegraf, Markup } = require('telegraf');
const express = require('express');
const path = require('path');

const bot = new Telegraf(process.env.BOT_TOKEN);
const app = express();

app.use(express.json());

// Telegram Webhook
app.use(bot.webhookCallback('/telegram-webhook'));

// ------------------- XOTIRA VA HOLATLAR -------------------
// Botga kirgan mijozlar ro'yxati (Unikal foydalanuvchilar)
const usersSet = new Set();

// Admin bilan muloqot holati (userState)
const userState = {};

// Admin huquqini tekshirish
function isAdmin(ctx) {
    const adminId = process.env.ADMIN_CHAT_ID;
    return ctx.from && String(ctx.from.id) === String(adminId);
}

// ------------------- BOT BUYRUQLARI -------------------

// Bot /start buyrug'i
bot.start((ctx) => {
    // Mijozni ro'yxatga olish
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

// Admin Paneli: /admin buyrug'i
bot.command('admin', (ctx) => {
    if (!isAdmin(ctx)) {
        return ctx.reply("❌ Sizda admin huquqlari yo'q!");
    }

    ctx.reply(
        "⚙️ Mebelix Admin Paneli\n\nKerakli bo'limni tanlang:",
        {
            parse_mode: 'Markdown',
            ...Markup.inlineKeyboard([
                [Markup.button.callback("📊 Mijozlar soni", "stat_users")],
                [Markup.button.callback("➕ Yangi mebel qo'shish", "add_product")]
            ])
        }
    );
});

// ------------------- ADMIN ACTIONS & DIALOGS -------------------

// Mijozlar statistikasi
bot.action('stat_users', (ctx) => {
    if (!isAdmin(ctx)) return;
    ctx.answerCbQuery();
    ctx.reply(👥 **Mebelix botidan foydalangan mijozlar soni:** ${usersSet.size} ta);
});

// Yangi mebel qo'shishni boshlash
bot.action('add_product', (ctx) => {
    if (!isAdmin(ctx)) return;
    ctx.answerCbQuery();

    userState[ctx.from.id] = {
        step: 'WAIT_NAME',
        photos: []
    };

    ctx.reply(1-Qadam:m:** Yangi mebel nomini kiriting (masalan: *Klassik burchakli divan*):", { parse_mode: 'Markdown' });
});

// Rasmlarni saqlash tugmasi
bot.action('save_photos', (ctx) => {
    if (!isAdmin(ctx)) return;
    ctx.answerCbQuery();

    const state = userState[ctx.from.id];
    if (!state || state.photos.length === 0) {
        return ctx.reply("⚠️ Kamida 1 ta rasm yuborishingiz kerak!");
    }

    // Mahsulot ma'lumotlari tayyor
    const newProduct = {
        name: state.name,
        description: state.description,
        price: state.price,
        photos: state.photos
    };

    delete userState[ctx.from.id]; // Holatni tozalash

    ctx.reply(
        ✅ **Yangi mebel muvaffaqiyatli saqlandi!**\n\n +
        📌 **Nomi:** ${newProduct.name}\n +
        📝 **Tavsif:** ${newProduct.description}\n +
        💵 **Narxi:** ${newProduct.price.toLocaleString()} so'm\n +
        🖼 **Rasmlar soni:** ${newProduct.photos.length} ta,
        { parse_mode: 'Markdown' }
    );
});

// Matnli xabarlarni tutib olish (Nom, Tavsif, Narx uchun)
bot.on('text', (ctx) => {
    const userId = ctx.from.id;
    const state = userState[userId];

    if (!isAdmin(ctx) || !state) return;

    if (state.step === 'WAIT_NAME') {
        state.name = ctx.message.text;
        state.step = 'WAIT_DESC';
     2-Qadam:x.reply("📝 **2-Qadam:** Mebel haqida batafsil ma'lumot (tavsif) kiritib yuboring:");
    }

    if (state.step === 'WAIT_DESC') {
        state.description = ctx.message.text;
        state.step = 'WAIT_PRICE';
     3-Qadam:x.reply("💰 **3-Qadam:** Mebel narxini kiriting (faqat raqamlarda, masalan: *4500000*):");
    }if (state.step === 'WAIT_PRICE') {
        const price = parseInt(ctx.message.text.replace(/\D/g, ''));
        if (isNaN(price) || price <= 0) {
            return ctx.reply("⚠️ Iltimos, narxni faqat raqamlarda to'g'ri kiriting!");
        }
        state.price = price;
        state.step = 'WAIT_PHOTOS';
        return ctx.reply(
            "🖼 4-Qadam: Mebel rasmlarini yuboring (1 tagacha 10 tagacha foto yuborishingiz mumkin).\n\n" +
            "Rasmlarni yuborib bo'lgach, pastdagi '✅ Saqlash' tugmasini bosing:",
            Markup.inlineKeyboard([
                [Markup.button.callback("✅ Saqlash", "save_photos")]
            ])
        );
    }
});

// Rasmlarni tutib olish (Fotosuratlar uchun)
bot.on('photo', (ctx) => {
    const userId = ctx.from.id;
    const state = userState[userId];

    if (!isAdmin(ctx)  !state  state.step !== 'WAIT_PHOTOS') return;

    if (state.photos.length >= 10) {
        return ctx.reply("⚠️ Maksimal 10 ta rasm yuklay olasiz! Endi '✅ Saqlash' tugmasini bosing.");
    }

    // Eng yuqori sifatli rasming file_id sini saqlash
    const photoArray = ctx.message.photo;
    const fileId = photoArray[photoArray.length - 1].file_id;

    state.photos.push(fileId);

    ctx.reply(
        📸 Rasm qabul qilindi! (${state.photos.length}/10)\n +
        Yana rasm yuborishingiz yoki saqlashingiz mumkin:,
        Markup.inlineKeyboard([
            [Markup.button.callback("✅ Saqlash", "save_photos")]
        ])
    );
});

// ------------------- EXISTING SERVER LOGIC -------------------

// Adminga buyurtma yuborish funksiyasi
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

// Buyurtmani qabul qilish uchun API
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

// Asosiy sahifa - index.html faylini ochish
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log("Server " + PORT + "-portda ishga tushdi");
});
