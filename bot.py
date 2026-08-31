import asyncio
import json
import logging
import os
import threading
import requests
from flask import Flask
from telegram import Update, BotCommand
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
HISTORY_FILE = "history.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

active_chats = set()
last_phien = None

# --- QUẢN LÝ LƯU TRỮ LỊCH SỬ RA FILE (KHÔNG BỊ XÓA MẤT) ---
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Lỗi đọc file history: {e}")
    return {}

def save_history(data):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Lỗi ghi file history: {e}")

# Cache lịch sử dự đoán: { "phien_id": "TÀI" / "XỈU" }
predictions_history = load_history()

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
    if not data:
        return []
    
    raw_list = []
    if isinstance(data, list):
        raw_list = data
    elif isinstance(data, dict):
        for k in ["data", "history", "list", "results"]:
            if k in data and isinstance(data[k], list):
                raw_list = data[k]
                break
        if not raw_list and ("phien" in data or "phiên" in data):
            raw_list = [data]

    completed_items = []
    for item in raw_list:
        if isinstance(item, dict):
            d1 = item.get("d1")
            kq = item.get("kết quả") or item.get("ket_qua") or item.get("result")
            if (d1 is not None and str(d1) != "-") or (kq and str(kq) != "---"):
                completed_items.append(item)
                
    return completed_items

def get_phien_id(item):
    if not isinstance(item, dict):
        return None
    for k in ["phiên", "phien", "session", "id", "code"]:
        if k in item and item[k] is not None:
            return str(item[k])
    return None

def get_kq_type(item):
    if not isinstance(item, dict):
        return 'TÀI'
    
    kq = str(item.get("kết quả") or item.get("ket_qua") or item.get("result") or "").upper()
    if "TÀI" in kq or "TAI" in kq:
        return 'TÀI'
    if "XỈU" in kq or "XIU" in kq:
        return 'XỈU'
        
    tong = item.get("tổng") or item.get("tong") or item.get("total")
    if tong is not None:
        try:
            return 'TÀI' if int(tong) >= 11 else 'XỈU'
        except Exception:
            pass
            
    d1, d2, d3 = item.get("d1"), item.get("d2"), item.get("d3")
    if d1 is not None and d2 is not None and d3 is not None:
        try:
            return 'TÀI' if (int(d1) + int(d2) + int(d3)) >= 11 else 'XỈU'
        except Exception:
            pass
            
    return 'TÀI'

def generate_cau_string(items, limit=10):
    recent = items[:limit]
    recent_reversed = list(reversed(recent))
    
    cau_symbols = []
    for item in recent_reversed:
        t_or_x = get_kq_type(item)
        if t_or_x == 'TÀI':
            cau_symbols.append("🔴")
        else:
            cau_symbols.append("⚪")
            
    return "".join(cau_symbols)

# --- THUẬT TOÁN MỚI: SMART CHAOS ENGINE (PHÂN PHỐI BIÊN ĐỘ) ---
def smart_chaos_engine(items):
    """Mô phỏng thuật toán Smart Chaos Engine phân tích biên độ tổng điểm"""
    if not items or len(items) < 3:
        return "TÀI", 85.0, "🔥 Smart Chaos Engine: Kích hoạt mô hình phân phối biên độ"

    totals = []
    for item in items[:10]:
        t = item.get("tổng") or item.get("tong")
        if t is not None:
            try:
                totals.append(int(t))
            except Exception:
                pass
        else:
            d1 = item.get("d1", 0)
            d2 = item.get("d2", 0)
            d3 = item.get("d3", 0)
            try:
                totals.append(int(d1) + int(d2) + int(d3))
            except Exception:
                pass

    if len(totals) < 3:
        return "TÀI", 88.5, "🔥 Smart Chaos Engine: Kích hoạt mô hình phân phối biên độ"

    # Tính biến động biên độ
    avg_total = sum(totals[:5]) / min(5, len(totals))
    last_type = get_kq_type(items[0])
    
    # Đoán bẻ hoặc theo biên độ chuẩn
    if avg_total > 11.5:
        prediction = "XỈU"
        confidence = round(85.0 + (avg_total - 11.5) * 2.5, 1)
    elif avg_total < 9.5:
        prediction = "TÀI"
        confidence = round(85.0 + (9.5 - avg_total) * 2.5, 1)
    else:
        prediction = "XỈU" if last_type == "TÀI" else "TÀI"
        confidence = 94.5

    confidence = min(98.5, max(75.0, confidence))
    analysis = "🔥 Smart Chaos Engine: Kích hoạt mô hình phân phối biên độ"
    
    return prediction, confidence, analysis

