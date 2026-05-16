from config import IDLE_TIMEOUT_MINUTES

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
            "/help — это сообщение\n\n"
            "<b>О боте:</b>\n"
            "Бот позволяет написать мне анонимно. Твоё имя не раскрывается.\n\n"
            "<b>Сменить язык:</b>"
        ),
        "stopped":      "Пересылка остановлена. Отправь /start чтобы возобновить.",
        "auto_stopped": f"Пересылка остановлена автоматически — нет активности {IDLE_TIMEOUT_MINUTES} мин.\nОтправь /start чтобы возобновить.",
        "resumed":      "Пересылка возобновлена. Пиши:",
        "sending":      "<b>Отправка включена.</b>\nПиши — сообщения будут переданы.\n\n/stop — остановить.",
        "not_active":   "Пересылка остановлена. Отправь /start чтобы возобновить.",
        "banned":       "Ты заблокирован.",
        "replied":      "<b>Ответ:</b>\n\n",
        "shop_empty":   "Магазин пока пуст.",
        "shop_title":   "<b>Магазин</b>\n\nВыбери товар:",
        "order_done":   "Заказ оформлен. Ожидай ответа владельца.",
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
            "/help — це повідомлення\n\n"
            "<b>Про бота:</b>\n"
            "Бот дозволяє написати мені анонімно. Твоє ім'я не розкривається.\n\n"
            "<b>Змінити мову:</b>"
        ),
        "stopped":      "Пересилання зупинено. Надішли /start щоб відновити.",
        "auto_stopped": f"Пересилання зупинено автоматично — немає активності {IDLE_TIMEOUT_MINUTES} хв.\nНадішли /start щоб відновити.",
        "resumed":      "Пересилання відновлено. Пиши:",
        "sending":      "<b>Надсилання увімкнено.</b>\nПиши — повідомлення будуть передані.\n\n/stop — зупинити.",
        "not_active":   "Пересилання зупинено. Надішли /start щоб відновити.",
        "banned":       "Тебе заблоковано.",
        "replied":      "<b>Відповідь:</b>\n\n",
        "shop_empty":   "Магазин поки порожній.",
        "shop_title":   "<b>Магазин</b>\n\nОбери товар:",
        "order_done":   "Замовлення оформлено. Очікуй відповіді власника.",
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
            "/help — this message\n\n"
            "<b>About:</b>\n"
            "This bot lets you write to me anonymously. Your identity is not revealed.\n\n"
            "<b>Change language:</b>"
        ),
        "stopped":      "Forwarding stopped. Send /start to resume.",
        "auto_stopped": f"Forwarding stopped automatically — no activity for {IDLE_TIMEOUT_MINUTES} min.\nSend /start to resume.",
        "resumed":      "Forwarding resumed. Write:",
        "sending":      "<b>Forwarding is on.</b>\nWrite — messages will be passed on.\n\n/stop — stop.",
        "not_active":   "Forwarding is stopped. Send /start to resume.",
        "banned":       "You are blocked.",
        "replied":      "<b>Reply:</b>\n\n",
        "shop_empty":   "The shop is empty for now.",
        "shop_title":   "<b>Shop</b>\n\nChoose an item:",
        "order_done":   "Order placed. Wait for the owner's reply.",
    },
}
