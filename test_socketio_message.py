import socketio
import sys
import time
import requests
import re

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

def send_message_via_socketio(session_id, sender, receiver, message):
    """Отправить сообщение через Socket.IO"""
    print(f"Подготовка отправки сообщения от {sender} к {receiver}: {message}")
    
    # Сортируем отправителя и получателя для формирования ID комнаты
    participants = sorted([sender, receiver])
    room_id = f"private_{participants[0]}_{participants[1]}"
    print(f"ID комнаты: {room_id}")
    
    # Создаем клиент Socket.IO
    sio = socketio.Client()
    
    # Флаг для отслеживания успешной отправки
    sent_successfully = False
    received_response = False
    server_response = None
    
    # Обработчики событий
    @sio.event
    def connect():
        print("Подключено к серверу Socket.IO")
        # Присоединяемся к комнате
        print(f"Присоединение к комнате {room_id}...")
        sio.emit('join_private', {'room': room_id}, callback=handle_join_response)
    
    @sio.event
    def connect_error(error):
        print(f"Ошибка подключения: {error}")
    
    @sio.event
    def disconnect():
        print("Отключено от сервера Socket.IO")
    
    # Обработчик ответа на присоединение к комнате
    def handle_join_response(response):
        print(f"Ответ на присоединение к комнате: {response}")
        
        # Отправляем сообщение
        print(f"Отправка сообщения...")
        sio.emit('send_private_message', {
            'room': room_id,
            'receiver': receiver,
            'message': message
        }, callback=handle_message_response)
    
    # Обработчик ответа на отправку сообщения
    def handle_message_response(response):
        nonlocal sent_successfully, received_response, server_response
        received_response = True
        server_response = response
        print(f"Ответ сервера на отправку сообщения: {response}")
        
        if response and not response.get('error'):
            sent_successfully = True
            print(f"Сообщение успешно отправлено, ID: {response.get('id', 'неизвестно')}")
        else:
            error = response.get('error', 'неизвестная ошибка')
            print(f"Ошибка при отправке сообщения: {error}")
        
        # Отключаемся от сервера
        sio.disconnect()
    
    # Слушаем входящие сообщения
    @sio.on('receive_private_message')
    def on_message(data):
        print(f"Получено сообщение: {data}")
    
    try:
        # Подключаемся к серверу с session_id в query параметре
        print("Подключение к серверу Socket.IO...")
        sio.connect(f'http://localhost:5000?session_id={session_id}', transports=['websocket'])
        
        # Ожидаем небольшое время для обработки сообщения
        timeout = 10  # секунд
        start_time = time.time()
        
        while not received_response and time.time() - start_time < timeout:
            time.sleep(0.5)
        
        if not received_response:
            print(f"Таймаут ожидания ответа от сервера после {timeout} секунд")
        
        # Отключаемся, если еще подключены
        if sio.connected:
            sio.disconnect()
        
        return sent_successfully, server_response
        
    except Exception as e:
        print(f"Ошибка при использовании Socket.IO: {e}")
        import traceback
        traceback.print_exc()
        
        # Отключаемся, если еще подключены
        if hasattr(sio, 'connected') and sio.connected:
            sio.disconnect()
            
        return False, {'error': str(e)}

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Использование: python test_socketio_message.py <имя_пользователя> <пароль> <получатель> <сообщение>")
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
    
    # Отправляем сообщение через Socket.IO
    success, response = send_message_via_socketio(session_id, username, receiver, message)
    
    if success:
        print("\nТест успешно завершен. Сообщение отправлено.")
    else:
        print("\nТест завершен с ошибкой. Сообщение не отправлено.")
        if response and response.get('error'):
            print(f"Причина: {response.get('error')}") 