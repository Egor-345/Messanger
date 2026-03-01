"""
Модели данных для мессенджера
Содержит классы, описывающие сущности системы
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime
import json


# ============================================
# МОДЕЛЬ ПОЛЬЗОВАТЕЛЯ
# ============================================

@dataclass
class User:
    """
    Класс, представляющий пользователя мессенджера

    Атрибуты:
        id: Уникальный идентификатор пользователя
        login: Логин для входа (уникальный)
        password_hash: Хеш пароля (никогда не храним пароль в открытом виде)
        display_name: Отображаемое имя (никнейм)
        avatar_path: Путь к файлу аватарки
        status: Текущий статус (online, offline, away)
        last_seen: Время последней активности
        registered_at: Дата регистрации
        email: Email пользователя (опционально)
        public_key: Публичный ключ для шифрования (для продвинутой версии)
    """
    id: int
    login: str
    password_hash: str
    display_name: str = None
    avatar_path: Optional[str] = None
    status: str = "offline"
    last_seen: Optional[datetime] = None
    registered_at: datetime = field(default_factory=datetime.now)
    email: Optional[str] = None
    public_key: Optional[str] = None

    def __post_init__(self):
        """Выполняется после инициализации"""
        if self.display_name is None:
            self.display_name = self.login

    def to_dict(self) -> Dict[str, Any]:
        """
        Преобразует объект в словарь для отправки по сети
        или сохранения в БД
        """
        data = asdict(self)
        # Преобразуем datetime в строку для JSON
        if self.last_seen:
            data['last_seen'] = self.last_seen.isoformat()
        if self.registered_at:
            data['registered_at'] = self.registered_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        """
        Создает объект User из словаря
        (например, после получения из БД или по сети)
        """
        # Преобразуем строки обратно в datetime
        if 'last_seen' in data and data['last_seen']:
            data['last_seen'] = datetime.fromisoformat(data['last_seen'])
        if 'registered_at' in data and data['registered_at']:
            data['registered_at'] = datetime.fromisoformat(
                data['registered_at'])
        return cls(**data)

    def to_json(self) -> str:
        """Преобразует объект в JSON строку"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> 'User':
        """Создает объект из JSON строки"""
        data = json.loads(json_str)
        return cls.from_dict(data)

    def update_status(self, new_status: str):
        """Обновляет статус пользователя"""
        valid_statuses = ['online', 'offline', 'away']
        if new_status in valid_statuses:
            self.status = new_status
            self.last_seen = datetime.now()

    def __str__(self) -> str:
        return f"User(id={self.id}, login={self.login}, status={self.status})"


# ============================================
# МОДЕЛЬ СООБЩЕНИЯ
# ============================================

@dataclass
class Message:
    """
    Класс, представляющий сообщение в чате

    Атрибуты:
        id: Уникальный идентификатор сообщения
        sender_id: ID отправителя
        chat_id: ID чата (кому отправлено)
        text: Текст сообщения
        sent_at: Время отправки
        delivered_at: Время доставки на сервер
        read_at: Время прочтения
        status: Статус сообщения (sending, sent, delivered, read, error)
        message_type: Тип сообщения (text, image, file, voice)
        file_path: Путь к файлу (если это файл)
        file_size: Размер файла в байтах
        reply_to_id: ID сообщения, на которое отвечаем (для ответов)
        is_encrypted: Флаг шифрования
        metadata: Дополнительные данные (размеры изображения, длительность аудио и т.д.)
    """
    id: int = None
    sender_id: int = None
    chat_id: int = None
    text: str = ""
    sent_at: datetime = field(default_factory=datetime.now)
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    status: str = "sending"
    message_type: str = "text"
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    reply_to_id: Optional[int] = None
    is_encrypted: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Валидация после создания"""
        if self.message_type != "text" and not self.file_path:
            raise ValueError(
                f"Для типа {self.message_type} необходимо указать file_path")

    def to_dict(self) -> Dict[str, Any]:
        """Преобразует объект в словарь"""
        data = asdict(self)
        # Преобразуем datetime в строку
        for field in ['sent_at', 'delivered_at', 'read_at']:
            if data.get(field):
                data[field] = data[field].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Создает объект из словаря"""
        # Преобразуем строки обратно в datetime
        for field in ['sent_at', 'delivered_at', 'read_at']:
            if field in data and data[field]:
                data[field] = datetime.fromisoformat(data[field])
        return cls(**data)

    def mark_as_delivered(self):
        """Отмечает сообщение как доставленное"""
        self.status = "delivered"
        self.delivered_at = datetime.now()

    def mark_as_read(self):
        """Отмечает сообщение как прочитанное"""
        self.status = "read"
        self.read_at = datetime.now()

    def is_file(self) -> bool:
        """Проверяет, является ли сообщение файлом"""
        return self.message_type in ['image', 'file', 'voice']

    def get_short_text(self, max_length: int = 50) -> str:
        """Возвращает укороченный текст для превью"""
        if len(self.text) <= max_length:
            return self.text
        return self.text[:max_length] + "..."

    def __str__(self) -> str:
        return f"Message(id={self.id}, from={self.sender_id}, status={self.status})"


# ============================================
# МОДЕЛЬ ЧАТА (ДИАЛОГА ИЛИ ГРУППЫ)
# ============================================

