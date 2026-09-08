import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())

import os
from pyrogram import Client, filters
import yt_dlp

# --- Yahan Apna Bot Data Dalein ---
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

    # Smart Format 
    ydl_opts = {
        'outtmpl': '%(id)s.%(ext)s',
        'format': 'bestvideo+bestaudio/best', 
        'merge_output_format': 'mp4',
        'quiet': True,
        'noplaylist': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if not os.path.exists(filename):
                filename = filename.rsplit('.', 1)[0] + '.mp4'

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

# --- Bot ko run karna ---
if __name__ == "__main__":
    print("Bot is running purely on Termux! Send a link on Telegram...")
    app.run() 