def get_stat_by_count(items, count):
    """Tính tỷ lệ chính xác dựa vào lịch sử dự đoán thực tế đã lưu"""
    if not items:
        return f"Chưa đủ dữ liệu cho {count} tay"
    
    wins = 0
    total = 0
    
    for item in items[:count]:
        pid = get_phien_id(item)
        if pid in predictions_history:
            actual = get_kq_type(item)
            pred = predictions_history[pid]
            if pred == actual:
                wins += 1
            total += 1
            
    if total == 0:
        return f"0/{count} (Chưa có lịch sử đối soát)"
        
    rate = round((wins / total) * 100)
    return f"{wins}/{total} ({rate}%)"

def calculate_accuracy_stats(items):
    stats_msg = (
        f"📊 **thống kê độ chính xác thực tế:**\n"
        f"• 10 tay gần nhất: **{get_stat_by_count(items, 10)}**\n"
        f"• 20 tay gần nhất: **{get_stat_by_count(items, 20)}**\n"
        f"• 30 tay gần nhất: **{get_stat_by_count(items, 30)}**\n"
        f"• 50 tay gần nhất: **{get_stat_by_count(items, 50)}**"
    )
    return stats_msg

def format_full_analysis(items):
    if not items:
        return "không có dữ liệu api hợp lệ."

    latest = items[0]
    phien_id = get_phien_id(latest) or "---"
    
    kq_raw = latest.get("kết quả") or latest.get("ket_qua") or "---"
    kq = str(kq_raw).lower()
    
    tong_raw = latest.get("tổng") or latest.get("tong") or "---"
    tong = str(tong_raw).lower()
    
    d1 = latest.get("d1", "-")
    d2 = latest.get("d2", "-")
    d3 = latest.get("d3", "-")
    
    # Kiểm tra xem dự đoán của phiên vừa ra có đúng không
    check_prev_str = ""
    if phien_id in predictions_history:
        prev_pred = predictions_history[phien_id]
        actual_type = get_kq_type(latest)
        if prev_pred == actual_type:
            check_prev_str = f"🎯 **kiểm tra dự đoán phiên này:** ✅ **đúng** (đã đoán: {prev_pred})\n"
        else:
            check_prev_str = f"🎯 **kiểm tra dự đoán phiên này:** ❌ **sai** (đã đoán: {prev_pred} | thực tế: {actual_type})\n"

    cau_symbols = generate_cau_string(items, 10)
    
    # Chạy thuật toán Smart Chaos Engine cho phiên tiếp theo
    pred, conf, analysis_text = smart_chaos_engine(items)
    
    # Lưu dự đoán phiên tiếp theo vào file JSON
    try:
        next_phien_id = str(int(phien_id) + 1)
        predictions_history[next_phien_id] = pred
        save_history(predictions_history)
    except Exception:
        pass

    stats_text = calculate_accuracy_stats(items)
    
    msg = (
        f"🎲 ------ **dự đoán hitclub md5** ------\n\n"
        f"=== **kết quả** ===\n"
        f"• phiên: `{phien_id}`\n"
        f"• xúc xắc: {d1}-{d2}-{d3}\n"
        f"• tổng: {tong}\n"
        f"• kết quả: {kq}\n"
        f"{check_prev_str}"
        f"• cầu (10 phiên): {cau_symbols}\n\n"
        f"=== **dự đoán phiên tiếp theo** ===\n"
        f"🎯 dự đoán: **{pred}**\n"
        f"📈 độ tin cậy: {conf}%\n"
        f"💡 phân tích: {analysis_text}\n\n"
        f"-----------------------------------\n"
        f"{stats_text}"
    )
    return msg

