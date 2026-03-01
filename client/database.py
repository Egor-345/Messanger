"""
Модуль для работы с локальной базой данных SQLite
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Optional, Dict, Any


class Database:
    """
    Класс для работы с SQLite базой данных
    """

    def __init__(self, db_path: str = "messenger.db"):
        """
        Инициализация подключения к БД

        Args:
            db_path: путь к файлу базы данных
        """
        self.db_path = db_path

        # Создаем папку для БД, если её нет
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

        # Создаем таблицы при первом запуске
        self._create_tables()

    def _get_connection(self):
        """
        Создает и возвращает подключение к БД
        """
        conn = sqlite3.connect(self.db_path)
        # Включаем поддержку внешних ключей
        conn.execute("PRAGMA foreign_keys = ON")
        # Возвращаем строки как словари (удобно)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_tables(self):
        """
        Создает необходимые таблицы, если их нет
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    login TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    display_name TEXT,
                    avatar_path TEXT,
                    status TEXT DEFAULT 'offline',
                    last_seen TIMESTAMP,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    email TEXT,
                    public_key TEXT
                )
            ''')

            # Таблица сообщений
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    text TEXT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    delivered_at TIMESTAMP,
                    read_at TIMESTAMP,
                    status TEXT DEFAULT 'sending',
                    message_type TEXT DEFAULT 'text',
                    file_path TEXT,
                    file_size INTEGER,
                    reply_to_id INTEGER,
                    is_encrypted BOOLEAN DEFAULT 0,
                    metadata TEXT,
                    FOREIGN KEY (sender_id) REFERENCES users(id),
                    FOREIGN KEY (chat_id) REFERENCES chats(id),
                    FOREIGN KEY (reply_to_id) REFERENCES messages(id)
                )
            ''')

            # Таблица чатов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT DEFAULT 'dialog',
                    name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by INTEGER,
                    avatar_path TEXT,
                    last_message_id INTEGER,
                    last_message_preview TEXT,
                    last_message_time TIMESTAMP,
                    is_pinned BOOLEAN DEFAULT 0,
                    metadata TEXT,
                    FOREIGN KEY (created_by) REFERENCES users(id),
                    FOREIGN KEY (last_message_id) REFERENCES messages(id)
                )
            ''')

            # Таблица участников чата
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_participants (
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    unread_count INTEGER DEFAULT 0,
                    last_read_message_id INTEGER,
                    PRIMARY KEY (chat_id, user_id),
                    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')

            conn.commit()
            print("✓ Таблицы успешно созданы или уже существуют")

    # ========== МЕТОДЫ ДЛЯ РАБОТЫ С ПОЛЬЗОВАТЕЛЯМИ ==========

    def add_user(self, login: str, password_hash: str,
                 display_name: str = None) -> int:
        """
        Добавляет нового пользователя

        Returns:
            ID созданного пользователя
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (login, password_hash, display_name)
                VALUES (?, ?, ?)
            ''', (login, password_hash, display_name or login))
            conn.commit()
            return cursor.lastrowid

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Получает пользователя по ID
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_user_by_login(self, login: str) -> Optional[Dict[str, Any]]:
        """
        Получает пользователя по логину
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE login = ?', (login,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_user_status(self, user_id: int, status: str):
        """
        Обновляет статус пользователя
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET status = ?, last_seen = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (status, user_id))
            conn.commit()

    # ========== МЕТОДЫ ДЛЯ РАБОТЫ С СООБЩЕНИЯМИ ==========

    def add_message(self, sender_id: int, chat_id: int, text: str,
                    message_type: str = "text", file_path: str = None) -> int:
        """
        Добавляет новое сообщение

        Returns:
            ID созданного сообщения
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO messages (sender_id, chat_id, text, message_type, file_path)
                VALUES (?, ?, ?, ?, ?)
            ''', (sender_id, chat_id, text, message_type, file_path))
            conn.commit()
            message_id = cursor.lastrowid

            # Обновляем информацию о последнем сообщении в чате
            self.update_chat_last_message(chat_id, message_id, text)

            # Увеличиваем счетчик непрочитанных для всех участников, кроме отправителя
            self.increment_unread_for_participants(chat_id, sender_id)

            return message_id

    def get_chat_messages(self, chat_id: int, limit: int = 50,
                          offset: int = 0) -> List[Dict[str, Any]]:
        """
        Получает историю сообщений чата
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT m.*, u.login as sender_login, u.display_name as sender_name
                FROM messages m
                JOIN users u ON m.sender_id = u.id
                WHERE m.chat_id = ?
                ORDER BY m.sent_at DESC
                LIMIT ? OFFSET ?
            ''', (chat_id, limit, offset))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def mark_message_as_delivered(self, message_id: int):
        """
        Отмечает сообщение как доставленное
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE messages 
                SET status = 'delivered', delivered_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (message_id,))
            conn.commit()

    def mark_message_as_read(self, message_id: int, user_id: int):
        """
        Отмечает сообщение как прочитанное
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE messages 
                SET status = 'read', read_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (message_id,))
            conn.commit()

            # Обновляем last_read_message_id для участника
            cursor.execute('''
                UPDATE chat_participants 
                SET last_read_message_id = ? 
                WHERE user_id = ? AND chat_id = (
                    SELECT chat_id FROM messages WHERE id = ?
                )
            ''', (message_id, user_id, message_id))
            conn.commit()

    # ========== МЕТОДЫ ДЛЯ РАБОТЫ С ЧАТАМИ ==========

    def create_chat(self, chat_type: str, name: str = None,
                    created_by: int = None) -> int:
        """
        Создает новый чат

        Returns:
            ID созданного чата
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO chats (type, name, created_by)
                VALUES (?, ?, ?)
            ''', (chat_type, name, created_by))
            conn.commit()
            return cursor.lastrowid

    def add_participant_to_chat(self, chat_id: int, user_id: int):
        """
        Добавляет участника в чат
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO chat_participants (chat_id, user_id)
                VALUES (?, ?)
            ''', (chat_id, user_id))
            conn.commit()

    def get_user_chats(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Получает все чаты пользователя
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT c.*, cp.unread_count
                FROM chats c
                JOIN chat_participants cp ON c.id = cp.chat_id
                WHERE cp.user_id = ?
                ORDER BY c.last_message_time DESC
            ''', (user_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def update_chat_last_message(self, chat_id: int, message_id: int,
                                 message_preview: str):
        """
        Обновляет информацию о последнем сообщении в чате
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE chats 
                SET last_message_id = ?, 
                    last_message_preview = ?,
                    last_message_time = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (message_id, message_preview[:50], chat_id))
            conn.commit()

    def increment_unread_for_participants(self, chat_id: int,
                                          exclude_user_id: int):
        """
        Увеличивает счетчик непрочитанных для всех участников, кроме указанного
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE chat_participants 
                SET unread_count = unread_count + 1 
                WHERE chat_id = ? AND user_id != ?
            ''', (chat_id, exclude_user_id))
            conn.commit()

    def reset_unread_count(self, chat_id: int, user_id: int):
        """
        Сбрасывает счетчик непрочитанных для пользователя в чате
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE chat_participants 
                SET unread_count = 0 
                WHERE chat_id = ? AND user_id = ?
            ''', (chat_id, user_id))
            conn.commit()


# ========== ТЕСТИРОВАНИЕ ==========

if __name__ == "__main__":
    print("=" * 50)
    print("ТЕСТИРОВАНИЕ БАЗЫ ДАННЫХ")
    print("=" * 50)

    # Создаем экземпляр БД (в памяти для теста)
    db = Database(":memory:")  # :memory: - БД в оперативной памяти

    # Тест 1: Добавление пользователей
    print("\n1. Добавление пользователей:")
    user1_id = db.add_user("alice", "hash123", "Алиса")
    user2_id = db.add_user("bob", "hash456", "Боб")
    print(
        f"   Созданы пользователи: Alice (id={user1_id}), Bob (id={user2_id})")

    # Тест 2: Получение пользователя
    print("\n2. Получение пользователя:")
    user = db.get_user(user1_id)
    print(f"   {user}")

    # Тест 3: Создание чата
    print("\n3. Создание чата:")
    chat_id = db.create_chat("dialog", created_by=user1_id)
    db.add_participant_to_chat(chat_id, user1_id)
    db.add_participant_to_chat(chat_id, user2_id)
    print(f"   Создан чат id={chat_id} с участниками {user1_id}, {user2_id}")

    # Тест 4: Отправка сообщений
    print("\n4. Отправка сообщений:")
    msg1_id = db.add_message(user1_id, chat_id, "Привет, Боб!")
    msg2_id = db.add_message(user2_id, chat_id, "Привет, Алиса!")
    print(f"   Отправлено 2 сообщения")

    # Тест 5: Получение истории
    print("\n5. История чата:")
    messages = db.get_chat_messages(chat_id, limit=10)
    for msg in messages:
        print(f"   [{msg['sent_at']}] {msg['sender_name']}: {msg['text']}")

    # Тест 6: Получение чатов пользователя
    print("\n6. Чаты пользователя Алиса:")
    chats = db.get_user_chats(user1_id)
    for chat in chats:
        print(
            f"   Чат id={chat['id']}, последнее: {chat['last_message_preview']}, "
            f"непрочитано: {chat['unread_count']}")

    print("\n" + "=" * 50)
    print("✓ Все тесты пройдены успешно!")
    print("=" * 50)