import socketio
import requests
import json
import sys
import time

class GreenTalkSocketMonitor:
    def __init__(self, server_url='http://localhost:5000'):
        self.server_url = server_url
        self.session = requests.Session()
        self.sio = socketio.Client()
        self.setup_socket_handlers()
    
    def setup_socket_handlers(self):
        """Настройка обработчиков событий Socket.IO"""
        
        @self.sio.event
        def connect():
            print(f"[SocketIO] Соединение установлено")
            
        @self.sio.event
        def disconnect():
            print(f"[SocketIO] Соединение разорвано")
            
        @self.sio.event
        def connect_error(error):
            print(f"[SocketIO] Ошибка подключения: {error}")
        
        # Общий обработчик для всех событий
        @self.sio.on('*')
        def catch_all(event, data):
            # Преобразуем данные в JSON с поддержкой юникода
            if isinstance(data, dict):
                data_json = json.dumps(data, ensure_ascii=False, indent=2)
            else:
                data_json = str(data)
                
            print(f"\n[СОБЫТИЕ: {event}]")
            print(f"{data_json}")
        
        # Специализированные обработчики для конкретных событий
        @self.sio.on('receive_private_message')
        def on_private_message(data):
            print(f"\n[ПРИВАТНОЕ СООБЩЕНИЕ]")
            
            # Проверяем, является ли сообщение файловым
            if 'message' in data and isinstance(data['message'], str) and data['message'].startswith('FILE:'):
                parts = data['message'].split(':')
                if len(parts) >= 3:
                    file_type = parts[1]
                    file_url = parts[2]
                    print(f"📎 Получен файл типа {file_type} от {data.get('sender')} для {data.get('recipient')}")
                    print(f"   URL: {file_url}")
            else:
                # Обычное текстовое сообщение
                print(f"✉️ Сообщение от {data.get('sender')} для {data.get('recipient')}: {data.get('message')}")
            
            # Дополнительная информация о сообщении
            print(f"   ID: {data.get('id')}")
            print(f"   Timestamp: {data.get('timestamp')}")
            print(f"   Комната: {data.get('room')}")
            print(f"   Прочитано: {data.get('read', False)}")
        
        @self.sio.on('chat_update')
        def on_chat_update(data):
            print(f"\n[ОБНОВЛЕНИЕ ЧАТА]")
            print(f"   ID: {data.get('id')}")
            print(f"   Имя: {data.get('name')}")
            
            # Информация о последнем сообщении
            last_msg = data.get('last_message', {})
            if last_msg:
                print(f"   Последнее сообщение: {last_msg.get('text')}")
                print(f"   Отправитель: {last_msg.get('sender')}")
                print(f"   Timestamp: {last_msg.get('timestamp')}")
                
            print(f"   Непрочитанных: {data.get('unread_count', 0)}")
        
        @self.sio.on('someone_typing')
        def on_typing(data):
            print(f"\n[ПЕЧАТАЕТ] {data.get('user')} печатает...")
        
        @self.sio.on('someone_stopped_typing')
        def on_stop_typing(data):
            print(f"\n[ПЕРЕСТАЛ ПЕЧАТАТЬ] {data.get('user')} перестал печатать")
            
        @self.sio.on('error')
        def on_error(data):
            print(f"\n[ОШИБКА] {data.get('message', json.dumps(data, ensure_ascii=False))}")
    
    def login(self, username, password):
        """Авторизация в приложении"""
        print(f"Авторизация пользователя {username}...")
        
        # Отправляем запрос на авторизацию
        response = self.session.post(f"{self.server_url}/login", data={
            'username': username,
            'password': password
        }, allow_redirects=False)
        
        # Проверяем статус ответа
        if response.status_code == 302 and '/modern_chat' in response.headers.get('Location', ''):
            # Получаем cookie с session_id
            cookies = self.session.cookies.get_dict()
            session_id = cookies.get('session')
            
            if session_id:
                print(f"Пользователь {username} успешно авторизован, session_id: {session_id[:10]}...")
                self.username = username
                return session_id
            else:
                print(f"Не удалось получить session_id")
                return None
        else:
            print(f"Ошибка авторизации пользователя {username}")
            return None
    
    def connect_socketio(self, session_id=None):
        """Подключение к Socket.IO серверу"""
        try:
            print(f"Подключение к Socket.IO серверу...")
            
            # Если есть session_id, используем его в качестве параметра запроса
            if session_id:
                self.sio.connect(f"{self.server_url}?session_id={session_id}", transports=['websocket'])
            else:
                # Иначе используем куки сессии из requests.Session
                self.sio.connect(self.server_url, transports=['websocket'])
                
            print(f"Успешное подключение к Socket.IO")
            return True
        except Exception as e:
            print(f"Ошибка подключения к Socket.IO: {e}")
            return False
    
    def join_room(self, room):
        """Присоединиться к комнате Socket.IO"""
        if not self.sio.connected:
            print(f"Нет соединения с Socket.IO")
            return False
            
        print(f"Присоединение к комнате: {room}")
        self.sio.emit('join', {'room': room})
        return True
    
    def run(self, duration=-1):
        """Запуск мониторинга на указанное время (в секундах)"""
        print(f"Запуск мониторинга Socket.IO событий...")
        
        if duration > 0:
            print(f"Мониторинг будет активен {duration} секунд")
            start_time = time.time()
            
            try:
                while time.time() - start_time < duration:
                    time.sleep(1)
                    elapsed = int(time.time() - start_time)
                    if elapsed % 10 == 0:  # Каждые 10 секунд
                        print(f"Мониторинг активен {elapsed}/{duration} секунд")
                        
                print(f"Мониторинг завершен после {duration} секунд")
            except KeyboardInterrupt:
                print("Мониторинг прерван пользователем")
                
        else:
            # Бесконечный мониторинг до прерывания пользователем
            print("Мониторинг активен. Нажмите Ctrl+C для остановки.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("Мониторинг прерван пользователем")
        
        # Отключаемся от Socket.IO
        self.disconnect()
    
    def disconnect(self):
        """Отключение от Socket.IO сервера"""
        if hasattr(self, 'sio') and self.sio.connected:
            print(f"Отключение от Socket.IO...")
            self.sio.disconnect()


def main():
    """Основная функция для мониторинга Socket.IO"""
    if len(sys.argv) < 3:
        print("Использование: python socketio_monitor.py <имя_пользователя> <пароль> [продолжительность_в_секундах]")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    duration = int(sys.argv[3]) if len(sys.argv) > 3 else -1  # -1 означает бесконечный мониторинг
    
    monitor = GreenTalkSocketMonitor()
    
    try:
        # Авторизация
        session_id = monitor.login(username, password)
        if not session_id:
            print("Не удалось авторизоваться")
            sys.exit(1)
        
        # Подключение к Socket.IO
        if not monitor.connect_socketio(session_id):
            print("Не удалось подключиться к Socket.IO")
            sys.exit(1)
        
        # Запуск мониторинга
        monitor.run(duration)
        
    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        monitor.disconnect()
        print("Работа программы завершена")


if __name__ == "__main__":
    main() 