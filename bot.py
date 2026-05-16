import asyncio
import sqlite3
import logging
import socket
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ===================== НАСТРОЙКИ =====================
BOT_TOKEN = "8878080269:AAFlh-1yI8BjfI9JtSarBXs1bSy3l0yudgg"   # <-- Вставь токен бота сюда
OWNER_ID = 6141804437              # Твой Telegram ID
IDLE_TIMEOUT_MINUTES = 5

# Spotify — получи на https://developer.spotify.com/dashboard
SPOTIFY_CLIENT_ID     = "a1e4677d338a422390dc7e632d9d29c1"
SPOTIFY_CLIENT_SECRET = "c9c9a0b53c194d81ae2c7367d0a4c87b"
SPOTIFY_REFRESH_TOKEN = "AQDrJdEgvU7IQ-BiFXuuqPrUzGdVa6D_v2_5neXKBd9LAElkv5bYcFAKD3K2ZWEEyvaCvFgQlpt2mNZzp543cUcbUSduePG6AVD-2CXLdvObabzm8USxLBOk1FYf1L-kq3c"
# Инструкция по получению REFRESH_TOKEN — в README.md
# =====================================================

logging.basicConfig(level=logging.INFO)

bot: Bot = None
dp = Dispatcher(storage=MemoryStorage())
idle_tasks: dict = {}

# ===================== БД =====================

