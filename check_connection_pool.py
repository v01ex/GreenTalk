import sqlite3
import threading
import time
import random
import queue

# Пул соединений с базой данных
connection_pool = queue.Queue(maxsize=5)

def initialize_connection_pool():
    """Инициализация пула соединений"""
    print("Инициализация пула соединений...")
    for i in range(5):
        try:
            conn = sqlite3.connect('database.db', check_same_thread=False)
            conn.row_factory = sqlite3.Row
            connection_pool.put(conn)
            print(f"Соединение {i+1} добавлено в пул")
        except Exception as e:
            print(f"Ошибка при создании соединения {i+1}: {e}")
    
    print(f"Пул соединений инициализирован, размер: {connection_pool.qsize()}")

def get_connection():
    """Получить соединение из пула"""
    conn = connection_pool.get()
    return conn

def release_connection(conn):
    """Вернуть соединение в пул"""
    connection_pool.put(conn)

def check_database_access(thread_id):
    """Проверка доступа к базе данных из потока"""
    print(f"Поток {thread_id}: Запуск проверки доступа к БД")
    
    try:
        # Получаем соединение из пула
        print(f"Поток {thread_id}: Ожидание доступного соединения...")
        start_time = time.time()
        conn = get_connection()
        wait_time = time.time() - start_time
        print(f"Поток {thread_id}: Получено соединение (ожидание: {wait_time:.4f} сек)")
        
        try:
            # Проверяем доступность таблиц
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM private_messages")
            count = cursor.fetchone()[0]
            print(f"Поток {thread_id}: В таблице private_messages {count} записей")
            
            # Эмулируем некоторую работу
            time.sleep(random.uniform(0.2, 1.0))
            
            # Тестируем транзакцию
            try:
                conn.execute("BEGIN")
                
                # Имитируем вставку тестовых данных
                timestamp = time.time()
                cursor.execute("""
                    INSERT INTO private_messages 
                    (sender, receiver, timestamp, compressed_message) 
                    VALUES (?, ?, ?, ?)
                """, (f"test_user_{thread_id}", f"test_receiver_{thread_id}", timestamp, b"test"))
                
                # Получаем ID
                row_id = cursor.lastrowid
                print(f"Поток {thread_id}: Вставлена тестовая запись с ID {row_id}")
                
                # Удаляем тестовую запись
                cursor.execute("DELETE FROM private_messages WHERE id = ?", (row_id,))
                print(f"Поток {thread_id}: Тестовая запись удалена")
                
                # Фиксируем транзакцию
                conn.commit()
                print(f"Поток {thread_id}: Транзакция успешно завершена")
                
            except Exception as tx_error:
                conn.rollback()
                print(f"Поток {thread_id}: Ошибка в транзакции: {tx_error}")
                raise
                
        finally:
            # Возвращаем соединение в пул
            release_connection(conn)
            print(f"Поток {thread_id}: Соединение возвращено в пул (размер пула: {connection_pool.qsize()})")
    
    except Exception as e:
        print(f"Поток {thread_id}: Ошибка при работе с БД: {e}")

def run_multithread_test(num_threads=10):
    """Запуск многопоточного теста"""
    print(f"Запуск многопоточного теста с {num_threads} потоками")
    
    # Инициализируем пул соединений
    initialize_connection_pool()
    
    # Создаем и запускаем потоки
    threads = []
    for i in range(num_threads):
        thread = threading.Thread(target=check_database_access, args=(i,))
        threads.append(thread)
        thread.start()
        # Небольшая задержка между запусками потоков
        time.sleep(0.1)
    
    # Ожидаем завершения всех потоков
    for i, thread in enumerate(threads):
        thread.join()
        print(f"Поток {i} завершен")
    
    print("Многопоточный тест завершен")
    
    # Закрываем все соединения в пуле
    print("Закрытие соединений...")
    while not connection_pool.empty():
        conn = connection_pool.get()
        conn.close()
        print("Соединение закрыто")

if __name__ == "__main__":
    run_multithread_test() 