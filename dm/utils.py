import asyncio
import logging
from aiogram.types import Message

from config import IDLE_TIMEOUT_MINUTES, OWNER_ID
from database import (
    get_user_lang, is_user_active, set_user_active,
    clear_pending, get_status_msg, set_status_msg, clear_status_msg
)
from texts import TEXTS

# Импортируем bot лениво чтобы избежать циклического импорта
import bot_instance

idle_tasks: dict = {}


def get_lang(user_id):
    return get_user_lang(user_id) or "ru"


def get_media_type(message: Message):
    if message.photo:      return "photo",      message.photo[-1].file_id
    if message.video:      return "video",       message.video.file_id
    if message.document:   return "document",    message.document.file_id
    if message.audio:      return "audio",       message.audio.file_id
    if message.voice:      return "voice",       message.voice.file_id
    if message.sticker:    return "sticker",     message.sticker.file_id
    if message.video_note: return "video_note",  message.video_note.file_id
    return None, None


async def update_user_status(user_id, lang):
    """Создаём статус-сообщение один раз. Если уже есть — не трогаем."""
    old_id = get_status_msg(user_id)
    if old_id:
        return
    msg = await bot_instance.bot.send_message(user_id, TEXTS[lang]["sending"], parse_mode="HTML")
    set_status_msg(user_id, msg.message_id)


async def delete_user_status(user_id):
    old_id = get_status_msg(user_id)
    if old_id:
        try:
            await bot_instance.bot.delete_message(user_id, old_id)
        except Exception:
            pass
        clear_status_msg(user_id)


# ── Авто-стоп ──────────────────────────────────────────

async def idle_timer(user_id):
    await asyncio.sleep(IDLE_TIMEOUT_MINUTES * 60)
    lang = get_lang(user_id)
    if is_user_active(user_id):
        set_user_active(user_id, False)
        clear_pending(user_id)
        old_status = get_status_msg(user_id)
        if old_status:
            try:
                await bot_instance.bot.delete_message(user_id, old_status)
            except Exception:
                pass
            clear_status_msg(user_id)
        try:
            await bot_instance.bot.send_message(user_id, TEXTS[lang]["auto_stopped"], parse_mode="HTML")
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
