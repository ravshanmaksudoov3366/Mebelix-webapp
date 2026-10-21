// Eski Render xizmati (mebelix-webapp.onrender.com) uchun yo'naltiruvchi.
// Bot endi yangi xizmatda (mebelix.onrender.com, app.py) ishlaydi; bu fayl botni ishga tushirmaydi.
const http = require('http');
const NEW_URL = 'https://mebelix.onrender.com';

http.createServer((req, res) => {
  res.writeHead(301, { Location: NEW_URL + req.url });
  res.end();
}).listen(process.env.PORT || 3000);
