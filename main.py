import os
import time
import requests
import telebot
from telebot import types
import yt_dlp

# --- НАСТРОЙКИ ---
MY_ADMIN_ID = 6647613921  # Твой Telegram ID

# Умная проверка токена: если на сервере есть скрытая настройка, берем её.
# Если запускаешь на ПК — автоматически включится твой обычный токен.
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    BOT_TOKEN = '8889472880:AAF0-z3ybjo1qaYqGavg6PZsUoUs3oUlvnA'

bot = telebot.TeleBot(BOT_TOKEN)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

messages_db = {}
SLEEP_FILE = "sleep_mode.txt"


def is_sleeping():
    """Проверяет, включен ли режим сна"""
    return os.path.exists(SLEEP_FILE)


def download_tiktok(url: str, user_id: int) -> str | None:
    output_template = os.path.join(DOWNLOAD_DIR, f"{user_id}_%(id)s.%(ext)s")
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)
    except Exception as e:
        print(f"Ошибка при скачивании TikTok: {e}")
        return None


def search_and_download_track(query: str, user_id: int) -> tuple[str | None, str | None]:
    output_template = os.path.join(DOWNLOAD_DIR, f"{user_id}_track_%(id)s.%(ext)s")
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=True)
            if 'entries' in info and len(info['entries']) > 0:
                video_info = info['entries'][0]
                video_url = video_info.get('webpage_url')
                filename = ydl.prepare_filename(video_info)
                return filename, video_url
    except Exception as e:
        print(f"Ошибка при поиске/скачивании трека: {e}")
    return None, None


