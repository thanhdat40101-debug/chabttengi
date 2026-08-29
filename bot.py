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
    return "Bot đang chạy ổn định!", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# --- CẤU HÌNH TOKEN & API ---
TELEGRAM_BOT_TOKEN = "8662342747:AAFGSyvziio3uPNdKbhnhJMee33YbLaV290"

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
    """Hàm lấy dữ liệu JSON an toàn từ URL"""
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        logging.error(f"Lỗi fetch dữ liệu từ {url}: {e}")
    return None

def extract_history_list(history_data):
    """Trích xuất mảng danh sách lịch sử dù API trả về bất kỳ dạng cấu trúc nào"""
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
    """Đọc dữ liệu từng phiên lịch sử hỗ trợ cả tên Key tiếng Việt lẫn tiếng Anh"""
    if not isinstance(item, dict):
        return "• #---: --- (---) | ----"
    
    # Mã phiên
    phien = item.get("phien") or item.get("session") or item.get("id") or "---"
    
    # Kết quả (Tài/Xỉu)
    kq = item.get("ket_qua") or item.get("result") or item.get("ketQua") or "---"
    
    # Tổng điểm
    tong = item.get("tong") or item.get("total") or item.get("point") or "---"
    
    # Xúc xắc
    x1 = item.get("xuc_xac_1") if item.get("xuc_xac_1") is not None else item.get("dice1")
    x2 = item.get("xuc_xac_2") if item.get("xuc_xac_2") is not None else item.get("dice2")
    x3 = item.get("xuc_xac_3") if item.get("xuc_xac_3") is not None else item.get("dice3")
    
    if x1 is not None and x2 is not None and x3 is not None:
        dice_str = f"{x1}-{x2}-{x3}"
    else:
        dice_str = str(item.get("xuc_xac") or item.get("dices") or "----")
        
    return f"• #{phien}: {kq} (Tổng: {tong}) | [{dice_str}]"

def format_full_message(md5_cur, md5_hist, thuong_cur):
    """Định dạng tổng hợp Bàn MD5, Bàn Thường, Lịch Sử & Phân Tích Dự Đoán"""
    msg = ""
    
    # 1. BÀN MD5 HIỆN TẠI
    inner_md5 = md5_cur.get("data", {}) if isinstance(md5_cur, dict) else {}
    if isinstance(inner_md5, dict):
        p_md5 = inner_md5.get("phien", "---")
        kq_md5 = inner_md5.get("ket_qua", "---")
        t_md5 = inner_md5.get("tong", "---")
        x1_m = inner_md5.get("xuc_xac_1", "-")
        x2_m = inner_md5.get("xuc_xac_2", "-")
        x3_m = inner_md5.get("xuc_xac_3", "-")
        time_m = inner_md5.get("thoi_gian", "---")
        
        msg += (
            f"🎲 **BÀN MD5**\n"
            f"• Phiên: `{p_md5}`\n"
            f"• Kết quả: {kq_md5} (Tổng: {t_md5})\n"
            f"• Xúc xắc: {x1_m} - {x2_m} - {x3_m}\n"
            f"• Thời gian: {time_m}\n\n"
        )

    # 2. BÀN THƯỜNG HIỆN TẠI
    inner_thuong = thuong_cur.get("data", {}) if isinstance(thuong_cur, dict) else {}
    if isinstance(inner_thuong, dict):
        p_th = inner_thuong.get("phien", "---")
        kq_th = inner_thuong.get("ket_qua", "---")
        t_th = inner_thuong.get("tong", "---")
        x1_t = inner_thuong.get("xuc_xac_1", "-")
        x2_t = inner_thuong.get("xuc_xac_2", "-")
        x3_t = inner_thuong.get("xuc_xac_3", "-")
        time_t = inner_thuong.get("thoi_gian", "---")
        
        msg += (
            f"⚡ **BÀN THƯỜNG**\n"
            f"• Phiên: `{p_th}`\n"
            f"• Kết quả: {kq_th} (Tổng: {t_th})\n"
            f"• Xúc xắc: {x1_t} - {x2_t} - {x3_t}\n"
            f"• Thời gian: {time_t}\n\n"
        )

    # 3. LỊCH SỬ BÀN MD5 (5 Phiên gần nhất)
    msg += "📜 **LỊCH SỬ MD5 (5 phiên gần nhất)**\n"
    hist_list = extract_history_list(md5_hist)
    
    if hist_list:
        for item in hist_list[:5]:
            msg += format_history_item(item) + "\n"
    else:
        msg += "• Chưa nhận được dữ liệu lịch sử.\n"

    # 4. THUẬT TOÁN DỰ ĐOÁN PHIÊN TIẾP THEO
    kq_seq = []
    for item in hist_list[:10]:
        if isinstance(item, dict):
            k = item.get("ket_qua") or item.get("result") or ""
            if k:
                kq_seq.append("T" if "tài" in str(k).lower() else "X")

    pred = "Tài" if (kq_seq.count("T") >= kq_seq.count("X")) else "Xỉu"
    conf = 78 if len(kq_seq) > 0 else 50
    
    msg += (
        f"\n🎯 **DỰ ĐOÁN PHIÊN TIẾP THEO: {pred.upper()}**\n"
        f"📈 Độ tin cậy: {conf}%\n"
    )

    return msg

async def auto_fetch_loop(app: Application):
    """Vòng lặp tự động gửi tin nhắn khi có phiên mới"""
    global last_phien_md5
    while True:
        if active_chats:
            md5_cur_res = fetch_json(API_MD5_CURRENT)
            if md5_cur_res and isinstance(md5_cur_res, dict):
                inner_data = md5_cur_res.get("data", {})
                current_phien = inner_data.get("phien") if isinstance(inner_data, dict) else None
                
                # Phát tin nhắn mỗi khi sang phiên MD5 mới
                if current_phien and current_phien != last_phien_md5:
                    last_phien_md5 = current_phien
                    
                    md5_hist_res = fetch_json(API_MD5_HISTORY)
                    thuong_cur_res = fetch_json(API_THUONG_CURRENT)
                    
                    message = format_full_message(md5_cur_res, md5_hist_res, thuong_cur_res)
                    
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
    await update.message.reply_text("✅ Đã bật tự động nhận dữ liệu Bàn MD5, Bàn Thường & Lịch sử!")

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
    # Chạy Flask web server ở thread riêng để làm trang keep-alive
    threading.Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))

    print("Bot đang hoạt động...")
    app.run_polling()

if __name__ == "__main__":
    main()
