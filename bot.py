import asyncio
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- CẤU HÌNH ---
TELEGRAM_BOT_TOKEN = "8662342747:AAEBP4wIDnUD4Ts-uU2KHhIMhv_QGH-bi4Y"
DATA_API_URL = "https://kwinstore.com/hitclub/md5/8167b2c16888dae174a454f493022e22242f35288df59f41"
INTERVAL_SECONDS = 5  # Thời gian quét lại dữ liệu (tính bằng giây)

# Cấu hình log để dễ theo dõi lỗi
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Lưu trữ các Chat ID đăng ký nhận dữ liệu tự động
active_chats = set()
last_data_hash = None  # Giúp tránh gửi lại dữ liệu trùng lặp nếu API chưa cập nhật phiên mới

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
    """Định dạng dữ liệu trả về từ API thành tin nhắn đẹp mắt"""
    if isinstance(data, dict):
        text = "<b>=== DỮ LIỆU CẬP NHẬT TỰ ĐỘNG ===</b>\n"
        for key, value in data.items():
            text += f"<b>{key}:</b> <code>{value}</code>\n"
        return text
    return f"Dữ liệu: <code>{str(data)}</code>"

async def auto_fetch_loop(app: Application):
    """Vòng lặp tự động lấy dữ liệu và gửi cho người dùng"""
    global last_data_hash
    while True:
        if active_chats:
            data = fetch_api_data()
            if data:
                # Chuyển dữ liệu thành chuỗi để kiểm tra trùng lặp
                current_data_str = str(data)
                
                # Chỉ gửi khi có dữ liệu mới (phiên mới)
                if current_data_str != last_data_hash:
                    last_data_hash = current_data_str
                    message = format_message(data)
                    
                    # Gửi tin nhắn đến tất cả các chat đang bật tự động
                    for chat_id in list(active_chats):
                        try:
                            await app.bot.send_message(
                                chat_id=chat_id, 
                                text=message, 
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            logging.error(f"Lỗi gửi tin tới chat {chat_id}: {e}")
        
        await asyncio.sleep(INTERVAL_SECONDS)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /start: Bật tự động nhận dữ liệu"""
    chat_id = update.effective_chat.id
    active_chats.add(chat_id)
    await update.message.reply_text(
        "✅ **Đã bật chế độ tự động lấy dữ liệu bàn T!**\n"
        "Bot sẽ liên tục quét và gửi thông tin mới nhất cho bạn.\n"
        "Gửi /stop để dừng lại."
    )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /stop: Tắt tự động"""
    chat_id = update.effective_chat.id
    if chat_id in active_chats:
        active_chats.remove(chat_id)
        await update.message.reply_text("⛔ **Đã tắt tự động nhận dữ liệu.**")
    else:
        await update.message.reply_text("Bạn chưa bật chế độ tự động.")

async def post_init(application: Application):
    """Khởi chạy vòng lặp tự động ngầm khi Bot bắt đầu"""
    asyncio.create_task(auto_fetch_loop(application))

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))

    print("Bot đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    main()
