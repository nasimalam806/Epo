import asyncio
# YE LINE SABSE UPAR HONI CHAHIYE (Pyrogram import hone se pehle)
asyncio.set_event_loop(asyncio.new_event_loop())

import os
from pyrogram import Client, filters
import yt_dlp

# --- Yahan Apna Bot Data Dalein ---
API_ID = int(os.environ.get("API_ID", 0))        
API_HASH = os.environ.get("API_HASH", "")    
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")  

app = Client("video_downloader_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Func 1: Sirf URL nikalna (Bina download kiye)
def extract_info_only(url):
    ydl_opts = {
        'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
        'quiet': True,
        'noplaylist': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

# Func 2: 720p me fast download karna
def download_with_ytdlp(url):
    ydl_opts = {
        'outtmpl': '%(id)s.%(ext)s',
        'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best', # Quality 720p par limit kardi
        'merge_output_format': 'mp4',
        'quiet': True,
        'noplaylist': True,
        'external_downloader': 'aria2c',
        'external_downloader_args': ['-x', '16', '-s', '16', '-k', '1M'],
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if not os.path.exists(filename):
            filename = filename.rsplit('.', 1)[0] + '.mp4'
        return info, filename

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("Hello! Mujhe link bhejo, main use Smart Dual-Mode se download karke dunga.")

@app.on_message(filters.text & ~filters.command("start"))
async def download_video(client, message):
    urls = message.text.split() 
    
    for url in urls:
        if not url.startswith("http"):
            continue
            
        msg = await message.reply_text(f"🔍 Link check kar raha hoon...\nLink: {url}")

        try:
            # TRY 1: Direct Upload
            info = await asyncio.to_thread(extract_info_only, url)
            direct_url = info.get('url')
            title = info.get('title', 'Unknown Title')
            
            if direct_url:
                try:
                    await msg.edit_text("🚀 Direct Upload try kar raha hoon (Superfast)...")
                    await client.send_video(
                        chat_id=message.chat.id,
                        video=direct_url,
                        caption=f"**Title:** {title}",
                        supports_streaming=True
                    )
                    await msg.delete()
                    continue # Agar kamyab hua, toh agle link par jao
                except Exception:
                    # Agar Telegram server ne 20MB limit ya security ki wajah se fail kiya toh aage badho
                    pass 

            # TRY 2: Local 720p Fast Download
            await msg.edit_text("⚡ Direct Link fail hua. 720p me fast download shuru kar raha hoon...")
            info, filename = await asyncio.to_thread(download_with_ytdlp, url)
            
            await msg.edit_text("📤 Telegram par upload ho raha hai...")
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

if __name__ == "__main__":
    print("Bot is running purely on Termux with Smart Dual-Mode! Send links...")
    app.run()
