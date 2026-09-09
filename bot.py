import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())

import os
import time
import math
import subprocess
import requests
import json
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
# 4. DOWNLOAD ENGINES (YTDLP + FALLBACKS)
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

def get_formats(url):
    ydl_opts = {
        'quiet': True, 'noplaylist': True,
        'impersonate': ImpersonateTarget.from_str('chrome'),
        'extractor_args': {'youtube': ['player_client=ios,android']},
        'http_headers': {'User-Agent': 'Mozilla/5.0'}
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
            return available_res, info.get('extractor_key', 'Unknown Website')
    except:
        return [360, 480, 720, 1080], "Fallback/Unknown Website"

def extract_info_only(url, selected_res):
    ydl_opts = {
        'format': f'best[height<={selected_res}]',
        'quiet': True, 'noplaylist': True,
        'impersonate': ImpersonateTarget.from_str('chrome'),
        'extractor_args': {'youtube': ['player_client=ios,android']}
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

def download_with_ytdlp(url, msg_id, selected_res):
    if CANCEL_TASKS.get(msg_id): return None, None
    ydl_opts = {
        'outtmpl': '%(id)s.%(ext)s',
        'format': f'bestvideo[height<={selected_res}]+bestaudio/best[height<={selected_res}]/best',
        'merge_output_format': 'mp4',
        'fixup': 'never', 'quiet': True, 'noplaylist': True,
        'impersonate': ImpersonateTarget.from_str('chrome'),
        'extractor_args': {'youtube': ['player_client=ios,android']},
        'external_downloader': 'aria2c',
        'external_downloader_args': ['-c', '-x', '16', '-s', '16', '-k', '1M'],
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

# --- FALLBACK 1: COBALT API ---
def download_with_cobalt(url, msg_id, quality):
    if CANCEL_TASKS.get(msg_id): return None, "CANCELLED"
    try:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
        data = {
            "url": url,
            "vQuality": str(quality)
        }
        # Using a public cobalt instance (you can change this to another instance if it goes down)
        res = requests.post("https://co.wuk.sh/api/json", headers=headers, json=data, timeout=30)
        res_json = res.json()
        
        if res_json.get("status") == "stream" or res_json.get("status") == "redirect":
            direct_link = res_json.get("url")
            # Ab Aria2c se wo direct link download karenge
            filename = f"cobalt_{msg_id}.mp4"
            cmd = ["aria2c", "-c", "-x", "16", "-s", "16", "-k", "1M", "-o", filename, direct_link]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if os.path.exists(filename):
                return {"title": "Cobalt Fetch", "extractor_key": "Cobalt API"}, filename
    except Exception as e:
        return None, f"COBALT_ERROR: {str(e)}"
    return None, "COBALT_ERROR: Fetch Failed"

# --- FALLBACK 2: GALLERY-DL ---
def download_with_gallerydl(url, msg_id):
    if CANCEL_TASKS.get(msg_id): return None, "CANCELLED"
    try:
        filename = f"gdl_{msg_id}.mp4"
        # --exec parameter filename rename karne ke liye use hota hai
        cmd = ["gallery-dl", "-D", ".", "-f", filename, url]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Gallery-dl original filename me download karta hai, hume sabse recent .mp4 dhundna padega
        files = [f for f in os.listdir('.') if os.path.isfile(f) and (f.endswith('.mp4') or f.endswith('.mkv'))]
        if files:
             files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
             latest_file = files[0]
             return {"title": "Gallery-DL Fetch", "extractor_key": "Gallery-DL"}, latest_file
    except Exception as e:
        return None, f"GDL_ERROR: {str(e)}"
    return None, "GDL_ERROR: Not found"

# ==========================================
# 5. BACKGROUND WORKER (QUEUE SYSTEM)
# ==========================================
async def process_queue():
    while True:
        task = await download_queue.get()
        url, chat_id, msg, selected_res = task 
        
        if url in queue_display: queue_display.remove(url) 
        if CANCEL_TASKS.get(msg.id):
            await msg.edit_text("❌ Task Cancelled before starting.")
            download_queue.task_done()
            continue

        try:
            cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{msg.id}")]])
            await msg.edit_text("🔍 Checking Direct Link...", reply_markup=cancel_markup)
            
            try: info_direct = await asyncio.to_thread(extract_info_only, url, selected_res)
            except Exception: info_direct = None
            if CANCEL_TASKS.get(msg.id): raise Exception("Cancelled by user")

            direct_url = info_direct.get('url') if info_direct else None
            title = info_direct.get('title', 'Unknown Title') if info_direct else 'Unknown Title'
            website = info_direct.get('extractor_key', 'Unknown Website') if info_direct else 'Unknown Website'
            
            caption_text = f"**🎬 Title:** {title}\n**🌐 Website:** {website}\n**⚙️ Quality:** {selected_res}p\n**🔗 Source:** [Original Link]({url})"
            
            if direct_url:
                try:
                    await msg.edit_text("🚀 Trying Direct Upload (Superfast)...", reply_markup=cancel_markup)
                    await app.send_video(chat_id=chat_id, video=direct_url, caption=caption_text, supports_streaming=True)
                    await msg.delete()
                    if msg.id in CANCEL_TASKS: del CANCEL_TASKS[msg.id]
                    if msg.id in STOP_UPLOAD: del STOP_UPLOAD[msg.id]
                    download_queue.task_done()
                    continue 
                except Exception: pass 

            # --- ENGINE 1: YT-DLP ---
            await msg.edit_text(f"⚡ Downloading locally (yt-dlp)...\nQuality: {selected_res}p", reply_markup=cancel_markup)
            info, filename = await asyncio.to_thread(download_with_ytdlp, url, msg.id, selected_res)
            if filename == "CANCELLED" or CANCEL_TASKS.get(msg.id): raise Exception("Cancelled by user")
            
            # --- ENGINE 2: COBALT FALLBACK ---
            if not info and filename and filename.startswith("YTDLP_ERROR:"):
                await msg.edit_text(f"⚠️ yt-dlp failed. Trying Fallback 1 (Cobalt API)...", reply_markup=cancel_markup)
                info, filename = await asyncio.to_thread(download_with_cobalt, url, msg.id, selected_res)
                if filename == "CANCELLED" or CANCEL_TASKS.get(msg.id): raise Exception("Cancelled by user")

            # --- ENGINE 3: GALLERY-DL FALLBACK ---
            if not info and filename and filename.startswith("COBALT_ERROR:"):
                await msg.edit_text(f"⚠️ Cobalt failed. Trying Fallback 2 (Gallery-DL)...", reply_markup=cancel_markup)
                info, filename = await asyncio.to_thread(download_with_gallerydl, url, msg.id)
                if filename == "CANCELLED" or CANCEL_TASKS.get(msg.id): raise Exception("Cancelled by user")

            # Agar sab fail ho gaya
            if not filename or filename.startswith("GDL_ERROR:") or filename.startswith("COBALT_ERROR:"):
                raise Exception("Saare engines fail ho gaye. Ye website bohot heavily secured hai ya link galat hai.")

            local_title = info.get('title', 'Unknown Title')
            local_website = info.get('extractor_key', 'Fallback Downloader')
            local_caption = f"**🎬 Title:** {local_title}\n**🌐 Website:** {local_website}\n**⚙️ Quality:** {selected_res}p\n**🔗 Source:** [Original Link]({url})"

            await msg.edit_text("📤 Uploading...", reply_markup=cancel_markup)
            start_time = time.time()
            
            try:
                await app.send_video(
                    chat_id=chat_id, video=filename, caption=local_caption,
                    supports_streaming=True, progress=progress_bar, progress_args=(msg, start_time, "Uploading")
                )
                await msg.delete()
            except Exception as e:
                if "Upload Cancelled" in str(e): raise Exception("Cancelled by user during upload")
                else: raise e 

            if os.path.exists(filename): os.remove(filename)

        except Exception as e:
            if "Cancelled" in str(e):
                 await msg.edit_text("❌ Video Download/Upload Rok Diya Gaya Hai.")
                 subprocess.run(["pkill", "-f", "aria2c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                 await msg.edit_text(f"❌ Error: {str(e)}")
            try:
                if 'filename' in locals() and os.path.exists(filename) and not "ERROR:" in filename:
                    os.remove(filename)
            except: pass
        finally:
            if msg.id in CANCEL_TASKS: del CANCEL_TASKS[msg.id]
            if msg.id in STOP_UPLOAD: del STOP_UPLOAD[msg.id]
            try: download_queue.task_done()
            except ValueError: pass

# ==========================================
# 6. TELEGRAM COMMANDS & HANDLERS
# ==========================================
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("Hello! Main v2.0 Premium Downloader hoon. Mujhe links bhejiye!\n(Features: Queue, Quality, 3x Fallback Engines)")

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
    urls = message.text.split() 
    for url in urls:
        if not url.startswith("http"): continue
        msg = await message.reply_text(f"🔍 Fetching quality options... Please wait!")
        URL_CACHE[msg.id] = url
        try:
            res_list, website = await asyncio.to_thread(get_formats, url)
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
            
            await msg.edit_text(
                f"**🔗 Link:** {url}\n**🌐 Source:** {website}\n\n👇 **Select Quality to Download:**", 
                reply_markup=reply_markup, disable_web_page_preview=True
            )
        except Exception as e:
            await msg.edit_text(f"❌ Error fetching qualities: {str(e)}")

@app.on_callback_query(filters.regex(r"^res_"))
async def select_resolution(client, callback_query):
    data = callback_query.data.split("_")
    selected_res = int(data[1])
    msg_id = int(data[2])
    
    url = URL_CACHE.get(msg_id)
    if not url:
         await callback_query.answer("Error: Link purana ho gaya hai, wapas link bhejein.", show_alert=True)
         return
    
    position = len(queue_display) + 1
    queue_display.append(url)
    await download_queue.put((url, callback_query.message.chat.id, callback_query.message, selected_res))
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
    print("Bot is running v3.0 purely on Render Cloud!")
    print("Features: Queue | Captions | YT-DLP + Cobalt + Gallery-DL Fallback")
    print("========================================")
    
    loop = asyncio.get_event_loop()
    loop.create_task(process_queue())
    app.run()
    
