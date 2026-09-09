import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())

import os
import time
import math
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp
from pyrogram.errors import MessageNotModified
from yt_dlp.networking.impersonate import ImpersonateTarget

# --- Yahan Apna Bot Data Dalein ---
API_ID = int(os.environ.get("API_ID", 0))        
API_HASH = os.environ.get("API_HASH", "")    
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")  

app = Client("video_downloader_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- QUEUE & CANCEL SYSTEM ---
download_queue = asyncio.Queue()
queue_display = [] 
CANCEL_TASKS = {}

# File size ko MB/GB me dikhane ka formula
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

# --- LIVE PROGRESS BAR ---
async def progress_bar(current, total, msg, start_time, action="Uploading"):
    # Agar user ne cancel daba diya hai, toh error throw karke upload rok do
    if CANCEL_TASKS.get(msg.id):
        raise Exception("Cancelled by user!")

    now = time.time()
    diff = now - start_time
    if diff < 1: return # 1 second se pehle update na kare (taaki bot ban na ho)
    
    # Har 3 second me message update karein
    if round(diff % 3.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff
        time_to_completion = round((total - current) / speed) if speed > 0 else 0
        
        # Progress bar ka design [████░░░░░░]
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

# --- DOWNLOAD ENGINE (WITH RESUME) ---
def download_with_ytdlp(url, msg_id):
    if CANCEL_TASKS.get(msg_id): return None, None
    
    ydl_opts = {
        'outtmpl': '%(id)s.%(ext)s',
        'format': 'best',
        'fixup': 'never',
        'quiet': True,
        'noplaylist': True,
        'impersonate': ImpersonateTarget.from_str('chrome'),
        'extractor_args': {'generic': ['impersonate']},
        'external_downloader': 'aria2c',
        # NAYA: '-c' lagaya gaya hai Resume (Auto-Save) ke liye!
        'external_downloader_args': ['-c', '-x', '16', '-s', '16', '-k', '1M'],
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        
        if not filename.endswith('.mp4') and os.path.exists(filename):
            new_filename = filename.rsplit('.', 1)[0] + '.mp4'
            os.rename(filename, new_filename)
            filename = new_filename
            
        return info, filename

# --- BACKGROUND WORKER (QUEUE SYSTEM) ---
async def process_queue():
    while True:
        task = await download_queue.get()
        url, message, msg = task
        
        if url in queue_display:
            queue_display.remove(url) 
        
        if CANCEL_TASKS.get(msg.id):
            await msg.edit_text("❌ Task Cancelled.")
            download_queue.task_done()
            continue

        try:
            cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{msg.id}")]])
            await msg.edit_text(f"⚡ Downloading...\nLink: {url}", reply_markup=cancel_markup)
            
            info, filename = await asyncio.to_thread(download_with_ytdlp, url, msg.id)
            
            if CANCEL_TASKS.get(msg.id): raise Exception("Cancelled by user!")
            if not filename: raise Exception("Download failed.")

            await msg.edit_text("📤 Uploading...", reply_markup=cancel_markup)
            
            start_time = time.time()
            await app.send_video(
                chat_id=message.chat.id,
                video=filename,
                caption=f"**Title:** {info.get('title', 'Unknown Title')}",
                supports_streaming=True,
                progress=progress_bar,
                progress_args=(msg, start_time, "Uploading")
            )
            await msg.delete()

            # Space bachane ke liye upload ke baad delete karein
            if os.path.exists(filename): os.remove(filename)

        except Exception as e:
            if "Cancelled" in str(e):
                await msg.edit_text("❌ Video Download/Upload Rok Diya Gaya Hai.")
            else:
                await msg.edit_text(f"❌ Error: {str(e)}")
        finally:
            download_queue.task_done()

# --- BOT COMMANDS ---
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("Hello! Main v2.0 par chal raha hoon. Mujhe links bhejiye! (Queue, Resume, & Progress bar active)")

@app.on_message(filters.command("queue"))
async def show_queue(client, message):
    if not queue_display:
        await message.reply_text("📭 Queue bilkul khaali hai! Koi link bhejein.")
        return
    
    text = "**📋 Line me lagi hui videos:**\n\n"
    for i, url in enumerate(queue_display):
        text += f"{i+1}. {url}\n"
    await message.reply_text(text)

@app.on_message(filters.text & ~filters.command(["start", "queue"]))
async def handle_links(client, message):
    urls = message.text.split() 
    for url in urls:
        if not url.startswith("http"): continue
        
        # Link ko queue me daalna
        position = len(queue_display) + 1
        msg = await message.reply_text(f"⏳ Line me lag gaya! (Position: {position})")
        queue_display.append(url)
        await download_queue.put((url, message, msg))

@app.on_callback_query(filters.regex(r"^cancel_"))
async def cancel_callback(client, callback_query):
    msg_id = int(callback_query.data.split("_")[1])
    CANCEL_TASKS[msg_id] = True
    await callback_query.answer("Cancelling task... Please wait!", show_alert=True)

if __name__ == "__main__":
    print("Bot is running v2.0 with Queue, Progress Bar & Resume! Send links...")
    # Background worker ko start karna
    loop = asyncio.get_event_loop()
    loop.create_task(process_queue())
    app.run()