async def auto_fetch_loop(app: Application):
    global last_phien
    while True:
        if active_chats:
            raw_data = fetch_json(API_MD5_HISTORY)
            items = extract_history_items(raw_data)
            
            if items and len(items) > 0:
                latest = items[0]
                current_phien = get_phien_id(latest)
                
                if current_phien is not None:
                    current_phien_str = str(current_phien)
                    
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

# --- CÁC HÀM XỬ LÝ LỆNH ---
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

async def handle_stat_command(update: Update, context: ContextTypes.DEFAULT_TYPE, count: int):
    raw_data = fetch_json(API_MD5_HISTORY)
    items = extract_history_items(raw_data)
    if not items:
        await update.message.reply_text("⚠️ chưa tải được dữ liệu từ api.")
        return
        
    res = get_stat_by_count(items, count)
    msg = f"📊 **thống kê độ chính xác {count} tay gần nhất:**\n👉 Kết quả: **{res}**"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def thongke10(u, c): await handle_stat_command(u, c, 10)
async def thongke20(u, c): await handle_stat_command(u, c, 20)
async def thongke30(u, c): await handle_stat_command(u, c, 30)
async def thongke40(u, c): await handle_stat_command(u, c, 40)
async def thongke50(u, c): await handle_stat_command(u, c, 50)
async def thongke60(u, c): await handle_stat_command(u, c, 60)
async def thongke70(u, c): await handle_stat_command(u, c, 70)
async def thongke80(u, c): await handle_stat_command(u, c, 80)
async def thongke90(u, c): await handle_stat_command(u, c, 90)
async def thongke100(u, c): await handle_stat_command(u, c, 100)

async def post_init(application: Application):
    commands = [
        BotCommand("start", "bật tự động dự đoán"),
        BotCommand("stop", "tắt tự động dự đoán"),
        BotCommand("thongke10", "xem thống kê 10 tay"),
        BotCommand("thongke20", "xem thống kê 20 tay"),
        BotCommand("thongke30", "xem thống kê 30 tay"),
        BotCommand("thongke40", "xem thống kê 40 tay"),
        BotCommand("thongke50", "xem thống kê 50 tay"),
        BotCommand("thongke60", "xem thống kê 60 tay"),
        BotCommand("thongke70", "xem thống kê 70 tay"),
        BotCommand("thongke80", "xem thống kê 80 tay"),
        BotCommand("thongke90", "xem thống kê 90 tay"),
        BotCommand("thongke100", "xem thống kê 100 tay"),
    ]
    await application.bot.set_my_commands(commands)
    asyncio.create_task(auto_fetch_loop(application))

def main():
    threading.Thread(target=run_web, daemon=True).start()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    
    app.add_handler(CommandHandler("thongke10", thongke10))
    app.add_handler(CommandHandler("thongke20", thongke20))
    app.add_handler(CommandHandler("thongke30", thongke30))
    app.add_handler(CommandHandler("thongke40", thongke40))
    app.add_handler(CommandHandler("thongke50", thongke50))
    app.add_handler(CommandHandler("thongke60", thongke60))
    app.add_handler(CommandHandler("thongke70", thongke70))
    app.add_handler(CommandHandler("thongke80", thongke80))
    app.add_handler(CommandHandler("thongke90", thongke90))
    app.add_handler(CommandHandler("thongke100", thongke100))

    app.run_polling()

if __name__ == "__main__":
    main()
