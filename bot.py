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
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        logging.error(f"lỗi kết nối api: {e}")
    return None

def extract_latest_item(data):
    """Trích xuất phần tử mới nhất từ dữ liệu JSON kiểu mảng"""
    if not data:
        return None
    if isinstance(data, list) and len(data) > 0:
        return data[0]
    if isinstance(data, dict):
        if "phien" in data:
            return data
        for k in ["data", "history", "list", "results"]:
            if k in data and isinstance(data[k], list) and len(data[k]) > 0:
                return data[k][0]
    return None

def format_single_item(item):
    """Đọc dữ liệu chính xác từ item JSON và hạ về chữ thường"""
    if not isinstance(item, dict):
        return "không có dữ liệu hợp lệ."

    phien_raw = item.get("phien")
    phien = str(phien_raw).lower() if phien_raw is not None else "---"
    
    kq_raw = item.get("kết quả") or item.get("ket_qua")
    kq = str(kq_raw).lower() if kq_raw is not None else "---"
    
    tong_raw = item.get("tổng") or item.get("tong")
    tong = str(tong_raw).lower() if tong_raw is not None else "---"
    
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
            latest = extract_latest_item(raw_data)
            
            if latest and isinstance(latest, dict):
                current_phien = latest.get("phien")
                
                if current_phien is not None:
                    current_phien_str = str(current_phien)
                    
                    # Chỉ phát tin nhắn khi phát hiện mã phiên khác phiên trước đó
                    if current_phien_str != str(last_phien):
                        last_phien = current_phien_str
                        message = format_single_item(latest)
                        
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
    latest = extract_latest_item(raw_data)
    
    if latest:
        msg = "✅ đã bật tự động nhận dữ liệu bàn md5!\n\n" + format_single_item(latest)
    else:
        msg = "✅ đã bật tự động!\n\n⚠️ chưa tải được dữ liệu từ api. vui lòng đợi phiên tiếp theo..."
        
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