def init_db():
    conn = sqlite3.connect("messages.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            full_name TEXT,
            message_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            language TEXT DEFAULT 'ru',
            is_active INTEGER DEFAULT 1,
            is_banned INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_messages (
            user_id INTEGER PRIMARY KEY,
            owner_message_id INTEGER,
            accumulated_text TEXT,
            has_media INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_status_msg (
            user_id INTEGER PRIMARY KEY,
            status_message_id INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS shop_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            price TEXT NOT NULL,
            payment_info TEXT,
            photo_id TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect("messages.db")

def save_message(user_id, username, full_name, text):
    conn = get_db()
    conn.execute(
        "INSERT INTO messages (user_id, username, full_name, message_text, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, username or "", full_name or "", text, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()

def set_user_lang(user_id, lang):
    conn = get_db()
    conn.execute(
        "INSERT INTO user_settings (user_id, language, is_active, is_banned) VALUES (?, ?, 1, 0) "
        "ON CONFLICT(user_id) DO UPDATE SET language=excluded.language",
        (user_id, lang)
    )
    conn.commit()
    conn.close()

def get_user_lang(user_id):
    conn = get_db()
    row = conn.execute("SELECT language FROM user_settings WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row[0] if row else None

def is_user_active(user_id):
    conn = get_db()
    row = conn.execute("SELECT is_active FROM user_settings WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row[0] == 1 if row else False

def set_user_active(user_id, active):
    conn = get_db()
    conn.execute("UPDATE user_settings SET is_active=? WHERE user_id=?", (1 if active else 0, user_id))
    conn.commit()
    conn.close()

def is_banned(user_id):
    conn = get_db()
    row = conn.execute("SELECT is_banned FROM user_settings WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row[0] == 1 if row else False

def set_banned(user_id, banned):
    conn = get_db()
    conn.execute(
        "INSERT INTO user_settings (user_id, language, is_active, is_banned) VALUES (?, 'ru', 0, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET is_banned=excluded.is_banned",
        (user_id, 1 if banned else 0)
    )
    conn.commit()
    conn.close()

def get_pending(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT owner_message_id, accumulated_text, has_media FROM pending_messages WHERE user_id=?",
        (user_id,)
    ).fetchone()
    conn.close()
    return row

def set_pending(user_id, owner_message_id, accumulated_text, has_media=False):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO pending_messages (user_id, owner_message_id, accumulated_text, has_media) VALUES (?, ?, ?, ?)",
        (user_id, owner_message_id, accumulated_text, 1 if has_media else 0)
    )
    conn.commit()
    conn.close()

def clear_pending(user_id):
    conn = get_db()
    conn.execute("DELETE FROM pending_messages WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def get_status_msg(user_id):
    conn = get_db()
    row = conn.execute("SELECT status_message_id FROM user_status_msg WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row[0] if row else None

def set_status_msg(user_id, msg_id):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO user_status_msg (user_id, status_message_id) VALUES (?, ?)",
        (user_id, msg_id)
    )
    conn.commit()
    conn.close()

def clear_status_msg(user_id):
    conn = get_db()
    conn.execute("DELETE FROM user_status_msg WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

# Магазин — БД функции
def get_shop_items():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, description, price, payment_info, photo_id FROM shop_items WHERE is_active=1 ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return rows

def get_shop_item(item_id):
    conn = get_db()
    row = conn.execute(
        "SELECT id, title, description, price, payment_info, photo_id FROM shop_items WHERE id=? AND is_active=1",
        (item_id,)
    ).fetchone()
    conn.close()
    return row

def add_shop_item(title, description, price, payment_info, photo_id):
    conn = get_db()
    conn.execute(
        "INSERT INTO shop_items (title, description, price, payment_info, photo_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (title, description, price, payment_info, photo_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()

def delete_shop_item(item_id):
    conn = get_db()
    conn.execute("UPDATE shop_items SET is_active=0 WHERE id=?", (item_id,))
    conn.commit()
    conn.close()

# ===================== SPOTIFY =====================

_spotify_access_token = None
_spotify_token_expires = 0

async def spotify_refresh_access_token():
    global _spotify_access_token, _spotify_token_expires
    import base64, time
    credentials = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            "https://accounts.spotify.com/api/token",
            headers={"Authorization": f"Basic {credentials}"},
            data={"grant_type": "refresh_token", "refresh_token": SPOTIFY_REFRESH_TOKEN}
        )
        data = await resp.json()
    _spotify_access_token = data.get("access_token")
    _spotify_token_expires = time.time() + data.get("expires_in", 3600) - 60

async def get_spotify_token():
    import time
    if not _spotify_access_token or time.time() > _spotify_token_expires:
        await spotify_refresh_access_token()
    return _spotify_access_token

async def get_now_playing():
    """Возвращает (artist, track, is_playing) или None если ошибка/не настроено."""
    if SPOTIFY_CLIENT_ID == "YOUR_SPOTIFY_CLIENT_ID":
        return None
    try:
        token = await get_spotify_token()
        async with aiohttp.ClientSession() as session:
            resp = await session.get(
                "https://api.spotify.com/v1/me/player/currently-playing",
                headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status == 204:
                # Ничего не играет — берём последний трек
                resp2 = await session.get(
                    "https://api.spotify.com/v1/me/player/recently-played?limit=1",
                    headers={"Authorization": f"Bearer {token}"}
                )
                if resp2.status == 200:
                    data = await resp2.json()
                    items = data.get("items", [])
                    if items:
                        track = items[0]["track"]
                        artist = ", ".join(a["name"] for a in track["artists"])
                        return artist, track["name"], False
                return None
            if resp.status != 200:
                return None
            data = await resp.json()
            item = data.get("item")
            if not item:
                return None
            artist = ", ".join(a["name"] for a in item["artists"])
            return artist, item["name"], data.get("is_playing", False)
    except Exception as e:
        logging.error(f"Spotify error: {e}")
        return None

# ===================== ТЕКСТЫ =====================

TEXTS = {
    "ru": {
        "choose_lang": "Выбери язык / Choose language / Оберіть мову:",
        "welcome": (
            "<b>Добро пожаловать.</b>\n\n"
            "Здесь ты можешь написать мне анонимно.\n\n"
            "<b>Как написать:</b>\n"
            "Просто отправь сообщение — текст, фото, видео или файл.\n\n"
            "<b>Как остановить:</b>\n"
            "Отправь /stop.\n\n"
            f"<b>Авто-стоп:</b>\n"
            f"Если не пишешь {IDLE_TIMEOUT_MINUTES} минут — пересылка останавливается автоматически."
        ),
        "help": (
            "<b>Команды:</b>\n"
            "/start — начать / возобновить\n"
            "/stop — остановить пересылку\n"
            "/shop — магазин\n"
            "/music — что сейчас играет\n"
            "/help — это сообщение\n\n"
            "<b>О боте:</b>\n"
            "Бот позволяет написать мне анонимно. Твоё имя не раскрывается.\n\n"
            "<b>Сменить язык:</b>"
        ),
        "stopped": "Пересылка остановлена. Отправь /start чтобы возобновить.",
        "auto_stopped": f"Пересылка остановлена автоматически — нет активности {IDLE_TIMEOUT_MINUTES} мин.\nОтправь /start чтобы возобновить.",
        "resumed": "Пересылка возобновлена. Пиши:",
        "sending": "<b>Отправка включена.</b>\nПиши — сообщения будут переданы.\n\n/stop — остановить.",
        "not_active": "Пересылка остановлена. Отправь /start чтобы возобновить.",
        "banned": "Ты заблокирован.",
        "replied": "<b>Ответ:</b>\n\n",
        "shop_empty": "Магазин пока пуст.",
        "shop_title": "<b>Магазин</b>\n\nВыбери товар:",
        "order_done": "Заказ оформлен. Ожидай ответа владельца.",
        "music_playing": "Сейчас слушаю:\n<b>{track}</b>\n{artist}",
        "music_last": "Последнее что слушал:\n<b>{track}</b>\n{artist}",
        "music_off": "Сейчас ничего не слушаю.",
        "music_disabled": "Spotify не подключён.",
    },
    "uk": {
        "choose_lang": "Оберіть мову / Choose language / Выберите язык:",
        "welcome": (
            "<b>Ласкаво просимо.</b>\n\n"
            "Тут ти можеш написати мені анонімно.\n\n"
            "<b>Як написати:</b>\n"
            "Просто надішли повідомлення — текст, фото, відео або файл.\n\n"
            "<b>Як зупинити:</b>\n"
            "Надішли /stop.\n\n"
            f"<b>Авто-стоп:</b>\n"
            f"Якщо не пишеш {IDLE_TIMEOUT_MINUTES} хвилин — пересилання зупиняється автоматично."
        ),
        "help": (
            "<b>Команди:</b>\n"
            "/start — почати / відновити\n"
            "/stop — зупинити пересилання\n"
            "/shop — магазин\n"
            "/music — що зараз грає\n"
            "/help — це повідомлення\n\n"
            "<b>Про бота:</b>\n"
            "Бот дозволяє написати мені анонімно. Твоє ім'я не розкривається.\n\n"
            "<b>Змінити мову:</b>"
        ),
        "stopped": "Пересилання зупинено. Надішли /start щоб відновити.",
        "auto_stopped": f"Пересилання зупинено автоматично — немає активності {IDLE_TIMEOUT_MINUTES} хв.\nНадішли /start щоб відновити.",
        "resumed": "Пересилання відновлено. Пиши:",
        "sending": "<b>Надсилання увімкнено.</b>\nПиши — повідомлення будуть передані.\n\n/stop — зупинити.",
        "not_active": "Пересилання зупинено. Надішли /start щоб відновити.",
        "banned": "Тебе заблоковано.",
        "replied": "<b>Відповідь:</b>\n\n",
        "shop_empty": "Магазин поки порожній.",
        "shop_title": "<b>Магазин</b>\n\nОбери товар:",
        "order_done": "Замовлення оформлено. Очікуй відповіді власника.",
        "music_playing": "Зараз слухаю:\n<b>{track}</b>\n{artist}",
        "music_last": "Останнє що слухав:\n<b>{track}</b>\n{artist}",
        "music_off": "Зараз нічого не слухаю.",
        "music_disabled": "Spotify не підключено.",
    },
    "en": {
        "choose_lang": "Choose language / Выберите язык / Оберіть мову:",
        "welcome": (
            "<b>Welcome.</b>\n\n"
            "Here you can write to me anonymously.\n\n"
            "<b>How to write:</b>\n"
            "Just send a message — text, photo, video or file.\n\n"
            "<b>How to stop:</b>\n"
            "Send /stop.\n\n"
            f"<b>Auto-stop:</b>\n"
            f"If you're inactive for {IDLE_TIMEOUT_MINUTES} minutes — forwarding stops automatically."
        ),
        "help": (
            "<b>Commands:</b>\n"
            "/start — start / resume\n"
            "/stop — stop forwarding\n"
            "/shop — shop\n"
            "/music — what's playing now\n"
            "/help — this message\n\n"
            "<b>About:</b>\n"
            "This bot lets you write to me anonymously. Your identity is not revealed.\n\n"
            "<b>Change language:</b>"
        ),
        "stopped": "Forwarding stopped. Send /start to resume.",
        "auto_stopped": f"Forwarding stopped automatically — no activity for {IDLE_TIMEOUT_MINUTES} min.\nSend /start to resume.",
        "resumed": "Forwarding resumed. Write:",
        "sending": "<b>Forwarding is on.</b>\nWrite — messages will be passed on.\n\n/stop — stop.",
        "not_active": "Forwarding is stopped. Send /start to resume.",
        "banned": "You are blocked.",
        "replied": "<b>Reply:</b>\n\n",
        "shop_empty": "The shop is empty for now.",
        "shop_title": "<b>Shop</b>\n\nChoose an item:",
        "order_done": "Order placed. Wait for the owner's reply.",
        "music_playing": "Currently listening to:\n<b>{track}</b>\n{artist}",
        "music_last": "Last listened to:\n<b>{track}</b>\n{artist}",
        "music_off": "Not listening to anything right now.",
        "music_disabled": "Spotify is not connected.",
    },
}

# ===================== КЛАВИАТУРЫ =====================

def lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="RU", callback_data="lang_ru"),
        InlineKeyboardButton(text="UA", callback_data="lang_uk"),
        InlineKeyboardButton(text="EN", callback_data="lang_en"),
    ]])

def owner_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Ответить", callback_data=f"reply_{user_id}"),
        InlineKeyboardButton(text="Бан", callback_data=f"ban_{user_id}"),
        InlineKeyboardButton(text="Разбан", callback_data=f"unban_{user_id}"),
    ]])

def shop_list_keyboard(items):
    rows = []
    for item_id, title, *_ in items:
        rows.append([InlineKeyboardButton(text=title, callback_data=f"shopitem_{item_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def shop_item_keyboard(item_id, lang):
    labels = {"ru": "Оформить заказ", "uk": "Оформити замовлення", "en": "Place order"}
    back   = {"ru": "Назад", "uk": "Назад", "en": "Back"}
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=labels.get(lang, "Place order"), callback_data=f"shopbuy_{item_id}")],
        [InlineKeyboardButton(text=back.get(lang, "Back"), callback_data="shopback")],
    ])

def owner_shop_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добавить товар", callback_data="shop_add")],
        [InlineKeyboardButton(text="Список товаров", callback_data="shop_list_owner")],
    ])

