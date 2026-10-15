const { Telegraf } = require('telegraf');
const express = require('express');

const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_CHAT_ID = process.env.ADMIN_CHAT_ID;
const WEBAPP_URL = "https://ravshanmaksudoov3366.github.io/Mebelix-webapp/";

if (!BOT_TOKEN) {
  console.error("BOT_TOKEN ko'rsatilmadi!");
  process.exit(1);
}

const bot = new Telegraf(BOT_TOKEN);

// /start buyrug'i uchun
bot.start((ctx) => {
  ctx.reply("🛋 Mebelix do'koniga xush kelibsiz!\n\nQuyidagi tugmani bosib tayyor mebellar katalogini ko'rishingiz mumkin:", {
    reply_markup: {
      keyboard: [
        [{ text: "🛋 Do'konni ochish", web_app: { url: WEBAPP_URL } }]
      ],
      resize_keyboard: true
    }
  });
});

// WebApp'dan buyurtma kelganda (tg.sendData orqali)
bot.on('web_app_data', async (ctx) => {
  try {
    const rawData = ctx.web_app_data && ctx.web_app_data.data;
    if (!rawData) return;

    const data = JSON.parse(rawData);
    const user = ctx.from;

    let itemsText = "";
    if (data.items && Array.isArray(data.items)) {
      data.items.forEach((item, index) => {
        itemsText += `${index + 1}. **${item.title}** — ${item.count} ta x ${item.price} $ = ${item.subtotal} $\n`;
      });
    }

    const adminMessage = `
🛒 **YANGI BUYURTMA!**

👤 **Mijoz:** ${user.first_name || ''} ${user.last_name || ''} (@${user.username || 'username_yoq'})
🆔 **ID:** \`${user.id}\`

📦 **Buyurtma qilingan mebellar:**
${itemsText}
💰 **Jami summa:** ${data.totalPrice} $
`;

    // 1. Mijozga tasdiqlash xabari
    await ctx.reply(`✅ Buyurtmangiz qabul qilindi!\n\nJami summa: **${data.totalPrice} $**\nTez orada menejerimiz siz bilan bog'lanadi!`, { parse_mode: 'Markdown' });

    // 2. Adminga xabar yuborish
    if (ADMIN_CHAT_ID) {
      await ctx.telegram.sendMessage(ADMIN_CHAT_ID, adminMessage, { parse_mode: 'Markdown' });
    }

  } catch (err) {
    console.error("Buyurtmani qayta ishlashda xatolik:", err);
  }
});

bot.launch().then(() => console.log("Mebelix Boti muvaffaqiyatli ishga tushdi!"));

// Express server (Render porti uchun)
const app = express();
const PORT = process.env.PORT || 10000;
app.get('/', (req, res) => res.send('Mebelix Bot Server is Active!'));
app.listen(PORT, () => console.log(`Server listening on port ${PORT}`));
