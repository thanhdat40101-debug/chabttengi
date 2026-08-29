import asyncio
import logging
import os
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- WEB SERVER ĐỂ KEEP-ALIVE TRÊN RENDER ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot đang chạy!", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# --- CẤU HÌNH API & BOT ---
TELEGRAM_BOT_TOKEN = "8662342747:AAFGSyvziio3uPNdKbhnhJMee33YbLaV290"

# API Phiên hiện tại & API Lịch sử MD5
API_CURRENT = "https://kwinstore.com/hitclub/md5/8167b2c16888dae174a454f493022e22242f35288df59f41"
API_HISTORY = "https://kwinstore.com/hitclub/md5/history/8167b2c16888dae174a454f493022e22242f35288df59f41"

INTERVAL_SECONDS = 3  # Quét dữ liệu mỗi 3 giây

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

active_chats = set()
last_phien = None

def fetch_json(url):
    """Hàm phụ trợ lấy dữ liệu JSON từ API"""
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logging.error(f"Lỗi khi lấy dữ liệu từ {url}: {e}")
    return None

def format_combined_message(current_data, history_data):
    """Định dạng kết hợp Bàn MD5 và Lịch sử MD5"""
    msg = ""
    
    # 1. PHẦN BÀN MD5 (Phiên hiện tại)
    if isinstance(current_data, dict):
        inner_cur = current_data.get("data", {})
        if isinstance(inner_cur, dict):
            phien = inner_cur.get("phien", "---")
            ket_qua = inner_cur.get("ket_qua", "---")
            tong = inner_cur.get("tong", "---")
            x1 = inner_cur.get("xuc_xac_1", "-")
            x2 = inner_cur.get("xuc_xac_2", "-")
            x3 = inner_cur.get("xuc_xac_3", "-")
            thoi_gian = inner_cur.get("thoi_gian", "---")

            msg += (
                f"🎲 **BÀN MD5 HIỆN TẠI**\n"
                f"• Phiên: `{phien}`\n"
                f"• Kết quả: {ket_qua} (Tổng: {tong})\n"
                f"• Xúc xắc: {x1} - {x2} - {x3}\n"
                f"• Thời gian: {thoi_gian}\n\n"
            )
    
    # 2. PHẦN LỊCH SỬ BÀN MD5 (Lấy 5 phiên gần nhất)
    msg += "📜 **LỊCH SỬ BÀN MD5 (5 phiên gần nhất)**\n"
    
    # Tự động nhận diện mảng lịch sử (dù trả về list trực tiếp hay nằm trong key "data")
    history_list = []
    if isinstance(history_data, list):
        history_list = history_data
    elif isinstance(history_data, dict):
        history_list = history_data.get("data", [])
    
    if isinstance(history_list, list) and len(history_list) > 0:
        # Lấy 5 phiên mới nhất
        recent_items = history_list[:5]
        for item in recent_items:
            if isinstance(item, dict):
                h_phien = item.get("phien", "---")
                h_kq = item.get("ket_qua", "---")
                h_tong = item.get("tong", "---")
                h_x1 = item.get("xuc_xac_1", "-")
                h_x2 = item.get("xuc_xac_2", "-")
                h_x3 = item.get("xuc_xac_3", "-")
                
                msg += f"• #{h_phien}: {h_kq} ({h_tong}) | [{h_x1}-{h_x2}-{h_x3}]\n"
    else:
        msg += "• Chưa có dữ liệu lịch sử.\n"

    return msg

async def auto_fetch_loop(app: Application):
    """Vòng lặp quét API - Chỉ gửi khi có PHIÊN MỚI"""
    global last_phien
    while True:
        if active_chats:
            cur_res = fetch_json(API_CURRENT)
            if cur_res and isinstance(cur_res, dict):
                inner_data = cur_res.get("data", {})
                current_phien = inner_data.get("phien") if isinstance(inner_data, dict) else None
                
                # Khi có phiên mới, lấy tiếp dữ liệu Lịch sử và gửi
                if current_phien and current_phien != last_phien:
                    last_phien = current_phien
                    
                    # Lấy dữ liệu API Lịch sử
                    hist_res = fetch_json(API_HISTORY)
                    
                    # Ghép thông tin thành 1 tin nhắn duy nhất
                    message = format_combined_message(cur_res, hist_res)
                    
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
    await update.message.reply_text(
        "✅ Đã bật tự động nhận dữ liệu Bàn MD5 & Lịch sử MD5!\n"
        "Bot sẽ tự động gửi thông báo khi xuất hiện PHIÊN MỚI."
    )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in active_chats:
        active_chats.remove(chat_id)
        await update.message.reply_text("⛔ Đã tắt tự động nhận dữ liệu.")
    else:
        await update.message.reply_text("Bạn chưa bật chế độ tự động.")

async def post_init(application: Application):
    asyncio.create_task(auto_fetch_loop(application))

def main():
    # Chạy Web Server giữ kết nối cho Render
    threading.Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))

    print("Bot đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    main()
