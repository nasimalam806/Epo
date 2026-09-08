import asyncio
import os
from pyrogram import Client, filters
import yt_dlp

# Naye Pyrogram version ke liye loop set karna
asyncio.set_event_loop(asyncio.new_event_loop())

# --- Yahan Apna Bot Data Dalein ---
API_ID = int(os.environ.get("API_ID", 0))        
API_HASH = os.environ.get("API_HASH", "")    
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")  

app = Client("video_downloader_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Is function ko hum background thread me chalayenge
def download_with_ytdlp(url):
    # Super-Fast Download Format (Aria2c ke sath)
    ydl_opts = {
        'outtmpl': '%(id)s.%(ext)s',
        'format': 'bestvideo+bestaudio/best', 
        'merge_output_format': 'mp4',
        'quiet': True,
        'noplaylist': True,
        'external_downloader': 'aria2c',  # Superfast speed engine
        'external_downloader_args': ['-x', '16', '-s', '16', '-k', '1M'], # 16 tukdo me download karega
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        # Agar file ka naam alag hai, toh use mp4 banayenge
        if not os.path.exists(filename):
            filename = filename.rsplit('.', 1)[0] + '.mp4'
        return info, filename

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("Hello! Mujhe kisi bhi website ka video link bhejo aur main use superfast download karke dunga.")

@app.on_message(filters.text & ~filters.command("start"))
async def download_video(client, message):
    # Agar message me ek se zyada link hain toh unhe alag-alag karein
    urls = message.text.split() 
    
    for url in urls:
        # Sirf wahi text check karega jo asal me ek link (http) hai
        if not url.startswith("http"):
            continue
            
        msg = await message.reply_text(f"⏳ Downloading video...\nLink: {url}")

        try:
            # Multi-threading: Is command se main bot freeze nahi hoga, background me download hoga
            info, filename = await asyncio.to_thread(download_with_ytdlp, url)

            await msg.edit_text("📤 Uploading to Telegram...")
            await client.send_video(
                chat_id=message.chat.id,
                video=filename,
                caption=f"**Title:** {info.get('title', 'Unknown Title')}",
                supports_streaming=True
            )
            await msg.delete()

            # Video bhejne ke baad phone ki memory khali karne ke liye file delete karna
            if os.path.exists(filename):
                os.remove(filename)
                
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)}")

# --- Bot ko run karna ---
if __name__ == "__main__":
    print("Bot is running purely on Termux with Aria2c Speed Booster! Send links on Telegram...")
    app.run()
