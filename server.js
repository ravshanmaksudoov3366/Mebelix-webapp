const { Telegraf, Markup } = require('telegraf');
const express = require('express');
const path = require('path');

const bot = new Telegraf(process.env.BOT_TOKEN);
const app = express();

app.use(express.json());

// 1. WebApp frontend statik fayllarini ulash
app.use(express.static(path.join(__dirname, 'dist')));
app.use(express.static(path.join(__dirname, 'build')));
app.use(express.static(__dirname));

// 2. Telegram Webhook ulanishi
app.use(bot.webhookCallback('/telegram-webhook'));

// 3. /start buyrug'i
bot.start((ctx) => {
    ctx.reply(
        "Assalomu alaykum! Mebelix do'koniga xush kelibsiz! Quyidagi tugmani bosib tayyor mebellar katalogini ko'rishingiz mumkin:",
        Markup.keyboard([
            [Markup.button.webApp("🛋 Mebellarni ko'rish", "https://mebelix-webapp.onrender.com")]
        ]).resize()
    );
});

// 4. Adminga buyurtma yuborish mantiqi
async function sendOrderToAdmin(orderData, productImageUrls, adminGroupId) {
    let caption = "YANGI BUYURTMA!\n";
    caption += "Mijoz: " + orderData.fullName + "\n";
    caption += "Tel: " + orderData.phone + "\n";
    
    if (productImageUrls && productImageUrls.length > 0) {
        await bot.telegram.sendPhoto(adminGroupId, productImageUrls[0], { caption: caption });
    } else {
        await bot.telegram.sendMessage(adminGroupId, caption);
    }
    
    if (orderData.latitude && orderData.longitude) {
        await bot.telegram.sendLocation(adminGroupId, orderData.latitude, orderData.longitude);
    }
}

// 5. API marshrutlari
app.post('/api/order', async (req, res) => {
    try {
        const { orderData, productImageUrls } = req.body;
        const adminGroupId = process.env.ADMIN_GROUP_ID;
        await sendOrderToAdmin(orderData, productImageUrls, adminGroupId);
        res.status(200).send({ success: true, message: "Buyurtma qabul qilindi" });
    } catch (error) {
        console.error(error);
        res.status(500).send({ success: false, error: error.message });
    }
});

// 6. Barcha sahifalarni React index.html ga yo'naltirish
app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'), (err) => {
        if (err) {
            res.send("Mebelix Bot Server muvaffaqiyatli ishlamoqda!");
        }
    });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log("Server " + PORT + "-portda ishga tushdi");
});
