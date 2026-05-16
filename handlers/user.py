from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext

import bot_instance
from config import OWNER_ID
from database import (
    get_user_lang, set_user_lang, set_user_active, is_banned,
    is_user_active, set_status_msg, save_message,
    get_pending, set_pending, clear_pending
)
from texts import TEXTS
from keyboards import lang_keyboard, owner_keyboard
from utils import get_lang, get_media_type, update_user_status, reset_idle_timer

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    if message.from_user.id == OWNER_ID:
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


@router.callback_query(F.data.startswith("lang_"))
async def choose_language(callback: CallbackQuery):
    lang = callback.data.split("_")[1]
    uid = callback.from_user.id
    set_user_lang(uid, lang)
    set_user_active(uid, True)
    reset_idle_timer(uid)
    await callback.message.edit_text(TEXTS[lang]["welcome"], parse_mode="HTML")
    msg = await bot_instance.bot.send_message(uid, TEXTS[lang]["sending"], parse_mode="HTML")
    set_status_msg(uid, msg.message_id)
    await callback.answer()


@router.message(Command("help"))
async def cmd_help(message: Message):
    if message.from_user.id == OWNER_ID:
        return
    uid = message.from_user.id
    if is_banned(uid):
        return
    lang = get_lang(uid)
    await message.answer(TEXTS[lang]["help"], parse_mode="HTML", reply_markup=lang_keyboard())


@router.message(Command("stop"))
async def cmd_stop(message: Message):
    if message.from_user.id == OWNER_ID:
        return
    from utils import cancel_idle_timer, delete_user_status
    uid = message.from_user.id
    lang = get_lang(uid)
    set_user_active(uid, False)
    cancel_idle_timer(uid)
    clear_pending(uid)
    await delete_user_status(uid)
    await message.answer(TEXTS[lang]["stopped"], parse_mode="HTML")


@router.message()
async def handle_user_message(message: Message, state: FSMContext):
    if message.from_user.id == OWNER_ID:
        return

    uid = message.from_user.id
    username  = message.from_user.username or ""
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
    text     = message.text or message.caption or ""
    log_text = f"[{media_type}] {text}" if media_type else (text or "[сообщение]")
    save_message(uid, username, full_name, log_text)

    bot = bot_instance.bot

    if media_type:
        pending    = get_pending(uid)
        prior_text = pending[1] if pending else ""
        parts      = [header]
        combined   = "\n".join(filter(None, [prior_text, text]))
        if combined:
            parts.append(combined)
        caption = "\n\n".join(parts)

        if pending:
            try:
                await bot.delete_message(OWNER_ID, pending[0])
            except Exception:
                pass
            clear_pending(uid)

        try:
            kb = owner_keyboard(uid)
            if media_type == "photo":
                await bot.send_photo(OWNER_ID,    file_id, caption=caption[:1024], parse_mode="HTML", reply_markup=kb)
            elif media_type == "video":
                await bot.send_video(OWNER_ID,    file_id, caption=caption[:1024], parse_mode="HTML", reply_markup=kb)
            elif media_type == "document":
                await bot.send_document(OWNER_ID, file_id, caption=caption[:1024], parse_mode="HTML", reply_markup=kb)
            elif media_type == "audio":
                await bot.send_audio(OWNER_ID,    file_id, caption=caption[:1024], parse_mode="HTML", reply_markup=kb)
            elif media_type == "voice":
                await bot.send_message(OWNER_ID, header, parse_mode="HTML")
                await bot.send_voice(OWNER_ID, file_id, reply_markup=kb)
            elif media_type == "sticker":
                await bot.send_message(OWNER_ID, header, parse_mode="HTML")
                await bot.send_sticker(OWNER_ID, file_id, reply_markup=kb)
            elif media_type == "video_note":
                await bot.send_message(OWNER_ID, header, parse_mode="HTML")
                await bot.send_video_note(OWNER_ID, file_id, reply_markup=kb)
        except Exception as e:
            import logging
            logging.error(f"Ошибка отправки медиа: {e}")
    else:
        pending = get_pending(uid)
        if pending:
            owner_msg_id, accumulated, _ = pending
            new_accumulated = accumulated + "\n" + text
            new_body = header + "\n\n" + new_accumulated
            try:
                await bot.edit_message_text(
                    chat_id=OWNER_ID, message_id=owner_msg_id,
                    text=new_body[:4096], parse_mode="HTML",
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
