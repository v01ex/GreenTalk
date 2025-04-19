# GreenTalk

GreenTalk - это веб-приложение для общения, разработанное на Python с использованием Flask и Socket.IO.

## Особенности

- Обмен сообщениями в реальном времени
- Загрузка и сжатие медиафайлов (видео, аудио)
- Профили пользователей с аватарами
- Групповые чаты

## Установка

1. Клонировать репозиторий:
   ```
   git clone https://github.com/YourUsername/GreenTalk.git
   cd GreenTalk
   ```

2. Установить зависимости:
   ```
   pip install Flask Flask-SocketIO pillow
   ```

3. Инициализировать базу данных:
   ```
   python init_db.py
   ```

4. Запустить сервер:
   ```
   python server_flask.py
   ```

5. Открыть в браузере http://localhost:5000

## Структура проекта

- `server_flask.py` - Основной файл сервера
- `socketio_monitor.py` - Модуль для мониторинга WebSocket соединений
- `compression.py`, `video_compression.py`, `audio_compression.py` - Модули для сжатия файлов
- `templates/` - HTML шаблоны
- `static/` - CSS, JavaScript и другие статические файлы 