# ===================== FSM =====================

class ReplyState(StatesGroup):
    waiting_reply = State()

class ShopAddState(StatesGroup):
    title        = State()
    description  = State()
    price        = State()
    payment_info = State()
    photo        = State()

# ===================== АВТО-СТОП =====================

async def idle_timer(user_id):
    await asyncio.sleep(IDLE_TIMEOUT_MINUTES * 60)
    lang = get_user_lang(user_id) or "ru"
    if is_user_active(user_id):
        set_user_active(user_id, False)
        clear_pending(user_id)
        old_status = get_status_msg(user_id)
        if old_status:
            try:
                await bot.delete_message(user_id, old_status)
            except Exception:
                pass
            clear_status_msg(user_id)
        try:
            await bot.send_message(user_id, TEXTS[lang]["auto_stopped"], parse_mode="HTML")
        except Exception:
            pass

def reset_idle_timer(user_id):
    if user_id in idle_tasks:
        idle_tasks[user_id].cancel()
    idle_tasks[user_id] = asyncio.create_task(idle_timer(user_id))

def cancel_idle_timer(user_id):
    if user_id in idle_tasks:
        idle_tasks[user_id].cancel()
        del idle_tasks[user_id]

# ===================== ХЕЛПЕРЫ =====================

async def update_user_status(user_id, lang):
    old_id = get_status_msg(user_id)
    if old_id:
        return
    msg = await bot.send_message(user_id, TEXTS[lang]["sending"], parse_mode="HTML")
    set_status_msg(user_id, msg.message_id)

