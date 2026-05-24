import sqlite3
import bcrypt
from datetime import datetime

class Database:
    def __init__(self, db_path="messenger.db"):
        self.db_path = db_path
        self._create_tables()
    
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _create_tables(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    login TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    display_name TEXT,
                    status TEXT DEFAULT 'offline',
                    last_seen TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица чатов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT DEFAULT 'dialog',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица участников чатов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_participants (
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, user_id),
                    FOREIGN KEY (chat_id) REFERENCES chats(id),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Таблица сообщений
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    text TEXT,
                    file_path TEXT,
                    file_size INTEGER,
                    file_type TEXT DEFAULT 'file',
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    delivered_at TIMESTAMP,
                    read_at TIMESTAMP,
                    status TEXT DEFAULT 'sent',
                    message_type TEXT DEFAULT 'text',
                    is_edited BOOLEAN DEFAULT 0,
                    edited_at TIMESTAMP,
                    FOREIGN KEY (sender_id) REFERENCES users(id),
                    FOREIGN KEY (chat_id) REFERENCES chats(id)
                )
            ''')
            
            # Таблица прочтений
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS message_reads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (message_id) REFERENCES messages(id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    UNIQUE(message_id, user_id)
                )
            ''')
            
            # Таблица реакций
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS message_reactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    reaction TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (message_id) REFERENCES messages(id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    UNIQUE(message_id, user_id)
                )
            ''')
            
            conn.commit()
            print("✅ Все таблицы созданы")
    
    # ========== РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ==========
    
    def hash_password(self, password: str) -> str:
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    def check_password(self, password: str, hashed: str) -> bool:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    
    def add_user(self, login: str, password: str, display_name: str = None) -> int:
        password_hash = self.hash_password(password)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (login, password_hash, display_name)
                VALUES (?, ?, ?)
            ''', (login, password_hash, display_name or login))
            conn.commit()
            return cursor.lastrowid
    
    def get_user(self, user_id: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_user_by_login(self, login: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE login = ?', (login,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def verify_user(self, login: str, password: str):
        user = self.get_user_by_login(login)
        if user and self.check_password(password, user['password_hash']):
            return user
        return None
    
    def update_user_status(self, user_id: int, status: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET status = ?, last_seen = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (status, user_id))
            conn.commit()
    
    # ========== ЧАТЫ ==========
    
    def get_or_create_dialog(self, user1_id, user2_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT c.id FROM chats c
                JOIN chat_participants cp1 ON c.id = cp1.chat_id
                JOIN chat_participants cp2 ON c.id = cp2.chat_id
                WHERE c.type = 'dialog'
                  AND cp1.user_id = ?
                  AND cp2.user_id = ?
            ''', (user1_id, user2_id))
            
            row = cursor.fetchone()
            if row:
                return row['id']
            
            cursor.execute('INSERT INTO chats (type) VALUES ("dialog")')
            chat_id = cursor.lastrowid
            
            cursor.execute('INSERT INTO chat_participants (chat_id, user_id) VALUES (?, ?)', (chat_id, user1_id))
            cursor.execute('INSERT INTO chat_participants (chat_id, user_id) VALUES (?, ?)', (chat_id, user2_id))
            
            conn.commit()
            return chat_id
    
    def get_messages_between_users(self, user1_id, user2_id, limit=50, offset=0):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT c.id FROM chats c
                    JOIN chat_participants cp1 ON c.id = cp1.chat_id
                    JOIN chat_participants cp2 ON c.id = cp2.chat_id
                    WHERE c.type = 'dialog'
                      AND cp1.user_id = ?
                      AND cp2.user_id = ?
                ''', (user1_id, user2_id))
                
                chat_row = cursor.fetchone()
                if not chat_row:
                    return []
                
                chat_id = chat_row['id']
                
                cursor.execute('''
                    SELECT m.*, u.display_name as sender_name
                    FROM messages m
                    JOIN users u ON m.sender_id = u.id
                    WHERE m.chat_id = ?
                    ORDER BY m.sent_at DESC
                    LIMIT ? OFFSET ?
                ''', (chat_id, limit, offset))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows][::-1]
        except Exception as e:
            print(f"Ошибка: {e}")
            return []
    
    def get_total_messages_count(self, user1_id, user2_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT c.id FROM chats c
                JOIN chat_participants cp1 ON c.id = cp1.chat_id
                JOIN chat_participants cp2 ON c.id = cp2.chat_id
                WHERE c.type = 'dialog'
                  AND cp1.user_id = ?
                  AND cp2.user_id = ?
            ''', (user1_id, user2_id))
            
            chat_row = cursor.fetchone()
            if not chat_row:
                return 0
            
            chat_id = chat_row['id']
            
            cursor.execute('SELECT COUNT(*) as count FROM messages WHERE chat_id = ?', (chat_id,))
            row = cursor.fetchone()
            return row['count'] if row else 0
    
    def search_messages_in_chat(self, user1_id, user2_id, query, limit=50, offset=0):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT c.id FROM chats c
                    JOIN chat_participants cp1 ON c.id = cp1.chat_id
                    JOIN chat_participants cp2 ON c.id = cp2.chat_id
                    WHERE c.type = 'dialog'
                      AND cp1.user_id = ?
                      AND cp2.user_id = ?
                ''', (user1_id, user2_id))
                
                chat_row = cursor.fetchone()
                if not chat_row:
                    return []
                
                chat_id = chat_row['id']
                
                cursor.execute('''
                    SELECT m.*, u.display_name as sender_name
                    FROM messages m
                    JOIN users u ON m.sender_id = u.id
                    WHERE m.chat_id = ? AND m.text LIKE ?
                    ORDER BY m.sent_at DESC
                    LIMIT ? OFFSET ?
                ''', (chat_id, f'%{query}%', limit, offset))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows][::-1]
        except Exception as e:
            print(f"Ошибка поиска: {e}")
            return []
    
    # ========== СООБЩЕНИЯ ==========
    
    def create_message(self, sender_id, chat_id, text, message_type="text"):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO messages (sender_id, chat_id, text, message_type, sent_at, status)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 'sent')
            ''', (sender_id, chat_id, text, message_type))
            conn.commit()
            return cursor.lastrowid
    
    def create_message_with_file(self, sender_id, chat_id, text, file_path, file_size, file_type="file"):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO messages (sender_id, chat_id, text, message_type, file_path, file_size, file_type, sent_at, status)
                VALUES (?, ?, ?, 'file', ?, ?, ?, CURRENT_TIMESTAMP, 'sent')
            ''', (sender_id, chat_id, text, file_path, file_size, file_type))
            conn.commit()
            return cursor.lastrowid
    
    def get_message(self, message_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM messages WHERE id = ?', (message_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_message(self, message_id, new_text):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE messages 
                SET text = ?, edited_at = CURRENT_TIMESTAMP, is_edited = 1
                WHERE id = ?
            ''', (new_text, message_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_message(self, message_id, user_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM messages WHERE id = ? AND sender_id = ?', (message_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def mark_message_delivered(self, message_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE messages 
                SET status = 'delivered', delivered_at = CURRENT_TIMESTAMP 
                WHERE id = ? AND status = 'sent'
            ''', (message_id,))
            conn.commit()
    
    def mark_message_read(self, message_id, user_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE messages 
                SET status = 'read', read_at = CURRENT_TIMESTAMP 
                WHERE id = ? AND read_at IS NULL
            ''', (message_id,))
            
            cursor.execute('''
                INSERT OR IGNORE INTO message_reads (message_id, user_id, read_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (message_id, user_id))
            
            conn.commit()
    
    # ========== РЕАКЦИИ ==========
    
    def add_reaction(self, message_id, user_id, reaction):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO message_reactions (message_id, user_id, reaction)
                VALUES (?, ?, ?)
            ''', (message_id, user_id, reaction))
            conn.commit()
    
    def remove_reaction(self, message_id, user_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM message_reactions WHERE message_id = ? AND user_id = ?
            ''', (message_id, user_id))
            conn.commit()
    
    def get_reactions(self, message_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT reaction, COUNT(*) as count, user_id
                FROM message_reactions
                WHERE message_id = ?
                GROUP BY reaction
            ''', (message_id,))
            return [dict(row) for row in cursor.fetchall()]