import sqlite3
import os
import time
import sys
import compression

def get_db_connection():
    """Получить соединение с базой данных"""
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def test_transaction(sender, receiver, message):
    """Тест транзакции SQLite"""
    print(f"Тест транзакции с сообщением от {sender} для {receiver}: {message}")
    
    # Подготовительные данные
    compressed_msg = compression.compress(message.encode('utf-8'))
    timestamp = time.time()
    
    print("=== Этап 1: Тест транзакции для private_messages ===")
    # Проверка INSERT в private_messages
    conn = get_db_connection()
    conn.execute("BEGIN TRANSACTION")
    
    try:
        conn.execute("""
            INSERT INTO private_messages (sender, receiver, timestamp, compressed_message)
            VALUES (?, ?, ?, ?)
        """, (sender, receiver, timestamp, compressed_msg))
        
        # Получаем ID нового сообщения перед фиксацией
        message_id_before_commit = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        print(f"ID сообщения до коммита: {message_id_before_commit}")
        
        # Проверяем, что сообщение доступно в транзакции до коммита
        msg_data = conn.execute("SELECT * FROM private_messages WHERE id = ?", (message_id_before_commit,)).fetchone()
        print(f"Сообщение видно внутри транзакции: {msg_data is not None}")
        
        # Фиксируем изменения
        conn.commit()
        print("Транзакция зафиксирована")
        
        # Получаем ID нового сообщения после фиксации
        message_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        print(f"ID сообщения после коммита: {message_id}")
        
        # Проверяем, что сообщение доступно после коммита
        msg_data = conn.execute("SELECT * FROM private_messages WHERE id = ?", (message_id,)).fetchone()
        print(f"Сообщение найдено после коммита: {msg_data is not None}")
        
        # Проверяем разблокировку базы данных
        try:
            conn2 = get_db_connection()
            msg_data2 = conn2.execute("SELECT * FROM private_messages WHERE id = ?", (message_id,)).fetchone()
            print(f"Сообщение доступно из другого соединения: {msg_data2 is not None}")
            conn2.close()
        except Exception as e:
            print(f"Ошибка при проверке из другого соединения: {e}")
        
        print("\n=== Этап 2: Тест обновления private_chats ===")
        # Проверка работы с таблицей private_chats
        conn.execute("BEGIN TRANSACTION")
        
        # Проверяем существование чата
        chat_exists = conn.execute("""
            SELECT id FROM private_chats 
            WHERE (user1 = ? AND user2 = ?) OR (user1 = ? AND user2 = ?)
        """, (sender, receiver, receiver, sender)).fetchone()
        
        if chat_exists:
            print(f"Найден существующий чат с ID {chat_exists['id']}")
            
            # Пробуем обновить данные чата
            conn.execute("""
                UPDATE private_chats
                SET last_message_timestamp = ?,
                    last_message = ?
                WHERE (user1 = ? AND user2 = ?) OR (user1 = ? AND user2 = ?)
            """, (timestamp, compressed_msg, sender, receiver, receiver, sender))
            
            print("Запрос UPDATE выполнен")
        else:
            print("Создание нового чата")
            
            # Пробуем создать новый чат
            conn.execute("""
                INSERT INTO private_chats (user1, user2, last_message, last_message_timestamp, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (sender, receiver, compressed_msg, timestamp, timestamp))
            
            print("Запрос INSERT для чата выполнен")
        
        # Фиксируем транзакцию
        conn.commit()
        print("Транзакция для private_chats зафиксирована")
        
        # Проверяем результат
        chat_data = conn.execute("""
            SELECT * FROM private_chats 
            WHERE (user1 = ? AND user2 = ?) OR (user1 = ? AND user2 = ?)
        """, (sender, receiver, receiver, sender)).fetchone()
        
        if chat_data:
            print(f"Чат найден после коммита, ID: {chat_data['id']}")
            print(f"Последнее сообщение timestamp: {chat_data['last_message_timestamp']}")
        else:
            print("ОШИБКА: Чат не найден после коммита!")
        
        print("\n=== Тест успешно завершен ===")
        
    except Exception as e:
        # Если возникла ошибка, откатываем транзакцию
        conn.rollback()
        print(f"Ошибка во время транзакции: {e}")
        print("Транзакция отменена")
        import traceback
        traceback.print_exc()
        
    finally:
        # Закрываем соединение
        conn.close()
        print("Соединение с БД закрыто")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Использование: python test_transaction.py <отправитель> <получатель> <сообщение>")
        sys.exit(1)
    
    sender = sys.argv[1]
    receiver = sys.argv[2]
    message = sys.argv[3]
    
    test_transaction(sender, receiver, message) 