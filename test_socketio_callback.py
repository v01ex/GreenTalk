import socketio
import sys
import time
import requests
import json

def get_session_id(username, password):
    """Получить Session ID Flask через авторизацию"""
    print(f"Авторизация пользователя {username}...")
    
    # URL для авторизации
    login_url = 'http://localhost:5000/login'
    
    # Создаем сессию для сохранения cookies
    session = requests.Session()
    
    # Отправляем запрос на авторизацию
    response = session.post(login_url, data={
        'username': username,
        'password': password
    }, allow_redirects=False)
    
    # Проверяем, успешна ли авторизация
    if response.status_code == 302 and '/modern_chat' in response.headers.get('Location', ''):
        # Получаем cookie с session_id
        cookies = session.cookies.get_dict()
        session_id = cookies.get('session')
        
        if session_id:
            print(f"Пользователь {username} успешно авторизован, session_id: {session_id[:10]}...")
            return session_id
        else:
            print(f"Не удалось получить session_id")
            return None
    else:
        print(f"Ошибка авторизации пользователя {username}")
        return None

def test_callback(session_id, sender, receiver, message):
    """Тестирование callback-функций Socket.IO"""
    print(f"Тестирование callback-функций с сообщением от {sender} к {receiver}: {message}")
    
    # Сортируем отправителя и получателя для формирования ID комнаты
    participants = sorted([sender, receiver])
    room_id = f"private_{participants[0]}_{participants[1]}"
    print(f"ID комнаты: {room_id}")
    
    # Создаем клиент Socket.IO с вербозным логированием
    sio = socketio.Client(logger=True, engineio_logger=True)
    
    # Флаги для отслеживания успешности операций
    join_success = False
    message_sent = False
    callback_received = False
    callback_data = None
    
    # Обработчики событий
    @sio.event
    def connect():
        print("\n[CONNECT] Успешное подключение к серверу Socket.IO")
        
        # Присоединяемся к комнате с пошаговыми логами
        print("[EMIT] Отправка события join_private...")
        sio.emit('join_private', {'room': room_id}, callback=handle_join_response)
        print("[EMIT] Событие join_private отправлено, ожидание callback...")
    
    @sio.event
    def connect_error(data):
        print(f"\n[ERROR] Ошибка подключения: {data}")
    
    @sio.event
    def disconnect():
        print("\n[DISCONNECT] Отключение от сервера Socket.IO")
    
    # Обработчик ответа на присоединение к комнате
    def handle_join_response(response):
        nonlocal join_success
        
        print(f"\n[CALLBACK] Получен ответ на join_private: {response}")
        
        if response and response.get('success', False):
            join_success = True
            print("[JOIN] Успешное присоединение к комнате")
            
            # После присоединения отправляем сообщение
            print(f"\n[EMIT] Отправка private_message в комнату {room_id}...")
            payload = {
                'room': room_id,
                'receiver': receiver,
                'message': message
            }
            print(f"[PAYLOAD] {json.dumps(payload, ensure_ascii=False)}")
            
            sio.emit('send_private_message', payload, callback=handle_message_response)
            print("[EMIT] Событие send_private_message отправлено, ожидание callback...")
        else:
            print(f"[JOIN] Ошибка при присоединении к комнате: {response}")
    
    # Обработчик ответа на отправку сообщения
    def handle_message_response(response):
        nonlocal message_sent, callback_received, callback_data
        
        callback_received = True
        callback_data = response
        
        print(f"\n[CALLBACK] Получен ответ на send_private_message: {json.dumps(response, ensure_ascii=False) if response else 'None'}")
        
        if response:
            if response.get('success', False):
                message_sent = True
                print(f"[MESSAGE] Сообщение успешно отправлено, ID: {response.get('id')}")
                print(f"[MESSAGE] Timestamp: {response.get('timestamp')}")
            else:
                error = response.get('error', 'неизвестная ошибка')
                print(f"[ERROR] Ошибка при отправке сообщения: {error}")
        else:
            print("[ERROR] Получен пустой ответ от сервера")
        
        # Отключаемся после получения ответа
        print("[ACTION] Отключение от сервера через 2 секунды...")
        time.sleep(2)  # Даем время на логирование и обработку
        sio.disconnect()
    
    # Обработчик входящих сообщений для проверки эхо
    @sio.on('receive_private_message')
    def on_message(data):
        print(f"\n[EVENT] receive_private_message: {json.dumps(data, ensure_ascii=False)}")
        
        # Проверяем, является ли это эхо нашего сообщения
        if data.get('message') == message and data.get('sender') == sender:
            print("[ECHO] Получено эхо отправленного сообщения")
    
    try:
        # Подключаемся к серверу с session_id в query параметре
        print("\n[CONNECT] Подключение к серверу Socket.IO...")
        sio.connect(f'http://localhost:5000?session_id={session_id}', transports=['websocket'])
        
        # Ожидаем некоторое время для обработки событий
        timeout = 15  # секунд
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if callback_received:
                # Если получили ответ на отправку сообщения, можем завершить
                break
            
            # Индикатор ожидания
            elapsed = int(time.time() - start_time)
            if elapsed % 3 == 0:
                print(f"[WAIT] Ожидание ответа... ({elapsed}/{timeout} сек)")
            
            time.sleep(1)
        
        if not callback_received:
            print(f"\n[TIMEOUT] Время ожидания ответа истекло после {timeout} секунд")
        
        # Если еще подключены, отключаемся
        if sio.connected:
            print("\n[DISCONNECT] Принудительное отключение...")
            sio.disconnect()
        
        # Выводим итоги теста
        print("\n========== РЕЗУЛЬТАТЫ ТЕСТА ==========")
        print(f"Подключение к серверу: {'Успешно' if True else 'Не удалось'}")
        print(f"Присоединение к комнате: {'Успешно' if join_success else 'Не удалось'}")
        print(f"Отправка сообщения: {'Успешно' if message_sent else 'Не удалось'}")
        print(f"Получение callback: {'Да' if callback_received else 'Нет'}")
        if callback_data:
            print(f"Данные callback: {json.dumps(callback_data, ensure_ascii=False)}")
        
        return message_sent, callback_data
        
    except Exception as e:
        print(f"\n[ERROR] Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()
        
        # Если еще подключены, отключаемся
        if hasattr(sio, 'connected') and sio.connected:
            sio.disconnect()
        
        return False, {'error': str(e)}

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Использование: python test_socketio_callback.py <имя_пользователя> <пароль> <получатель> <сообщение>")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    receiver = sys.argv[3]
    message = sys.argv[4]
    
    # Получаем session_id через авторизацию
    session_id = get_session_id(username, password)
    if not session_id:
        print("Не удалось получить session_id, выход")
        sys.exit(1)
    
    # Запускаем тест callback-функций
    success, response = test_callback(session_id, username, receiver, message)
    
    if success:
        print("\nТест успешно завершен. Callback-функции работают корректно.")
        sys.exit(0)
    else:
        print("\nТест завершен с ошибкой. Callback-функции не работают должным образом.")
        sys.exit(1) 