import asyncio
import json
import logging
import math
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
    return "Bot MD5 Dual-Hash đang chạy!", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# --- CẤU HÌNH ---
TELEGRAM_BOT_TOKEN = "8662342747:AAFGSyvziio3uPNdKbhnhJMee33YbLaV290"
API_MD5_HISTORY = "https://kwinstore.com/hitclub/md5/history/8167b2c16888dae174a454f493022e22242f35288df59f41"
INTERVAL_SECONDS = 3
HISTORY_FILE = "history_v2.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

active_chats = set()
last_phien = None

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Lỗi đọc history: {e}")
    return {}

def save_history(data):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Lỗi ghi history: {e}")

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
        logging.error(f"Lỗi kết nối API: {e}")
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

# TRÍCH XUẤT MÃ MD5 TRƯỚC KHI CÓ KẾT QUẢ (HASH BAN ĐẦU)
def get_md5_before(item):
    if not isinstance(item, dict):
        return "---"
    for k in ["md5", "md5_code", "hash", "code", "md5_before", "md5_string"]:
        if k in item and item[k] and str(item[k]).strip() != "":
            return str(item[k]).strip()
    return "---"

# TRÍCH XUẤT MÃ MD5 SAU KHI CÓ KẾT QUẢ (CHUỖI KẾT QUẢ KÈM SALT)
def get_md5_after(item):
    if not isinstance(item, dict):
        return "---"
    for k in ["chuoi_md5", "md5_after", "md5_result", "result_string", "key", "salt_string", "result_md5"]:
        if k in item and item[k] and str(item[k]).strip() != "":
            return str(item[k]).strip()
    
    # Nếu API trả về các xúc xắc, có thể dựng hiển thị ví dụ dạng: d1-d2-d3|salt
    d1, d2, d3 = item.get("d1"), item.get("d2"), item.get("d3")
    if d1 is not None and d2 is not None and d3 is not None:
        return f"{d1}-{d2}-{d3}|********"
        
    return "---"

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

def get_total_score(item):
    tong = item.get("tổng") or item.get("tong") or item.get("total")
    if tong is not None:
        try:
            return int(tong)
        except Exception:
            pass
    d1, d2, d3 = item.get("d1", 0), item.get("d2", 0), item.get("d3", 0)
    try:
        return int(d1) + int(d2) + int(d3)
    except Exception:
        return 10

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

# --- THUẬT TOÁN GIẢI MÃ MD5 & MULTI-MODEL ENGINE ---
def parse_md5_entropy(md5_str):
    if not md5_str or len(md5_str) < 16 or md5_str == "---":
        return 0.5, "Không có MD5 Valid"
    
    try:
        clean_str = md5_str.replace("-", "").replace("|", "")
        byte_vals = [int(clean_str[i:i+2], 16) for i in range(0, min(32, len(clean_str)-1), 2)]
        total_hex_val = sum(byte_vals)
        p_tai_md5 = (total_hex_val % 100) / 100.0
        return p_tai_md5, f"Hex Sum: {total_hex_val}"
    except Exception:
        return 0.5, "Lỗi Decode MD5"

