 import asyncio
import socketio
import requests
import os
import json
import sys
import time

class GreenTalkFileUploader:
    def __init__(self, server_url='http://localhost:5000'):
        self.server_url = server_url
        self.session = requests.Session()
        self.sio = socketio.Client()
        self.username = None
        self.setup_socket_handlers()
    
    def setup_socket_handlers(self):
        """Настройка обработчиков событий Socket.IO"""
        
        @self.sio.event
        def connect():
            print(f"[+] Соединение с Socket.IO установлено")
            
        @self.sio.event
        def disconnect():
            print(f"[-] Соединение с Socket.IO разорвано")
            
        @self.sio.event
        def connect_error(error):
            print(f"[-] Ошибка подключения: {error}")
            
        @self.sio.on('receive_private_message')
        def on_message(data):
            print(f"\n[←] Получено сообщение: {json.dumps(data, ensure_ascii=False)}")
            
            # Проверяем, является ли это файловым сообщением
            if 'message' in data and data['message'].startswith('FILE:'):
                parts = data['message'].split(':')
                if len(parts) >= 3:
                    file_type = parts[1]
                    file_url = parts[2]
                    print(f"    📎 Получен файл типа {file_type}: {file_url}")
            
        @self.sio.on('error')
        def on_error(data):
            print(f"[-] Ошибка Socket.IO: {data}")
            
        @self.sio.on('chat_update')
        def on_chat_update(data):
            print(f"[i] Обновление чата: {json.dumps(data, ensure_ascii=False)}")
    
    def login(self, username, password):
        """Авторизация в приложении"""
        print(f"[*] Авторизация пользователя {username}...")
        
        # Отправляем запрос на авторизацию
        response = self.session.post(f"{self.server_url}/login", data={
            'username': username,
            'password': password
        }, allow_redirects=False)
        
        # Проверяем статус ответа
        if response.status_code == 302 and '/modern_chat' in response.headers.get('Location', ''):
            print(f"[+] Пользователь {username} успешно авторизован")
            self.username = username
            return True
        else:
            print(f"[-] Ошибка авторизации")
            return False
    
    def connect_socketio(self):
        """Подключение к Socket.IO серверу"""
        try:
            print(f"[*] Подключение к Socket.IO серверу...")
            self.sio.connect(self.server_url, transports=['websocket'])
            print(f"[+] Успешное подключение к Socket.IO")
            return True
        except Exception as e:
            print(f"[-] Ошибка подключения к Socket.IO: {e}")
            return False
    
    def upload_file(self, file_path, receiver):
        """Загрузка файла и отправка через Socket.IO"""
        if not os.path.exists(file_path):
            print(f"[-] Файл не найден: {file_path}")
            return False
        
        # Определяем тип файла по расширению
        filename = os.path.basename(file_path)
        file_ext = os.path.splitext(filename)[1].lower().lstrip('.')
        file_type = self._determine_file_type(file_ext)
        
        print(f"[*] Загрузка файла {filename} (тип: {file_type}) для пользователя {receiver}...")
        
        # Загружаем файл на сервер
        with open(file_path, 'rb') as f:
            files = {'file': (filename, f)}
            response = self.session.post(f"{self.server_url}/upload", files=files)
        
        if response.status_code != 200:
            print(f"[-] Ошибка загрузки файла: {response.status_code}")
            return False
        
        # Получаем данные о загруженном файле
        try:
            file_data = response.json()
            
            if not file_data.get('success'):
                print(f"[-] Сервер вернул ошибку: {file_data.get('error', 'Неизвестная ошибка')}")
                return False
            
            file_url = file_data.get('file_url')
            print(f"[+] Файл успешно загружен: {file_url}")
            
            # Генерируем приватную комнату для общения
            # Формат: private_username1_username2 (в алфавитном порядке)
            usernames = sorted([self.username, receiver])
            room = f"private_{usernames[0]}_{usernames[1]}"
            
            # Создаем сообщение в формате FILE:тип:url
            file_message = f"FILE:{file_type}:{file_url}"
            
            # Отправляем сообщение через Socket.IO
            print(f"[*] Отправка файлового сообщения в комнату {room}...")
            self.sio.emit('send_private_message', 
                         {'room': room, 'receiver': receiver, 'message': file_message},
                         callback=self._on_message_sent)
            
            return True
            
        except Exception as e:
            print(f"[-] Ошибка при обработке ответа: {e}")
            return False
    
    def send_message(self, receiver, message):
        """Отправка обычного текстового сообщения"""
        if not self.sio.connected:
            print(f"[-] Нет соединения с Socket.IO")
            return False
        
        # Генерируем приватную комнату для общения
        usernames = sorted([self.username, receiver])
        room = f"private_{usernames[0]}_{usernames[1]}"
        
        print(f"[*] Отправка сообщения '{message}' для {receiver} в комнате {room}...")
        self.sio.emit('send_private_message', 
                     {'room': room, 'receiver': receiver, 'message': message},
                     callback=self._on_message_sent)
        return True
    
    def disconnect(self):
        """Отключение от Socket.IO сервера"""
        if hasattr(self, 'sio') and self.sio.connected:
            print(f"[*] Отключение от Socket.IO...")
            self.sio.disconnect()
    
    def _on_message_sent(self, response):
        """Обработка колбэка после отправки сообщения"""
        if isinstance(response, dict):
            if response.get('success'):
                print(f"[+] Сообщение успешно отправлено (id: {response.get('id')})")
            else:
                print(f"[-] Ошибка отправки сообщения: {response.get('error', 'Неизвестная ошибка')}")
        else:
            print(f"[i] Ответ сервера: {response}")
    
    def _determine_file_type(self, extension):
        """Определение типа файла по расширению"""
        image_types = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg']
        video_types = ['mp4', 'webm', 'mkv', 'avi', 'mov']
        audio_types = ['mp3', 'wav', 'ogg', 'opus']
        
        if extension in image_types:
            return 'image'
        elif extension in video_types:
            return 'video'
        elif extension in audio_types:
            return 'audio'
        else:
            return 'document'


def main():
    """Основная функция для тестирования загрузки файлов"""
    if len(sys.argv) < 4:
        print("Использование: python file_upload_test.py <имя_пользователя> <пароль> <получатель> [путь_к_файлу]")
        print("Если файл не указан, будет отправлено только текстовое сообщение")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    receiver = sys.argv[3]
    file_path = sys.argv[4] if len(sys.argv) > 4 else None
    
    uploader = GreenTalkFileUploader()
    
    try:
        # Авторизация
        if not uploader.login(username, password):
            print("Не удалось авторизоваться")
            sys.exit(1)
        
        # Подключение к Socket.IO
        if not uploader.connect_socketio():
            print("Не удалось подключиться к Socket.IO")
            sys.exit(1)
        
        # Отправляем текстовое сообщение
        uploader.send_message(receiver, f"Тестовое сообщение от {username} в {time.strftime('%H:%M:%S')}")
        
        # Если указан файл, загружаем и отправляем его
        if file_path:
            uploader.upload_file(file_path, receiver)
        
        # Ждем некоторое время для получения ответов
        print("\n[*] Ожидание ответных сообщений (10 секунд)...")
        time.sleep(10)
        
    except KeyboardInterrupt:
        print("\n[*] Прерывание работы программы...")
    finally:
        uploader.disconnect()
        print("[*] Работа программы завершена")


if __name__ == "__main__":
    main()