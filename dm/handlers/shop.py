from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import bot_instance
from config import OWNER_ID
from database import (
    get_shop_items, get_shop_item, add_shop_item, delete_shop_item,
    save_active_order, get_active_order_msg, delete_active_order # <-- Добавь эти три
)
from texts import TEXTS
from keyboards import (
    shop_list_keyboard, shop_item_keyboard,
    owner_shop_keyboard, order_keyboard, owner_keyboard
)
from utils import get_lang

router = Router()


class ShopAddState(StatesGroup):
    title        = State()
    description  = State()
    price        = State()
    payment_info = State()
    photo        = State()


# ── Юзер ──────────────────────────────────────────────

@router.message(Command("shop"))
async def cmd_shop(message: Message):
    uid = message.from_user.id

    if uid == OWNER_ID:
        await message.answer("Управление магазином:", reply_markup=owner_shop_keyboard())
        return

    lang  = get_lang(uid)
    items = get_shop_items()
    if not items:
        await message.answer(TEXTS[lang]["shop_empty"])
        return
    await message.answer(TEXTS[lang]["shop_title"], parse_mode="HTML", reply_markup=shop_list_keyboard(items))


@router.callback_query(F.data.startswith("order_accept_"))
async def shop_order_accept(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return
    
    data = callback.data.split("_")
    user_id = int(data[2])
    item_id = int(data[3])
    
    item = get_shop_item(item_id)
    if not item:
        await callback.answer("Товар не найден в базе.", show_alert=True)
        return
        
    title = item[1]
    # Берем реквизиты из базы данных (payment_info)
    payment_info = item[4] if item[4] else "Реквизиты не указаны владельцем."
    
    # Текст, который изначально отправляется пользователю
    user_text = (
        f"<b> Ваш заказ на товар «{title}» принят!</b>\n\n"
        f" Реквизиты для оплаты:\n<code>{payment_info}</code>"
    )
    
    try:
        # Отправляем сообщение пользователю
        user_msg = await bot_instance.bot.send_message(chat_id=user_id, text=user_text, parse_mode="HTML")
        
        # Сохраняем ID этого сообщения в базу данных
        save_active_order(user_id, item_id, user_msg.message_id)
        
        # Обновляем инлайн-кнопки в твоем чате (добавляется кнопка скрыть карточку)
        await callback.message.edit_reply_markup(reply_markup=order_keyboard(user_id, item_id, details_shown=True))
        await callback.answer("Заказ принят, реквизиты отправлены пользователю.")
    except Exception as e:
        await callback.answer(f"Не удалось отправить сообщение пользователю: {e}", show_alert=True)

@router.callback_query(F.data.startswith("shopitem_"))
async def shop_item_view(callback: CallbackQuery):
    uid     = callback.from_user.id
    lang    = get_lang(uid)
    item_id = int(callback.data.split("_")[1])
    item    = get_shop_item(item_id)

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
        await bot_instance.bot.send_photo(uid, photo_id, caption=text, parse_mode="HTML", reply_markup=kb)
    else:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("shopbuy_"))
async def shop_buy(callback: CallbackQuery):
    uid     = callback.from_user.id
    lang    = get_lang(uid)
    item_id = int(callback.data.split("_")[1])
    item    = get_shop_item(item_id)

    if not item:
        await callback.answer("Товар не найден.", show_alert=True)
        return

    _, title, _, price, _, _ = item
    username  = callback.from_user.username or ""
    full_name = callback.from_user.full_name or ""
    display   = f"@{username}" if username else full_name

    await bot_instance.bot.send_message(
        OWNER_ID,
        f"<b>Новый заказ</b>\n\n"
        f"Товар: {title}\n"
        f"Цена: {price}\n\n"
        f"От: {display} (<code>{uid}</code>)",
        parse_mode="HTML",
        reply_markup=order_keyboard(uid, item_id)
    )
    await callback.answer(TEXTS[lang]["order_done"], show_alert=True)


# ── Владелец — принять / отменить заказ ───────────────

