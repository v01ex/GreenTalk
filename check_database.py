import sqlite3
import os

def check_database():
    # Путь к базе данных
    db_path = 'database.db'
    
    if not os.path.exists(db_path):
        print(f"ОШИБКА: База данных не найдена: {db_path}")
        return
        
    print(f"База данных найдена: {db_path}")
    print(f"Размер файла: {os.path.getsize(db_path)} байт")
    
    # Подключение к базе данных
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Проверка существующих таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"\nТаблицы в базе данных: {tables}")
        
        # Проверка структуры таблицы private_chats
        if 'private_chats' in tables:
            cursor.execute("PRAGMA table_info(private_chats);")
            columns = [row[1] for row in cursor.fetchall()]
            print(f"\nСтруктура таблицы private_chats: {columns}")
            
            # Проверка количества записей
            cursor.execute("SELECT COUNT(*) FROM private_chats;")
            count = cursor.fetchone()[0]
            print(f"Записей в private_chats: {count}")
            
            # Если есть записи, выводим примеры
            if count > 0:
                cursor.execute("SELECT * FROM private_chats LIMIT 3;")
                rows = cursor.fetchall()
                print("\nПримеры записей в private_chats:")
                for row in rows:
                    row_dict = {column: row[column] for column in row.keys()}
                    print(f"  {row_dict}")
        else:
            print("\nТаблица private_chats ОТСУТСТВУЕТ!")
        
        # Проверка структуры таблицы private_messages
        if 'private_messages' in tables:
            cursor.execute("PRAGMA table_info(private_messages);")
            columns = [row[1] for row in cursor.fetchall()]
            print(f"\nСтруктура таблицы private_messages: {columns}")
            
            # Проверка количества записей
            cursor.execute("SELECT COUNT(*) FROM private_messages;")
            count = cursor.fetchone()[0]
            print(f"Записей в private_messages: {count}")
            
            # Если есть записи, выводим примеры (без бинарных данных)
            if count > 0:
                cursor.execute("""
                    SELECT id, sender, receiver, timestamp, read, 
                           deleted_for_sender, deleted_for_receiver, edited 
                    FROM private_messages 
                    ORDER BY timestamp DESC 
                    LIMIT 3;
                """)
                rows = cursor.fetchall()
                print("\nПоследние записи в private_messages:")
                for row in rows:
                    row_dict = {column: row[column] for column in row.keys()}
                    print(f"  {row_dict}")
        else:
            print("\nТаблица private_messages ОТСУТСТВУЕТ!")
        
        # Закрываем подключение
        conn.close()
        
    except sqlite3.Error as e:
        print(f"Ошибка базы данных: {e}")
    except Exception as e:
        print(f"Общая ошибка: {e}")

if __name__ == "__main__":
    check_database() 