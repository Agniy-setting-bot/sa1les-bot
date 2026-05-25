import os
import time
import requests
import telebot
from telebot import types
import yt_dlp
from PIL import Image  # Библиотека для обрезки картинок
import threading  # Для запуска веб-сервера в фоне
from http.server import BaseHTTPRequestHandler, HTTPServer  # Безопасный сервер

# --- НАСТРОЙКИ ---
MY_ADMIN_ID = 6647613921  # Твой Telegram ID

# Безопасное получение токена
BOT_TOKEN = os.getenv("BOT_TOKEN", "8889472880:AAGUFuHkBTPN6AIti1Kmy7PyPtjsjRbguo8")

bot = telebot.TeleBot(BOT_TOKEN)

DOWNLOAD_DIR = "downloads"
# Личные файлы рекомендаций
MY_TRACK_FILE = "my_recommendation.mp3"
WELCOME_PHOTO_FILE = "welcome.jpg"  # Приветственная картинка

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

messages_db = {}
SLEEP_FILE = "sleep_mode.txt"


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def is_sleeping():
    """Проверяет, включен ли режим сна"""
    return os.path.exists(SLEEP_FILE)


def crop_to_square(image_path):
    """Обрезает прямоугольное превью YouTube до идеального квадрата по центру"""
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            min_edge = min(width, height)

            left = (width - min_edge) // 2
            top = (height - min_edge) // 2
            right = (width + min_edge) // 2
            bottom = (height + min_edge) // 2

            img_cropped = img.crop((left, top, right, bottom))
            img_cropped.thumbnail((500, 500))
            img_cropped.save(image_path, "JPEG")
            return True
    except Exception as e:
        print(f"Ошибка при обрезке картинки: {e}")
        return False


def download_tiktok(url: str, user_id: int) -> str | None:
    """Скачивает видео из TikTok без водяных знаков"""
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


def search_and_download_track(query: str, user_id: int) -> tuple[str | None, str | None, str | None]:
    """Ищет трек на YouTube, скачивает его и вытаскивает ссылку на превью"""
    output_template = os.path.join(DOWNLOAD_DIR, f"{user_id}_%(title)s")
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template + '.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'ffmpeg_location': '.',
        'writemetadata': True,
        'postprocessors': [
            {
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            },
            {
                'key': 'FFmpegMetadata',
                'add_metadata': True,
            }
        ],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=True)
            if 'entries' in info and len(info['entries']) > 0:
                video_info = info['entries'][0]
                video_url = video_info.get('webpage_url')
                thumb_url = video_info.get('thumbnail')

                filename_base = ydl.prepare_filename(video_info)
                expected_filename = os.path.splitext(filename_base)[0] + ".mp3"

                if os.path.exists(expected_filename):
                    return expected_filename, video_url, thumb_url
    except Exception as e:
        print(f"Ошибка при поиске/скачивании трека: {e}")
    return None, None, None


def get_streaming_links(youtube_url: str) -> str:
    """Получает ссылки на музыкальные платформы через Songlink API"""
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


def process_send_cat(chat_id, reply_to_id=None):
    """Получает случайного котика из публичного API и отправляет пользователю"""
    bot.send_chat_action(chat_id, 'upload_photo')
    try:
        response = requests.get("https://api.thecatapi.com/v1/images/search", timeout=5)
        if response.status_code == 200:
            data = response.json()
            cat_url = data[0]['url']
            bot.send_photo(chat_id=chat_id, photo=cat_url, caption="🐾 Вот Вам милый котик!", reply_to_message_id=reply_to_id)
        else:
            bot.send_message(chat_id, "❌ Не удалось поймать котика, попробуйте еще раз позже!")
    except Exception as e:
        bot.send_message(chat_id, "❌ Произошла ошибка при поиске котика.")
        print(f"Ошибка отправки котика: {e}")


def process_send_recommended_track(chat_id, reply_to_id=None):
    """Отправляет твою личную заготовленную песню"""
    bot.send_chat_action(chat_id, 'upload_document')
    if not os.path.exists(MY_TRACK_FILE):
        bot.send_message(chat_id,
                         "❌ Трек от автора сейчас недоступен.\n\n_Админ:_ Загрузи файл трека на сервер и назови его `my_recommendation.mp3`!")
        return

    try:
        with open(MY_TRACK_FILE, 'rb') as audio:
            bot.send_audio(
                chat_id=chat_id,
                audio=audio,
                caption="🔥 **Рекомендация от Вашего Величества! Обязательно к прослушиванию.**",
                parse_mode="Markdown",
                reply_to_message_id=reply_to_id
            )
    except Exception as e:
        bot.send_message(chat_id, "❌ Не удалось отправить трек.")
        print(f"Ошибка личной рекомендации: {e}")


# --- ОБРАБОТЧИКИ ХЕНДЛЕРОВ ---

