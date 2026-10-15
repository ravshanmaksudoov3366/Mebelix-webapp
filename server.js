const { Telegraf, Markup } = require('telegraf');
const express = require('express');

const bot = new Telegraf(process.env.BOT_TOKEN);
const app = express();

app.use(express.json());
app.use(bot.webhookCallback('/telegram-webhook'));

// Bot /start
bot.start((ctx) => {
    ctx.reply(
        "Assalomu alaykum! Mebelix mebel buyurtma berish botiga xush kelibsiz. Quyidagi tugmani bosing:",
        Markup.keyboard([
            [Markup.button.webApp("🛋 Mebellarni ko'rish", "https://mebelix-webapp.onrender.com")]
        ]).resize()
    );
});

// Adminga buyurtma yuborish
async function sendOrderToAdmin(orderData, productImageUrls, adminGroupId) {
    let caption = "Yangi Buyurtma!\n";
    caption += Mijoz: ${orderData.fullName}\n;
    caption += Tel: ${orderData.phone}\n;
    
    if (productImageUrls && productImageUrls.length > 0) {
        await bot.telegram.sendPhoto(adminGroupId, productImageUrls[0], { caption: caption });
    } else {
        await bot.telegram.sendMessage(adminGroupId, caption);
    }
    
    await bot.telegram.sendLocation(adminGroupId, orderData.latitude, orderData.longitude);
}

// API
app.post('/api/products', async (req, res) => {
    res.status(200).send({ message: 'Mahsulot muvaffaqiyatli qo\'shildi' });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(Server ${PORT}-portda ishga tushdi);
});
