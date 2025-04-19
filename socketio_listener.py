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
            return session_id, username
        else:
            print(f"Не удалось получить session_id")
            return None, None
    else:
        print(f"Ошибка авторизации пользователя {username}")
        return None, None

def monitor_socketio_events(session_id, username, duration=60):
    """Мониторинг Socket.IO событий"""
    print(f"Запуск мониторинга Socket.IO событий на {duration} секунд...")
    
    # Создаем клиент Socket.IO
    sio = socketio.Client()
    
    # Обработчики событий
    @sio.event
    def connect():
        print("[СОЕДИНЕНИЕ] Подключено к серверу Socket.IO")
        
        # Присоединяемся к личной комнате
        print(f"[СОЕДИНЕНИЕ] Присоединение к личной комнате {username}...")
        sio.emit('join_private', {'room': username})
    
    @sio.event
    def connect_error(error):
        print(f"[ОШИБКА] Ошибка подключения: {error}")
    
    @sio.event
    def disconnect():
        print("[СОЕДИНЕНИЕ] Отключено от сервера Socket.IO")
    
    # Обрабатываем все типы сообщений
    @sio.on('*')
    def catch_all(event, data):
        print(f"[СОБЫТИЕ] {event}: {json.dumps(data, ensure_ascii=False)}")
    
    # Конкретные обработчики для важных событий
    @sio.on('receive_private_message')
    def on_message(data):
        print(f"[СООБЩЕНИЕ] Получено сообщение от {data.get('sender')} для {data.get('recipient')}: {data.get('message')}")
        print(f"[СООБЩЕНИЕ] Детали: ID={data.get('id')}, timestamp={data.get('timestamp')}, room={data.get('room')}")
    
    @sio.on('error')
    def on_error(data):
        print(f"[ОШИБКА] Получена ошибка: {data}")
    
    @sio.on('chat_update')
    def on_chat_update(data):
        print(f"[ОБНОВЛЕНИЕ ЧАТА] {data.get('id')}: {json.dumps(data, ensure_ascii=False)}")
    
    try:
        # Подключаемся к серверу с session_id в query параметре
        print("[СОЕДИНЕНИЕ] Подключение к серверу Socket.IO...")
        sio.connect(f'http://localhost:5000?session_id={session_id}', transports=['websocket'])
        
        # Мониторим события указанное время
        print(f"[ИНФОРМАЦИЯ] Мониторинг запущен на {duration} секунд...")
        start_time = time.time()
        
        while time.time() - start_time < duration:
            time.sleep(1)
            elapsed = int(time.time() - start_time)
            if elapsed % 10 == 0:  # Каждые 10 секунд
                print(f"[ИНФОРМАЦИЯ] Мониторинг активен {elapsed}/{duration} секунд...")
        
        # Завершаем мониторинг
        print("[ИНФОРМАЦИЯ] Мониторинг завершен")
        if sio.connected:
            sio.disconnect()
        
    except Exception as e:
        print(f"[ОШИБКА] Ошибка при мониторинге: {e}")
        import traceback
        traceback.print_exc()
        
        # Отключаемся, если еще подключены
        if hasattr(sio, 'connected') and sio.connected:
            sio.disconnect()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Использование: python socketio_listener.py <имя_пользователя> <пароль> [продолжительность_в_секундах]")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    duration = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    
    # Получаем session_id через авторизацию
    session_id, username = get_session_id(username, password)
    if not session_id:
        print("Не удалось получить session_id, выход")
        sys.exit(1)
    
    # Запускаем мониторинг
    monitor_socketio_events(session_id, username, duration) 