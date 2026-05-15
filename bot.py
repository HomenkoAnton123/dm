import asyncio
import sqlite3
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ===================== НАСТРОЙКИ =====================
BOT_TOKEN = "8878080269:AAFlh-1yI8BjfI9JtSarBXs1bSy3l0yudgg"   # <-- Вставь токен бота сюда
OWNER_ID = 6141804437                  # <-- Вставь свой Telegram ID
IDLE_TIMEOUT_MINUTES = 5
# =====================================================

logging.basicConfig(level=logging.INFO)

import socket
import aiohttp

# bot создаётся в main() чтобы TCPConnector имел event loop
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
        "stopped": "Пересылка остановлена. Отправь /start чтобы возобновить.",
        "auto_stopped": f"Пересылка остановлена автоматически — нет активности {IDLE_TIMEOUT_MINUTES} мин.\nОтправь /start чтобы возобновить.",
        "resumed": "Пересылка возобновлена. Пиши:",
        "sending": "<b>Отправка включена.</b>\nПиши — сообщения будут переданы.\n\n/stop — остановить.",
        "not_active": "Пересылка остановлена. Отправь /start чтобы возобновить.",
        "banned": "Ты заблокирован.",
        "replied": "<b>Ответ:</b>\n\n",
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
        "stopped": "Пересилання зупинено. Надішли /start щоб відновити.",
        "auto_stopped": f"Пересилання зупинено автоматично — немає активності {IDLE_TIMEOUT_MINUTES} хв.\nНадішли /start щоб відновити.",
        "resumed": "Пересилання відновлено. Пиши:",
        "sending": "<b>Надсилання увімкнено.</b>\nПиши — повідомлення будуть передані.\n\n/stop — зупинити.",
        "not_active": "Пересилання зупинено. Надішли /start щоб відновити.",
        "banned": "Тебе заблоковано.",
        "replied": "<b>Відповідь:</b>\n\n",
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
        "stopped": "Forwarding stopped. Send /start to resume.",
        "auto_stopped": f"Forwarding stopped automatically — no activity for {IDLE_TIMEOUT_MINUTES} min.\nSend /start to resume.",
        "resumed": "Forwarding resumed. Write:",
        "sending": "<b>Forwarding is on.</b>\nWrite — messages will be passed on.\n\n/stop — stop.",
        "not_active": "Forwarding is stopped. Send /start to resume.",
        "banned": "You are blocked.",
        "replied": "<b>Reply:</b>\n\n",
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

# ===================== FSM =====================

class ReplyState(StatesGroup):
    waiting_reply = State()

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
    """Создаём статус-сообщение один раз. Если уже есть — не трогаем."""
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

# ===================== ХЕНДЛЕРЫ ЮЗЕРА =====================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.from_user.id == OWNER_ID:
        await message.answer(
            "<b>Панель владельца</b>\n\n"
            "/history — последние 20 сообщений\n"
            "/clear — очистить БД\n"
            "/banlist — список забаненных\n\n"
            "Кнопки под сообщениями: Ответить / Бан / Разбан",
            parse_mode="HTML"
        )
        return

    uid = message.from_user.id

    if is_banned(uid):
        lang = get_user_lang(uid) or "ru"
        await message.answer(TEXTS[lang]["banned"])
        return

    lang = get_user_lang(uid)

    # Первый запуск — показываем выбор языка
    if not lang:
        await message.answer(TEXTS["ru"]["choose_lang"], reply_markup=lang_keyboard())
        return

    # Повторный /start — возобновляем
    set_user_active(uid, True)
    reset_idle_timer(uid)
    # Сначала инструкция, потом статус-сообщение внизу
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

    # Редактируем сообщение с кнопками на инструкцию
    await callback.message.edit_text(TEXTS[lang]["welcome"], parse_mode="HTML")
    # Отдельным сообщением — статус (юзер видит его последним)
    msg = await bot.send_message(uid, TEXTS[lang]["sending"], parse_mode="HTML")
    set_status_msg(uid, msg.message_id)
    await callback.answer()


@dp.message(Command("stop"))
async def cmd_stop(message: Message):
    if message.from_user.id == OWNER_ID:
        return
    uid = message.from_user.id
    lang = get_user_lang(uid) or "ru"
    set_user_active(uid, False)
    cancel_idle_timer(uid)
    clear_pending(uid)
    await delete_user_status(uid)
    await message.answer(TEXTS[lang]["stopped"], parse_mode="HTML")

# ===================== ХЕНДЛЕРЫ ВЛАДЕЛЬЦА =====================

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
    lang = get_user_lang(user_id) or "ru"
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

    lang = get_user_lang(user_id) or "ru"
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
        lang = get_user_lang(uid) or "ru"
        await message.answer(TEXTS[lang]["banned"])
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
        # Если до медиа был текст (pending) — берём его как caption
        pending = get_pending(uid)
        prior_text = pending[1] if pending else ""
        # caption = header + prior_text + caption самого медиа (если есть)
        parts = [header]
        combined_text = "\n".join(filter(None, [prior_text, text]))
        if combined_text:
            parts.append(combined_text)
        caption = "\n\n".join(parts)

        # Если было текстовое pending — удаляем то сообщение у владельца (заменяем медиа)
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
    # Патч aiohttp чтобы все соединения шли через IPv4
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