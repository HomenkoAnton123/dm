from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import bot_instance
from config import OWNER_ID
from database import (
    get_db, set_banned, set_user_active, clear_pending, get_user_lang
)
from texts import TEXTS
from keyboards import owner_keyboard
from utils import get_lang, get_media_type, cancel_idle_timer, delete_user_status

router = Router()


class ReplyState(StatesGroup):
    waiting_reply = State()


@router.message(Command("history"))
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


@router.message(Command("clear"))
async def cmd_clear(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    conn = get_db()
    conn.execute("DELETE FROM messages")
    conn.execute("DELETE FROM pending_messages")
    conn.commit()
    conn.close()
    await message.answer("БД очищена.")


@router.message(Command("banlist"))
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


@router.callback_query(F.data.startswith("ban_"))
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
        await bot_instance.bot.send_message(user_id, TEXTS[lang]["banned"])
    except Exception:
        pass
    await callback.answer(f"Пользователь {user_id} забанен", show_alert=True)


@router.callback_query(F.data.startswith("unban_"))
async def owner_unban(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return
    user_id = int(callback.data.split("_")[1])
    set_banned(user_id, False)
    await callback.answer(f"Пользователь {user_id} разбанен", show_alert=True)


@router.callback_query(F.data.startswith("reply_"))
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


@router.message(ReplyState.waiting_reply)
async def owner_send_reply(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    data = await state.get_data()
    user_id = data.get("reply_to")
    await state.clear()

    lang   = get_lang(user_id)
    header = TEXTS[lang]["replied"]
    media_type, file_id = get_media_type(message)
    bot = bot_instance.bot

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
