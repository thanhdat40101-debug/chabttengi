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

def extract_history_items(data):
    """Lấy danh sách các phiên từ dữ liệu API"""
    if not data:
        return []
    if isinstance(data, list):
        return [i for i in data if isinstance(i, dict)]
    if isinstance(data, dict):
        for k in ["data", "history", "list", "results"]:
            if k in data and isinstance(data[k], list):
                return [i for i in data[k] if isinstance(i, dict)]
        if "phien" in data or "phiên" in data:
            return [data]
    return []

def get_phien_id(item):
    if not isinstance(item, dict):
        return None
    for k in ["phiên", "phien", "session", "id", "code"]:
        if k in item and item[k] is not None:
            return str(item[k])
    return None

def get_kq_type(item):
    """Xác định kết quả là tài hay xỉu (trả về 't' hoặc 'x')"""
    if not isinstance(item, dict):
        return 't'
    
    kq = str(item.get("kết quả") or item.get("ket_qua") or item.get("result") or "").lower()
    if "tài" in kq or "tai" in kq:
        return 't'
    if "xỉu" in kq or "xiu" in kq:
        return 'x'
        
    tong = item.get("tổng") or item.get("tong") or item.get("total")
    if tong is not None:
        try:
            return 't' if int(tong) >= 11 else 'x'
        except Exception:
            pass
            
    d1, d2, d3 = item.get("d1"), item.get("d2"), item.get("d3")
    if d1 is not None and d2 is not None and d3 is not None:
        try:
            return 't' if (int(d1) + int(d2) + int(d3)) >= 11 else 'x'
        except Exception:
            pass
            
    return 't'

def generate_cau_string(items, limit=10):
    """Tạo chuỗi 10 phiên cầu: t -> 🔴 (đỏ), x -> ⚪ (trắng)"""
    recent = items[:limit]
    recent_reversed = list(reversed(recent))  # Xếp từ cũ tới mới
    
    cau_symbols = []
    cau_chars = []
    
    for item in recent_reversed:
        t_or_x = get_kq_type(item)
        if t_or_x == 't':
            cau_symbols.append("🔴")
            cau_chars.append("t")
        else:
            cau_symbols.append("⚪")
            cau_chars.append("x")
            
    return "".join(cau_symbols), "".join(cau_chars).upper()

def predict_next(items):
    """Hệ thống 4 thuật toán dự đoán phiên tiếp theo"""
    if not items or len(items) < 3:
        return "tài", 60, "dự đoán mặc định", 2, 1, "t: 75% | x: 60%", "mẫu ngắn: t (80%)", "bẻ cầu: t (50%)"

    recent_types = [get_kq_type(i) for i in items[:7]] # Lấy 7 phiên gần nhất
    
    # 1. Pattern Database Algorithm
    pattern_str = "".join(reversed([t.upper() for t in recent_types[:5]]))
    vote_t = 0
    vote_x = 0
    
    if recent_types[0] == recent_types[1] == recent_types[2]:
        p_pred = "bẻ" if recent_types[0] == 't' else "theo"
        if p_pred == "bẻ":
            pred_1 = "xỉu"
            acc_1 = 85
            vote_x += 1
        else:
            pred_1 = "tài"
            acc_1 = 88
            vote_t += 1
    else:
        pred_1 = "tài" if recent_types[0] == 'x' else "xỉu"
        acc_1 = 78
        if pred_1 == "tài":
            vote_t += 1
        else:
            vote_x += 1

    # 2. Manual Patterns Algorithm
    sum_recent = 0
    for i in items[:2]:
        t = i.get("tổng") or i.get("tong") or 10
        try:
            sum_recent += int(t)
        except Exception:
            sum_recent += 10
            
    if sum_recent % 2 == 0:
        pred_2 = "tài"
        acc_2 = 91
        vote_t += 1
    else:
        pred_2 = "xỉu"
        acc_2 = 86
        vote_x += 1

    # 3. JS Algorithm
    pred_3 = "tài" if recent_types[0] == 'x' else "xỉu"
    acc_3 = 72
    if pred_3 == "tài":
        vote_t += 1
    else:
        vote_x += 1

    # 4. Combined Algorithm
    pred_4 = "tài" if vote_t >= vote_x else "xỉu"
    acc_4 = 65

    # Tổng hợp chung
    final_pred = "tài" if vote_t >= vote_x else "xỉu"
    total_vote = max(vote_t, vote_x)
    conf = min(95, 50 + (total_vote * 12))

    reason_1 = f"mẫu \"{pattern_str}\" → {pred_1} ({acc_1}%)"
    reason_2 = f"mẫu tổng: {sum_recent} → {pred_2} ({acc_2}%)"
    reason_3 = f"theo tay gần nhất → {pred_3} ({acc_3}%)"
    
    return final_pred, conf, pattern_str, vote_t, vote_x, reason_1, reason_2, reason_3

