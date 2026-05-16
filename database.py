import sqlite3
from datetime import datetime


def get_db():
    return sqlite3.connect("messages.db")


def init_db():
    conn = get_db()
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
    c.execute("""
        CREATE TABLE IF NOT EXISTS active_orders (
            user_id INTEGER,
            item_id INTEGER,
            user_msg_id INTEGER,
            PRIMARY KEY (user_id, item_id)
        )
    """)
    conn.commit()
    conn.close()


# ── Сообщения ──────────────────────────────────────────

def save_message(user_id, username, full_name, text):
    conn = get_db()
    conn.execute(
        "INSERT INTO messages (user_id, username, full_name, message_text, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, username or "", full_name or "", text, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()


# ── Настройки пользователя ─────────────────────────────

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


# ── Pending (накопленные сообщения) ────────────────────

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
        "INSERT OR REPLACE INTO pending_messages (user_id, owner_message_id, accumulated_text, has_media) "
        "VALUES (?, ?, ?, ?)",
        (user_id, owner_message_id, accumulated_text, 1 if has_media else 0)
    )
    conn.commit()
    conn.close()


def clear_pending(user_id):
    conn = get_db()
    conn.execute("DELETE FROM pending_messages WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


# ── Статус-сообщение у юзера ───────────────────────────

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


# ── Магазин ────────────────────────────────────────────

def get_shop_items():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, description, price, payment_info, photo_id "
        "FROM shop_items WHERE is_active=1 ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return rows


def get_shop_item(item_id):
    conn = get_db()
    row = conn.execute(
        "SELECT id, title, description, price, payment_info, photo_id "
        "FROM shop_items WHERE id=? AND is_active=1",
        (item_id,)
    ).fetchone()
    conn.close()
    return row


def add_shop_item(title, description, price, payment_info, photo_id):
    conn = get_db()
    conn.execute(
        "INSERT INTO shop_items (title, description, price, payment_info, photo_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (title, description, price, payment_info, photo_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()


def delete_shop_item(item_id):
    conn = get_db()
    conn.execute("UPDATE shop_items SET is_active=0 WHERE id=?", (item_id,))
    conn.commit()
    conn.close()

def save_active_order(user_id, item_id, user_msg_id):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO active_orders (user_id, item_id, user_msg_id) VALUES (?, ?, ?)",
        (user_id, item_id, user_msg_id)
    )
    conn.commit()
    conn.close()

def get_active_order_msg(user_id, item_id):
    conn = get_db()
    row = conn.execute("SELECT user_msg_id FROM active_orders WHERE user_id=? AND item_id=?", (user_id, item_id)).fetchone()
    conn.close()
    return row[0] if row else None

def delete_active_order(user_id, item_id):
    conn = get_db()
    conn.execute("DELETE FROM active_orders WHERE user_id=? AND item_id=?", (user_id, item_id))
    conn.commit()
    conn.close()