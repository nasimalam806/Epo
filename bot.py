import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())

import os
import time
import math
import subprocess
import requests
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp
from pyrogram.errors import MessageNotModified
from yt_dlp.networking.impersonate import ImpersonateTarget

# ==========================================
# 1. BOT CREDENTIALS
# ==========================================
API_ID = int(os.environ.get("API_ID", 0))        
API_HASH = os.environ.get("API_HASH", "")    
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")  

app = Client("video_downloader_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ==========================================
# 2. QUEUE, CANCEL MANAGER & CACHE
# ==========================================
download_queue = asyncio.Queue()
queue_display = [] 
CANCEL_TASKS = {}
STOP_UPLOAD = {} 
URL_CACHE = {} 

def format_bytes(size):
    size = int(size)
    if not size: return '0 B'
    power = 2**10
    n = 0
    dic_powerN = {0: 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size > power:
        size /= power
        n += 1
    return f"{round(size, 2)} {dic_powerN[n]}"

# ==========================================
# 3. LIVE PROGRESS BAR ENGINE
# ==========================================
async def progress_bar(current, total, msg, start_time, action="Uploading"):
    if STOP_UPLOAD.get(msg.id):
        raise Exception("Upload Cancelled")

    now = time.time()
    diff = now - start_time
    if diff < 1: return 
    
    if round(diff % 3.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff
        time_to_completion = round((total - current) / speed) if speed > 0 else 0
        
        progress = "[{0}{1}]".format(
            ''.join(["█" for i in range(math.floor(percentage / 10))]),
            ''.join(["░" for i in range(10 - math.floor(percentage / 10))])
        )
        
        text = f"🚀 **{action}...**\n\n"
        text += f"📊 {progress} **{round(percentage, 2)}%**\n"
        text += f"📦 **Size:** {format_bytes(current)} / {format_bytes(total)}\n"
        text += f"⚡ **Speed:** {format_bytes(speed)}/s\n"
        text += f"⏳ **ETA:** {time_to_completion} Seconds"
        
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{msg.id}")]]
        )
        
        try:
            await msg.edit_text(text, reply_markup=reply_markup)
        except MessageNotModified:
            pass

# ==========================================
# 4. DOWNLOAD ENGINES (FORCE FFMPEG + YTDLP)
# ==========================================
class CancelledError(Exception):
    pass

class MyLogger(object):
    def __init__(self, msg_id):
        self.msg_id = msg_id
    def debug(self, msg):
        if CANCEL_TASKS.get(self.msg_id): raise CancelledError("Download cancelled")
    def warning(self, msg): pass
    def error(self, msg): pass

# 🔥 NAYA ENGINE: DIRECT FORCE DOWNLOADER (Ab poora FFmpeg par chalega!)
def download_direct_force(url, msg_id, referer=None):
    if CANCEL_TASKS.get(msg_id): return None, "CANCELLED"
    filename = f"force_{msg_id}.mp4"
    try:
        cmd = ["ffmpeg", "-y"]
        
        # Wahi exact User-Agent jo aapne Termux me use kiya tha
        user_agent = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
        
        # Referer header lagana
        if referer:
            cmd.extend(["-headers", f"Referer: {referer}\r\n"])
            
        cmd.extend(["-user_agent", user_agent])
        cmd.extend(["-i", url, "-c", "copy"])
        
        # Agar m3u8 file hai, toh audio fix karna zaroori hota hai
        if ".m3u8" in url:
            cmd.extend(["-bsf:a", "aac_adtstoasc"])
            
        cmd.append(filename)
        
        # FFmpeg ko run karna
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        if os.path.exists(filename) and os.path.getsize(filename) > 1024:
            return {"title": "FFmpeg Direct Fetch", "extractor_key": "FFmpeg Master"}, filename
    except Exception:
        pass
    return None, "FORCE_ERROR"

def get_formats(url, referer=None):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    if referer: headers['Referer'] = referer
    ydl_opts = {
        'quiet': True, 'noplaylist': True,
        'impersonate': ImpersonateTarget.from_str('chrome'),
        'extractor_args': {'youtube': ['player_client=ios,android']},
        'http_headers': headers
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            resolutions = set()
            for f in formats:
                h = f.get('height')
                if h and isinstance(h, int) and h >= 144: resolutions.add(h)
            common_res = [144, 240, 360, 480, 720, 1080, 1440, 2160]
            available_res = sorted([r for r in resolutions if r in common_res])
            if not available_res: available_res = sorted(list(resolutions))
            return available_res, info.get('extractor_key', 'Direct Video')
    except:
        return [360, 480, 720, 1080], "Fallback Engine"

def extract_info_only(url, selected_res, referer=None):
    headers = {'User-Agent': 'Mozilla/5.0'}
    if referer: headers['Referer'] = referer
    ydl_opts = {
        'format': f'best[height<={selected_res}]',
        'quiet': True, 'noplaylist': True,
        'impersonate': ImpersonateTarget.from_str('chrome'),
        'extractor_args': {'youtube': ['player_client=ios,android']},
        'http_headers': headers
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

def download_with_ytdlp(url, msg_id, selected_res, referer=None):
    if CANCEL_TASKS.get(msg_id): return None, None
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    if referer: headers['Referer'] = referer
    ydl_opts = {
        'outtmpl': '%(id)s.%(ext)s',
        'format': f'bestvideo[height<={selected_res}]+bestaudio/best[height<={selected_res}]/best',
        'merge_output_format': 'mp4',
        'fixup': 'never', 'quiet': True, 'noplaylist': True,
        'impersonate': ImpersonateTarget.from_str('chrome'),
        'extractor_args': {'youtube': ['player_client=ios,android']},
        'external_downloader': 'aria2c',
        'external_downloader_args': ['-c', '-x', '16', '-s', '16', '-k', '1M'],
        'http_headers': headers,
        'logger': MyLogger(msg_id) 
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if not filename.endswith('.mp4') and os.path.exists(filename):
                new_filename = filename.rsplit('.', 1)[0] + '.mp4'
                os.rename(filename, new_filename)
                filename = new_filename
            return info, filename
    except CancelledError: return None, "CANCELLED"
    except Exception as e: return None, f"YTDLP_ERROR: {str(e)}"

# ==========================================
# 5. BACKGROUND WORKER (QUEUE SYSTEM)
# ==========================================
async def process_queue():
    while True:
        task = await download_queue.get()
        url, chat_id, msg, selected_res, referer = task  
        
        if url in queue_display: queue_display.remove(url) 
        if CANCEL_TASKS.get(msg.id):
            await msg.edit_text("❌ Task Cancelled before starting.")
            download_queue.task_done()
            continue

        try:
            cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{msg.id}")]])
            
            # 🔥 BYPASS: Agar direct file hai ya Referer diya hai toh FFmpeg chalega
            if referer or url.endswith(".mp4") or url.endswith(".m3u8"):
                await msg.edit_text(f"⚡ Forced FFmpeg Download Active...\n🛡️ Referer: {'Yes' if referer else 'No'}", reply_markup=cancel_markup)
                info, filename = await asyncio.to_thread(download_direct_force, url, msg.id, referer)
                if filename == "CANCELLED" or CANCEL_TASKS.get(msg.id): raise Exception("Cancelled by user")
                
                if not filename or filename.startswith("FORCE_ERROR"):
                    raise Exception("FFmpeg failed. Link expire ho gaya hai ya block hai.")
            else:
                # NORMAL FLOW (yt-dlp)
                await msg.edit_text(f"⚡ Downloading locally (yt-dlp)...", reply_markup=cancel_markup)
                info, filename = await asyncio.to_thread(download_with_ytdlp, url, msg.id, selected_res, referer)
                if filename == "CANCELLED" or CANCEL_TASKS.get(msg.id): raise Exception("Cancelled by user")
                
                if not info and filename and filename.startswith("YTDLP_ERROR:"):
                    raise Exception("yt-dlp Blocked (Shayad Render IP Ban hai).")

            local_title = info.get('title', 'Unknown Title') if info else 'Unknown Title'
            local_website = info.get('extractor_key', 'FFmpeg Extractor') if info else 'FFmpeg Extractor'
            local_caption = f"**🎬 Title:** {local_title}\n**🌐 Website:** {local_website}\n**⚙️ Quality:** {selected_res}p\n**🔗 Source:** [Link]({referer if referer else url})"

            await msg.edit_text("📤 Uploading...", reply_markup=cancel_markup)
            start_time = time.time()
            
            try:
                await app.send_video(
                    chat_id=chat_id, video=filename, caption=local_caption,
                    supports_streaming=True, progress=progress_bar, progress_args=(msg, start_time, "Uploading")
                )
                await msg.delete()
            except Exception as e:
                if "Upload Cancelled" in str(e): raise Exception("Cancelled by user")
                else: raise e 
            if os.path.exists(filename): os.remove(filename)

        except Exception as e:
            if "Cancelled" in str(e):
                 await msg.edit_text("❌ Video Download/Upload Rok Diya Gaya Hai.")
                 subprocess.run(["pkill", "-f", "aria2c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                 subprocess.run(["pkill", "-f", "ffmpeg"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                 await msg.edit_text(f"❌ Error: {str(e)}")
            try:
                if 'filename' in locals() and os.path.exists(filename) and not "ERROR" in filename: os.remove(filename)
            except: pass
        finally:
            if msg.id in CANCEL_TASKS: del CANCEL_TASKS[msg.id]
            if msg.id in STOP_UPLOAD: del STOP_UPLOAD[msg.id]
            try: download_queue.task_done()
            except: pass

# ==========================================
# 6. TELEGRAM COMMANDS & HANDLERS
# ==========================================
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("Hello! Main v4.1 Premium Downloader hoon.\n(Naya Feature: Master FFmpeg Engine Support for .mp4/.m3u8)")

@app.on_message(filters.command("queue"))
async def show_queue(client, message):
    if not queue_display:
        await message.reply_text("📭 Queue bilkul khaali hai! Koi naya link bhejein.")
        return
    text = "**📋 Line me lagi hui videos:**\n\n"
    for i, url in enumerate(queue_display): text += f"{i+1}. {url}\n"
    await message.reply_text(text)

@app.on_message(filters.text & ~filters.command(["start", "queue"]))
async def handle_links(client, message):
    lines = message.text.split('\n') 
    for line in lines:
        if not line.startswith("http"): continue
        
        parts = line.split('|')
        url = parts[0].strip()
        referer = parts[1].strip() if len(parts) > 1 else None

        # 🔥 SUPER HACK: Agar Referer diya hai, ya URL ke end me .mp4/.m3u8 hai, toh Seedha FFmpeg!
        if referer or url.endswith(".mp4") or url.endswith(".m3u8"):
            position = len(queue_display) + 1
            queue_display.append(url)
            msg = await message.reply_text(f"⚡ FFmpeg Direct Triggered! Skipping checks... Line me lag gaya!\n(Position: {position})")
            # Seedha Queue me bhej do
            await download_queue.put((url, message.chat.id, msg, 1080, referer))
            continue

        # Normal Website Flow
        msg = await message.reply_text(f"🔍 Fetching quality options... Please wait!")
        URL_CACHE[msg.id] = {'url': url, 'referer': referer} 
        
        try:
            res_list, website = await asyncio.to_thread(get_formats, url, referer)
            if not res_list: res_list = [360, 480, 720, 1080] 
            
            buttons = []
            row = []
            for res in res_list:
                row.append(InlineKeyboardButton(f"🎬 {res}p", callback_data=f"res_{res}_{msg.id}"))
                if len(row) == 2:
                    buttons.append(row)
                    row = []
            if row: buttons.append(row)
            
            buttons.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{msg.id}")])
            reply_markup = InlineKeyboardMarkup(buttons)
            
            text_msg = f"**🔗 Link:** {url}\n**🌐 Source:** {website}"
            if referer: text_msg += f"\n🛡️ **Referer Bypass:** {referer}"
            text_msg += "\n\n👇 **Select Quality to Download:**"
            
            await msg.edit_text(text_msg, reply_markup=reply_markup, disable_web_page_preview=True)
        except Exception as e:
            await msg.edit_text(f"❌ Error fetching qualities: {str(e)}")

@app.on_callback_query(filters.regex(r"^res_"))
async def select_resolution(client, callback_query):
    data = callback_query.data.split("_")
    selected_res = int(data[1])
    msg_id = int(data[2])
    
    cache_data = URL_CACHE.get(msg_id)
    if not cache_data:
         await callback_query.answer("Error: Link purana ho gaya hai, wapas link bhejein.", show_alert=True)
         return
    
    url = cache_data['url']
    referer = cache_data['referer']
    
    position = len(queue_display) + 1
    queue_display.append(url)
    
    await download_queue.put((url, callback_query.message.chat.id, callback_query.message, selected_res, referer))
    await callback_query.message.edit_text(f"⏳ Line me lag gaya!\n(Position: {position} | Quality: {selected_res}p)")

@app.on_callback_query(filters.regex(r"^cancel_"))
async def cancel_callback(client, callback_query):
    msg_id = int(callback_query.data.split("_")[1])
    CANCEL_TASKS[msg_id] = True
    STOP_UPLOAD[msg_id] = True 
    await callback_query.answer("Cancelling task... Please wait!", show_alert=True)
    try: await callback_query.message.edit_text("❌ Task Cancelled.")
    except: pass

# ==========================================
# 7. BOT RUNNER
# ==========================================
if __name__ == "__main__":
    print("========================================")
    print("Bot is running v4.1 purely on Render Cloud!")
    print("Features: Master FFmpeg Engine | Anti-Hotlink")
    print("========================================")
    
    loop = asyncio.get_event_loop()
    loop.create_task(process_queue())
    app.run()
