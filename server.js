const { Telegraf, Markup } = require('telegraf');
const express = require('express');
const path = require('path');

const bot = new Telegraf(process.env.BOT_TOKEN);
const app = express();

app.use(express.json());

// Telegram Webhook
app.use(bot.webhookCallback('/telegram-webhook'));

// Bot /start buyrug'i
bot.start((ctx) => {
    ctx.reply(
        "Assalomu alaykum! Mebelix do'koniga xush kelibsiz! Quyidagi tugmani bosing:",
        Markup.keyboard([
            [Markup.button.webApp("🛋 Do'konni ochish", "https://mebelix-webapp.onrender.com")]
        ]).resize()
    );
});

// Adminga buyurtma yuborish
async function sendOrderToAdmin(orderData) {
    const adminGroupId = process.env.ADMIN_GROUP_ID;
    let caption = "📦 YANGI BUYURTMA!\n\n";
    caption += "👤 Mijoz: " + orderData.fullName + "\n";
    caption += "📞 Tel: " + orderData.phone + "\n";
    caption += "💰 Jami: " + (orderData.total ? orderData.total.toLocaleString() : 0) + " so'm\n\n";
    caption += "🛒 Buyurtmalar:\n";
    
    if (orderData.cart && orderData.cart.length > 0) {
        orderData.cart.forEach(item => {
            caption += • ${item.name} - ${item.price.toLocaleString()} so'm\n;
        });
    }

    await bot.telegram.sendMessage(adminGroupId, caption);
}

// Buyurtma API
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

// Asosiy sahifa - index.html ni chiqarish
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log("Server " + PORT + "-portda ishga tushdi");
});
