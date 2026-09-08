import asyncio
# YE LINE SABSE UPAR HONI CHAHIYE
asyncio.set_event_loop(asyncio.new_event_loop())

import os
from pyrogram import Client, filters
import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget

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
        'impersonate': ImpersonateTarget.from_str('chrome'),
        'extractor_args': {'generic': ['impersonate']},
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

# Func 2: 720p me fast download karna (FFMPEG Crash Fix ke sath)
def download_with_ytdlp(url):
    ydl_opts = {
        'outtmpl': '%(id)s.%(ext)s',
        'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
        
        # 'merge_output_format': 'mp4',  <--- HATA DIYA GAYA (Code 8 error rokne ke liye)
        'fixup': 'never',  # NAYA: Stream ko merge na kare
        
        'quiet': True,
        'noplaylist': True,
        'impersonate': ImpersonateTarget.from_str('chrome'),
        'extractor_args': {'generic': ['impersonate']},
        'external_downloader': 'aria2c',
        'external_downloader_args': ['-x', '16', '-s', '16', '-k', '1M'],
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        
        # Agar file bina mp4 ke download hui hai toh use zabardasti rename karke mp4 banana
        if os.path.exists(filename):
            if not filename.endswith('.mp4'):
                new_filename = filename.rsplit('.', 1)[0] + '.mp4'
                os.rename(filename, new_filename)
                filename = new_filename
        else:
            # Agar yt-dlp ne khud kisi reason se extension change kar diya ho
            fallback_filename = filename.rsplit('.', 1)[0] + '.mp4'
            if os.path.exists(fallback_filename):
                filename = fallback_filename

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
                    continue 
                except Exception:
                    pass 

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
    print("Bot is running with Advanced Cloudflare & FFMPEG Fix! Send links...")
    app.run()
