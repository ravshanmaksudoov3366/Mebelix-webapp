FROM python:3.12-slim
WORKDIR /app
# ffmpeg — mahsulot videolarini siqish uchun
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Baza va rasmlar shu papkada saqlanadi — hostingda unga doimiy disk (volume) ulang
VOLUME /app/data
EXPOSE 8080
CMD ["python", "app.py"]
