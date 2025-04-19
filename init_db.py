import sqlite3
import os

def init_database():
    db_path = 'green_talk.db'
    
    # Удалить существующую пустую БД, если она есть
    if os.path.exists(db_path) and os.path.getsize(db_path) == 0:
        os.remove(db_path)
        print(f"Удалена пустая БД '{db_path}'")
    
    # Создать новую БД
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Создание таблицы пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        email TEXT UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP,
        profile_pic TEXT,
        status TEXT DEFAULT 'offline'
    )
    ''')
    
    # Создание таблицы чатов (диалогов)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        is_group BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_message_at TIMESTAMP
    )
    ''')
    
    # Создание таблицы участников чатов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chat_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (chat_id) REFERENCES chats (id),
        FOREIGN KEY (user_id) REFERENCES users (id),
        UNIQUE (chat_id, user_id)
    )
    ''')
    
    # Создание таблицы сообщений
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        sender_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        is_file BOOLEAN DEFAULT 0,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (chat_id) REFERENCES chats (id),
        FOREIGN KEY (sender_id) REFERENCES users (id)
    )
    ''')
    
    # Создание таблицы статусов прочтения сообщений
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS message_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        is_read BOOLEAN DEFAULT 0,
        read_at TIMESTAMP,
        FOREIGN KEY (message_id) REFERENCES messages (id),
        FOREIGN KEY (user_id) REFERENCES users (id),
        UNIQUE (message_id, user_id)
    )
    ''')
    
    # Создание таблицы файлов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        file_path TEXT NOT NULL,
        file_type TEXT NOT NULL,
        file_size INTEGER NOT NULL,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (message_id) REFERENCES messages (id)
    )
    ''')
    
    # Добавление тестовых данных
    # Пользователи с хешем пароля 'test' для тестирования
    test_users = [
        ('user1', 'pbkdf2:sha256:150000$abcdefgh$1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef', 'user1@example.com'),
        ('user2', 'pbkdf2:sha256:150000$abcdefgh$1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef', 'user2@example.com'),
    ]
    cursor.executemany("INSERT OR IGNORE INTO users (username, password_hash, email) VALUES (?, ?, ?)", test_users)
    
    # Создание тестового чата
    cursor.execute("INSERT OR IGNORE INTO chats (name, is_group) VALUES ('Тестовый чат', 0)")
    chat_id = cursor.lastrowid or 1
    
    # Добавление пользователей в чат
    user_ids = cursor.execute("SELECT id FROM users LIMIT 2").fetchall()
    if user_ids and len(user_ids) >= 2:
        chat_members = [
            (chat_id, user_ids[0][0]),
            (chat_id, user_ids[1][0])
        ]
        cursor.executemany("INSERT OR IGNORE INTO chat_members (chat_id, user_id) VALUES (?, ?)", chat_members)
        
        # Добавление тестовых сообщений
        test_messages = [
            (chat_id, user_ids[0][0], 'Привет! Как дела?'),
            (chat_id, user_ids[1][0], 'Всё хорошо, спасибо!'),
            (chat_id, user_ids[0][0], 'FILE:image.jpg')
        ]
        cursor.executemany("INSERT OR IGNORE INTO messages (chat_id, sender_id, content, is_file) VALUES (?, ?, ?, ?)", 
                           [(m[0], m[1], m[2], 1 if m[2].startswith('FILE:') else 0) for m in test_messages])
        
        # Добавление тестового файла
        message_id = cursor.execute("SELECT id FROM messages WHERE is_file = 1 LIMIT 1").fetchone()
        if message_id:
            cursor.execute('''
            INSERT OR IGNORE INTO files (message_id, filename, file_path, file_type, file_size)
            VALUES (?, ?, ?, ?, ?)
            ''', (message_id[0], 'image.jpg', 'uploads/image.jpg', 'image/jpeg', 102400))
    
    conn.commit()
    conn.close()
    
    print(f"База данных '{db_path}' успешно инициализирована с необходимыми таблицами")
    print("Добавлены тестовые данные для пользователей и чатов")

if __name__ == "__main__":
    init_database() 