# Python 3.10 ka base image
FROM python:3.10-slim

# FFmpeg, Aria2c aur zaroori tools install karna
RUN apt-get update && apt-get install -y \
    ffmpeg \
    aria2 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Kaam karne ka folder set karna
WORKDIR /app

# Requirements copy karke install karna
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Aapki saari files copy karna (bot.py, web.py, start.sh)
COPY . .

# start.sh ko chalane ki permission dena
RUN chmod +x start.sh

# Aakhir me bot start karna
CMD ["./start.sh"]
