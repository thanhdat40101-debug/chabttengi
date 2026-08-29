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

# Các đường dẫn API
API_MD5_CURRENT = "https://kwinstore.com/hitclub/md5/8167b2c16888dae174a454f493022e22242f35288df59f41"
API_MD5_HISTORY = "https://kwinstore.com/hitclub/md5/history/8167b2c16888dae174a454f493022e22242f35288df59f41"
API_THUONG_CURRENT = "https://kwinstore.com/hitclub/tx/8167b2c16888dae174a454f493022e22242f35288df59f41"

INTERVAL_SECONDS = 3  # Quét dữ liệu mỗi 3 giây

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

active_chats = set()
last_phien_md5 = None

def fetch_json(url):
    """Hàm phụ trợ lấy dữ liệu JSON từ API"""
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logging.error(f"Lỗi khi lấy dữ liệu từ {url}: {e}")
    return None

def extract_session_info(data_json):
    """Trích xuất thông tin phiên gọn gàng"""
    if not isinstance(data_json, dict):
        return None
    inner = data_json.get("data", {})
    if isinstance(inner, dict):
        return {
            "phien": inner.get("phien", "---"),
            "ket_qua": inner.get("ket_qua", "---"),
            "tong": inner.get("tong", "---"),
            "x1": inner.get("xuc_xac_1", "-"),
            "x2": inner.get("xuc_xac_2", "-"),
            "x3": inner.get("xuc_xac_3", "-"),
            "thoi_gian": inner.get("thoi_gian", "---")
        }
    return None

def format_all_data(md5_cur, md5_hist, thuong_cur):
    """Ghép toàn bộ thông tin Bàn MD5, Lịch sử MD5 và Bàn Thường"""
    msg = ""
    
    # 1. BÀN MD5 HIỆN TẠI
    info_md5 = extract_session_info(md5_cur)
    if info_md5:
        msg += (
            f"🎲 **BÀN MD5**\n"
            f"• Phiên: `{info_md5['phien']}`\n"
            f"• Kết quả: {info_md5['ket_qua']} (Tổng: {info_md5['tong']})\n"
            f"• Xúc xắc: {info_md5['x1']} - {info_md5['x2']} - {info_md5['x3']}\n"
            f"• Thời gian: {info_md5['thoi_gian']}\n\n"
        )

    # 2. BÀN THƯỜNG HIỆN TẠI
    info_thuong = extract_session_info(thuong_cur)
    if info_thuong:
        msg += (
            f"⚡ **BÀN THƯỜNG**\n"
            f"• Phiên: `{info_thuong['phien']}`\n"
            f"• Kết quả: {info_thuong['ket_qua']} (Tổng: {info_thuong['tong']})\n"
            f"• Xúc xắc: {info_thuong['x1']} - {info_thuong['x2']} - {info_thuong['x3']}\n"
            f"• Thời gian: {info_thuong['thoi_gian']}\n\n"
        )
    
    # 3. LỊCH SỬ BÀN MD5 (5 phiên gần nhất)
    msg += "📜 **LỊCH SỬ MD5 (5 phiên gần nhất)**\n"
    history_list = []
    if isinstance(md5_hist, list):
        history_list = md5_hist
    elif isinstance(md5_hist, dict):
        history_list = md5_hist.get("data", [])
    
    if isinstance(history_list, list) and len(history_list) > 0:
        for item in history_list[:5]:
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
    """Vòng lặp tự động quét dữ liệu và đẩy về Telegram khi có phiên mới"""
    global last_phien_md5
    while True:
        if active_chats:
            md5_cur_res = fetch_json(API_MD5_CURRENT)
            if md5_cur_res and isinstance(md5_cur_res, dict):
                inner_data = md5_cur_res.get("data", {})
                current_phien = inner_data.get("phien") if isinstance(inner_data, dict) else None
                
                # Chỉ phát tin nhắn mới khi Bàn MD5 sang phiên mới
                if current_phien and current_phien != last_phien_md5:
                    last_phien_md5 = current_phien
                    
                    # Quét thêm Lịch sử MD5 và Bàn Thường
                    md5_hist_res = fetch_json(API_MD5_HISTORY)
                    thuong_cur_res = fetch_json(API_THUONG_CURRENT)
                    
                    # Tổng hợp nội dung
                    message = format_all_data(md5_cur_res, md5_hist_res, thuong_cur_res)
                    
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
        "✅ Đã bật tự động nhận dữ liệu!\n"
        "Bot sẽ tự động tổng hợp Bàn MD5, Bàn Thường & Lịch sử MD5 mỗi khi có phiên mới."
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
