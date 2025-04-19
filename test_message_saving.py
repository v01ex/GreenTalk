import sqlite3
import os
import time
import sys
import compression

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def save_test_message(sender, receiver, message):
    print(f"Попытка сохранить сообщение от {sender} для {receiver}: {message}")
    
    try:
        conn = get_db_connection()
        
        # 1. Сжимаем сообщение
        compressed_msg = compression.compress(message.encode('utf-8'))
        timestamp = time.time()
        
        # 2. Сохраняем сообщение в таблицу private_messages
        print("Шаг 1: Сохранение в private_messages...")
        conn.execute("""
            INSERT INTO private_messages (sender, receiver, timestamp, compressed_message)
            VALUES (?, ?, ?, ?)
        """, (sender, receiver, timestamp, compressed_msg))
        
        conn.commit()
        
        # 3. Получаем ID нового сообщения
        message_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        print(f"Сообщение сохранено с ID: {message_id}")
        
        # 4. Проверяем существование чата в таблице private_chats
        print("Шаг 2: Проверка записи в private_chats...")
        chat_exists = conn.execute("""
            SELECT id FROM private_chats 
            WHERE (user1 = ? AND user2 = ?) OR (user1 = ? AND user2 = ?)
        """, (sender, receiver, receiver, sender)).fetchone()
        
        # 5. Создаем или обновляем запись чата
        if not chat_exists:
            print(f"Создание новой записи чата для {sender} и {receiver}...")
            conn.execute("""
                INSERT INTO private_chats (user1, user2, last_message, last_message_timestamp, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (sender, receiver, compressed_msg, timestamp, timestamp))
        else:
            print(f"Обновление существующей записи чата ID {chat_exists['id']}...")
            conn.execute("""
                UPDATE private_chats
                SET last_message_timestamp = ?,
                    last_message = ?
                WHERE (user1 = ? AND user2 = ?) OR (user1 = ? AND user2 = ?)
            """, (timestamp, compressed_msg, sender, receiver, receiver, sender))
        
        conn.commit()
        
        # 6. Проверяем, что сообщение сохранилось
        saved_message = conn.execute("""
            SELECT id, sender, receiver, compressed_message 
            FROM private_messages 
            WHERE id = ?
        """, (message_id,)).fetchone()
        
        if saved_message:
            # Разжимаем сообщение для проверки
            try:
                decompressed = compression.decompress(saved_message['compressed_message']).decode('utf-8')
                print(f"Проверка успешна! Сохраненное сообщение: {decompressed}")
            except Exception as e:
                print(f"Ошибка при разжатии сообщения: {e}")
        else:
            print("ОШИБКА: Сообщение не найдено после сохранения!")
        
        # 7. Проверяем обновление чата
        chat_record = conn.execute("""
            SELECT * FROM private_chats 
            WHERE (user1 = ? AND user2 = ?) OR (user1 = ? AND user2 = ?)
        """, (sender, receiver, receiver, sender)).fetchone()
        
        if chat_record:
            print(f"Запись чата ID {chat_record['id']} обновлена.")
            print(f"user1={chat_record['user1']}, user2={chat_record['user2']}")
            if chat_record['last_message_timestamp']:
                print(f"Время последнего сообщения: {chat_record['last_message_timestamp']}")
        else:
            print("ОШИБКА: Запись чата не найдена после создания/обновления!")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"Ошибка при сохранении сообщения: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Использование: python test_message_saving.py <отправитель> <получатель> <сообщение>")
        sys.exit(1)
    
    sender = sys.argv[1]
    receiver = sys.argv[2]
    message = sys.argv[3]
    
    success = save_test_message(sender, receiver, message)
    
    if success:
        print("\nТест завершен успешно!")
    else:
        print("\nТест завершен с ошибками!") 