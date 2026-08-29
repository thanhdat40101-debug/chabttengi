import asyncio
import logging
import os
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- WEB SERVER GIỮ KẾT NỐI (KEEP-ALIVE) ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "bot dang chay!", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# --- CẤU HÌNH TOKEN & API ---
TELEGRAM_BOT_TOKEN = "8662342747:AAFGSyvziio3uPNdKbhnhJMee33YbLaV290"

# Chỉ dùng duy nhất 1 API Lịch sử MD5
API_MD5_HISTORY = "https://kwinstore.com/hitclub/md5/history/8167b2c16888dae174a454f493022e22242f35288df59f41"

INTERVAL_SECONDS = 3  # Quét dữ liệu mỗi 3 giây

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

active_chats = set()
last_phien = None

def fetch_json(url):
    """Hàm lấy dữ liệu JSON từ API"""
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        logging.error(f"Lỗi fetch dữ liệu: {e}")
    return None

def extract_history_list(history_data):
    """Bóc tách mảng lịch sử từ JSON"""
    if not history_data:
        return []
    if isinstance(history_data, list):
        return history_data
    if isinstance(history_data, dict):
        for key in ["data", "history", "list", "results", "rows"]:
            if key in history_data and isinstance(history_data[key], list):
                return history_data[key]
    return []

def format_history_item(item):
    """Đọc từng phiên và chuyển tất cả kí tự về chữ thường"""
    if not isinstance(item, dict):
        return "• #---: --- (---) | ----"
    
    # Mã phiên
    phien = item.get("phien") or item.get("session") or item.get("id") or "---"
    
    # Kết quả (chuyển về chữ thường)
    kq = str(item.get("ket_qua") or item.get("result") or item.get("ketQua") or "---").lower()
    
    # Tổng điểm
    tong = str(item.get("tong") or item.get("total") or item.get("point") or "---").lower()
    
    # Xúc xắc
    x1 = item.get("xuc_xac_1") if item.get("xuc_xac_1") is not None else item.get("dice1")
    x2 = item.get("xuc_xac_2") if item.get("xuc_xac_2") is not None else item.get("dice2")
    x3 = item.get("xuc_xac_3") if item.get("xuc_xac_3") is not None else item.get("dice3")
    
    if x1 is not None and x2 is not None and x3 is not None:
        dice_str = f"{x1}-{x2}-{x3}"
    else:
        dice_str = str(item.get("xuc_xac") or item.get("dices") or "----").lower()
        
    return f"• #{phien}: {kq} (tổng: {tong}) | [{dice_str}]"

def format_all_lowercase_message(md5_hist):
    """Tạo tin nhắn tổng hợp toàn bộ chữ thường"""
    hist_list = extract_history_list(md5_hist)
    
    if not hist_list:
        return "chưa nhận được dữ liệu lịch sử."

    # Lấy thông tin phiên mới nhất (phần tử đầu tiên)
    latest = hist_list[0] if isinstance(hist_list[0], dict) else {}
    latest_phien = latest.get("phien") or latest.get("session") or "---"
    latest_kq = str(latest.get("ket_qua") or latest.get("result") or "---").lower()
    latest_tong = str(latest.get("tong") or latest.get("total") or "---").lower()

    msg = (
        f"📜 **lịch sử bàn md5**\n"
        f"• phiên mới nhất: `{latest_phien}`\n"
        f"• kết quả: {latest_kq} (tổng: {latest_tong})\n\n"
        f"📊 **danh sách 5 phiên gần nhất:**\n"
    )

    for item in hist_list[:5]:
        msg += format_history_item(item) + "\n"

    return msg

async def auto_fetch_loop(app: Application):
    """Vòng lặp chỉ quét duy nhất 1 API Lịch sử MD5"""
    global last_phien
    while True:
        if active_chats:
            hist_res = fetch_json(API_MD5_HISTORY)
            hist_list = extract_history_list(hist_res)
            
            if hist_list and len(hist_list) > 0:
                first_item = hist_list[0] if isinstance(hist_list[0], dict) else {}
                current_phien = first_item.get("phien") or first_item.get("session")
                
                # Phát tin nhắn khi có phiên mới
                if current_phien and current_phien != last_phien:
                    last_phien = current_phien
                    
                    message = format_all_lowercase_message(hist_res)
                    
                    for chat_id in list(active_chats):
                        try:
                            await app.bot.send_message(
                                chat_id=chat_id, 
                                text=message,
                                parse_mode="Markdown"
                            )
                        except Exception as e:
                            logging.error(f"Lỗi gửi tin tới chat {chat_id}: {e}")
        
        await asyncio.sleep(INTERVAL_SECONDS)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    active_chats.add(chat_id)
    await update.message.reply_text("✅ đã bật tự động nhận dữ liệu lịch sử bàn md5 (chữ thường)!")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in active_chats:
        active_chats.remove(chat_id)
        await update.message.reply_text("⛔ đã tắt tự động nhận dữ liệu.")
    else:
        await update.message.reply_text("bạn chưa bật chế độ tự động.")

async def post_init(application: Application):
    asyncio.create_task(auto_fetch_loop(application))

def main():
    threading.Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))

    print("bot dang chay...")
    app.run_polling()

if __name__ == "__main__":
    main()
