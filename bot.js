const { Telegraf, Markup } = require('telegraf');
const { createClient } = require('@supabase/supabase-js');

// Bot va Supabase sozlamalari
const bot = new Telegraf('SIZNING_BOT_TOKENINGIZ'); // O'z bot tokeningizni yozing

const SUPABASE_URL = 'https://avryabmbrowguthrvatf.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable_KuReIRnnzOoTVD-vfIzeUA_9XE2AqCt';
const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

const ADMIN_ID = 1027326101; // Sizning Telegram ID raqamingiz

// Foydalanuvchilarning qo'shish jarayonini saqlash uchun vaqtinchalik xotira
const userStates = {};

const categories = [
    "Shkaflar",
    "Oyoq kiyim javoni",
    "Kitoblar javoni",
    "Krovatlar",
    "Yotoqxona to'plami",
    "Yumshoq mebellar",
    "Tumbalar",
    "Mexmonxona uchun mebellar",
    "Oshxona uchun mebellar",
    "Bolalar uchun mebellar",
    "Stol va stullar",
    "Ofis uchun mebellar"
];

// /start buyrug'i
bot.start((ctx) => {
    const chatId = ctx.from.id;
    
    let keyboard = [
        [{ text: "Mebelix Do'koni 🛒", web_app: { url: "https://ravshanmaksudoov3366.github.io/Mebelix-webapp/?v=2" } }]
    ];

    if (chatId === ADMIN_ID) {
        keyboard.push([{ text: "➕ Mebel qo'shish", callback_data: "add_product" }]);
    }

    ctx.reply("Assalomu alaykum! Mebelix botiga xush kelibsiz. Kerakli tugmani tanlang:", Markup.inlineKeyboard(keyboard));
});

// Admin mebel qo'shishni boshlaganda
bot.action('add_product', (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return ctx.answerCbQuery("Siz admin emassiz!");
    
    userStates[ctx.from.id] = { step: 'waiting_for_name', images: [] };
    ctx.reply("Mebel nomini kiriting:");
    ctx.answerCbQuery();
});

// Matnli xabarlarni qabul qilish (Admin kiritayotgan ma'lumotlar)
bot.on('text', async (ctx) => {
    const userId = ctx.from.id;
    if (userId !== ADMIN_ID) return;

    const state = userStates[userId];
    if (!state) return;

    const text = ctx.message.text;

    if (state.step === 'waiting_for_name') {
        state.title = text;
        state.step = 'waiting_for_price';
        ctx.reply("Narxini kiriting (faqat raqam):");
    } else if (state.step === 'waiting_for_price') {
        const price = parseFloat(text);
        if (isNaN(price)) {
            return ctx.reply("Iltimos, narxni faqat raqamlarda kiriting!");
        }
        state.price = price;
        state.step = 'waiting_for_description';
        ctx.reply("Mebel haqida qisqacha ma'lumot (tavsif) kiriting:");
    } else if (state.step === 'waiting_for_description') {
        state.description = text;
        state.step = 'waiting_for_images';

        // Kategoriyalarni tugma ko'rinishida chiqarish
        const keyboard = categories.map(cat => [Markup.button.callback(cat, `cat_${cat}`)]);
        ctx.reply("Kategoriyani tanlang:", Markup.inlineKeyboard(keyboard));
    }
});

// Kategoriyani tanlash
bot.action(/^cat_(.+)$/, async (ctx) => {
    const userId = ctx.from.id;
    if (userId !== ADMIN_ID) return;

    const state = userStates[userId];
    if (!state || state.step !== 'waiting_for_images') return;

    state.category = ctx.match[1];
    state.step = 'collecting_photos';

    ctx.answerCbQuery();
    ctx.reply(`Kategoriya tanlandi: ${state.category}\n\nEndi ushbu mebel uchun **1 tadan 5 tagacha rasm** yuboring. Rasmlarni yuborib bo'lib, **"Tamom"** deb yozing yoki tugmani bosing.`,
        Markup.inlineKeyboard([[Markup.button.callback("✅ Rasmlarni tugatish", "finish_photos")]])
    );
});

// Rasmlarni qabul qilish
bot.on('photo', async (ctx) => {
    const userId = ctx.from.id;
    if (userId !== ADMIN_ID) return;

    const state = userStates[userId];
    if (!state || state.step !== 'collecting_photos') return;

    const photo = ctx.message.photo;
    const fileId = photo[photo.length - 1].file_id;

    const fileLink = await ctx.telegram.getFileLink(fileId);
    state.images.push(fileLink.href);

    ctx.reply(`Rasm qabul qilindi! Jami rasmlar: ${state.images.length} ta. Yana rasm yuborishingiz yoki tugmani bosishingiz mumkin.`,
        Markup.inlineKeyboard([[Markup.button.callback("✅ Rasmlarni tugatish", "finish_photos")]])
    );
});

// Rasmlarni yig'ishni yakunlash va bazaga saqlash
bot.action('finish_photos', async (ctx) => {
    const userId = ctx.from.id;
    if (userId !== ADMIN_ID) return;

    const state = userStates[userId];
    if (!state || state.images.length === 0) {
        return ctx.reply("Kamida 1 ta rasm yuborishingiz kerak!");
    }

    ctx.answerCbQuery();

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
        ctx.reply("❌ Bazaga saqlashda xatolik yuz berdi!");
    } else {
        ctx.reply(`✅ Mebel muvaffaqiyatli qo'shildi!\n\n📷 Rasmlar soni: ${state.images.length} ta\n📁 Kategoriya: ${state.category}`);
    }

    delete userStates[userId];
});

// Veb-ilovadan kelgan mijoz buyurtmalarini va xarita havolasini qabul qilish
bot.on('web_app_data', (ctx) => {
    try {
        const data = JSON.parse(ctx.webAppData.data);
        
        // Mijozga tasdiq xabari
        ctx.reply("✅ Buyurtmangiz qabul qilindi! Tez orada operatorlarimiz siz bilan bog'lanishadi.");

        // Adminga yuboriladigan xabar
        let adminMessage = `🎉 <b>Yangi buyurtma tushdi!</b>\n\n` +
                           `🛋 <b>Mebel:</b> ${data.product}\n` +
                           `💰 <b>Narxi:</b> ${Number(data.price).toLocaleString()} so'm\n\n` +
                           `👤 <b>Mijoz:</b> ${data.clientName}\n` +
                           `📞 <b>Telefon:</b> ${data.clientPhone}\n` +
                           `📍 <b>Manzil:</b> ${data.clientAddress}`;

        // Agar mijoz Google Maps havolasini yuborgan bo'lsa, xabarga qo'shamiz
        if (data.geoLink && data.geoLink.trim() !== '') {
            adminMessage += `\n\n🗺 <b>Lokatsiya:</b> <a href="${data.geoLink}">Xaritada ko'rish</a>`;
        }

        bot.telegram.sendMessage(ADMIN_ID, adminMessage, { parse_mode: 'HTML', disable_web_page_preview: true });

    } catch (e) {
        ctx.reply("Buyurtma qabul qilindi.");
    }
});

bot.launch();
console.log('Bot ishga tushdi!');
