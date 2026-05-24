# check_db.py
import sqlite3

conn = sqlite3.connect('messenger.db')
cursor = conn.cursor()

# Список всех таблиц
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Таблицы в БД:")
for table in tables:
    print(f"  - {table[0]}")

# Проверяем таблицу chats
print("\nПроверка таблицы chats:")
try:
    cursor.execute("SELECT * FROM chats")
    rows = cursor.fetchall()
    print(f"  Найдено чатов: {len(rows)}")
    for row in rows:
        print(f"    {row}")
except Exception as e:
    print(f"  Ошибка: {e}")
    print("  Таблица chats не существует!")

# Проверяем таблицу chat_participants
print("\nПроверка таблицы chat_participants:")
try:
    cursor.execute("SELECT * FROM chat_participants")
    rows = cursor.fetchall()
    print(f"  Найдено участников: {len(rows)}")
    for row in rows:
        print(f"    {row}")
except Exception as e:
    print(f"  Ошибка: {e}")
    print("  Таблица chat_participants не существует!")

conn.close()