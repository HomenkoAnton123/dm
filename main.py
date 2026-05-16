import asyncio
import socket
import aiohttp
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

import bot_instance
from config import BOT_TOKEN, OWNER_ID
from database import init_db
from handlers import user, owner, shop

logging.basicConfig(level=logging.INFO)

dp = Dispatcher(storage=MemoryStorage())


async def main():
    # Патч aiohttp — принудительно IPv4 (для PythonAnywhere и др.)
    original_init = aiohttp.TCPConnector.__init__
    def patched_init(self, *args, **kwargs):
        kwargs.setdefault("family", socket.AF_INET)
        original_init(self, *args, **kwargs)
    aiohttp.TCPConnector.__init__ = patched_init

    bot_instance.bot = Bot(token=BOT_TOKEN)

    init_db()

    # Приветствие владельцу при запуске
    try:
        await bot_instance.bot.send_message(
            OWNER_ID,
            "<b>Бот запущен.</b>\n\n"
            "/history — последние 20 сообщений\n"
            "/clear — очистить БД\n"
            "/banlist — забаненные\n"
            "/shop — управление магазином",
            parse_mode="HTML"
        )
    except Exception:
        pass

    # Регистрируем роутеры
    # Порядок важен: owner и shop раньше user,
    # чтобы команды владельца не перехватывал общий хендлер
    dp.include_router(owner.router)
    dp.include_router(shop.router)
    dp.include_router(user.router)

    await dp.start_polling(bot_instance.bot)


if __name__ == "__main__":
    asyncio.run(main())