@bot.message_handler(func=lambda message: is_sleeping())
def echo_sleeping(message):
    if message.from_user.id == MY_ADMIN_ID:
        if message.text == "/start":
            if os.path.exists(SLEEP_FILE):
                os.remove(SLEEP_FILE)
            bot.send_message(MY_ADMIN_ID, "☀️ Ваше Величество, бот проснулся и готов к Вашим услугам!")
            return
    bot.send_message(message.chat.id, "💤 **Бот сейчас спит так же, как и его создатель.**", parse_mode="Markdown")


@bot.message_handler(commands=['start'])
def send_welcome(message):
    # Создаем клавиатуру в любом случае (и для админа, и для юзеров)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_suggest = types.KeyboardButton("✍️ Написать анонимно")
    btn_music = types.KeyboardButton("🎵 Найти песню")
    btn_my_track = types.KeyboardButton("🔥 Мой рекомендованный трек")
    btn_cat = types.KeyboardButton("🐱 Котики")

    markup.add(btn_suggest, btn_music)
    markup.add(btn_my_track, btn_cat)

    if message.from_user.id == MY_ADMIN_ID:
        welcome_text = "👑 **Приветствую Вас, Ваше Величество!** Бот запущен и полностью подчиняется Вашей воле. Вы также можете использовать кнопки ниже 👇"
    else:
        welcome_text = (
            "🤫 **Привет! Это твой личный бот-помощник.**\n\n"
            "✨ Нажимай на кнопки внизу, чтобы затестить новые функции, послушать мои рекомендации или получить милого котика!"
        )

    if os.path.exists(WELCOME_PHOTO_FILE):
        try:
            with open(WELCOME_PHOTO_FILE, 'rb') as photo:
                bot.send_photo(
                    chat_id=message.chat.id,
                    photo=photo,
                    caption=welcome_text,
                    parse_mode="Markdown",
                    reply_markup=markup
                )
        except Exception as e:
            print(f"Ошибка при отправке welcome.jpg: {e}")
            bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text in ["🐱 Котики", "🔥 Мой рекомендованный трек"])
def handle_menu_buttons(message):
    if message.text == "🐱 Котики":
        process_send_cat(message.chat.id, message.message_id)
    elif message.text == "🔥 Мой рекомендованный трек":
        process_send_recommended_track(message.chat.id, message.message_id)


