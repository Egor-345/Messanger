# test_db.py
from client.database import Database

# Создаем базу данных
db = Database("my_messenger.db")
print("База данных создана!")

# Добавим тестового пользователя
user_id = db.add_user("test", "123", "Тестер")
print(f"Пользователь создан с id: {user_id}")

# Проверим, что пользователь сохранился
user = db.get_user(user_id)
print(f"Найден пользователь: {user}")