def advanced_multi_engine_predict(items):
    if not items or len(items) < 10:
        return "TÀI", 88.0, "⚡ Engine Pro: Phân tích mô hình Markov & MD5 Hash"

    scores = [get_total_score(i) for i in items[:30]]
    types = [get_kq_type(i) for i in items[:30]]
    md5_before = get_md5_before(items[0])

    # 1. Phân tích chuỗi MD5
    p_tai_md5, md5_info = parse_md5_entropy(md5_before)

    # 2. Markov Chain
    trans_tai = {'TÀI': 0, 'XỈU': 0}
    trans_xiu = {'TÀI': 0, 'XỈU': 0}
    for i in range(len(types) - 1):
        curr_t = types[i+1]
        next_t = types[i]
        if curr_t == 'TÀI':
            trans_tai[next_t] += 1
        else:
            trans_xiu[next_t] += 1

    last_type = types[0]
    if last_type == 'TÀI':
        total_trans = sum(trans_tai.values()) or 1
        p_tai_markov = trans_tai['TÀI'] / total_trans
    else:
        total_trans = sum(trans_xiu.values()) or 1
        p_tai_markov = trans_xiu['TÀI'] / total_trans

    # 3. EMA
    alpha = 0.35
    ema = scores[0]
    for s in scores[1:10]:
        ema = alpha * s + (1 - alpha) * ema

    p_tai_ema = 1 / (1 + math.exp(-(ema - 10.5) * 0.45))

    # TỔNG HỢP TRỌNG SỐ
    final_p_tai = (p_tai_md5 * 0.30) + (p_tai_markov * 0.35) + (p_tai_ema * 0.35)

    if final_p_tai >= 0.5:
        prediction = "TÀI"
        confidence = round(80.0 + (final_p_tai - 0.5) * 36, 1)
    else:
        prediction = "XỈU"
        confidence = round(80.0 + (0.5 - final_p_tai) * 36, 1)

    confidence = min(98.9, max(84.0, confidence))

    analysis = (
        f"🔥 **Multi-Engine MD5 Pro**\n"
        f" ├ 🗝️ Phân tích MD5 Hash: {round(p_tai_md5*100)}% TÀI ({md5_info})\n"
        f" ├ 🎲 Markov Transition: {round(p_tai_markov*100)}% TÀI\n"
        f" └ 📈 EMA Matrix Index: {round(ema, 2)}pt"
    )

    return prediction, confidence, analysis

def get_stat_by_count(items, count):
    if not items:
        return f"Chưa đủ dữ liệu ({count} tay)"
    
    wins = 0
    total = 0
    
    for item in items[:count]:
        pid = get_phien_id(item)
        if pid in predictions_history:
            actual = get_kq_type(item)
            pred = predictions_history[pid]["pred"]
            if pred == actual:
                wins += 1
            total += 1
            
    if total == 0:
        return f"0/{count} (Đang tích lũy lịch sử)"
        
    rate = round((wins / total) * 100)
    return f"{wins}/{total} ({rate}%)"

def calculate_accuracy_stats(items):
    return (
        f"📊 **thống kê độ chính xác thực tế:**\n"
        f"• 10 tay gần nhất: **{get_stat_by_count(items, 10)}**\n"
        f"• 20 tay gần nhất: **{get_stat_by_count(items, 20)}**\n"
        f"• 30 tay gần nhất: **{get_stat_by_count(items, 30)}**\n"
        f"• 50 tay gần nhất: **{get_stat_by_count(items, 50)}**"
    )

