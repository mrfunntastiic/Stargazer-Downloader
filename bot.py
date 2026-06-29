import os
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
import re

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

if not TOKEN or TOKEN == "your_telegram_bot_token_here":
    print("Please set TELEGRAM_BOT_TOKEN in .env")
    exit(1)

bot = telebot.TeleBot(TOKEN)

# URL Regex
URL_PATTERN = re.compile(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+')


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(
        message,
        "👋 Welcome to Stargazer Bot!\n\n"
        "Just send me any video link (YouTube, TikTok, Instagram, Twitter, etc.) "
        "and I will help you download it as MP4 or MP3."
    )


@bot.message_handler(regexp=URL_PATTERN)
def handle_url(message):
    url = re.search(URL_PATTERN, message.text).group(0)
    
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🎬 Video MP4", callback_data=f"dl|video|{url}"),
        InlineKeyboardButton("🎵 Audio MP3", callback_data=f"dl|audio|{url}")
    )
    
    bot.reply_to(message, "Link detected! Choose format:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith('dl|'))
def callback_query(call):
    _, fmt, url = call.data.split('|', 2)
    
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        "⏳ Downloading and processing... Please wait. (This might take a few minutes for large files)",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    
    try:
        # Call backend API
        response = requests.post(
            f"{BASE_URL}/api/bot/download",
            json={"url": url, "format": fmt},
            timeout=600 # 10 minutes timeout for big files
        )
        
        if response.status_code == 200:
            data = response.json()
            download_link = f"{BASE_URL}{data['download_url']}"
            
            # Use public URL if available (replace localhost for VPS deployment)
            public_url = os.getenv("PUBLIC_URL", BASE_URL)
            if public_url != BASE_URL:
                download_link = f"{public_url}{data['download_url']}"
                
            bot.edit_message_text(
                f"✅ **Download Ready!**\n\n"
                f"Format: {fmt.upper()}\n"
                f"Link: [Click here to download]({download_link})\n\n"
                f"*(Link expires in 10 minutes)*",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        else:
            err = response.json().get("detail", "Unknown error")
            bot.edit_message_text(
                f"❌ Error: {err}",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )
            
    except Exception as e:
        bot.edit_message_text(
            f"❌ Failed to process request: {str(e)}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )

print("Bot is running...")
bot.infinity_polling()