import asyncio
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- CẤU HÌNH ---
TELEGRAM_BOT_TOKEN = "8662342747:AAEBP4wIDnUD4Ts-uU2KHhIMhv_QGH-bi4Y"
DATA_API_URL = "https://kwinstore.com/hitclub/md5/8167b2c16888dae174a454f493022e22242f35288df59f41"
INTERVAL_SECONDS = 3  # Quét dữ liệu mỗi 3 giây

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

active_chats = set()
last_phien = None  # Luu tru so phien gan nhat de so sanh

def fetch_api_data():
    """Lấy dữ liệu từ API bàn T"""
    try:
        response = requests.get(DATA_API_URL, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logging.error(f"Lỗi khi lấy dữ liệu API: {e}")
    return None

def format_message(data):
    """Định dạng chữ thường, trình bày gọn gàng, dễ nhìn"""
    if not isinstance(data, dict):
        return f"Dữ liệu: {str(data)}"
    
    # Lấy thông tin từ object 'data' bên trong JSON
    inner_data = data.get("data", {})
    if isinstance(inner_data, dict):
        phien = inner_data.get("phien", "---")
        ket_qua = inner_data.get("ket_qua", "---")
        tong = inner_data.get("tong", "---")
        x1 = inner_data.get("xuc_xac_1", "-")
        x2 = inner_data.get("xuc_xac_2", "-")
        x3 = inner_data.get("xuc_xac_3", "-")
        thoi_gian = inner_data.get("thoi_gian", "---")

        msg = (
            f"🎲 Phiên: {phien}\n"
            f"📊 Kết quả: {ket_qua} (Tổng: {tong})\n"
            f"🎯 Xúc xắc: {x1} - {x2} - {x3}\n"
            f"⏰ Thời gian: {thoi_gian}"
        )
        return msg
    
    return str(data)

async def auto_fetch_loop(app: Application):
    """Vòng lặp tự động - Chỉ gửi khi số PHIÊN thay đổi"""
    global last_phien
    while True:
        if active_chats:
            res = fetch_api_data()
            if res and isinstance(res, dict):
                inner_data = res.get("data", {})
                current_phien = inner_data.get("phien") if isinstance(inner_data, dict) else None
                
                # Chỉ gửi tin nhắn khi có số PHIÊN mới
                if current_phien and current_phien != last_phien:
                    last_phien = current_phien
                    message = format_message(res)
                    
                    for chat_id in list(active_chats):
                        try:
                            await app.bot.send_message(
                                chat_id=chat_id, 
                                text=message
                            )
                        except Exception as e:
                            logging.error(f"Lỗi gửi tin tới chat {chat_id}: {e}")
        
        await asyncio.sleep(INTERVAL_SECONDS)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /start: Bật tự động nhận dữ liệu"""
    chat_id = update.effective_chat.id
    active_chats.add(chat_id)
    await update.message.reply_text(
        "✅ Đã bật tự động nhận dữ liệu bàn T!\n"
        "Bot sẽ chỉ gửi tin nhắn khi có PHIÊN MỚI."
    )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /stop: Tắt tự động"""
    chat_id = update.effective_chat.id
    if chat_id in active_chats:
        active_chats.remove(chat_id)
        await update.message.reply_text("⛔ Đã tắt tự động nhận dữ liệu.")
    else:
        await update.message.reply_text("Bạn chưa bật chế độ tự động.")

async def post_init(application: Application):
    asyncio.create_task(auto_fetch_loop(application))

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))

    print("Bot đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    main()