@router.callback_query(F.data.startswith("order_accept_"))
async def order_accept(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return
    parts   = callback.data.split("_")
    user_id = int(parts[2])
    item_id = int(parts[3])
    item    = get_shop_item(item_id)
    lang    = get_lang(user_id)

    payment_info = item[4] if item else ""
    title        = item[1] if item else "товар"

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
        await bot_instance.bot.send_message(user_id, text, parse_mode="HTML")
    except Exception:
        pass

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Заказ принят, реквизиты отправлены.", show_alert=True)


@router.callback_query(F.data.startswith("order_decline_"))
async def order_decline(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return
    parts   = callback.data.split("_")
    user_id = int(parts[2])
    lang    = get_lang(user_id)

    decline_texts = {
        "ru": "Заказ отменён.",
        "uk": "Замовлення скасовано.",
        "en": "Order declined.",
    }
    try:
        await bot_instance.bot.send_message(user_id, decline_texts.get(lang, "Order declined."))
    except Exception:
        pass
    
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Заказ отменён.", show_alert=True)


@router.callback_query(F.data.startswith("order_toggle_"))
async def shop_order_toggle(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return
        
    data = callback.data.split("_")
    user_id = int(data[2])
    item_id = int(data[3])
    next_status = int(data[4]) # 1 = показать карточку, 0 = скрыть карточку
    
    # Пытаемся найти ID сообщения, которое видит пользователь
    user_msg_id = get_active_order_msg(user_id, item_id)
    if not user_msg_id:
        await callback.answer("Сообщение у пользователя не найдено (возможно, заказ устарел).", show_alert=True)
        return
        
    item = get_shop_item(item_id)
    if not item:
        await callback.answer("Товар не найден.", show_alert=True)
        return
        
    title = item[1]
    payment_info = item[4] if item[4] else "Реквизиты не указаны"
    
    # Меняем текст сообщения пользователя в зависимости от нажатой кнопки
    if next_status == 1:
        new_text = (
            f"<b>Ваш заказ на товар «{title}» принят!</b>\n\n"
            f"Реквизиты для оплаты:\n<code>{payment_info}</code>"
        )
        is_shown = True
    else:
        new_text = (
            f"<b>Ваш заказ на товар «{title}» принят!</b>\n\n"
            f"<i>Владелец временно скрыл реквизиты. Ожидайте обновления информации.</i>"
        )
        is_shown = False
        
    try:
        # Редактируем сообщение прямо в чате у пользователя!
        await bot_instance.bot.edit_message_text(
            chat_id=user_id,
            message_id=user_msg_id,
            text=new_text,
            parse_mode="HTML"
        )
        
        # Меняем кнопку у тебя (админа) на противоположную
        await callback.message.edit_reply_markup(reply_markup=order_keyboard(user_id, item_id, details_shown=is_shown))
        
        status_word = "показаны" if is_shown else "скрыты"
        await callback.answer(f"Реквизиты {status_word} у юзера!")
    except Exception as e:
        await callback.answer(f"Ошибка изменения сообщения: {e}", show_alert=True)

    
# ── Владелец — управление товарами ────────────────────

@router.callback_query(F.data == "shop_add")
async def shop_add_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        return
    await state.set_state(ShopAddState.title)
    await callback.message.answer("Введи название товара:")
    await callback.answer()


@router.message(ShopAddState.title)
async def shop_add_title(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    await state.update_data(title=message.text)
    await state.set_state(ShopAddState.description)
    await message.answer("Описание товара (или отправь — чтобы пропустить):")


@router.message(ShopAddState.description)
async def shop_add_description(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    await state.update_data(description=message.text if message.text != "—" else "")
    await state.set_state(ShopAddState.price)
    await message.answer("Цена (например: 500 грн, $20):")


@router.message(ShopAddState.price)
async def shop_add_price(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    await state.update_data(price=message.text)
    await state.set_state(ShopAddState.payment_info)
    await message.answer("Реквизиты для оплаты (или — чтобы пропустить):")


@router.message(ShopAddState.payment_info)
async def shop_add_payment(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    await state.update_data(payment_info=message.text if message.text != "—" else "")
    await state.set_state(ShopAddState.photo)
    await message.answer("Отправь фото товара (или — чтобы без фото):")


@router.message(ShopAddState.photo)
async def shop_add_photo(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    data     = await state.get_data()
    photo_id = message.photo[-1].file_id if message.photo else None
    await state.clear()
    add_shop_item(data["title"], data["description"], data["price"], data["payment_info"], photo_id)
    await message.answer(f"Товар «{data['title']}» добавлен в магазин.")


@router.callback_query(F.data == "shop_list_owner")
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
    lines.append("\nУдалить: /delitem_ID (пример: /delitem_3)")
    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


@router.message(F.text.regexp(r"^/delitem_(\d+)$"))
async def shop_delete_item(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    item_id = int(message.text.split("_")[1])
    if not get_shop_item(item_id):
        await message.answer("Товар не найден.")
        return
    delete_shop_item(item_id)
    await message.answer(f"Товар [{item_id}] удалён.")
