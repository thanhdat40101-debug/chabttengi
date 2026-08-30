import asyncio
import logging
import os
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- WEB SERVER KEEP-ALIVE ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "bot dang chay!", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# --- CẤU HÌNH ---
TELEGRAM_BOT_TOKEN = "8662342747:AAFGSyvziio3uPNdKbhnhJMee33YbLaV290"
API_MD5_HISTORY = "https://kwinstore.com/hitclub/md5/history/8167b2c16888dae174a454f493022e22242f35288df59f41"
INTERVAL_SECONDS = 3

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

active_chats = set()
last_phien = None

def fetch_json(url):
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        logging.error(f"lỗi kết nối api: {e}")
    return None

def extract_first_item(data):
    if not data:
        return None
    if isinstance(data, list) and len(data) > 0:
        return data[0]
    if isinstance(data, dict):
        for key in ["data", "history", "list", "results", "rows"]:
            if key in data and isinstance(data[key], list) and len(data[key]) > 0:
                return data[key][0]
    return None

def format_single_item(item):
    """Đọc dữ liệu chuẩn theo đúng key trong ảnh API và hạ về chữ thường"""
    if not isinstance(item, dict):
        return "không có dữ liệu."

    # Lấy đúng key từ JSON thực tế
    phien = str(item.get("phien", "---")).lower()
    kq = str(item.get("kết quả") or item.get("ket_qua") or "---").lower()
    tong = str(item.get("tổng") or item.get("tong") or "---").lower()
    
    d1 = item.get("d1", "-")
    d2 = item.get("d2", "-")
    d3 = item.get("d3", "-")
    
    return (
        f"🎲 **kết quả bàn md5**\n"
        f"• phiên: `{phien}`\n"
        f"• kết quả: {kq} (tổng: {tong})\n"
        f"• xúc xắc: {d1} - {d2} - {d3}"
    )

async def auto_fetch_loop(app: Application):
    global last_phien
    while True:
        if active_chats:
            raw_data = fetch_json(API_MD5_HISTORY)
            first_item = extract_first_item(raw_data)
            
            if first_item and isinstance(first_item, dict):
                current_phien = first_item.get("phien")
                
                # Chỉ phát tin nhắn khi có phiên mới
                if current_phien and str(current_phien) != str(last_phien):
                    last_phien = current_phien
                    message = format_single_item(first_item)
                    
                    for chat_id in list(active_chats):
                        try:
                            await app.bot.send_message(
                                chat_id=chat_id, 
                                text=message,
                                parse_mode="Markdown"
                            )
                        except Exception as e:
                            logging.error(f"lỗi gửi tin tới chat {chat_id}: {e}")
        
        await asyncio.sleep(INTERVAL_SECONDS)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    active_chats.add(chat_id)
    
    raw_data = fetch_json(API_MD5_HISTORY)
    first_item = extract_first_item(raw_data)
    
    if first_item:
        msg = "✅ đã bật tự động nhận dữ liệu bàn md5!\n\n" + format_single_item(first_item)
    else:
        msg = "✅ đã bật tự động!\n\n⚠️ không kết nối được tới api."
        
    await update.message.reply_text(msg, parse_mode="Markdown")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in active_chats:
        active_chats.remove(chat_id)
        await update.message.reply_text("⛔ đã tắt tự động.")
    else:
        await update.message.reply_text("bạn chưa bật chế độ tự động.")

async def post_init(application: Application):
    asyncio.create_task(auto_fetch_loop(application))

def main():
    threading.Thread(target=run_web, daemon=True).start()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.run_polling()

if __name__ == "__main__":
    main()
