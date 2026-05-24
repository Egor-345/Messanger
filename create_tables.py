# create_tables.py
import sqlite3

def create_tables():
    conn = sqlite3.connect('messenger.db')
    cursor = conn.cursor()
    
    # Таблица чатов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT DEFAULT 'dialog',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✅ Таблица 'chats' создана")
    
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
    print("✅ Таблица 'chat_participants' создана")
    
    # Проверяем, есть ли колонка chat_id в messages
    try:
        cursor.execute('ALTER TABLE messages ADD COLUMN chat_id INTEGER DEFAULT 1')
        print("✅ Колонка 'chat_id' добавлена в таблицу 'messages'")
    except sqlite3.OperationalError:
        print("ℹ️ Колонка 'chat_id' уже существует")
    
    conn.commit()
    conn.close()
    print("\n✅ Все таблицы успешно созданы!")

if __name__ == "__main__":
    create_tables()