@bot.message_handler(func=lambda message: message.text == "🎵 Найти песню")
def ask_for_track(message):
    if message.from_user.id == MY_ADMIN_ID:
        msg = bot.send_message(message.chat.id, "Какую песню желаете найти, Ваше Величество?", parse_mode="Markdown")
    else:
        msg = bot.send_message(message.chat.id, "Введите название трека или исполнителя:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_track_search)


def process_track_search(message):
    if is_sleeping():
        echo_sleeping(message)
        return
    if not message.text or message.text.startswith("/"):
        bot.send_message(message.chat.id, "Поиск отменен.")
        return

    if message.text == "✍️ Написать анонимно":
        forward_to_admin(message)
        return
    elif message.text in ["🐱 Котики", "🔥 Мой рекомендованный трек"]:
        handle_menu_buttons(message)
        return
    elif message.text == "🎵 Найти песню":
        ask_for_track(message)
        return

    query = message.text
    status_msg = bot.send_message(message.chat.id, f"🔍 Ищу трек «{query}»...")
    bot.send_chat_action(message.chat.id, 'upload_document')

    file_path, yt_url, thumb_url = search_and_download_track(query, message.from_user.id)

    if file_path and os.path.exists(file_path):
        links_text = get_streaming_links(yt_url)
        caption = f"🎶 Результат поиска по запросу: *{query}*\n\n{links_text}" if links_text else f"🎶 Держи трек: *{query}*"
        local_thumb_path = os.path.join(DOWNLOAD_DIR, f"{message.from_user.id}_thumb.jpg")
        thumb_ready = False

        if thumb_url:
            try:
                img_data = requests.get(thumb_url, timeout=5).content
                with open(local_thumb_path, 'wb') as handler:
                    handler.write(img_data)
                if os.path.exists(local_thumb_path):
                    thumb_ready = crop_to_square(local_thumb_path)
            except Exception as e:
                print(f"Ошибка обложки: {e}")

        try:
            with open(file_path, 'rb') as audio_file:
                display_name = os.path.basename(file_path).replace(f"{message.from_user.id}_", "").replace(".mp3", "")
                if thumb_ready and os.path.exists(local_thumb_path):
                    with open(local_thumb_path, 'rb') as thumb_file:
                        bot.send_audio(chat_id=message.chat.id, audio=audio_file, caption=caption,
                                       parse_mode="Markdown", title=display_name, thumbnail=thumb_file,
                                       reply_to_message_id=message.message_id)
                else:
                    bot.send_audio(chat_id=message.chat.id, audio=audio_file, caption=caption, parse_mode="Markdown",
                                   title=display_name, reply_to_message_id=message.message_id)
        except Exception as e:
            bot.send_message(message.chat.id, "❌ Ошибка при отправке аудио.")
        finally:
            if os.path.exists(file_path): os.remove(file_path)
            if os.path.exists(local_thumb_path): os.remove(local_thumb_path)
    else:
        bot.send_message(message.chat.id, "❌ Ничего не найдено.")
    try:
        bot.delete_message(message.chat.id, status_msg.message_id)
    except Exception:
        pass


@bot.message_handler(func=lambda message: message.reply_to_message is not None)
def handle_admin_reply(message):
    if message.from_user.id != MY_ADMIN_ID: return
    reply_id = message.reply_to_message.message_id
    if reply_id in messages_db:
        original_user_id = messages_db[reply_id]
        try:
            bot.copy_message(chat_id=original_user_id, from_chat_id=message.chat.id, message_id=message.message_id)
            bot.send_message(MY_ADMIN_ID, "✅ Ваше Величество, ответ успешно доставлен подданному!")
        except Exception as e:
            bot.send_message(MY_ADMIN_ID, f"❌ Ошибка отправки: {e}")


@bot.message_handler(func=lambda message: message.text is not None and "tiktok.com" in message.text)
def handle_tiktok(message):
    user_id = message.from_user.id
    status_msg = bot.send_message(message.chat.id, "⏳ Скачиваю видео из TikTok...")
    video_path = download_tiktok(message.text, user_id)

    if video_path and os.path.exists(video_path):
        try:
            with open(video_path, 'rb') as video_file:
                bot.send_video(chat_id=message.chat.id, video=video_file, caption="😁 Держи видосик",
                               reply_to_message_id=message.message_id)
        except Exception as e:
            bot.send_message(message.chat.id, "❌ Не удалось отправить видео.")
        finally:
            if os.path.exists(video_path): os.remove(video_path)
    else:
        bot.send_message(message.chat.id, "❌ Ошибка скачивания.")
    try:
        bot.delete_message(message.chat.id, status_msg.message_id)
    except Exception:
        pass


@bot.message_handler(
    content_types=['text', 'audio', 'document', 'photo', 'sticker', 'video', 'video_note', 'voice', 'location',
                   'contact'])
def forward_to_admin(message):
    # Если это сообщение от Вас (админа)
    if message.from_user.id == MY_ADMIN_ID:
        if message.text == "✍️ Написать анонимно":
            bot.send_message(message.chat.id, "Ваше Величество, писать анонимно самому себе не имеет глубокого смысла, но система Вас поняла! 😉")
        return

    # Защитная проверка: если обычный юзер нажал на кнопку из меню, НЕ отправляем её текст анонимно
    if message.text in ["✍️ Написать анонимно", "🎵 Найти песню", "🔥 Мой рекомендованный трек", "🐱 Котики"]:
        if message.text == "✍️ Написать анонимно":
            bot.send_message(message.chat.id, "Отлично! Отправьте мне текст или медиафайл прямо сейчас, и я передам его анонимно 👇")
        return

    # Если это реальный пост/медиафайл — перенаправляем Вам в админку
    try:
        first_name = message.from_user.first_name or ""
        last_name = message.from_user.last_name or ""
        full_name = f"{first_name} {last_name}".strip() or "Скрыто"
        username_text = f"🔗 @{message.from_user.username}" if message.from_user.username else "🔗 Скрыт"
        user_message_text = message.text or message.caption or "⚠️ Медиафайл"

        info_text = f"📩 **Ваше Величество, новая предложка!**\n\n👤 Имя: {full_name}\n{username_text}\n🆔 ID: `{message.from_user.id}`\n\n📝 **Текст:**\n{user_message_text}"
        bot.send_message(MY_ADMIN_ID, info_text, parse_mode="Markdown")
        sent_msg = bot.copy_message(chat_id=MY_ADMIN_ID, from_chat_id=message.chat.id, message_id=message.message_id)
        messages_db[sent_msg.message_id] = message.from_user.id
        bot.send_message(message.chat.id, "🚀 Успешно отправлено анонимно!")
    except Exception as e:
        print(f"Ошибка предложки: {e}")


# --- БЕЗОПАСНЫЙ ВЕБ-СЕРВЕР ---
class SafeHandler(BaseHTTPRequestHandler):
    """Этот обработчик отвечает заглушкой 'OK' вместо вывода списка файлов"""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<h1>Бот успешно работает! Проверка портов пройдена.</h1>".encode("utf-8"))

    def log_message(self, format, *args):
        return


def run_dummy_server():
    """Запуск скрытого веб-сервера для Render, чтобы он не закрывал порт"""
    port = int(os.getenv("PORT", 10000))
    server_address = ("", port)
    httpd = HTTPServer(server_address, SafeHandler)
    print(f"Фоновый веб-сервер успешно запущен на порту {port}")
    httpd.serve_forever()


if __name__ == "__main__":
    if os.path.exists(SLEEP_FILE):
        os.remove(SLEEP_FILE)

    # 1. Запускаем заглушку сервера в отдельном потоке
    threading.Thread(target=run_dummy_server, daemon=True).start()

    # 2. Запускаем основного бота
    print("Бот успешно запущен для Вашего Величества!")
    bot.infinity_polling(skip_pending=True)