def get_streaming_links(youtube_url: str) -> str:
    if not youtube_url:
        return ""
    api_url = f"https://api.songlink.io/v1-alpha.1/links?url={youtube_url}&userCountry=RU"
    try:
        response = requests.get(api_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            links_data = data.get("linksByPlatform", {})
            platforms = {
                "spotify": "🟢 Spotify", "appleMusic": "🍎 Apple Music",
                "youtubeMusic": "❤️ YouTube Music", "yandex": "🟡 Яндекс Музыка", "vk": "🔵 VK Музыка"
            }
            text_links = []
            for key, name in platforms.items():
                if key in links_data:
                    url = links_data[key].get("url")
                    text_links.append(f"[{name}]({url})")
            if text_links:
                return "🎵 *Слушать на площадках:*\n" + " | ".join(text_links)
    except (requests.exceptions.RequestException, Exception) as e:
        print(f"Временный сбой сети при получении ссылок стримингов: {e}")
    return ""


# Фильтр для проверки сна перед выполнением любой команды
@bot.message_handler(func=lambda message: is_sleeping())
def echo_sleeping(message):
    if message.from_user.id == MY_ADMIN_ID:
        if message.text == "/start":
            if os.path.exists(SLEEP_FILE):
                os.remove(SLEEP_FILE)
            bot.send_message(MY_ADMIN_ID, "☀️ Бот проснулся и готов к работе!")
            return

    bot.send_message(
        message.chat.id,
        "💤 **Бот сейчас спит так же, как и его автор.**\n\nНе переживай, когда я проснусь, твои действия сразу же заработают! Можешь написать свой запрос прямо сейчас.",
        parse_mode="Markdown"
    )


# 1. Обработка команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.from_user.id == MY_ADMIN_ID:
        bot.send_message(MY_ADMIN_ID, "Привет, админ! Бот запущен и готов к работе.")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_suggest = types.KeyboardButton("✍️ Написать анонимно")
    btn_music = types.KeyboardButton("🎵 Найти песню")
    markup.add(btn_suggest, btn_music)

    welcome_text = (
        "🤫 **Привет! Это твой многофункциональный бот-помощник.**\n\n"
        "⚡ **Что я умею:**\n"
        "1. **Скачивать TikTok:** Пришли мне ссылку на видео, и я скину его файлом без вотяных знаков!\n"
        "2. **Скачивать Музыку:** Нажми кнопку «🎵 Найти песню» или просто напиши название трека!\n"
        "3. **Анонимная связь:** Нажми кнопку предложки, чтобы тайно написать админу."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)


# 2. Обработка ответов админа (Reply)
@bot.message_handler(func=lambda message: message.reply_to_message is not None)
def handle_admin_reply(message):
    if message.from_user.id != MY_ADMIN_ID:
        return
    reply_id = message.reply_to_message.message_id
    if reply_id in messages_db:
        original_user_id = messages_db[reply_id]
        try:
            bot.copy_message(chat_id=original_user_id, from_chat_id=message.chat.id, message_id=message.message_id)
            bot.send_message(MY_ADMIN_ID, "✅ Ответ успешно отправлен пользователю!")
        except Exception as e:
            bot.send_message(MY_ADMIN_ID, f"❌ Не удалось отправить ответ. Ошибка: {e}")
    else:
        bot.send_message(MY_ADMIN_ID, "❌ Ошибка: не удалось связать ответ (сообщение устарело).")


# 3. Перехват ссылок на TikTok
@bot.message_handler(func=lambda message: message.text is not None and "tiktok.com" in message.text)
def handle_tiktok(message):
    user_id = message.from_user.id
    status_msg = bot.send_message(message.chat.id, "⏳ Скачиваю видео из TikTok, подожди секунду...")
    video_path = download_tiktok(message.text, user_id)

    if video_path and os.path.exists(video_path):
        try:
            with open(video_path, 'rb') as video_file:
                bot.send_video(chat_id=message.chat.id, video=video_file, caption="😁 Держи видосик <3 ",
                               reply_to_message_id=message.message_id)
        except Exception as e:
            bot.send_message(message.chat.id, "❌ Не удалось отправить видео.")
            print(f"Ошибка отправки ТТ: {e}")
        finally:
            if os.path.exists(video_path):
                os.remove(video_path)
    else:
        bot.send_message(message.chat.id, "❌ Не удалось скачать видео. Проверь ссылку.")
    bot.delete_message(message.chat.id, status_msg.message_id)


# 4. Логика кнопки "Найти песню"
@bot.message_handler(func=lambda message: message.text == "🎵 Найти песню")
def ask_for_track(message):
    msg = bot.send_message(message.chat.id, "Введите название трека или исполнителя (например: *Скриптонит - Ламба*):",
                           parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_track_search)


def process_track_search(message):
    if is_sleeping():
        echo_sleeping(message)
        return
    if not message.text or message.text in ["✍️ Написать анонимно", "🎵 Найти песню"] or message.text.startswith("/"):
        bot.send_message(message.chat.id, "Поиск отменен.")
        return

    query = message.text
    status_msg = bot.send_message(message.chat.id, f"🔍 Ищу трек «{query}» по всем базам и площадкам...")
    bot.send_chat_action(message.chat.id, 'upload_document')
    file_path, yt_url = search_and_download_track(query, message.from_user.id)

    if file_path and os.path.exists(file_path):
        mp3_path = os.path.splitext(file_path)[0] + ".mp3"
        try:
            if file_path != mp3_path:
                os.rename(file_path, mp3_path)
        except Exception as e:
            print(f"Ошибка переименования: {e}")
            mp3_path = file_path

        links_text = get_streaming_links(yt_url)
        caption = f"🎶 Результат поиска по запросу: *{query}*\n\n{links_text}" if links_text else f"🎶 Держи трек по запросу: *{query}*"

        try:
            with open(mp3_path, 'rb') as audio_file:
                bot.send_audio(chat_id=message.chat.id, audio=audio_file, caption=caption, parse_mode="Markdown",
                               reply_to_message_id=message.message_id)
        except Exception as e:
            bot.send_message(message.chat.id, "❌ Ошибка при отправке аудиофайла.")
            print(f"Ошибка отправки аудио: {e}")
        finally:
            if os.path.exists(mp3_path):
                os.remove(mp3_path)
    else:
        bot.send_message(message.chat.id, "❌ Ничего не найдено. Попробуй уточнить название или автора трека.")
    bot.delete_message(message.chat.id, status_msg.message_id)


# 5. Пересылка анонимной предложки
@bot.message_handler(
    content_types=['text', 'audio', 'document', 'photo', 'sticker', 'video', 'video_note', 'voice', 'location',
                   'contact'])
def forward_to_admin(message):
    if message.from_user.id == MY_ADMIN_ID:
        return
    if message.text == "✍️ Написать анонимно":
        bot.send_message(message.chat.id, "Отлично! Отправь мне текст, photo или медиафайл прямо сейчас 👇")
        return

    try:
        first_name = message.from_user.first_name or ""
        last_name = message.from_user.last_name or ""
        full_name = f"{first_name} {last_name}".strip() or "Скрыто"

        if message.from_user.username:
            username_text = f"🔗 Юзернейм: @{message.from_user.username}"
        else:
            username_text = "🔗 Юзернейм: отсутствует"

        info_text = f"""📩 **Новая анонимная предложка!**

👤 Ник/Имя: {full_name}
{username_text}
🆔 ID: `{message.from_user.id}`"""

        bot.send_message(MY_ADMIN_ID, info_text, parse_mode="Markdown")
        sent_msg = bot.copy_message(chat_id=MY_ADMIN_ID, from_chat_id=message.chat.id, message_id=message.message_id)
        messages_db[sent_msg.message_id] = message.from_user.id
        bot.send_message(message.chat.id, "🚀 Успешно отправлено анонимно!")
    except Exception as e:
        print(f"Ошибка пересылки админу: {e}")


if __name__ == "__main__":
    if os.path.exists(SLEEP_FILE):
        os.remove(SLEEP_FILE)
    print("Бот 'TikTok + Поиск Музыки + Predlozhka' успешно запущен...")

    # Исправленный бесконечный опрос серверов Telegram
    bot.infinity_polling()