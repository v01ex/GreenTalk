import sqlite3
import sys
import compression

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def load_chat_messages(user1, user2):
    print(f"Загрузка сообщений между {user1} и {user2}...")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем количество сообщений
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM private_messages
            WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)
        """, (user1, user2, user2, user1))
        
        total_count = cursor.fetchone()['count']
        print(f"Всего сообщений в чате: {total_count}")
        
        if total_count == 0:
            print("Сообщений не найдено!")
            return []
        
        # Получаем последние 10 сообщений
        limit = 10
        cursor.execute("""
            SELECT id, sender, receiver, timestamp, compressed_message, read
            FROM private_messages
            WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)
            ORDER BY timestamp DESC
            LIMIT ?
        """, (user1, user2, user2, user1, limit))
        
        rows = cursor.fetchall()
        print(f"Загружено {len(rows)} последних сообщений")
        
        # Декомпрессируем сообщения
        messages = []
        for row in rows:
            try:
                if row['compressed_message'] is None:
                    print(f"ПРЕДУПРЕЖДЕНИЕ: compressed_message равен None для сообщения с ID {row['id']}")
                    message_text = "[Сообщение недоступно]"
                else:
                    decompressed_msg = compression.decompress(row['compressed_message']).decode('utf-8')
                    message_text = decompressed_msg
                
                message_obj = {
                    'id': row['id'],
                    'sender': row['sender'],
                    'recipient': row['receiver'],
                    'message': message_text,
                    'timestamp': row['timestamp'],
                    'read': bool(row['read'])
                }
                
                messages.append(message_obj)
                
            except Exception as e:
                print(f"Ошибка при декомпрессии сообщения {row['id']}: {e}")
                import traceback
                traceback.print_exc()
        
        # Разворачиваем список, чтобы старые сообщения были вначале
        messages.reverse()
        
        # Выводим сообщения
        print("\nИстория сообщений:")
        for msg in messages:
            direction = "<<" if msg['sender'] == user2 else ">>"
            print(f"[{msg['id']}] {direction} {msg['sender']}: {msg['message']}")
        
        conn.close()
        return messages
        
    except Exception as e:
        print(f"Ошибка при загрузке сообщений: {e}")
        import traceback
        traceback.print_exc()
        return []

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Использование: python test_message_loading.py <пользователь1> <пользователь2>")
        sys.exit(1)
    
    user1 = sys.argv[1]
    user2 = sys.argv[2]
    
    messages = load_chat_messages(user1, user2)
    
    if messages:
        print(f"\nУспешно загружено {len(messages)} сообщений")
    else:
        print("\nНе удалось загрузить сообщения или чат пуст") 