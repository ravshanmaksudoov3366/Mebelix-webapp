const { Telegraf, Markup } = require('telegraf');
const express = require('express');

const bot = new Telegraf(process.env.BOT_TOKEN);
const app = express();

app.use(express.json());
app.use(bot.webhookCallback('/telegram-webhook'));

// Botga /start buyrug'i kelganda WebApp tugmasini chiqarish
bot.start((ctx) => {
    ctx.reply(
        "Assalomu alaykum! Mebelix mebel buyurtma berish botiga xush kelibsiz. Quyidagi tugmani bosing:",
        Markup.keyboard([
            [Markup.button.webApp("🛋 Mebellarni ko'rish", "https://mebelix-webapp.onrender.com")] // Bu yerga o'zingizning WebApp linkeingizni yozasiz
        ]).resize()
    );
});

// Adminga buyurtma va mahsulot rasmini yuborish funksiyasi
async function sendOrderToAdmin(orderData, productImageUrls, adminGroupId) {
    let caption = "Yangi Buyurtma!\n";
    caption += 'Mijoz: ${orderData.fullName}\n';
    caption += Tel: ${orderData.phone}\n;
    
    if (productImageUrls && productImageUrls.length > 0) {
        await bot.telegram.sendPhoto(adminGroupId, productImageUrls[0], { caption: caption });
    } else {
        await bot.telegram.sendMessage(adminGroupId, caption);
    }
    
    await bot.telegram.sendLocation(adminGroupId, orderData.latitude, orderData.longitude);
}

// Admin panel uchun API'lar
app.post('/api/products', async (req, res) => {
    res.status(200).send({ message: 'Mahsulot muvaffaqiyatli qo\'shildi' });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(Server ${PORT}-portda ishga tushdi);
});