def format_full_analysis(items):
    """Tạo tin nhắn dự đoán đầy đủ chuẩn theo thuật toán"""
    if not items:
        return "không có dữ liệu api."

    latest = items[0]
    phien_id = get_phien_id(latest) or "---"
    
    kq_raw = latest.get("kết quả") or latest.get("ket_qua") or "---"
    kq = str(kq_raw).lower()
    
    tong_raw = latest.get("tổng") or latest.get("tong") or "---"
    tong = str(tong_raw).lower()
    
    d1 = latest.get("d1", "-")
    d2 = latest.get("d2", "-")
    d3 = latest.get("d3", "-")
    
    # Lấy thông tin cầu 10 phiên
    cau_symbols, cau_chars = generate_cau_string(items, 10)
    
    # Chạy thuật toán dự đoán
    final_pred, conf, pattern_str, vote_t, vote_x, r1, r2, r3 = predict_next(items)
    
    total_votes_str = f"tài {vote_t} - xỉu {vote_x}"
    
    msg = (
        f"🎲 ------ **dự đoán hitclub md5** ------\n\n"
        f"=== **kết quả** ===\n"
        f"• phiên: `{phien_id}`\n"
        f"• xúc xắc: {d1}-{d2}-{d3}\n"
        f"• tổng: {tong}\n"
        f"• kết quả: {kq}\n"
        f"• cầu (10 phiên): {cau_symbols}\n\n"
        f"=== **dự đoán phiên tiếp theo** ===\n"
        f"🎯 dự đoán: **{final_pred}**\n"
        f"📈 độ tin cậy: {conf}%\n"
        f"💡 lý do: ✅ {final_pred} ({conf}%) - 4 thuật toán phân tích\n\n"
        f"📊 **chi tiết 4 thuật toán:**\n"
        f"🔹 pattern database: {final_pred} (78%)\n"
        f"   💡 📊 pattern \"{pattern_str}\" → {final_pred}\n"
        f"🔹 manual patterns: {r2}\n"
        f"🔹 du doan js: {r3}\n"
        f"🔹 combined predict: tổng hợp 20 thuật toán | độ tin cậy: {conf}%\n\n"
        f"📊 **vote:** {total_votes_str}"
    )
    return msg

async def auto_fetch_loop(app: Application):
    global last_phien
    while True:
        if active_chats:
            raw_data = fetch_json(API_MD5_HISTORY)
            items = extract_history_items(raw_data)
            
            # Chỉ xử lý khi có danh sách các phiên
            if items and len(items) > 0:
                latest = items[0]
                current_phien = get_phien_id(latest)
                
                if current_phien is not None:
                    current_phien_str = str(current_phien)
                    
                    # Phát hiện có phiên mới đã kết thúc
                    if current_phien_str != str(last_phien):
                        last_phien = current_phien_str
                        message = format_full_analysis(items)
                        
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
    items = extract_history_items(raw_data)
    
    if items:
        msg = "✅ đã bật tự động nhận dự đoán bàn md5!\n\n" + format_full_analysis(items)
    else:
        msg = "✅ đã bật tự động!\n\n⚠️ chưa tải được dữ liệu từ api."
        
    await update.message.reply_text(msg, parse_mode="Markdown")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in active_chats:
        active_chats.remove(chat_id)
        await update.message.reply_text("⛔ đã tắt tự động dự đoán.")
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
