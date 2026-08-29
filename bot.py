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
        logging.error(f"Lỗi kết nối API: {e}")
    return None

def extract_history_list(history_data):
    if not history_data:
        return []
    if isinstance(history_data, list):
        return history_data
    if isinstance(history_data, dict):
        for key in ["data", "history", "list", "results", "rows"]:
            if key in history_data and isinstance(history_data[key], list):
                return history_data[key]
    return []

def format_all_lowercase_message(md5_hist):
    hist_list = extract_history_list(md5_hist)
    
    if not hist_list:
        return "⚠️ không lấy được dữ liệu từ api (api bị lỗi hoặc đổi cấu trúc)."

    msg = "📜 **lịch sử bàn md5 (chữ thường)**\n\n"
    for item in hist_list[:5]:
        if isinstance(item, dict):
            phien = str(item.get("phien") or item.get("session") or "---").lower()
            kq = str(item.get("ket_qua") or item.get("result") or "---").lower()
            tong = str(item.get("tong") or item.get("total") or "---").lower()
            
            x1 = item.get("xuc_xac_1") if item.get("xuc_xac_1") is not None else item.get("dice1")
            x2 = item.get("xuc_xac_2") if item.get("xuc_xac_2") is not None else item.get("dice2")
            x3 = item.get("xuc_xac_3") if item.get("xuc_xac_3") is not None else item.get("dice3")
            
            if x1 is not None and x2 is not None and x3 is not None:
                dice_str = f"{x1}-{x2}-{x3}"
            else:
                dice_str = str(item.get("xuc_xac") or item.get("dices") or "----").lower()

            msg += f"• #{phien}: {kq} (tổng: {tong}) | [{dice_str}]\n"
        else:
            msg += f"• {str(item).lower()}\n"

    return msg

async def auto_fetch_loop(app: Application):
    global last_phien
    while True:
        if active_chats:
            hist_res = fetch_json(API_MD5_HISTORY)
            hist_list = extract_history_list(hist_res)
            
            if hist_list and len(hist_list) > 0:
                first_item = hist_list[0] if isinstance(hist_list[0], dict) else {}
                current_phien = first_item.get("phien") or first_item.get("session")
                
                # Bắt buộc gửi nếu là phiên mới
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
    
    # Lấy dữ liệu kiểm tra ngay lập tức khi người dùng bấm /start
    hist_res = fetch_json(API_MD5_HISTORY)
    test_msg = format_all_lowercase_message(hist_res)
    
    await update.message.reply_text(
        "✅ đã bật tự động nhận dữ liệu lịch sử bàn md5!\n\n"
        "🔍 **kết quả kiểm tra api hiện tại:**\n" + test_msg,
        parse_mode="Markdown"
    )

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
