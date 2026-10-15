const { Telegraf, Markup } = require('telegraf');
const express = require('express');
const path = require('path');

const bot = new Telegraf(process.env.BOT_TOKEN);
const app = express();

app.use(express.json());

// React fayllarini ulash (dist yoki build papkasi)
app.use(express.static(path.join(__dirname, 'client/dist')));

app.use(bot.webhookCallback('/telegram-webhook'));

// Bot /start buyrug'i
bot.start((ctx) => {
    ctx.reply(
        "Assalomu alaykum! Mebelix mebel buyurtma berish botiga xush kelibsiz. Quyidagi tugmani bosing:",
        Markup.keyboard([
            [Markup.button.webApp("🛋 Mebellarni ko'rish", "https://inglizcha-yoki-render-domen.onrender.com")]
        ]).resize()
    );
});

// Adminga buyurtma yuborish funksiyasi
async function sendOrderToAdmin(orderData, productImageUrls, adminGroupId) {
    let caption = "Yangi Buyurtma!\n";
    caption += "Mijoz: " + orderData.fullName + "\n";
    caption += "Tel: " + orderData.phone + "\n";
    
    if (productImageUrls && productImageUrls.length > 0) {
        await bot.telegram.sendPhoto(adminGroupId, productImageUrls[0], { caption: caption });
    } else {
        await bot.telegram.sendMessage(adminGroupId, caption);
    }
    
    await bot.telegram.sendLocation(adminGroupId, orderData.latitude, orderData.longitude);
}

// Barcha so'rovlarni React'ga yo'naltirish
app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, 'client/dist/index.html'));
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log("Server " + PORT + "-portda ishga tushdi");
});