async def delete_user_status(user_id):
    old_id = get_status_msg(user_id)
    if old_id:
        try:
            await bot.delete_message(user_id, old_id)
        except Exception:
            pass
        clear_status_msg(user_id)

def get_media_type(message: Message):
    if message.photo:      return "photo",      message.photo[-1].file_id
    if message.video:      return "video",      message.video.file_id
    if message.document:   return "document",   message.document.file_id
    if message.audio:      return "audio",      message.audio.file_id
    if message.voice:      return "voice",      message.voice.file_id
    if message.sticker:    return "sticker",    message.sticker.file_id
    if message.video_note: return "video_note", message.video_note.file_id
    return None, None

def get_lang(uid):
    return get_user_lang(uid) or "ru"

# ===================== /start =====================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.from_user.id == OWNER_ID:
        await message.answer(
            "<b>Панель владельца</b>\n\n"
            "/history — последние 20 сообщений\n"
            "/clear — очистить БД\n"
            "/banlist — список забаненных\n"
            "/shop — управление магазином\n\n"
            "Кнопки под сообщениями: Ответить / Бан / Разбан",
            parse_mode="HTML"
        )
        return

    uid = message.from_user.id
    if is_banned(uid):
        await message.answer(TEXTS[get_lang(uid)]["banned"])
        return

    lang = get_user_lang(uid)
    if not lang:
        await message.answer(TEXTS["ru"]["choose_lang"], reply_markup=lang_keyboard())
        return

    set_user_active(uid, True)
    reset_idle_timer(uid)
    await message.answer(TEXTS[lang]["welcome"], parse_mode="HTML")
    msg = await message.answer(TEXTS[lang]["sending"], parse_mode="HTML")
    set_status_msg(uid, msg.message_id)