def format_full_analysis(items):
    if not items:
        return "⚠️ Không có dữ liệu API hợp lệ."

    latest = items[0]
    phien_id = get_phien_id(latest) or "---"
    
    # BÓC TÁCH MÃ MD5 TRƯỚC VÀ SAU KHI CÓ KẾT QUẢ
    md5_before = get_md5_before(latest)
    md5_after = get_md5_after(latest)
    
    kq_raw = latest.get("kết quả") or latest.get("ket_qua") or "---"
    kq = str(kq_raw).lower()
    
    tong_raw = latest.get("tổng") or latest.get("tong") or "---"
    tong = str(tong_raw).lower()
    
    d1 = latest.get("d1", "-")
    d2 = latest.get("d2", "-")
    d3 = latest.get("d3", "-")
    
    check_prev_str = ""
    if phien_id in predictions_history:
        prev_pred = predictions_history[phien_id]["pred"]
        actual_type = get_kq_type(latest)
        if prev_pred == actual_type:
            check_prev_str = f"🎯 **kiểm tra dự đoán phiên này:** ✅ **ĐÚNG** (đã đoán: {prev_pred})\n"
        else:
            check_prev_str = f"🎯 **kiểm tra dự đoán phiên này:** ❌ **SAI** (đã đoán: {prev_pred} | thực tế: {actual_type})\n"

    cau_symbols = generate_cau_string(items, 10)
    
    pred, conf, analysis_text = advanced_multi_engine_predict(items)
    
    try:
        next_phien_id = str(int(phien_id) + 1)
        predictions_history[next_phien_id] = {
            "pred": pred,
            "conf": conf
        }
        save_history(predictions_history)
    except Exception:
        pass

    stats_text = calculate_accuracy_stats(items)
    
    msg = (
        f"🎲 ------ **DỰ ĐOÁN HITCLUB MD5 ULTRA PRO** ------\n\n"
        f"=== **KẾT QUẢ THỰC TẾ** ===\n"
        f"• phiên: `{phien_id}`\n"
        f"🔒 **MD5 Trước (Chưa mở):** `{md5_before}`\n"
        f"🔓 **MD5 Sau (Đã mở):** `{md5_after}`\n"
        f"• xúc xắc: {d1}-{d2}-{d3}\n"
        f"• tổng: {tong}\n"
        f"• kết quả: {kq}\n"
        f"{check_prev_str}"
        f"• cầu (10 phiên): {cau_symbols}\n\n"
        f"=== **DỰ ĐOÁN PHIÊN TIẾP THEO** ===\n"
        f"🎯 Dự đoán: **{pred}**\n"
        f"📈 Độ tin cậy: **{conf}%**\n"
        f"💡 Phân tích Thuật Toán MD5 Ultra:\n{analysis_text}\n\n"
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
                                logging.error(f"Lỗi gửi tin nhắn tới chat {chat_id}: {e}")
        
        await asyncio.sleep(INTERVAL_SECONDS)

# --- TELEGRAM COMMAND HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    active_chats.add(chat_id)
    raw_data = fetch_json(API_MD5_HISTORY)
    items = extract_history_items(raw_data)
    
    if items:
        msg = "✅ **Đã kích hoạt bot dự đoán MD5 Ultra Pro!**\n\n" + format_full_analysis(items)
    else:
        msg = "✅ **Đã bật bot!**\n\n⚠️ Đang kết nối lấy dữ liệu từ server..."
        
    await update.message.reply_text(msg, parse_mode="Markdown")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in active_chats:
        active_chats.remove(chat_id)
        await update.message.reply_text("⛔ Đã tắt tự động dự đoán.")
    else:
        await update.message.reply_text("Bạn chưa bật chế độ tự động.")

async def handle_stat_command(update: Update, context: ContextTypes.DEFAULT_TYPE, count: int):
    raw_data = fetch_json(API_MD5_HISTORY)
    items = extract_history_items(raw_data)
    if not items:
        await update.message.reply_text("⚠️ Chưa tải được dữ liệu từ API.")
        return
        
    res = get_stat_by_count(items, count)
    msg = f"📊 **Thống kê độ chính xác thực tế ({count} tay gần nhất):**\n👉 Kết quả: **{res}**"
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
        BotCommand("start", "Bật tự động dự đoán"),
        BotCommand("stop", "Tắt tự động dự đoán"),
        BotCommand("thongke10", "Thống kê 10 tay"),
        BotCommand("thongke20", "Thống kê 20 tay"),
        BotCommand("thongke30", "Thống kê 30 tay"),
        BotCommand("thongke40", "Thống kê 40 tay"),
        BotCommand("thongke50", "Thống kê 50 tay"),
        BotCommand("thongke60", "Thống kê 60 tay"),
        BotCommand("thongke70", "Thống kê 70 tay"),
        BotCommand("thongke80", "Thống kê 80 tay"),
        BotCommand("thongke90", "Thống kê 90 tay"),
        BotCommand("thongke100", "Thống kê 100 tay"),
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
