import os
from pyrogram import Client, filters
import yt_dlp
from flask import Flask
from threading import Thread

# --- Dummy Web Server (Render ko awake rakhne ke liye) ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is running 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- Yahan Apna Bot Data Dalein ---
# --- Yahan Apna Bot Data Dalein ---
# Ab hum token code me nahi daalenge, balki Render se automatically lenge
API_ID = int(os.environ.get("API_ID", 0))        
API_HASH = os.environ.get("API_HASH", "")    
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")  


app = Client("video_downloader_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("Hello! Mujhe kisi bhi website ka video link bhejo aur main use download karke dunga.")

@app.on_message(filters.text & ~filters.command("start"))
async def download_video(client, message):
    url = message.text
    msg = await message.reply_text("⏳ Downloading video... Please wait.")

    ydl_opts = {
        'outtmpl': '%(id)s.%(ext)s',
        'format': 'best',
        'quiet': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        await msg.edit_text("📤 Uploading to Telegram...")
        await client.send_video(
            chat_id=message.chat.id,
            video=filename,
            caption=f"**Title:** {info.get('title', 'Unknown Title')}",
            supports_streaming=True
        )
        await msg.delete()

        if os.path.exists(filename):
            os.remove(filename)
            
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")

# --- Bot aur Web Server dono ek sath run karna ---
if __name__ == "__main__":
    keep_alive() # Flask web server chalu karega
    print("Bot is running...")
    app.run()    # Telegram bot chalu karega
    