@dp.callback_query(F.data.startswith("lang_"))
async def choose_language(callback: CallbackQuery):
    lang = callback.data.split("_")[1]
    uid = callback.from_user.id
    set_user_lang(uid, lang)
    set_user_active(uid, True)
    reset_idle_timer(uid)
    await callback.message.edit_text(TEXTS[lang]["welcome"], parse_mode="HTML")
    msg = await bot.send_message(uid, TEXTS[lang]["sending"], parse_mode="HTML")
    set_status_msg(uid, msg.message_id)
    await callback.answer()

# ===================== /help =====================

@dp.message(Command("help"))
async def cmd_help(message: Message):
    if message.from_user.id == OWNER_ID:
        return
    uid = message.from_user.id
    if is_banned(uid):
        return
    lang = get_lang(uid)
    await message.answer(TEXTS[lang]["help"], parse_mode="HTML", reply_markup=lang_keyboard())

# ===================== /stop =====================

@dp.message(Command("stop"))
async def cmd_stop(message: Message):
    if message.from_user.id == OWNER_ID:
        return
    uid = message.from_user.id
    lang = get_lang(uid)
    set_user_active(uid, False)
    cancel_idle_timer(uid)
    clear_pending(uid)
    await delete_user_status(uid)
    await message.answer(TEXTS[lang]["stopped"], parse_mode="HTML")

# ===================== /music =====================

@dp.message(Command("music"))
async def cmd_music(message: Message):
    if message.from_user.id == OWNER_ID:
        return
    uid = message.from_user.id
    if is_banned(uid):
        return
    lang = get_lang(uid)
    t = TEXTS[lang]

    if SPOTIFY_CLIENT_ID == "YOUR_SPOTIFY_CLIENT_ID":
        await message.answer(t["music_disabled"])
        return

    result = await get_now_playing()
    # Ничего не играет и нет последнего трека — скрываем блок
    if result is None:
        return

    artist, track, is_playing = result
    if not is_playing:
        # Ничего не играет — скрываем
        return

    text = t["music_playing"].format(track=track, artist=artist)
    await message.answer(text, parse_mode="HTML")

# ===================== /shop — юзер =====================

@dp.message(Command("shop"))
async def cmd_shop(message: Message):
    uid = message.from_user.id

    # Владелец
    if uid == OWNER_ID:
        await message.answer("Управление магазином:", reply_markup=owner_shop_keyboard())
        return

    if is_banned(uid):
        return

    lang = get_lang(uid)
    items = get_shop_items()
    if not items:
        await message.answer(TEXTS[lang]["shop_empty"])
        return
    await message.answer(TEXTS[lang]["shop_title"], parse_mode="HTML", reply_markup=shop_list_keyboard(items))


@dp.callback_query(F.data == "shopback")
async def shop_back(callback: CallbackQuery):
    uid = callback.from_user.id
    lang = get_lang(uid)
    items = get_shop_items()
    if not items:
        await callback.message.edit_text(TEXTS[lang]["shop_empty"])
    else:
        await callback.message.edit_text(TEXTS[lang]["shop_title"], parse_mode="HTML", reply_markup=shop_list_keyboard(items))
    await callback.answer()


@dp.callback_query(F.data.startswith("shopitem_"))
async def shop_item_view(callback: CallbackQuery):
    uid = callback.from_user.id
    lang = get_lang(uid)
    item_id = int(callback.data.split("_")[1])
    item = get_shop_item(item_id)
    if not item:
        await callback.answer("Товар не найден.", show_alert=True)
        return

    _, title, description, price, payment_info, photo_id = item
    text = f"<b>{title}</b>\n\n"
    if description:
        text += f"{description}\n\n"
    text += f"<b>Цена:</b> {price}"

    kb = shop_item_keyboard(item_id, lang)
    if photo_id:
        await callback.message.delete()
        await bot.send_photo(uid, photo_id, caption=text, parse_mode="HTML", reply_markup=kb)
    else:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("shopbuy_"))
