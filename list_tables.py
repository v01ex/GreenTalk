import sqlite3
import os

db_path = 'green_talk.db'

# Проверка существования файла БД
if os.path.exists(db_path):
    print(f"БД файл '{db_path}' найден. Размер: {os.path.getsize(db_path)} байт")
    
    try:
        # Подключение к базе данных
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Получение списка таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        if tables:
            print("\nТаблицы в базе данных:")
            for table in tables:
                table_name = table[0]
                print(f"- {table_name}")
                
                # Получение структуры таблицы
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                if columns:
                    print("  Колонки:")
                    for col in columns:
                        print(f"    {col[1]} ({col[2]})")
                
                # Получение количества записей
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                print(f"  Количество записей: {count}")
                print()
        else:
            print("База данных не содержит таблиц.")
        
        # Закрытие подключения
        conn.close()
        
    except sqlite3.Error as e:
        print(f"Ошибка при работе с БД: {e}")
else:
    print(f"БД файл '{db_path}' не найден.")
    
    # Проверка других SQLite файлов в директории
    sql_files = [f for f in os.listdir('.') if f.endswith('.db') or f.endswith('.sqlite') or f.endswith('.sqlite3')]
    if sql_files:
        print("\nНайдены другие файлы SQLite в текущей директории:")
        for file in sql_files:
            print(f"- {file} (размер: {os.path.getsize(file)} байт)")
    else:
        print("Других файлов SQLite в текущей директории не найдено.") 