@dataclass
class Chat:
    """
    Класс, представляющий чат (диалог или группу)

    Атрибуты:
        id: Уникальный идентификатор чата
        type: Тип чата (dialog - диалог, group - группа)
        name: Название чата (для групп)
        participants: Список ID участников
        created_at: Дата создания
        created_by: ID создателя (для групп)
        avatar_path: Путь к аватару чата (для групп)
        last_message_id: ID последнего сообщения
        last_message_preview: Текст последнего сообщения (для превью)
        last_message_time: Время последнего сообщения
        unread_count: Количество непрочитанных сообщений для текущего пользователя
        is_pinned: Закреплен ли чат
        metadata: Дополнительные данные (описание группы, и т.д.)
    """
    id: int
    type: str = "dialog"  # "dialog" или "group"
    name: Optional[str] = None
    participants: List[int] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    created_by: Optional[int] = None
    avatar_path: Optional[str] = None
    last_message_id: Optional[int] = None
    last_message_preview: Optional[str] = None
    last_message_time: Optional[datetime] = None
    unread_count: int = 0
    is_pinned: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Валидация после создания"""
        if self.type == "dialog" and len(self.participants) != 2:
            # Для диалога можно автоматически установить имя
            pass
        elif self.type == "group" and not self.name:
            self.name = f"Группа {self.id}"

    def to_dict(self) -> Dict[str, Any]:
        """Преобразует объект в словарь"""
        data = asdict(self)
        # Преобразуем datetime в строку
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if self.last_message_time:
            data['last_message_time'] = self.last_message_time.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Chat':
        """Создает объект из словаря"""
        # Преобразуем строки обратно в datetime
        if 'created_at' in data and data['created_at']:
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'last_message_time' in data and data['last_message_time']:
            data['last_message_time'] = datetime.fromisoformat(
                data['last_message_time'])
        return cls(**data)

    def add_participant(self, user_id: int):
        """Добавляет участника в чат"""
        if user_id not in self.participants:
            self.participants.append(user_id)

    def remove_participant(self, user_id: int):
        """Удаляет участника из чата"""
        if user_id in self.participants:
            self.participants.remove(user_id)

    def update_last_message(self, message: Message):
        """Обновляет информацию о последнем сообщении"""
        self.last_message_id = message.id
        self.last_message_preview = message.get_short_text()
        self.last_message_time = message.sent_at

    def increment_unread(self):
        """Увеличивает счетчик непрочитанных"""
        self.unread_count += 1

    def reset_unread(self):
        """Сбрасывает счетчик непрочитанных"""
        self.unread_count = 0

    def get_display_name(self, current_user_id: int = None) -> str:
        """
        Возвращает имя для отображения
        Для диалога - имя собеседника
        Для группы - название группы
        """
        if self.type == "group":
            return self.name or f"Группа {self.id}"
        else:
            # Для диалога возвращаем имя собеседника
            if current_user_id and len(self.participants) == 2:
                other_id = \
                [p for p in self.participants if p != current_user_id][0]
                return f"User {other_id}"  # В реальности тут будет запрос к БД за именем
            return f"Dialog {self.id}"

    def __str__(self) -> str:
        return f"Chat(id={self.id}, type={self.type}, participants={len(self.participants)})"


# ============================================
# ВСПОМОГАТЕЛЬНЫЙ КЛАСС ДЛЯ ПАКЕТОВ ПО СЕТИ
# ============================================

@dataclass
class NetworkPacket:
    """
    Класс для упаковки данных при передаче по сети

    Атрибуты:
        type: Тип пакета (auth, message, status, file, etc.)
        payload: Данные пакета
        timestamp: Время отправки
        sender_id: ID отправителя
        packet_id: Уникальный ID пакета
    """
    type: str  # 'auth', 'message', 'status', 'typing', 'read_receipt', 'file_metadata'
    payload: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    sender_id: Optional[int] = None
    packet_id: Optional[str] = None

    def __post_init__(self):
        """Генерирует ID пакета если не указан"""
        if self.packet_id is None:
            import uuid
            self.packet_id = str(uuid.uuid4())[:8]

    def to_json(self) -> str:
        """Преобразует пакет в JSON строку для отправки"""
        data = {
            'type': self.type,
            'payload': self.payload,
            'timestamp': self.timestamp.isoformat(),
            'sender_id': self.sender_id,
            'packet_id': self.packet_id
        }
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> 'NetworkPacket':
        """Создает пакет из JSON строки"""
        data = json.loads(json_str)
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


# ============================================
# ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ (для тестирования)
# ============================================

if __name__ == "__main__":
    # Пример создания пользователя
    user1 = User(
        id=1,
        login="alice",
        password_hash="5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8",
        # "password"
        display_name="Алиса",
        status="online"
    )
    print("Создан пользователь:", user1)
    print("В виде словаря:", user1.to_dict())

    # Пример создания сообщения
    msg = Message(
        sender_id=1,
        chat_id=1,
        text="Привет, как дела?"
    )
    print("\nСоздано сообщение:", msg)
    msg.mark_as_delivered()
    print("После доставки:", msg.status)

    # Пример создания чата
    chat = Chat(
        id=1,
        type="dialog",
        participants=[1, 2]
    )
    chat.update_last_message(msg)
    print("\nСоздан чат:", chat)
    print("Последнее сообщение:", chat.last_message_preview)

    # Пример сетевого пакета
    packet = NetworkPacket(
        type="message",
        payload=msg.to_dict(),
        sender_id=1
    )
    print("\nСетевой пакет:", packet.to_json())