async def shop_buy(callback: CallbackQuery):
    uid = callback.from_user.id
    lang = get_lang(uid)
    item_id = int(callback.data.split("_")[1])
    item = get_shop_item(item_id)
    if not item:
        await callback.answer("Товар не найден.", show_alert=True)
        return

    _, title, _, price, _, _ = item
    username = callback.from_user.username or ""
    full_name = callback.from_user.full_name or ""
    display = f"@{username}" if username else full_name

    # Уведомить владельца — кнопки Принять / Отменить
    order_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Принять", callback_data=f"order_accept_{uid}_{item_id}"),
            InlineKeyboardButton(text="Отменить", callback_data=f"order_decline_{uid}_{item_id}"),
        ],
        [InlineKeyboardButton(text="Ответить", callback_data=f"reply_{uid}")],
    ])
    await bot.send_message(
        OWNER_ID,
        f"<b>Новый заказ</b>\n\n"
        f"Товар: {title}\n"
        f"Цена: {price}\n\n"
        f"От: {display} (<code>{uid}</code>)",
        parse_mode="HTML",
        reply_markup=order_kb
    )

    await callback.answer(TEXTS[lang]["order_done"], show_alert=True)


@dp.callback_query(F.data.startswith("order_accept_"))
async def order_accept(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return
    parts = callback.data.split("_")
    user_id = int(parts[2])
    item_id = int(parts[3])
    item = get_shop_item(item_id)
    lang = get_lang(user_id)

    payment_info = item[4] if item else ""
    title = item[1] if item else "товар"

    accept_texts = {
        "ru": f"Заказ принят.\n\nТовар: <b>{title}</b>",
        "uk": f"Замовлення прийнято.\n\nТовар: <b>{title}</b>",
        "en": f"Order accepted.\n\nItem: <b>{title}</b>",
    }
    text = accept_texts.get(lang, accept_texts["ru"])
    if payment_info:
        pay_label = {"ru": "Реквизиты для оплаты", "uk": "Реквізити для оплати", "en": "Payment details"}
        text += f"\n\n<b>{pay_label.get(lang, 'Payment details')}:</b>\n{payment_info}"

    try:
        await bot.send_message(user_id, text, parse_mode="HTML")
    except Exception:
        pass

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Заказ принят, реквизиты отправлены.", show_alert=True)


@dp.callback_query(F.data.startswith("order_decline_"))
async def order_decline(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return
    parts = callback.data.split("_")
    user_id = int(parts[2])
    lang = get_lang(user_id)

    decline_texts = {
        "ru": "Заказ отменён.",
        "uk": "Замовлення скасовано.",
        "en": "Order declined.",
    }
    try:
        await bot.send_message(user_id, decline_texts.get(lang, "Order declined."))
    except Exception:
        pass

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Заказ отменён.", show_alert=True)

# ===================== Магазин — владелец =====================

@dp.callback_query(F.data == "shop_add")
async def shop_add_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        return
    await state.set_state(ShopAddState.title)
    await callback.message.answer("Введи название товара:")
    await callback.answer()


@dp.message(ShopAddState.title)
async def shop_add_title(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    await state.update_data(title=message.text)
    await state.set_state(ShopAddState.description)
    await message.answer("Описание товара (или отправь — чтобы пропустить):")


@dp.message(ShopAddState.description)
async def shop_add_description(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    desc = message.text if message.text != "—" else ""
    await state.update_data(description=desc)
    await state.set_state(ShopAddState.price)
    await message.answer("Цена (например: 500 грн, $20):")


@dp.message(ShopAddState.price)
async def shop_add_price(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    await state.update_data(price=message.text)
    await state.set_state(ShopAddState.payment_info)
    await message.answer("Реквизиты для оплаты (или — чтобы пропустить):")


@dp.message(ShopAddState.payment_info)
async def shop_add_payment(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    pay = message.text if message.text != "—" else ""
    await state.update_data(payment_info=pay)
    await state.set_state(ShopAddState.photo)
    await message.answer("Отправь фото товара (или — чтобы без фото):")


@dp.message(ShopAddState.photo)
async def shop_add_photo(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    data = await state.get_data()
    photo_id = None
    if message.photo:
        photo_id = message.photo[-1].file_id
    await state.clear()
    add_shop_item(data["title"], data["description"], data["price"], data["payment_info"], photo_id)
    await message.answer(f"Товар «{data['title']}» добавлен в магазин.")


@dp.callback_query(F.data == "shop_list_owner")
async def shop_list_owner(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return
    items = get_shop_items()
    if not items:
        await callback.answer("Магазин пуст.", show_alert=True)
        return
    lines = ["<b>Товары в магазине:</b>\n"]
    for item_id, title, _, price, _, _ in items:
        lines.append(f"• [{item_id}] {title} — {price}")
    lines.append("\nЧтобы удалить: /delitem_ID (например /delitem_3)")
    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


@dp.message(F.text.regexp(r"^/delitem_(\d+)$"))
async def shop_delete_item(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    item_id = int(message.text.split("_")[1])
    item = get_shop_item(item_id)
    if not item:
        await message.answer("Товар не найден.")
        return
    delete_shop_item(item_id)
    await message.answer(f"Товар [{item_id}] удалён.")

# ===================== Владелец — сообщения =====================

@dp.message(Command("history"))
async def cmd_history(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    conn = get_db()
    rows = conn.execute(
        "SELECT username, user_id, message_text, created_at FROM messages ORDER BY id DESC LIMIT 20"
    ).fetchall()
    conn.close()
    if not rows:
        await message.answer("Сообщений пока нет.")
        return
    lines = ["<b>Последние 20 сообщений:</b>\n"]
    for username, uid, text, created_at in rows:
        name = f"@{username}" if username else f"id{uid}"
        lines.append(f"<b>{name}</b> ({uid}) [{created_at}]\n{text}\n")
    await message.answer("\n".join(lines)[:4000], parse_mode="HTML")


@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    conn = get_db()
    conn.execute("DELETE FROM messages")
    conn.execute("DELETE FROM pending_messages")
    conn.commit()
    conn.close()
    await message.answer("БД очищена.")


@dp.message(Command("banlist"))
async def cmd_banlist(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    conn = get_db()
    rows = conn.execute(
        "SELECT user_settings.user_id, messages.username "
        "FROM user_settings "
        "LEFT JOIN messages ON user_settings.user_id = messages.user_id "
        "WHERE user_settings.is_banned = 1 "
        "GROUP BY user_settings.user_id"
    ).fetchall()
    conn.close()
    if not rows:
        await message.answer("Забаненных нет.")
        return
    lines = ["<b>Забаненные:</b>\n"]
    for uid, uname in rows:
        name = f"@{uname}" if uname else f"id{uid}"
        lines.append(f"• {name} (<code>{uid}</code>)")
    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.callback_query(F.data.startswith("ban_"))
async def owner_ban(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return
    user_id = int(callback.data.split("_")[1])
    set_banned(user_id, True)
    set_user_active(user_id, False)
    cancel_idle_timer(user_id)
    clear_pending(user_id)
    lang = get_lang(user_id)
    try:
        await delete_user_status(user_id)
        await bot.send_message(user_id, TEXTS[lang]["banned"])
    except Exception:
        pass
    await callback.answer(f"Пользователь {user_id} забанен", show_alert=True)


@dp.callback_query(F.data.startswith("unban_"))
async def owner_unban(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return
    user_id = int(callback.data.split("_")[1])
    set_banned(user_id, False)
    await callback.answer(f"Пользователь {user_id} разбанен", show_alert=True)


@dp.callback_query(F.data.startswith("reply_"))
async def owner_reply_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        return
    user_id = int(callback.data.split("_")[1])
    await state.set_state(ReplyState.waiting_reply)
    await state.update_data(reply_to=user_id)
    await callback.message.answer(
        f"Напиши ответ для <code>{user_id}</code> (текст, фото, видео, файл):",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.message(ReplyState.waiting_reply)
async def owner_send_reply(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    data = await state.get_data()
    user_id = data.get("reply_to")
    await state.clear()

    lang = get_lang(user_id)
    header = TEXTS[lang]["replied"]
    media_type, file_id = get_media_type(message)

    try:
        if media_type == "photo":
            await bot.send_photo(user_id, file_id, caption=(header + (message.caption or "")).strip(), parse_mode="HTML")
        elif media_type == "video":
            await bot.send_video(user_id, file_id, caption=(header + (message.caption or "")).strip(), parse_mode="HTML")
        elif media_type == "document":
            await bot.send_document(user_id, file_id, caption=(header + (message.caption or "")).strip(), parse_mode="HTML")
        elif media_type == "audio":
            await bot.send_audio(user_id, file_id, caption=(header + (message.caption or "")).strip(), parse_mode="HTML")
        elif media_type == "voice":
            await bot.send_voice(user_id, file_id)
        elif media_type == "sticker":
            await bot.send_message(user_id, header, parse_mode="HTML")
            await bot.send_sticker(user_id, file_id)
        elif media_type == "video_note":
            await bot.send_message(user_id, header, parse_mode="HTML")
            await bot.send_video_note(user_id, file_id)
        else:
            await bot.send_message(user_id, header + (message.text or ""), parse_mode="HTML")
        await message.answer(f"Ответ отправлен → <code>{user_id}</code>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

# ===================== ОСНОВНОЙ ХЕНДЛЕР ЮЗЕРА =====================

@dp.message()
async def handle_user_message(message: Message, state: FSMContext):
    if message.from_user.id == OWNER_ID:
        return

    uid = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""

    if is_banned(uid):
        await message.answer(TEXTS[get_lang(uid)]["banned"])
        return

    lang = get_user_lang(uid)
    if not lang:
        await message.answer(TEXTS["ru"]["choose_lang"], reply_markup=lang_keyboard())
        return

    if not is_user_active(uid):
        await message.answer(TEXTS[lang]["not_active"], parse_mode="HTML")
        return

    reset_idle_timer(uid)
    await update_user_status(uid, lang)

    display_name = f"@{username}" if username else full_name
    header = f"<b>{display_name}</b> (<code>{uid}</code>)"

    media_type, file_id = get_media_type(message)
    text = message.text or message.caption or ""
    log_text = f"[{media_type}] {text}" if media_type else (text or "[сообщение]")
    save_message(uid, username, full_name, log_text)

    if media_type:
        pending = get_pending(uid)
        prior_text = pending[1] if pending else ""
        parts = [header]
        combined_text = "\n".join(filter(None, [prior_text, text]))
        if combined_text:
            parts.append(combined_text)
        caption = "\n\n".join(parts)

        if pending:
            try:
                await bot.delete_message(OWNER_ID, pending[0])
            except Exception:
                pass
            clear_pending(uid)

        try:
            if media_type == "photo":
                await bot.send_photo(OWNER_ID, file_id, caption=caption[:1024], parse_mode="HTML", reply_markup=owner_keyboard(uid))
            elif media_type == "video":
                await bot.send_video(OWNER_ID, file_id, caption=caption[:1024], parse_mode="HTML", reply_markup=owner_keyboard(uid))
            elif media_type == "document":
                await bot.send_document(OWNER_ID, file_id, caption=caption[:1024], parse_mode="HTML", reply_markup=owner_keyboard(uid))
            elif media_type == "audio":
                await bot.send_audio(OWNER_ID, file_id, caption=caption[:1024], parse_mode="HTML", reply_markup=owner_keyboard(uid))
            elif media_type == "voice":
                await bot.send_message(OWNER_ID, header, parse_mode="HTML")
                await bot.send_voice(OWNER_ID, file_id, reply_markup=owner_keyboard(uid))
            elif media_type == "sticker":
                await bot.send_message(OWNER_ID, header, parse_mode="HTML")
                await bot.send_sticker(OWNER_ID, file_id, reply_markup=owner_keyboard(uid))
            elif media_type == "video_note":
                await bot.send_message(OWNER_ID, header, parse_mode="HTML")
                await bot.send_video_note(OWNER_ID, file_id, reply_markup=owner_keyboard(uid))
        except Exception as e:
            logging.error(f"Ошибка отправки медиа: {e}")
    else:
        pending = get_pending(uid)
        if pending:
            owner_msg_id, accumulated, _ = pending
            new_accumulated = accumulated + "\n" + text
            new_body = header + "\n\n" + new_accumulated
            try:
                await bot.edit_message_text(
                    chat_id=OWNER_ID,
                    message_id=owner_msg_id,
                    text=new_body[:4096],
                    parse_mode="HTML",
                    reply_markup=owner_keyboard(uid)
                )
                set_pending(uid, owner_msg_id, new_accumulated)
            except Exception:
                sent = await bot.send_message(
                    OWNER_ID, header + "\n\n" + text,
                    parse_mode="HTML", reply_markup=owner_keyboard(uid)
                )
                set_pending(uid, sent.message_id, text)
        else:
            sent = await bot.send_message(
                OWNER_ID, header + "\n\n" + text,
                parse_mode="HTML", reply_markup=owner_keyboard(uid)
            )
            set_pending(uid, sent.message_id, text)

# ===================== ЗАПУСК =====================

async def main():
    global bot
    original_init = aiohttp.TCPConnector.__init__
    def patched_init(self, *args, **kwargs):
        kwargs.setdefault('family', socket.AF_INET)
        original_init(self, *args, **kwargs)
    aiohttp.TCPConnector.__init__ = patched_init

    bot = Bot(token=BOT_TOKEN)
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
