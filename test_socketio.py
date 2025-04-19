import requests
import sys
import json
import time

def get_user_session(username, password):
    """Аутентификация пользователя и получение сессии"""
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
    
    # Проверяем, успешна ли авторизация (редирект на /modern_chat)
    if response.status_code == 302 and '/modern_chat' in response.headers.get('Location', ''):
        print(f"Пользователь {username} успешно авторизован")
        return session
    else:
        print(f"Ошибка авторизации пользователя {username}")
        return None

def send_test_message(session, receiver, message):
    """Отправить тестовое сообщение через API"""
    print(f"Отправка сообщения для {receiver}: {message}")
    
    # URL для отправки сообщения
    send_url = 'http://localhost:5000/api/send_message'
    
    # Данные для отправки
    data = {
        'receiver': receiver,
        'message': message,
        'room': f"private_{session.cookies.get('username')}_{receiver}"  # предполагаем, что в куках есть username
    }
    
    # Отправляем запрос
    response = session.post(send_url, json=data)
    
    # Проверяем ответ
    if response.status_code == 200:
        result = response.json()
        if result.get('success'):
            print(f"Сообщение успешно отправлено, ID: {result.get('id')}")
            return True
        else:
            print(f"Ошибка при отправке сообщения: {result.get('error')}")
            return False
    else:
        print(f"Ошибка API: {response.status_code}")
        print(response.text)
        return False

def get_chat_history(session, partner):
    """Получить историю чата с указанным партнером"""
    print(f"Получение истории чата с {partner}...")
    
    # URL для получения истории
    history_url = 'http://localhost:5000/api/chat_history'
    
    # Данные для запроса
    username = session.cookies.get('username')
    room = f"private_{username}_{partner}" if username < partner else f"private_{partner}_{username}"
    
    # Отправляем запрос
    response = session.get(history_url, params={'room': room, 'page': 0})
    
    # Проверяем ответ
    if response.status_code == 200:
        result = response.json()
        if result.get('success'):
            messages = result.get('messages', [])
            print(f"Получено {len(messages)} сообщений")
            
            # Выводим последние сообщения
            if messages:
                print("\nПоследние сообщения:")
                for msg in messages[-5:]:  # показать только последние 5
                    direction = "<<" if msg['sender'] == partner else ">>"
                    print(f"[{msg['id']}] {direction} {msg['sender']}: {msg['message']}")
            else:
                print("История чата пуста")
                
            return True
        else:
            print(f"Ошибка при получении истории: {result.get('error')}")
            return False
    else:
        print(f"Ошибка API: {response.status_code}")
        print(response.text)
        return False

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Использование: python test_socketio.py <имя_пользователя> <пароль> <получатель> <сообщение>")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    receiver = sys.argv[3]
    message = sys.argv[4]
    
    # Получаем сессию пользователя
    session = get_user_session(username, password)
    if not session:
        print("Не удалось авторизоваться")
        sys.exit(1)
    
    # Отправляем тестовое сообщение
    success = send_test_message(session, receiver, message)
    
    # Если сообщение отправлено успешно, ожидаем немного и получаем историю
    if success:
        print("Ждем 2 секунды перед получением истории...")
        time.sleep(2)
        get_chat_history(session, receiver) 