import os
import uuid
import time
import sqlite3
import traceback
import shutil  # Для сброса статистики (удаления файлов)
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
import sys

# Ensure compression module is correctly imported
try:
    import compression  # Использует ваш compression.py для текстов
    print("Модуль сжатия compression.py успешно загружен")
except ImportError as e:
    print(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось загрузить модуль compression.py: {e}")
    sys.exit(1)

# Импортируем дополнительные модули сжатия
try:
    from video_compression import compress_video, decompress_video_blocks
    from audio_compression import compress_audio, decompress_audio_blocks
    COMPRESSION_MODULES_AVAILABLE = True
    print("Модули сжатия видео и аудио успешно загружены")
except ImportError as e:
    COMPRESSION_MODULES_AVAILABLE = False
    print(f"Внимание: модули сжатия видео и аудио не загружены: {e}")

from PIL import Image, ImageDraw
import io
import zlib
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app)

DATABASE = 'database.db'

app.static_folder = 'static'
UPLOAD_FOLDER = os.path.join(app.static_folder, 'uploads')
COMPRESSED_UPLOAD_FOLDER = os.path.join(app.static_folder, 'compressed_uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['COMPRESSED_UPLOAD_FOLDER'] = COMPRESSED_UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'avi', 'mov', 'mp3', 'wav', 'ogg', 'webm'}

for folder in [UPLOAD_FOLDER, COMPRESSED_UPLOAD_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Создаем папки для аватаров, если не существуют
avatar_folder = os.path.join(app.static_folder, 'avatars')
if not os.path.exists(avatar_folder):
    try:
        os.makedirs(avatar_folder, exist_ok=True)
        print(f"Создана папка для аватаров: {avatar_folder}")
    except Exception as e:
        print(f"Ошибка при создании папки для аватаров: {e}")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            username TEXT UNIQUE,
            email TEXT UNIQUE,
            password TEXT,
            avatar_url TEXT,
            last_name TEXT,
            birthdate TEXT,
            city TEXT,
            bio TEXT,
            last_seen REAL,
            status TEXT DEFAULT 'offline'
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS private_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT,
            receiver TEXT,
            timestamp REAL,
            compressed_message BLOB,
            read INTEGER DEFAULT 0,
            deleted_for_sender INTEGER DEFAULT 0,
            deleted_for_receiver INTEGER DEFAULT 0,
            edited INTEGER DEFAULT 0,
            original_message BLOB
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS private_chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1 TEXT,
            user2 TEXT,
            last_message BLOB,
            last_message_timestamp REAL,
            created_at REAL,
            is_favorite INTEGER DEFAULT 0,
            FOREIGN KEY (user1) REFERENCES users (username),
            FOREIGN KEY (user2) REFERENCES users (username),
            UNIQUE(user1, user2)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS file_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            original_size INTEGER,
            compressed_size INTEGER,
            compression_type TEXT,
            date_created REAL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS chat_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            creator TEXT,
            created_at REAL,
            description TEXT,
            avatar_url TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER,
            username TEXT,
            joined_at REAL,
            is_admin INTEGER DEFAULT 0,
            FOREIGN KEY (group_id) REFERENCES chat_groups (id),
            FOREIGN KEY (username) REFERENCES users (username)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS group_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER,
            sender TEXT,
            timestamp REAL,
            compressed_message BLOB,
            edited INTEGER DEFAULT 0,
            original_message BLOB,
            FOREIGN KEY (group_id) REFERENCES chat_groups (id),
            FOREIGN KEY (sender) REFERENCES users (username)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS message_reactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            message_type TEXT,
            username TEXT,
            reaction TEXT,
            timestamp REAL,
            FOREIGN KEY (username) REFERENCES users (username)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            contact_username TEXT,
            is_favorite INTEGER DEFAULT 0,
            is_blocked INTEGER DEFAULT 0,
            added_at REAL,
            FOREIGN KEY (username) REFERENCES users (username),
            FOREIGN KEY (contact_username) REFERENCES users (username)
        )
    ''')
    conn.commit()
    conn.close()
    
    # Создаем дефолтную аватарку, если ее нет
    default_avatar_path = os.path.join(app.static_folder, 'img', 'default-avatar.png')
    if not os.path.exists(default_avatar_path):
        try:
            os.makedirs(os.path.dirname(default_avatar_path), exist_ok=True)
            from PIL import Image, ImageDraw
            
            # Создаем простую аватарку с буквой "U" (user)
            img_size = 200
            img = Image.new('RGB', (img_size, img_size), color=(100, 149, 237))  # Голубой фон
            draw = ImageDraw.Draw(img)
            
            # Рисуем круг для аватарки
            draw.ellipse([(0, 0), (img_size, img_size)], fill=(70, 130, 180))
            
            # Сохраняем изображение
            img.save(default_avatar_path)
            print(f"Создана дефолтная аватарка по пути: {default_avatar_path}")
        except Exception as e:
            print(f"Ошибка при создании дефолтной аватарки: {e}")

def update_db_structure():
    """Проверяет и обновляет структуру БД, добавляя недостающие колонки"""
    print("Проверка и обновление структуры базы данных...")
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        
        # Получаем информацию о структуре таблицы users
        c.execute("PRAGMA table_info(users)")
        columns = c.fetchall()
        column_names = [column[1] for column in columns]
        print(f"Существующие колонки в таблице users: {', '.join(column_names)}")
        
        # Проверяем и добавляем недостающие колонки в users
        required_columns = {
            'last_name': 'TEXT',
            'birthdate': 'TEXT',
            'city': 'TEXT',
            'bio': 'TEXT',
            'avatar_url': 'TEXT',
            'last_seen': 'REAL',
            'status': 'TEXT DEFAULT "offline"'
        }
        
        for column_name, column_type in required_columns.items():
            if column_name not in column_names:
                print(f"Добавление колонки {column_name} типа {column_type}")
                c.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")
                conn.commit()

        # Получаем информацию о структуре таблицы private_messages
        c.execute("PRAGMA table_info(private_messages)")
        columns = c.fetchall()
        column_names = [column[1] for column in columns]
        print(f"Существующие колонки в таблице private_messages: {', '.join(column_names)}")
        
        # Проверяем и добавляем недостающие колонки в private_messages
        required_columns = {
            'read': 'INTEGER DEFAULT 0',
            'deleted_for_sender': 'INTEGER DEFAULT 0',
            'deleted_for_receiver': 'INTEGER DEFAULT 0',
            'edited': 'INTEGER DEFAULT 0',
            'original_message': 'BLOB'
        }
        
        for column_name, column_type in required_columns.items():
            if column_name not in column_names:
                print(f"Добавление колонки {column_name} типа {column_type}")
                c.execute(f"ALTER TABLE private_messages ADD COLUMN {column_name} {column_type}")
                conn.commit()
        
        # Проверяем существование таблицы private_chats
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='private_chats'")
        if not c.fetchone():
            print("Создание таблицы private_chats...")
            c.execute('''
                CREATE TABLE IF NOT EXISTS private_chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user1 TEXT,
                    user2 TEXT,
                    last_message BLOB,
                    last_message_timestamp REAL,
                    created_at REAL,
                    is_favorite INTEGER DEFAULT 0,
                    FOREIGN KEY (user1) REFERENCES users (username),
                    FOREIGN KEY (user2) REFERENCES users (username),
                    UNIQUE(user1, user2)
                )
            ''')
            conn.commit()
                
        # Создание новых таблиц, если они не существуют
        tables_to_check = ["chat_groups", "group_members", "group_messages", 
                          "message_reactions", "user_contacts"]
        
        for table in tables_to_check:
            c.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            if not c.fetchone():
                print(f"Таблица {table} не существует, создаем...")
                init_db()  # Вызываем init_db для создания недостающих таблиц
                break
        
        print("Структура базы данных обновлена успешно")
        conn.close()
    except Exception as e:
        print(f"Ошибка при обновлении структуры БД: {e}")
        traceback.print_exc()

# Инициализация и обновление БД
init_db()
update_db_structure()

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    if 'username' in session:
        # Если пользователь авторизован, перенаправляем в модерн чат
        return redirect(url_for('modern_chat'))
    # Иначе отправляем на страницу входа
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('modern_chat'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()
        if user:
            session['username'] = username
            return redirect(url_for('modern_chat'))
        else:
            flash('Неверное имя пользователя или пароль', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'username' in session:
        return redirect(url_for('modern_chat'))
    if request.method == 'POST':
        name = request.form['name']
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (name, username, email, password) VALUES (?, ?, ?, ?)',
                         (name, username, email, password))
            conn.commit()
            conn.close()
            session['username'] = username
            flash(f'Регистрация прошла успешно! Добро пожаловать, {name}', 'success')
            return redirect(url_for('modern_chat'))
        except sqlite3.IntegrityError:
            conn.close()
            flash('Пользователь с таким логином или электронной почтой уже существует', 'danger')
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/search', methods=['GET', 'POST'])
def search():
    if 'username' not in session:
        return redirect(url_for('login'))
    results = []
    if request.method == 'POST':
        query = request.form.get('query', '')
        conn = get_db_connection()
        results = conn.execute(
            "SELECT username, name FROM users WHERE username LIKE ? AND username != ?",
            (f'%{query}%', session['username'])
        ).fetchall()
        conn.close()
    return render_template('search.html', results=results)

@app.route('/private_chats', endpoint='private_chats')
def private_chats():
    if 'username' not in session:
        return redirect(url_for('login'))
    # Redirect to modern chat
    return redirect(url_for('modern_chat'))

@app.route('/modern_chat')
def modern_chat():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('modern_chat.html', username=session['username'])

@app.route('/favorites')
def favorites():
    if 'username' not in session:
        return redirect(url_for('login'))
    # Redirect to modern chat
    return redirect(url_for('modern_chat'))

@app.route('/profile/<username>')
def profile(username):
    if 'username' not in session:
        print(f"Попытка открыть профиль {username}, но пользователь не авторизован")
        return redirect(url_for('login'))
    
    print(f"Запрос на отображение профиля {username} от пользователя {session['username']}")
    
    conn = get_db_connection()
    try:
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if not user:
            print(f"Пользователь {username} не найден в базе данных")
            flash('Пользователь не найден', 'danger')
            return redirect(url_for('modern_chat'))
        
        # Получаем доступные поля из базы данных
        c = conn.cursor()
        c.execute("PRAGMA table_info(users)")
        columns = c.fetchall()
        column_names = [column[1] for column in columns]
        print(f"Доступные колонки в таблице users: {', '.join(column_names)}")
        
        field_names = user.keys()
        print(f"Пользователь {username} найден, доступные поля: {', '.join(field_names)}")
        
        # Подготовка данных профиля для отображения
        profile_data = {
            'username': user['username'],
            'name': user['name'] if 'name' in field_names and user['name'] else '',
            'avatar_url': url_for('static', filename='img/default-avatar.png'),
            'email': user['email'] if 'email' in field_names and user['email'] else '',
            'is_own_profile': username == session['username']
        }
        
        # Добавляем дополнительные поля, если они доступны
        if 'last_name' in field_names:
            profile_data['last_name'] = user['last_name'] if user['last_name'] else ''
        else:
            profile_data['last_name'] = ''
        
        if 'birthdate' in field_names:
            profile_data['birthdate'] = user['birthdate'] if user['birthdate'] else ''
        else:
            profile_data['birthdate'] = ''
        
        if 'city' in field_names:
            profile_data['city'] = user['city'] if user['city'] else ''
        else:
            profile_data['city'] = ''
        
        if 'bio' in field_names:
            profile_data['bio'] = user['bio'] if user['bio'] else ''
        else:
            profile_data['bio'] = ''
        
        print(f"Подготовлены данные профиля")
        
        # Безопасно проверяем наличие аватара
        try:
            if 'avatar_url' in field_names and user['avatar_url'] and isinstance(user['avatar_url'], str) and user['avatar_url'].strip():
                avatar_url = user['avatar_url']
                print(f"Обработка аватара: {avatar_url}")
                if avatar_url.startswith('/static/'):
                    profile_data['avatar_url'] = avatar_url
                    print(f"Используем абсолютный путь аватара: {profile_data['avatar_url']}")
                else:
                    # Делаем URL относительно /static/
                    profile_data['avatar_url'] = url_for('static', filename=avatar_url.replace('static/', ''))
                    print(f"Используем относительный путь аватара: {profile_data['avatar_url']}")
        except Exception as e:
            print(f"Ошибка при обработке URL аватара: {e}")
            traceback.print_exc()
            # Оставляем дефолтный аватар
        
        print(f"Рендерим шаблон profile.html с данными")
        try:
            return render_template('profile.html', profile=profile_data)
        except Exception as e:
            print(f"Ошибка при рендеринге шаблона profile.html: {e}")
            traceback.print_exc()
            flash('Ошибка при отображении шаблона профиля', 'danger')
            return redirect(url_for('modern_chat'))
    except Exception as e:
        print(f"Ошибка при загрузке профиля {username}: {e}")
        traceback.print_exc()
        flash('Произошла ошибка при загрузке профиля', 'danger')
        return redirect(url_for('modern_chat'))
    finally:
        conn.close()

@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'username' not in session:
        print("Сессия пользователя отсутствует, перенаправление на страницу входа")
        return redirect(url_for('login'))
    
    username = session['username']
    print(f"Открытие страницы редактирования профиля для пользователя: {username}")
    
    try:
        print("Попытка подключения к базе данных")
        conn = get_db_connection()
        
        try:
            print("Выполнение запроса на получение пользователя")
            user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
            if user:
                field_names = user.keys()
                print(f"Получены данные пользователя: {user['username']}")
                print(f"Доступные поля в записи: {', '.join(field_names)}")
            else:
                print("Пользователь не найден")
            
            if not user:
                conn.close()
                flash('Пользователь не найден', 'danger')
                return redirect(url_for('login'))
                
            if request.method == 'POST':
                print("Обработка POST-запроса")
                # Получаем данные из формы
                name = request.form.get('name', '')
                last_name = request.form.get('last_name', '')
                email = request.form.get('email', '')
                birthdate = request.form.get('birthdate', '')
                city = request.form.get('city', '')
                bio = request.form.get('bio', '')
                
                print(f"Полученные данные из формы: name={name}, last_name={last_name}, email={email}, birthdate={birthdate}, city={city}, bio длина={len(bio)}")
                
                # Обработка загрузки аватара - безопасно получаем текущее значение
                try:
                    avatar_url = user['avatar_url'] if 'avatar_url' in field_names and user['avatar_url'] else None
                    print(f"Текущий avatar_url: {avatar_url}")
                except Exception as e:
                    print(f"Ошибка при получении avatar_url из БД: {e}")
                    traceback.print_exc()
                    avatar_url = None
                    
                if 'avatar' in request.files and request.files['avatar'].filename:
                    print("Обнаружен файл аватара")
                    avatar_file = request.files['avatar']
                    print(f"Имя файла аватара: {avatar_file.filename}")
                    # Проверка типа файла
                    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
                    file_ext = avatar_file.filename.rsplit('.', 1)[1].lower() if '.' in avatar_file.filename else ''
                    if file_ext in allowed_extensions:
                        print(f"Расширение файла допустимо: {file_ext}")
                        # Генерация уникального имени файла
                        unique_filename = f"avatar_{username}_{int(time.time())}.{file_ext}"
                        
                        # Создаем папку, если не существует
                        avatar_folder = os.path.join(app.static_folder, 'avatars')
                        os.makedirs(avatar_folder, exist_ok=True)
                        
                        avatar_path = os.path.join(avatar_folder, unique_filename)
                        print(f"Путь сохранения аватара: {avatar_path}")
                        
                        # Сохраняем и изменяем размер аватара
                        try:
                            image = Image.open(avatar_file)
                            image.thumbnail((200, 200))  # Максимальный размер 200x200
                            image.save(avatar_path)
                            avatar_url = f"avatars/{unique_filename}"
                            print(f"Аватар сохранен, URL: {avatar_url}")
                        except Exception as e:
                            print(f"Ошибка при обработке аватара: {e}")
                            traceback.print_exc()
                            flash('Ошибка при загрузке аватара', 'danger')
                    else:
                        flash(f'Недопустимое расширение файла. Поддерживаемые форматы: {", ".join(allowed_extensions)}', 'danger')
                
                try:
                    print("Обновление данных пользователя в БД")
                    
                    # Проверяем доступные колонки в таблице users
                    c = conn.cursor()
                    c.execute("PRAGMA table_info(users)")
                    columns = c.fetchall()
                    column_names = [column[1] for column in columns]
                    print(f"Доступные колонки в таблице users: {', '.join(column_names)}")
                    
                    # Формируем запрос с учетом доступных колонок
                    update_fields = []
                    values = []
                    
                    # Базовые поля, которые всегда должны быть
                    if 'name' in column_names:
                        update_fields.append("name = ?")
                        values.append(name)
                    
                    if 'email' in column_names:
                        update_fields.append("email = ?")
                        values.append(email)
                    
                    # Дополнительные поля, которые могут отсутствовать
                    if 'last_name' in column_names:
                        update_fields.append("last_name = ?")
                        values.append(last_name)
                    
                    if 'birthdate' in column_names:
                        update_fields.append("birthdate = ?")
                        values.append(birthdate)
                    
                    if 'city' in column_names:
                        update_fields.append("city = ?")
                        values.append(city)
                    
                    if 'bio' in column_names:
                        update_fields.append("bio = ?")
                        values.append(bio)
                    
                    if 'avatar_url' in column_names:
                        update_fields.append("avatar_url = ?")
                        values.append(avatar_url)
                    
                    # Добавляем условие WHERE
                    values.append(username)
                    
                    # Формируем и выполняем запрос
                    query = f"UPDATE users SET {', '.join(update_fields)} WHERE username = ?"
                    print(f"Запрос на обновление: {query}")
                    conn.execute(query, values)
                    conn.commit()
                    
                    print("Данные пользователя успешно обновлены")
                    flash('Профиль успешно обновлен', 'success')
                    return redirect(url_for('profile', username=username))
                except Exception as e:
                    conn.rollback()
                    print(f"Ошибка при обновлении профиля: {e}")
                    traceback.print_exc()
                    flash('Ошибка при обновлении профиля', 'danger')
            
            # Подготовка данных профиля для формы редактирования
            try:
                print("Подготовка данных профиля для формы редактирования")
                field_names = user.keys()
                
                # Получаем доступные поля из базы данных
                c = conn.cursor()
                c.execute("PRAGMA table_info(users)")
                columns = c.fetchall()
                column_names = [column[1] for column in columns]
                
                # Базовая информация
                profile_data = {
                    'username': user['username'],
                    'name': user['name'] if 'name' in field_names and user['name'] else '',
                    'email': user['email'] if 'email' in field_names and user['email'] else '',
                    'avatar_url': url_for('static', filename='img/default-avatar.png')
                }
                
                # Дополнительные поля
                if 'last_name' in column_names:
                    profile_data['last_name'] = user['last_name'] if 'last_name' in field_names and user['last_name'] else ''
                else:
                    profile_data['last_name'] = ''
                
                if 'birthdate' in column_names:
                    profile_data['birthdate'] = user['birthdate'] if 'birthdate' in field_names and user['birthdate'] else ''
                else:
                    profile_data['birthdate'] = ''
                
                if 'city' in column_names:
                    profile_data['city'] = user['city'] if 'city' in field_names and user['city'] else ''
                else:
                    profile_data['city'] = ''
                
                if 'bio' in column_names:
                    profile_data['bio'] = user['bio'] if 'bio' in field_names and user['bio'] else ''
                else:
                    profile_data['bio'] = ''
                
                print(f"Успешно создан словарь profile_data с полями: {', '.join(profile_data.keys())}")
                
                # Безопасно проверяем наличие аватара
                try:
                    has_avatar = 'avatar_url' in field_names and user['avatar_url'] and isinstance(user['avatar_url'], str) and user['avatar_url'].strip()
                    if has_avatar:
                        # Проверяем, начинается ли с /static/
                        avatar_url = user['avatar_url']
                        print(f"Текущий avatar_url пользователя: {avatar_url}")
                        if avatar_url.startswith('/static/'):
                            profile_data['avatar_url'] = avatar_url
                            print(f"Установлен аватар пользователя (начинается с /static/): {profile_data['avatar_url']}")
                        else:
                            # Делаем URL относительно /static/
                            profile_data['avatar_url'] = url_for('static', filename=avatar_url.replace('static/', ''))
                            print(f"Установлен аватар пользователя (относительный путь): {profile_data['avatar_url']}")
                except Exception as e:
                    print(f"Ошибка при обработке URL аватара: {e}")
                    traceback.print_exc()
                    # Оставляем дефолтный аватар
                    print(f"Оставлен дефолтный аватар: {profile_data['avatar_url']}")
                
                print("Отправка данных в шаблон edit_profile.html")
                print(f"Всего полей в profile_data: {len(profile_data)}")
                
                try:
                    rendered_template = render_template('edit_profile.html', profile=profile_data)
                    print(f"Шаблон успешно отрендерен, длина HTML: {len(rendered_template)}")
                    return rendered_template
                except Exception as e:
                    print(f"Ошибка при рендеринге шаблона edit_profile.html: {e}")
                    traceback.print_exc()
                    flash('Ошибка при отображении страницы профиля', 'danger')
                    return redirect(url_for('modern_chat'))
            except Exception as e:
                print(f"Ошибка при подготовке данных профиля: {e}")
                traceback.print_exc()
                flash('Ошибка при загрузке профиля', 'danger')
                return redirect(url_for('modern_chat'))
        
        except Exception as e:
            print(f"Общая ошибка при обработке профиля: {e}")
            traceback.print_exc()
            flash('Произошла ошибка при загрузке профиля', 'danger')
            return redirect(url_for('modern_chat'))
        
    except Exception as e:
        print(f"Критическая ошибка в функции edit_profile: {e}")
        traceback.print_exc()
        flash('Критическая ошибка при открытии профиля', 'danger')
        return redirect(url_for('modern_chat'))
    
    finally:
        try:
            conn.close()
            print("Соединение с БД закрыто")
        except:
            pass

@app.route('/api/private_chats')
def api_private_chats():
    if 'username' not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    try:
        username = session['username']
        conn = get_db_connection()
        
        users = conn.execute('SELECT username FROM users WHERE username != ? ORDER BY username', (username,)).fetchall()
        users_list = [user['username'] for user in users]
        
        conn.close()
        
        return jsonify({
            "success": True,
            "users": users_list
        })
    except Exception as e:
        print(f"Ошибка при получении списка пользователей: {e}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": "Произошла ошибка при загрузке списка пользователей"
        }), 500

@app.route('/api/clear_chat', methods=['POST'])
def clear_chat():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    username = session['username']
    partner = data.get('partner')
    
    if not partner:
        return jsonify({"error": "No partner specified"}), 400
    
    print(f"Очистка чата между {username} и {partner}")
    
    try:
        conn = get_db_connection()
        
        if partner == username:
            # Удаляем закладки пользователя
            conn.execute('DELETE FROM favorites WHERE username = ?', (username,))
        else:
            # Помечаем сообщения как удаленные для текущего пользователя
            conn.execute('''
                UPDATE private_messages 
                SET deleted_for_sender = CASE WHEN sender = ? THEN 1 ELSE deleted_for_sender END,
                    deleted_for_receiver = CASE WHEN receiver = ? THEN 1 ELSE deleted_for_receiver END
                WHERE (sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?)
            ''', (username, username, username, partner, partner, username))
        
        conn.commit()
        conn.close()
        
        return jsonify({"success": True})
    except Exception as e:
        print(f"Ошибка при очистке чата: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/reset_stats', methods=['POST'])
def reset_stats():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        # Очищаем таблицу статистики файлов
        conn = get_db_connection()
        conn.execute("DELETE FROM file_stats")
        conn.commit()
        conn.close()
        
        # Удаляем все файлы из папки compressed_uploads
        for filename in os.listdir(app.config['COMPRESSED_UPLOAD_FOLDER']):
            file_path = os.path.join(app.config['COMPRESSED_UPLOAD_FOLDER'], filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Ошибка при удалении файла {file_path}: {e}")
        
        flash("Статистика сжатия и файлы успешно сброшены.", "success")
        return jsonify({"success": True, "message": "Статистика сброшена"})
    except Exception as e:
        print(f"Ошибка при сбросе статистики: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Ошибка при сбросе статистики: {str(e)}"}), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400
    
    # Generate a secure filename with uuid to prevent duplicates
    original_filename = secure_filename(file.filename)
    file_extension = os.path.splitext(original_filename)[1]
    unique_filename = f"{str(uuid.uuid4())}{file_extension}"
    
    # Save original file
    original_path = os.path.join(UPLOAD_FOLDER, unique_filename)
    file.save(original_path)
    
    # Get file size
    file_size = os.path.getsize(original_path)
    file_type = get_file_type(file_extension)
    
    # Compress image files if they are images
    compressed_path = None
    compressed_size = 0
    if file_type == 'image':
        try:
            compressed_filename = f"compressed_{unique_filename}"
            compressed_path = os.path.join(COMPRESSED_UPLOAD_FOLDER, compressed_filename)
            compress_image(original_path, compressed_path)
            if os.path.exists(compressed_path):
                compressed_size = os.path.getsize(compressed_path)
        except Exception as e:
            app.logger.error(f"Error compressing image: {str(e)}")
            compressed_path = None
    
    # Create file stat in database directly with SQL
    user_id = session.get('user_id', 0)  # Default to 0 if no user_id
    compression_type = 'PIL' if file_type == 'image' and compressed_path else ''
    
    # Connect to database
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO file_stats (filename, original_size, compressed_size, compression_type, date_created) VALUES (?, ?, ?, ?, ?)',
            (original_filename, file_size, compressed_size, compression_type, datetime.now().timestamp())
        )
        conn.commit()
        file_id = cursor.lastrowid
    except Exception as e:
        app.logger.error(f"Database error when saving file stats: {str(e)}")
        file_id = 0
    finally:
        conn.close()
    
    # Prepare response data
    file_url = f"/static/uploads/{unique_filename}"
    thumb_url = f"/static/compressed_uploads/compressed_{unique_filename}" if compressed_path else file_url
    
    return jsonify({
        'success': True,
        'file_id': file_id,
        'original_name': original_filename,
        'file_url': file_url,
        'thumbnail_url': thumb_url,
        'file_type': file_type,
        'file_size': file_size,
        'file_size_formatted': format_file_size(file_size)
    })

def get_file_type(extension):
    extension = extension.lower().strip('.')
    if extension in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg']:
        return 'image'
    elif extension in ['mp4', 'webm', 'mkv', 'avi', 'mov']:
        return 'video'
    elif extension in ['mp3', 'wav', 'ogg']:
        return 'audio'
    else:
        return 'document'

def format_file_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

def compress_image(input_path, output_path):
    try:
        img = Image.open(input_path)
        
        # Calculate new dimensions while maintaining aspect ratio
        max_size = (800, 800)
        img.thumbnail(max_size, Image.LANCZOS)
        
        # Save with reduced quality
        img.save(output_path, optimize=True, quality=85)
        
        return True
    except Exception as e:
        app.logger.error(f"Image compression error: {str(e)}")
        return False

def get_mime_type(filename, file_type=None):
    """Determine MIME type based on filename and optional file_type hint"""
    extension = filename.split('.')[-1].lower() if '.' in filename else ''
    
    # Image types
    if extension in ['jpg', 'jpeg']:
        return 'image/jpeg'
    elif extension == 'png':
        return 'image/png'
    elif extension == 'gif':
        return 'image/gif'
    elif extension == 'webp':
        return 'image/webp'
    elif extension == 'svg':
        return 'image/svg+xml'
    
    # Video types
    elif extension == 'mp4':
        return 'video/mp4'
    elif extension == 'webm':
        # If we have a hint that it's audio, return audio MIME type
        if file_type == 'audio':
            return 'audio/webm'
        return 'video/webm'
    elif extension == 'mkv':
        return 'video/x-matroska'
    elif extension == 'avi':
        return 'video/x-msvideo'
    elif extension == 'mov':
        return 'video/quicktime'
    
    # Audio types
    elif extension == 'mp3':
        return 'audio/mpeg'
    elif extension == 'wav':
        return 'audio/wav'
    elif extension == 'ogg':
        return 'audio/ogg'
    elif extension == 'opus':
        return 'audio/opus'
    
    # Document types
    elif extension == 'pdf':
        return 'application/pdf'
    elif extension in ['doc', 'docx']:
        return 'application/msword'
    elif extension == 'txt':
        return 'text/plain'
    
    # Use file_type hint as fallback
    elif file_type == 'image':
        return 'image/jpeg'  # Default image type
    elif file_type == 'video':
        return 'video/mp4'   # Default video type
    elif file_type == 'audio':
        return 'audio/ogg'   # Default audio type
    elif file_type == 'voice':
        return 'audio/webm'  # Default voice recording format
    
    # Default fallback
    else:
        return 'application/octet-stream'

@app.route('/static/compressed_uploads/<filename>')
def serve_compressed_file(filename):
    file_path = os.path.join(app.config['COMPRESSED_UPLOAD_FOLDER'], filename)
    print(f"Запрос на обслуживание сжатого файла: {filename}")
    print(f"Путь к файлу: {file_path}")
    
    if not os.path.exists(file_path):
        print(f"Файл не найден: {file_path}")
        return abort(404)
    
    try:
        with open(file_path, "rb") as f:
            data = f.read()
        
        print(f"Файл прочитан, размер: {len(data)} байт")
        
        # Пытаемся определить тип файла из имени
        file_type = None
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        if ext in ['mp3', 'wav', 'ogg', 'opus', 'webm']:
            file_type = 'audio'
        elif ext == 'webm':
            # webm может быть как аудио, так и видео
            # По умолчанию считаем видео, но это может быть переопределено в коде ниже
            file_type = 'video'
        
        # Проверка на пустые данные
        if not data:
            print("Файл пуст!")
            return "Пустой файл", 400
        
        # Обработка сжатых данных
        if len(data) > 0:
            header = data[0:1]
            payload = data[1:]
            
            if header == b'P':
                # PIL JPEG
                content = payload
                mimetype = 'image/jpeg'
            elif header == b'N':
                # Нейросетевое сжатие изображений
                try:
                    from green_compress_nn import GreenCompressUltraNN
                    compressor = GreenCompressUltraNN()
                    content = compressor.decompress(payload, 'image')
                    mimetype = 'image/png'
                except Exception as e:
                    print(f"Ошибка декомпрессии нейросетевого изображения: {e}")
                    return "Ошибка декомпрессии", 500
            elif header == b'V':
                # Видео, сжатое блочным методом
                try:
                    print("Распаковка блочно-сжатого видео...")
                    if COMPRESSION_MODULES_AVAILABLE:
                        content = decompress_video_blocks(payload)
                        print(f"Успешно распаковано {len(content)} байт блочного видео")
                    else:
                        print("Модуль декомпрессии видео недоступен!")
                        return "Ошибка декомпрессии: модуль недоступен", 500
                except Exception as e:
                    print(f"Ошибка декомпрессии блочного видео: {e}")
                    traceback.print_exc()
                    return "Ошибка декомпрессии видео", 500
                
                # Определяем MIME-тип для видео
                mimetype = get_mime_type(filename, 'video')
            elif header == b'M':
                # MP4 с частичным сжатием метаданных
                try:
                    print("Обработка частично сжатого MP4...")
                    # Восстанавливаем структуру файла MP4
                    
                    # Определяем алгоритм сжатия по первым байтам
                    if len(payload) > 2 and payload[:2] == b'BZ':
                        # BZ2 компрессия
                        import bz2
                        try:
                            header_size = min(len(payload), 262144)  # До 256KB
                            header_compressed = payload[:header_size]
                            body_data = payload[header_size:]
                            header_data = bz2.decompress(header_compressed)
                            content = header_data + body_data
                            print(f"Успешно распаковано частично сжатое MP4 (BZ2), размер: {len(content)} байт")
                        except Exception as e:
                            print(f"Ошибка при распаковке BZ2 метаданных MP4: {e}")
                            content = payload
                    elif len(payload) > 0 and (payload[0] & 0xE0) == 0:
                        # LZMA компрессия (проверка по формату заголовка LZMA)
                        import lzma
                        try:
                            header_size = min(len(payload), 262144)  # До 256KB
                            header_compressed = payload[:header_size]
                            body_data = payload[header_size:]
                            header_data = lzma.decompress(header_compressed)
                            content = header_data + body_data
                            print(f"Успешно распаковано частично сжатое MP4 (LZMA), размер: {len(content)} байт")
                        except Exception as e:
                            print(f"Ошибка при распаковке LZMA метаданных MP4: {e}")
                            content = payload
                    else:
                        # По умолчанию используем zlib
                        header_size = min(len(payload), 262144)  # Увеличили до 256KB
                        header_compressed = payload[:header_size]
                        body_data = payload[header_size:]
                        
                        try:
                            # Распаковываем метаданные
                            header_data = zlib.decompress(header_compressed)
                            # Собираем файл
                            content = header_data + body_data
                            print(f"Успешно распаковано частично сжатое MP4 (ZLIB), размер: {len(content)} байт")
                        except Exception as e:
                            print(f"Ошибка при распаковке метаданных MP4: {e}")
                            # В случае ошибки возвращаем данные как есть
                            content = payload
                except Exception as e:
                    print(f"Ошибка при обработке MP4: {e}")
                    traceback.print_exc()
                    content = payload
                
                # Определяем MIME-тип для MP4
                mimetype = 'video/mp4'
            elif header == b'W':
                # WebM с частичным сжатием метаданных (аналогично MP4)
                try:
                    print("Обработка частично сжатого WebM...")
                    
                    # Определяем алгоритм сжатия по первым байтам
                    if len(payload) > 2 and payload[:2] == b'BZ':
                        # BZ2 компрессия
                        import bz2
                        try:
                            header_size = min(len(payload), 409600)  # До 400KB
                            header_compressed = payload[:header_size]
                            body_data = payload[header_size:]
                            header_data = bz2.decompress(header_compressed)
                            content = header_data + body_data
                            print(f"Успешно распаковано частично сжатое WebM (BZ2), размер: {len(content)} байт")
                        except Exception as e:
                            print(f"Ошибка при распаковке BZ2 метаданных WebM: {e}")
                            content = payload
                    elif len(payload) > 0 and (payload[0] & 0xE0) == 0:
                        # LZMA компрессия
                        import lzma
                        try:
                            header_size = min(len(payload), 409600)  # До 400KB
                            header_compressed = payload[:header_size]
                            body_data = payload[header_size:]
                            header_data = lzma.decompress(header_compressed)
                            content = header_data + body_data
                            print(f"Успешно распаковано частично сжатое WebM (LZMA), размер: {len(content)} байт")
                        except Exception as e:
                            print(f"Ошибка при распаковке LZMA метаданных WebM: {e}")
                            content = payload
                    else:
                        # По умолчанию используем zlib
                        header_size = min(len(payload), 409600)  # До 400KB
                        header_compressed = payload[:header_size]
                        body_data = payload[header_size:]
                        
                        try:
                            # Распаковываем метаданные
                            header_data = zlib.decompress(header_compressed)
                            # Собираем файл
                            content = header_data + body_data
                            print(f"Успешно распаковано частично сжатое WebM (ZLIB), размер: {len(content)} байт")
                        except Exception as e:
                            print(f"Ошибка при распаковке метаданных WebM: {e}")
                            # В случае ошибки возвращаем данные как есть
                            content = payload
                except Exception as e:
                    print(f"Ошибка при обработке WebM: {e}")
                    traceback.print_exc()
                    content = payload
                
                # Определяем MIME-тип для WebM
                mimetype = 'video/webm'
            elif header == b'A':
                # Аудио компрессия (Neural Audio)
                try:
                    # Определяем MIME-тип
                    if '.ogg' in filename.lower():
                        mimetype = 'audio/ogg'
                    elif '.mp3' in filename.lower():
                        mimetype = 'audio/mpeg'
                    elif '.wav' in filename.lower():
                        mimetype = 'audio/wav'
                    elif '.opus' in filename.lower():
                        mimetype = 'audio/opus'
                    elif '.webm' in filename.lower():
                        mimetype = 'audio/webm'
                    else:
                        # По умолчанию для транскодированного аудио используем ogg
                        mimetype = 'audio/ogg'
                    
                    # В упрощенной версии просто возвращаем payload
                    content = payload
                except Exception as e:
                    print(f"Ошибка декомпрессии аудио: {e}")
                    traceback.print_exc()
                    # В случае ошибки возвращаем payload как есть
                    content = payload
                    mimetype = 'audio/ogg'  # Предполагаем, что это ogg
            elif header == b'B':
                # BZ2 сжатие для различных типов файлов
                try:
                    print("Распаковка BZ2 данных...")
                    import bz2
                    content = bz2.decompress(payload)
                    print(f"Успешно распаковано {len(content)} байт (BZ2)")
                except Exception as e:
                    print(f"Ошибка декомпрессии BZ2: {e}")
                    return "Ошибка декомпрессии", 500
                
                # Определяем MIME-тип с помощью нашей вспомогательной функции
                mimetype = get_mime_type(filename, file_type)
            elif header == b'L':
                # LZMA сжатие для различных типов файлов
                try:
                    print("Распаковка LZMA данных...")
                    import lzma
                    content = lzma.decompress(payload)
                    print(f"Успешно распаковано {len(content)} байт (LZMA)")
                except Exception as e:
                    print(f"Ошибка декомпрессии LZMA: {e}")
                    return "Ошибка декомпрессии", 500
                
                # Определяем MIME-тип с помощью нашей вспомогательной функции
                mimetype = get_mime_type(filename, file_type)
            elif header == b'T':
                # Нейросетевое сжатие текста
                try:
                    from green_compress_nn import GreenCompressUltraNN
                    compressor = GreenCompressUltraNN()
                    content = compressor.decompress(payload, 'text')
                    
                    # Определяем MIME-тип по расширению файла
                    ext = filename.split('.')[-1].lower() if '.' in filename else ''
                    if ext in ['txt', 'text']:
                        mimetype = 'text/plain'
                    elif ext == 'pdf':
                        mimetype = 'application/pdf'
                    elif ext in ['doc', 'docx']:
                        mimetype = 'application/msword'
                    else:
                        mimetype = 'application/octet-stream'
                except Exception as e:
                    print(f"Ошибка декомпрессии нейросетевого текста: {e}")
                    return "Ошибка декомпрессии", 500
            elif header == b'Z':
                # ZLIB сжатие
                try:
                    print("Распаковка zlib данных...")
                    content = zlib.decompress(payload)
                    print(f"Успешно распаковано {len(content)} байт (ZLIB)")
                except Exception as e:
                    print(f"Ошибка декомпрессии zlib: {e}")
                    return "Ошибка декомпрессии", 500
                
                # Определяем MIME-тип с помощью нашей вспомогательной функции
                mimetype = get_mime_type(filename, file_type)
            elif header == b'D':
                # Блочное сжатие аудио
                try:
                    print("Распаковка блочно-сжатых данных аудио...")
                    if COMPRESSION_MODULES_AVAILABLE:
                        content = decompress_audio_blocks(payload)
                        print(f"Успешно распаковано {len(content)} байт аудио")
                    else:
                        print("Модуль декомпрессии блоков аудио недоступен!")
                        return "Ошибка декомпрессии: модуль недоступен", 500
                except Exception as e:
                    print(f"Ошибка декомпрессии блоков аудио: {e}")
                    traceback.print_exc()
                    return "Ошибка декомпрессии аудио", 500
                
                # Определяем MIME-тип для аудио
                mimetype = get_mime_type(filename, 'audio')
            elif header == b'O':
                # Оригинал
                content = payload
                
                # Определяем MIME-тип с помощью нашей вспомогательной функции
                mimetype = get_mime_type(filename, file_type)
            else:
                # Нет заголовка, возвращаем как есть
                content = data
                mimetype = 'application/octet-stream'
        else:
            content = data
            mimetype = 'application/octet-stream'
        
        print(f"Отправка файла с MIME-типом: {mimetype}")
        
        return content, 200, {
            'Content-Type': mimetype,
            'Content-Disposition': 'inline',
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'
        }
    except Exception as e:
        print(f"Ошибка при обработке файла: {e}")
        traceback.print_exc()
        return f"Ошибка обработки файла: {str(e)}", 500

@app.route('/compression_stats')
def compression_stats():
    # Проверяем права доступа
    if 'username' not in session:
        return redirect(url_for('login'))

    # Получаем статистику из базы данных
    conn = get_db_connection()
    files = conn.execute("SELECT * FROM file_stats ORDER BY date_created DESC").fetchall()
    conn.close()
    
    # Преобразуем результаты запроса в список словарей
    file_list = []
    total_original_size = 0
    total_compressed_size = 0
    
    for file in files:
        original_size = file['original_size']
        compressed_size = file['compressed_size']
        
        # Вычисляем процент сжатия
        if original_size > 0:
            compression_ratio = ((original_size - compressed_size) / original_size) * 100
        else:
            compression_ratio = 0
        
        # Добавляем информацию о файле
        file_info = {
            'filename': file['filename'],
            'type': file['filename'].split('.')[-1].lower() if '.' in file['filename'] else '',
            'compressed_size': compressed_size,
            'original_size': original_size,
            'compression_type': file['compression_type'],
            'compression_ratio': compression_ratio,
            'date_created': file['date_created']
        }
        file_list.append(file_info)
        
        # Обновляем общую статистику
        total_original_size += original_size
        total_compressed_size += compressed_size
    
    # Вычисляем общий процент сжатия
    if total_original_size > 0:
        total_compression_ratio = ((total_original_size - total_compressed_size) / total_original_size) * 100
    else:
        total_compression_ratio = 0
    
    # Собираем статистику по типам файлов
    file_types = {}
    for file in file_list:
        file_type = file['type']
        if file_type not in file_types:
            file_types[file_type] = {
                'count': 0,
                'original_size': 0,
                'compressed_size': 0
            }
        
        file_types[file_type]['count'] += 1
        file_types[file_type]['original_size'] += file['original_size']
        file_types[file_type]['compressed_size'] += file['compressed_size']
    
    # Вычисляем процент сжатия для каждого типа файлов
    for file_type in file_types:
        if file_types[file_type]['original_size'] > 0:
            file_types[file_type]['compression_ratio'] = ((file_types[file_type]['original_size'] - file_types[file_type]['compressed_size']) / file_types[file_type]['original_size']) * 100
        else:
            file_types[file_type]['compression_ratio'] = 0
    
    # Переводим словарь типов файлов в список для удобства сортировки
    file_types_list = []
    for file_type, stats in file_types.items():
        file_types_list.append({
            'type': file_type,
            'count': stats['count'],
            'original_size': stats['original_size'],
            'compressed_size': stats['compressed_size'],
            'compression_ratio': stats['compression_ratio']
        })
    
    # Сортируем типы файлов по количеству (больше сверху)
    file_types_list.sort(key=lambda x: x['count'], reverse=True)
    
    # Общая статистика
    total_stats = {
        'total_files': len(file_list),
        'total_original_size': total_original_size,
        'total_compressed_size': total_compressed_size,
        'total_compression_ratio': total_compression_ratio,
        'saved_space': total_original_size - total_compressed_size
    }
    
    return render_template('compression_stats.html', 
                          files=file_list, 
                          file_types=file_types_list,
                          total_stats=total_stats)

@app.route('/compression_charts')
def compression_charts():
    # Проверяем права доступа
    if 'username' not in session:
        return redirect(url_for('login'))
    
    return render_template('compression_charts.html')

@app.route('/api/compression_data')
def api_compression_data():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        print("API: Начало получения данных для графиков")
        
        # Получаем данные из базы данных по файлам
        conn = get_db_connection()
        file_results = conn.execute("""
            SELECT filename, original_size, compressed_size, compression_type, 
                CASE 
                    WHEN original_size > 0 THEN (original_size - compressed_size) * 100.0 / original_size 
                    ELSE 0 
                END as compression_ratio,
                date_created
            FROM file_stats
            WHERE original_size > 0
        """).fetchall()
        
        print(f"API: Получено {len(file_results)} записей о файлах")
        
        # Получаем данные о сжатии сообщений
        msg_results = conn.execute("""
            SELECT sender, receiver, length(compressed_message) as compressed_size, 
                timestamp
            FROM private_messages
            WHERE length(compressed_message) > 0
        """).fetchall()
        
        print(f"API: Получено {len(msg_results)} записей о сообщениях")
        
        conn.close()
        
        # Преобразуем в формат для графиков
        data = []
        
        # Обработка данных по файлам
        for row in file_results:
            try:
                # Пропускаем некорректные данные
                if row['original_size'] <= 0 or row['compressed_size'] <= 0:
                    continue
                    
                # Определяем тип данных по расширению
                extension = row['filename'].split('.')[-1] if '.' in row['filename'] else 'unknown'
                data_type = 'unknown'
                if extension.lower() in ['jpg', 'jpeg', 'png', 'gif']:
                    data_type = 'image'
                elif extension.lower() in ['mp3', 'wav', 'ogg', 'opus']:
                    data_type = 'audio'
                elif extension.lower() in ['mp4', 'avi', 'webm']:
                    data_type = 'video'
                else:
                    data_type = 'other'
                
                # Расчет степени сжатия (проверяем деление на ноль)
                compression_ratio = 0
                if row['original_size'] > 0:
                    compression_ratio = (row['original_size'] - row['compressed_size']) * 100.0 / row['original_size']
                    if compression_ratio < 0:  # Защита от отрицательных значений
                        compression_ratio = 0
                
                # Расчет времени обработки на основе размера файла (эмуляция)
                processing_time = max(1, int(row['original_size'] / 1024 * 5))  # 5 мс на каждый КБ данных (условно)
                
                # Добавляем в набор данных
                data.append({
                    "algorithm": row['compression_type'] if row['compression_type'] else "unknown",
                    "dataType": data_type,
                    "dataSize": round(row['original_size'] / 1024, 2),  # КБ
                    "compressionRatio": round(float(compression_ratio), 2),
                    "processingTime": processing_time
                })
            except Exception as e:
                print(f"Ошибка при обработке записи файла: {e}")
                continue
        
        # Обработка данных по сообщениям
        for msg in msg_results:
            try:
                # Проверяем, что есть сжатые данные
                compressed_size = msg['compressed_size']
                if compressed_size <= 0:
                    continue
                    
                # Оцениваем исходный размер - предполагаем, что сжимается в 2.5 раза
                estimated_original_size = compressed_size * 2.5
                
                if estimated_original_size > 0:
                    compression_ratio = ((estimated_original_size - compressed_size) / estimated_original_size) * 100
                    if compression_ratio < 0:  # Защита от отрицательных значений
                        compression_ratio = 0
                    
                    # Добавляем в набор данных
                    data.append({
                        "algorithm": "bwt+mtf+rle+huffman",
                        "dataType": "text",
                        "dataSize": round(estimated_original_size / 1024, 2),  # КБ
                        "compressionRatio": round(compression_ratio, 2),
                        "processingTime": max(1, int(estimated_original_size / 1024 * 3))  # 3 мс на КБ (условно)
                    })
            except Exception as e:
                print(f"Ошибка при обработке записи сообщения: {e}")
                continue
        
        # Проверяем, что есть данные для графиков
        if not data:
            print("API: Нет данных для графиков, возвращаем пустой массив")
            # Добавляем базовые демонстрационные данные, если нет реальных данных
            demo_data = [
                {"algorithm": "bwt+mtf+rle+huffman", "dataType": "text", "dataSize": 10, "compressionRatio": 65, "processingTime": 5},
                {"algorithm": "zlib", "dataType": "text", "dataSize": 10, "compressionRatio": 45, "processingTime": 2}
            ]
            return jsonify({"data": demo_data})
        
        print(f"API: Возвращаем {len(data)} записей для графиков")
        
        # Возвращаем обработанные данные
        return jsonify({"data": data})
    except Exception as e:
        print(f"Ошибка при получении данных для графиков: {e}")
        traceback.print_exc()
        # В случае ошибки возвращаем пустой массив и код ошибки
        return jsonify({"error": str(e), "data": []}), 500

# Маршрут для отладки базы данных сообщений
@app.route('/debug-database')
def debug_database():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM private_messages ORDER BY id DESC LIMIT 20")
    rows = c.fetchall()
    conn.close()
    
    result = "<h1>Последние сообщения в базе данных</h1>"
    result += "<table border='1'><tr><th>ID</th><th>Sender</th><th>Receiver</th><th>Timestamp</th><th>Size</th></tr>"
    
    for row in rows:
        try:
            size = len(row['compressed_message']) if row['compressed_message'] else 0
            result += f"<tr><td>{row['id']}</td><td>{row['sender']}</td><td>{row['receiver']}</td>"
            result += f"<td>{row['timestamp']}</td><td>{size} bytes</td></tr>"
        except Exception as e:
            result += f"<tr><td colspan='5'>Error: {str(e)}</td></tr>"
    
    result += "</table>"
    return result

#########################################
# SocketIO: чаты
#########################################
@socketio.on('connect')
def handle_connect():
    """Обработка нового подключения"""
    try:
        if 'username' not in session:
            print("Соединение без авторизации")
            return
            
        username = session['username']
        print(f"Установлено соединение с пользователем: {username}")
        
        # Автоматически присоединяем пользователя к комнате с его именем
        # для доставки персональных уведомлений
        join_room(username)
        print(f"Пользователь {username} автоматически присоединен к личной комнате")
    except Exception as e:
        print(f"Ошибка при подключении пользователя: {e}")
        traceback.print_exc()

@socketio.on('disconnect')
def handle_disconnect():
    """Обработка отключения клиента"""
    try:
        if 'username' in session:
            username = session['username']
            print(f"Отключение пользователя: {username}")
            leave_room(username)
    except Exception as e:
        print(f"Ошибка при отключении пользователя: {e}")
        traceback.print_exc()

@socketio.on('join_private')
def handle_join_private(data):
    """Присоединение к приватной комнате для чата между двумя пользователями"""
    try:
        if 'username' not in session:
            print("Попытка присоединения к комнате без авторизации")
            emit('error', {'message': 'Требуется авторизация'})
            return
            
        room = data.get('room')
        if not room:
            print("Не указана комната для присоединения")
            emit('error', {'message': 'Не указана комната'})
            return
            
        print(f"Присоединение к комнате: {room}")
        
        # Проверяем формат комнаты
        parts = room.split('_')
        
        # Поддержка нового формата private_user1_user2
        if len(parts) == 3 and parts[0] == 'private':
            user1, user2 = parts[1], parts[2]
        # Поддержка старого формата user1_user2
        elif len(parts) == 2:
            user1, user2 = parts[0], parts[1]
        else:
            print(f"Неверный формат комнаты: {room}")
            emit('error', {'message': 'Неверный формат комнаты'})
            return
            
        # Проверяем, что текущий пользователь входит в комнату
        current_user = session['username']
        if current_user not in [user1, user2]:
            print(f"Ошибка доступа: пользователь {current_user} пытается присоединиться к комнате для {user1} и {user2}")
            emit('error', {'message': 'Доступ запрещен'})
            return
            
        join_room(room)
        print(f"Пользователь {current_user} присоединился к комнате {room}")
        emit('join_success', {'room': room})
    except Exception as e:
        print(f"Ошибка при присоединении к комнате: {e}")
        traceback.print_exc()
        emit('error', {'message': f'Ошибка: {str(e)}'})

@socketio.on('send_private_message')
def handle_send_private_message(data):
    """Обработка отправки приватного сообщения"""
    # Создаем объект ответа для callback-функции
    response_data = {'success': False}
    
    try:
        if 'username' not in session:
            print("Попытка отправки сообщения без авторизации")
            emit('error', {'message': 'Требуется авторизация'})
            response_data['error'] = 'Требуется авторизация'
            return response_data
            
        current_user = session['username']
        room = data.get('room')
        receiver = data.get('receiver')
        message = data.get('message')
        
        print(f"🚀 [SOCKETIO] Получен запрос на отправку сообщения от {current_user} для {receiver} в комнате {room}")
        
        # Проверка наличия всех необходимых данных
        if not room:
            print("Не указана комната для отправки сообщения")
            emit('error', {'message': 'Не указана комната'})
            response_data['error'] = 'Не указана комната'
            return response_data
            
        if not receiver:
            print("Не указан получатель сообщения")
            emit('error', {'message': 'Не указан получатель'})
            response_data['error'] = 'Не указан получатель'
            return response_data
            
        if not message or not message.strip():
            print("Получено пустое сообщение")
            emit('error', {'message': 'Сообщение не может быть пустым'})
            response_data['error'] = 'Сообщение не может быть пустым'
            return response_data
            
        print(f"Получено сообщение от {current_user} для {receiver} в комнате {room}")
        
        # Проверяем, что отправитель соответствует текущему пользователю
        if current_user != session['username']:
            print(f"Несоответствие отправителя: {current_user} vs {session['username']}")
            emit('error', {'message': 'Недопустимый отправитель'})
            response_data['error'] = 'Недопустимый отправитель'
            return response_data
            
        # Проверяем формат комнаты
        parts = room.split('_')
        
        # Поддержка нового формата private_user1_user2
        if len(parts) == 3 and parts[0] == 'private':
            user1, user2 = parts[1], parts[2]
        # Поддержка старого формата user1_user2
        elif len(parts) == 2:
            user1, user2 = parts[0], parts[1]
        else:
            print(f"Неверный формат комнаты: {room}")
            emit('error', {'message': 'Неверный формат комнаты'})
            response_data['error'] = 'Неверный формат комнаты'
            return response_data
        
        # Проверяем, что отправитель и получатель соответствуют комнате
        if sorted([current_user, receiver]) != sorted([user1, user2]):
            print(f"Несоответствие участников комнаты: {current_user}, {receiver} vs {user1}, {user2}")
            emit('error', {'message': 'Ошибка: несоответствие участников комнаты'})
            response_data['error'] = 'Ошибка: несоответствие участников комнаты'
            return response_data
        
        # Сжимаем и сохраняем сообщение в базу данных
        try:
            conn = get_db_connection()
            compressed_msg = compression.compress(message.encode('utf-8'))
            timestamp = time.time()
            
            # Предотвращаем SQL-инъекции с помощью параметризованных запросов
            conn.execute("""
                INSERT INTO private_messages (sender, receiver, timestamp, compressed_message)
                VALUES (?, ?, ?, ?)
            """, (current_user, receiver, timestamp, compressed_msg))
            
            conn.commit()
            
            # Получаем ID нового сообщения для отправки клиенту
            message_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Проверяем существование чата в таблице private_chats
            chat_exists = conn.execute("""
                SELECT id FROM private_chats 
                WHERE (user1 = ? AND user2 = ?) OR (user1 = ? AND user2 = ?)
            """, (current_user, receiver, receiver, current_user)).fetchone()
            
            if not chat_exists:
                # Создаем запись чата, если его нет
                print(f"Создаем новую запись чата между {current_user} и {receiver}")
                conn.execute("""
                    INSERT INTO private_chats (user1, user2, last_message, last_message_timestamp, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (current_user, receiver, compressed_msg, timestamp, timestamp))
                conn.commit()
            else:
                # Обновляем информацию о последнем сообщении в чате
                conn.execute("""
                    UPDATE private_chats
                    SET last_message_timestamp = ?,
                        last_message = ?
                    WHERE (user1 = ? AND user2 = ?) OR (user1 = ? AND user2 = ?)
                """, (timestamp, compressed_msg, current_user, receiver, receiver, current_user))
                conn.commit()
            
            conn.close()
            
            print(f"📝 Сообщение сохранено в БД: от {current_user} для {receiver}, ID: {message_id}")
            
            # Создаем объект данных сообщения
            message_data = {
                'id': message_id,
                'sender': current_user,
                'recipient': receiver,
                'message': message,
                'timestamp': timestamp,
                'room': room  # Добавляем room в данные для клиента
            }
            
            # Отправляем сообщение в комнату
            print(f"📡 Отправка сообщения в комнату {room} через Socket.IO")
            socketio.emit('receive_private_message', message_data, room=room)
            
            # Отправляем сообщение также лично получателю (для уведомлений)
            print(f"📡 Отправка сообщения получателю {receiver} через Socket.IO")
            socketio.emit('receive_private_message', message_data, room=receiver)
            
            print(f"✅ Сообщение успешно отправлено через Socket.IO")
            
            # Отправляем обновление чата обоим пользователям
            chat_update_data = {
                'id': f"private_{current_user}_{receiver}",
                'name': current_user if receiver == session['username'] else receiver,
                'last_message': {
                    'text': message if len(message) < 30 else message[:27] + '...',
                    'timestamp': timestamp,
                    'sender': current_user
                },
                'unread_count': 1 if receiver != session['username'] else 0
            }
            
            socketio.emit('chat_update', chat_update_data, room=current_user)
            socketio.emit('chat_update', chat_update_data, room=receiver)
            
            # Отправляем подтверждение отправителю через callback
            print(f"✅ Сообщение успешно отправлено и обработано: {message_id}")
            
            # Явно добавляем возврат данных для корректной работы callback
            response_data = {'success': True, 'id': message_id, 'timestamp': timestamp}
            return response_data
            
        except sqlite3.Error as db_error:
            error_msg = f"Ошибка базы данных при отправке сообщения: {str(db_error)}"
            print(error_msg)
            traceback.print_exc()
            emit('error', {'message': 'Ошибка сохранения сообщения'})
            response_data['error'] = error_msg
            return response_data
            
    except Exception as e:
        error_msg = f"Общая ошибка при отправке сообщения: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        emit('error', {'message': f'Ошибка при отправке сообщения: {str(e)}'})
        response_data['error'] = error_msg
        return response_data

@socketio.on('send_file_message')
def handle_send_file_message(data):
    """Отправка сообщения с файлом через Socket.IO"""
    # Создаем объект ответа для callback-функции
    response_data = {'success': False}
    
    try:
        if 'username' not in session:
            print("Попытка отправки файла без авторизации")
            emit('error', {'message': 'Требуется авторизация'})
            response_data['error'] = 'Требуется авторизация'
            return response_data
            
        current_user = session['username']
        room = data.get('room')
        receiver = data.get('receiver')
        file_type = data.get('file_type')
        file_url = data.get('file_url')
        
        # Проверка наличия всех необходимых данных
        if not room:
            print("Не указана комната для отправки файла")
            emit('error', {'message': 'Не указана комната'})
            response_data['error'] = 'Не указана комната'
            return response_data
            
        if not receiver:
            print("Не указан получатель файла")
            emit('error', {'message': 'Не указан получатель'})
            response_data['error'] = 'Не указан получатель'  
            return response_data
            
        if not file_type or not file_url:
            print("Не указан тип файла или URL")
            emit('error', {'message': 'Не указан тип файла или URL'})
            response_data['error'] = 'Не указан тип файла или URL'
            return response_data
        
        print(f"Получен файл от {current_user} для {receiver} в комнате {room}: {file_type}")
        
        # Формируем сообщение для файла
        message = f"FILE:{file_type}:{file_url}"
        
        # Добавляем временную метку
        timestamp = time.time()
        
        # Сохраняем сообщение в базу данных
        try:
            conn = get_db_connection()
            compressed_msg = compression.compress(message.encode('utf-8'))
            
            conn.execute("""
                INSERT INTO private_messages (sender, receiver, timestamp, compressed_message)
                VALUES (?, ?, ?, ?)
            """, (current_user, receiver, timestamp, compressed_msg))
            
            conn.commit()
            
            # Получаем ID нового сообщения для отправки клиенту
            message_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Проверяем существование чата в таблице private_chats
            chat_exists = conn.execute("""
                SELECT id FROM private_chats 
                WHERE (user1 = ? AND user2 = ?) OR (user1 = ? AND user2 = ?)
            """, (current_user, receiver, receiver, current_user)).fetchone()
            
            if not chat_exists:
                # Создаем запись чата, если его нет
                print(f"Создаем новую запись чата между {current_user} и {receiver} для файлового сообщения")
                conn.execute("""
                    INSERT INTO private_chats (user1, user2, last_message, last_message_timestamp, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (current_user, receiver, compressed_msg, timestamp, timestamp))
                conn.commit()
            else:
                # Обновляем информацию о последнем сообщении в чате
                conn.execute("""
                    UPDATE private_chats
                    SET last_message_timestamp = ?,
                        last_message = ?
                    WHERE (user1 = ? AND user2 = ?) OR (user1 = ? AND user2 = ?)
                """, (timestamp, compressed_msg, current_user, receiver, receiver, current_user))
                conn.commit()
            
            conn.close()
            
            print(f"Файловое сообщение сохранено в БД: от {current_user} для {receiver}")
            
            # Отправляем файловое сообщение в комнату
            message_data = {
                'id': message_id,
                'sender': current_user,
                'recipient': receiver,
                'message': message,
                'timestamp': timestamp,
                'room': room  # Добавляем room в данные для клиента
            }
            
            # Отправляем сообщение в комнату и получателю
            socketio.emit('receive_private_message', message_data, room=room)
            socketio.emit('receive_private_message', message_data, room=receiver)
            
            # Отправляем обновление для списка чатов
            file_type_display = {
                'image': '🖼️ Изображение',
                'video': '🎬 Видео',
                'audio': '🎵 Аудио',
                'document': '📎 Файл'
            }.get(file_type, '📎 Файл')
            
            chat_update_data = {
                'id': f"private_{current_user}_{receiver}",
                'name': current_user if receiver == session['username'] else receiver,
                'last_message': {
                    'text': file_type_display,
                    'timestamp': timestamp,
                    'sender': current_user
                },
                'unread_count': 1 if receiver != session['username'] else 0
            }
            
            socketio.emit('chat_update', chat_update_data, room=current_user)
            socketio.emit('chat_update', chat_update_data, room=receiver)
            
            print(f"Файловое сообщение отправлено в комнату: {room}")
            
            # Возвращаем успешный ответ для callback-функции
            response_data['success'] = True
            response_data['id'] = message_id
            response_data['timestamp'] = timestamp
            return response_data
            
        except sqlite3.Error as db_error:
            print(f"Ошибка базы данных при отправке файла: {db_error}")
            traceback.print_exc()
            emit('error', {'message': 'Ошибка сохранения файлового сообщения'})
            response_data['error'] = str(db_error)
            return response_data
            
    except Exception as e:
        print(f"Общая ошибка при отправке файлового сообщения: {e}")
        traceback.print_exc()
        emit('error', {'message': f'Ошибка при отправке файла: {str(e)}'})
        response_data['error'] = str(e)
        return response_data

@socketio.on('load_private_history')
def handle_load_private_history(data):
    try:
        room = data.get('room')
        page = data.get('page', 0)  # Страница запроса (0 - последние сообщения)
        messages_per_page = 20      # Количество сообщений на странице
        
        print(f"Загрузка истории для комнаты: {room}, страница: {page}")
        
        if not room:
            print("Ошибка: не указана комната для загрузки истории")
            emit('load_private_history', {'messages': [], 'error': 'Не указана комната'})
            return
        
        parts = room.split('_')
        
        # Поддержка нового формата private_user1_user2
        if len(parts) == 3 and parts[0] == 'private':
            user1, user2 = parts[1], parts[2]
        # Поддержка старого формата user1_user2
        elif len(parts) == 2:
            user1, user2 = parts[0], parts[1]
        else:
            print(f"Неверный формат комнаты: {room}")
            emit('load_private_history', {'messages': [], 'error': 'Неверный формат комнаты'})
            return
        
        # Проверяем, что пользователь авторизован и запрашивает только свои сообщения
        current_user = session.get('username')
        if not current_user:
            print("Ошибка: пользователь не авторизован")
            emit('load_private_history', {'messages': [], 'error': 'Требуется авторизация'})
            return
            
        if current_user not in [user1, user2]:
            print(f"Ошибка доступа: пользователь {current_user} пытается получить сообщения для {user1} и {user2}")
            emit('load_private_history', {'messages': [], 'error': 'Доступ запрещен'})
            return
        
        conn = None
        try:
            conn = get_db_connection()
            c = conn.cursor()
            print(f"Запрос истории для пользователей {user1} и {user2}")
            
            # Проверяем существование чата в таблице private_chats
            chat_exists = c.execute("""
                SELECT id FROM private_chats 
                WHERE (user1 = ? AND user2 = ?) OR (user1 = ? AND user2 = ?)
            """, (user1, user2, user2, user1)).fetchone()
            
            if not chat_exists:
                # Создаем запись чата, если его нет
                print(f"Создаем новую запись чата между {user1} и {user2} при загрузке истории")
                current_time = time.time()
                c.execute("""
                    INSERT INTO private_chats (user1, user2, created_at)
                    VALUES (?, ?, ?)
                """, (user1, user2, current_time))
                conn.commit()
            
            # Сначала получаем общее количество сообщений
            c.execute("""
                SELECT COUNT(*) as count 
                FROM private_messages
                WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)
            """, (user1, user2, user2, user1))
            
            result = c.fetchone()
            if not result:
                print("Ошибка: не удалось получить количество сообщений")
                emit('load_private_history', {'messages': [], 'error': 'Ошибка базы данных'})
                return
                
            total_count = result['count']
            offset = page * messages_per_page
            
            # Получаем сообщения для текущей страницы
            c.execute("""
                SELECT id, sender, receiver, timestamp, compressed_message, read
                FROM private_messages
                WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """, (user1, user2, user2, user1, messages_per_page, offset))
            
            rows = c.fetchall()
            
            print(f"Найдено {len(rows)} из {total_count} сообщений для страницы {page}")
            
            # Mark messages as read if current user is the receiver
            unread_msg_ids = []
            for row in rows:
                if row['receiver'] == current_user and row['read'] == 0:
                    unread_msg_ids.append(row['id'])
            
            if unread_msg_ids:
                # Mark messages as read in a single batch update
                placeholders = ','.join(['?'] * len(unread_msg_ids))
                c.execute(f"UPDATE private_messages SET read = 1 WHERE id IN ({placeholders})", unread_msg_ids)
                conn.commit()
                print(f"Отмечено прочитанными {len(unread_msg_ids)} сообщений")
            
            # Форматируем результаты для клиента, декомпрессируя сообщения
            messages = []
            
            # Отладочная информация
            print(f"Обработка {len(rows)} сообщений из базы данных")
            
            for row in rows:
                try:
                    # Проверяем, что compressed_message не равен None
                    if row['compressed_message'] is None:
                        print(f"ОШИБКА: compressed_message равен None для сообщения с ID {row['id']}")
                        # Добавляем заглушку вместо null-сообщения
                        messages.append({
                            'id': row['id'],
                            'sender': row['sender'],
                            'recipient': row['receiver'],
                            'message': '[Сообщение недоступно]',
                            'timestamp': row['timestamp'],
                            'read': bool(row['read']),
                            'room': room
                        })
                        continue
                    
                    decompressed_msg = compression.decompress(row['compressed_message']).decode('utf-8')
                    
                    # Добавляем сообщение в список
                    message_obj = {
                        'id': row['id'],
                        'sender': row['sender'],
                        'recipient': row['receiver'],
                        'message': decompressed_msg,
                        'timestamp': row['timestamp'],
                        'read': bool(row['read']),
                        'room': room  # Добавляем room в данные сообщения
                    }
                    
                    messages.append(message_obj)
                    
                except Exception as e:
                    print(f"Ошибка при декомпрессии сообщения {row['id']}: {e}")
                    traceback.print_exc()
                    
                    # В случае ошибки декомпрессии добавляем сообщение с текстом ошибки
                    messages.append({
                        'id': row['id'],
                        'sender': row['sender'],
                        'recipient': row['receiver'],
                        'message': f'[Ошибка декомпрессии: {str(e)}]',
                        'timestamp': row['timestamp'],
                        'read': bool(row['read']),
                        'room': room
                    })
            
            # Sort messages by timestamp in ascending order (oldest first)
            messages.sort(key=lambda m: m['timestamp'])
            
            # Сохраняем количество сообщений после обработки
            processed_count = len(messages)
            print(f"Успешно обработано {processed_count} из {len(rows)} сообщений")
            
            has_more = total_count > (offset + messages_per_page)
            
            print(f"Отправляем {len(messages)} сообщений для страницы {page}, есть еще: {has_more}")
            emit('load_private_history', {
                'messages': messages,
                'page': page,
                'has_more': has_more,
                'total_count': total_count
            })
        except sqlite3.Error as db_error:
            print(f"Ошибка базы данных при загрузке истории: {db_error}")
            traceback.print_exc()
            emit('load_private_history', {'messages': [], 'error': f'Ошибка базы данных: {str(db_error)}'})
        finally:
            if conn:
                conn.close()
            
    except Exception as e:
        print(f"Общая ошибка при загрузке истории сообщений: {e}")
        traceback.print_exc()
        # Отправляем пустой массив сообщений, чтобы клиент мог обработать ошибку
        emit('load_private_history', {'messages': [], 'error': f'Ошибка при загрузке истории: {str(e)}'})

@socketio.on('clear_chat')
def handle_clear_chat(data):
    if 'username' not in session:
        print("Ошибка: пользователь не авторизован")
        return
    
    room = data.get('room')
    partner = data.get('partner')
    cleared_by = session.get('username', 'Неизвестный пользователь')
    
    print(f"Очистка чата в комнате {room} с партнером {partner}, инициатор: {cleared_by}")
    
    # Отправляем уведомление всем участникам комнаты
    socketio.emit('chat_cleared', {
        'cleared_by': cleared_by, 
        'timestamp': time.time()
    }, room=room)

@socketio.on('typing')
def handle_typing(data):
    room = data.get('room')
    user = data.get('user')
    socketio.emit('someone_typing', {'user': user}, room=room)

@socketio.on('stop_typing')
def handle_stop_typing(data):
    """Обработка события, когда пользователь перестает печатать"""
    room = data.get('room')
    user = session.get('username')
    
    if not room or not user:
        return
    
    emit('someone_stopped_typing', {'user': user}, room=room)
    print(f"Stop typing event: {user} в комнате {room}")

@socketio.on('read_message')
def handle_read_message(data):
    """Обработка события прочтения сообщения"""
    if 'username' not in session:
        print("Ошибка: пользователь не авторизован при попытке отметить сообщение как прочитанное")
        return
    
    current_user = session['username']
    room = data.get('room')
    message_id = data.get('message_id')
    
    if not room or not message_id:
        print(f"Ошибка: отсутствуют данные для отметки прочтения сообщения. room={room}, message_id={message_id}")
        return
    
    print(f"Отметка прочтения сообщения {message_id} пользователем {current_user} в комнате {room}")
    
    try:
        conn = get_db_connection()
        
        # Проверяем, имеет ли пользователь право отмечать это сообщение как прочитанное
        message = conn.execute("""
            SELECT sender, receiver FROM private_messages WHERE id = ?
        """, (message_id,)).fetchone()
        
        if not message:
            print(f"Ошибка: сообщение с ID {message_id} не найдено")
            conn.close()
            return
        
        # Убедимся, что текущий пользователь - получатель сообщения
        if message['receiver'] != current_user:
            print(f"Ошибка: пользователь {current_user} пытается отметить как прочитанное сообщение, где получатель {message['receiver']}")
            conn.close()
            return
        
        # Отмечаем сообщение как прочитанное
        conn.execute("""
            UPDATE private_messages SET read = 1 WHERE id = ? AND receiver = ? AND read = 0
        """, (message_id, current_user))
        conn.commit()
        
        # Получаем количество обновленных строк для логирования
        updated_count = conn.total_changes
        
        if updated_count > 0:
            print(f"Сообщение {message_id} успешно отмечено как прочитанное")
            
            # Отправляем уведомление отправителю о прочтении
            socketio.emit('message_read', {
                'message_id': message_id,
                'read_by': current_user,
                'room': room
            }, room=message['sender'])
            
            # Получаем количество непрочитанных сообщений от отправителя к получателю
            unread_count = conn.execute("""
                SELECT COUNT(*) as count FROM private_messages 
                WHERE sender = ? AND receiver = ? AND read = 0
            """, (message['sender'], current_user)).fetchone()['count']
            
            # Определяем участников комнаты
            participants = room.replace('private_', '').split('_')
            if len(participants) != 2:
                print(f"Предупреждение: неверный формат комнаты {room}")
                participants = [message['sender'], current_user]
            
            # Обновляем чат для обоих пользователей
            chat_update_data = {
                'id': room,
                'partner': message['sender'] if current_user == message['receiver'] else message['receiver'],
                'unread_count': unread_count
            }
            
            # Получаем последнее сообщение для обновления чата
            last_message = conn.execute("""
                SELECT sender, compressed_message, timestamp 
                FROM private_messages 
                WHERE (sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?)
                ORDER BY timestamp DESC LIMIT 1
            """, (participants[0], participants[1], participants[1], participants[0])).fetchone()
            
            if last_message:
                try:
                    # Декомпрессируем сообщение
                    last_message_text = compression.decompress(last_message['compressed_message']).decode('utf-8')
                    
                    # Ограничиваем длину для отображения
                    if len(last_message_text) > 30:
                        last_message_text = last_message_text[:27] + '...'
                    
                    # Добавляем информацию о последнем сообщении
                    chat_update_data['last_message'] = {
                        'text': last_message_text,
                        'timestamp': last_message['timestamp'],
                        'sender': last_message['sender']
                    }
                except Exception as e:
                    print(f"Ошибка при декомпрессии последнего сообщения: {e}")
            
            # Отправляем обновление обоим пользователям
            for participant in participants:
                # Подготавливаем данные для каждого пользователя
                user_data = chat_update_data.copy()
                
                # Правильный партнер для каждого участника
                if participant == participants[0]:
                    user_data['partner'] = participants[1]
                else:
                    user_data['partner'] = participants[0]
                
                # Определяем количество непрочитанных для каждого участника
                if participant == current_user:
                    # Текущий пользователь только что прочитал все сообщения
                    user_data['unread_count'] = 0
                else:
                    # Для другого пользователя количество непрочитанных не изменилось
                    other_unread_count = conn.execute("""
                        SELECT COUNT(*) as count FROM private_messages 
                        WHERE sender = ? AND receiver = ? AND read = 0
                    """, (current_user, participant)).fetchone()['count']
                    user_data['unread_count'] = other_unread_count
                
                # Отправляем обновление
                print(f"Отправка обновления чата для {participant}: {user_data}")
                socketio.emit('chat_update', user_data, room=participant)
        
        conn.close()
    except Exception as e:
        print(f"Ошибка при отметке сообщения как прочитанное: {e}")
        traceback.print_exc()

@app.route('/api/cleanup_db', methods=['POST'])
def cleanup_db():
    """Очистка базы данных от некорректных записей (NULL сообщения)"""
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        conn = get_db_connection()
        
        # Находим сообщения с NULL отправителем или получателем
        c = conn.cursor()
        c.execute('SELECT COUNT(*) as count FROM private_messages WHERE sender IS NULL OR receiver IS NULL')
        null_count = c.fetchone()['count']
        
        # Удаляем сообщения с NULL отправителем или получателем
        if null_count > 0:
            c.execute('DELETE FROM private_messages WHERE sender IS NULL OR receiver IS NULL')
            conn.commit()
            print(f"Удалено {null_count} сообщений с NULL отправителем или получателем")
        
        conn.close()
        
        return jsonify({
            "success": True,
            "deleted_count": null_count,
            "message": f"Удалено {null_count} некорректных сообщений из базы данных"
        })
    except Exception as e:
        print(f"Ошибка при очистке базы данных: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Ошибка сервера: {str(e)}"}), 500

@app.route('/debug_profile')
def debug_profile():
    if 'username' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    try:
        username = session['username']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Get all field names from the user record
        field_names = user.keys()
        print(f"Поля в записи пользователя: {', '.join(field_names)}")
        
        # Convert the user row to a dictionary
        user_dict = {}
        for key in field_names:
            try:
                user_dict[key] = user[key]
            except Exception as e:
                user_dict[key] = f"<Error: {str(e)}>"
        
        # Add the avatar URL that would be used
        user_dict["processed_avatar_url"] = url_for('static', filename='img/default-avatar.png')
        user_dict["avatar_status"] = "using default"
        
        # Check if avatar_url exists and is valid
        if 'avatar_url' in field_names and user['avatar_url'] is not None:
            avatar_url = user['avatar_url']
            if isinstance(avatar_url, str) and avatar_url.strip():
                if avatar_url.startswith('/static/'):
                    user_dict['processed_avatar_url'] = avatar_url
                    user_dict["avatar_status"] = "absolute path"
                else:
                    user_dict['processed_avatar_url'] = url_for('static', filename=avatar_url.replace('static/', ''))
                    user_dict["avatar_status"] = "relative path"
        
        return jsonify({
            "success": True,
            "user": user_dict,
            "route_info": {
                "route": "edit_profile",
                "method": "GET",
                "template": "edit_profile.html"
            }
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/api/debug/create_test_user', methods=['GET'])
def create_test_user():
    try:
        # Создаем тестового пользователя с известными учетными данными
        username = "test_debug_user"
        password = "test_password"
        name = "Test Debug User"
        last_name = "Test Last Name"
        email = "test_debug@example.com"
        birthdate = "2000-01-01"
        city = "Test City"
        bio = "This is a test user bio created for debugging purposes"
        
        conn = get_db_connection()
        
        # Проверяем, существует ли уже такой пользователь
        existing_user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if existing_user:
            # Если пользователь уже существует, обновляем его данные
            conn.execute('''
                UPDATE users 
                SET name = ?, last_name = ?, email = ?, password = ?, birthdate = ?, city = ?, bio = ?
                WHERE username = ?
            ''', (name, last_name, email, password, birthdate, city, bio, username))
            conn.commit()
            user_info = {
                "username": username,
                "password": password,
                "name": name,
                "last_name": last_name,
                "email": email,
                "birthdate": birthdate,
                "city": city,
                "bio": bio
            }
            return jsonify({
                "success": True,
                "message": "Test user updated with all fields",
                "user": user_info
            })
        
        # Создаем нового пользователя
        conn.execute('''
            INSERT INTO users (name, username, email, password, last_name, birthdate, city, bio) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, username, email, password, last_name, birthdate, city, bio))
        conn.commit()
        conn.close()
        
        user_info = {
            "username": username,
            "password": password,
            "name": name,
            "last_name": last_name,
            "email": email,
            "birthdate": birthdate,
            "city": city,
            "bio": bio
        }
        
        return jsonify({
            "success": True,
            "message": "Test user created successfully with all fields",
            "user": user_info
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

@app.route('/api/file_stats')
def api_file_stats():
    # Код для API статистики файлов
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Требуется авторизация'})
    
    try:
        conn = get_db_connection()
        stats = conn.execute('SELECT * FROM file_stats ORDER BY date_created DESC').fetchall()
        conn.close()
        
        result = []
        for stat in stats:
            result.append({
                'id': stat['id'],
                'filename': stat['filename'],
                'original_size': stat['original_size'],
                'compressed_size': stat['compressed_size'],
                'compression_type': stat['compression_type'],
                'date_created': stat['date_created']
            })
        
        return jsonify({'success': True, 'stats': result})
    except Exception as e:
        print(f"Ошибка при получении статистики файлов: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/chats', methods=['GET'])
def api_chats():
    try:
        if 'username' not in session:
            return jsonify({'error': 'Unauthorized'}), 401

        username = session['username']
        error_message = None

        try:
            conn = get_db_connection()
            try:
                c = conn.cursor()
                
                # Проверяем наличие записей в таблице private_chats
                c.execute("""
                SELECT COUNT(*) as count FROM private_chats 
                WHERE user1 = ? OR user2 = ?
                """, (username, username))
                
                chat_count = c.fetchone()['count']
                
                # Если чатов нет, создаем их на основе сообщений
                if chat_count == 0:
                    print(f"Чаты для пользователя {username} не найдены, создаем на основе сообщений")
                    c.execute("""
                    SELECT DISTINCT 
                        CASE 
                            WHEN sender = ? THEN receiver 
                            ELSE sender 
                        END as partner,
                        MAX(timestamp) as last_timestamp
                    FROM private_messages
                    WHERE sender = ? OR receiver = ?
                    GROUP BY partner
                    """, (username, username, username))
                    
                    partners = c.fetchall()
                    
                    for partner_row in partners:
                        partner = partner_row['partner']
                        if partner:
                            # Получаем последнее сообщение
                            c.execute("""
                            SELECT sender, compressed_message, timestamp
                            FROM private_messages
                            WHERE ((sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?))
                                  AND timestamp = ?
                            LIMIT 1
                            """, (username, partner, partner, username, partner_row['last_timestamp']))
                            
                            last_msg = c.fetchone()
                            
                            if last_msg:
                                print(f"Создаем чат между {username} и {partner}")
                                c.execute("""
                                INSERT INTO private_chats (user1, user2, last_message, last_message_timestamp, created_at)
                                VALUES (?, ?, ?, ?, ?)
                                """, (username, partner, last_msg['compressed_message'], last_msg['timestamp'], last_msg['timestamp']))
                                conn.commit()
                            else:
                                print(f"Ошибка: не найдено последнее сообщение для {username} и {partner}")
                
                # Получаем самые последние сообщения для каждого чата
                c.execute("""
                WITH LastMessages AS (
                    SELECT 
                        sender,
                        receiver,
                        compressed_message,
                        timestamp,
                        read,
                        ROW_NUMBER() OVER (
                            PARTITION BY 
                                CASE 
                                    WHEN sender < receiver THEN sender || '_' || receiver
                                    ELSE receiver || '_' || sender
                                END 
                            ORDER BY timestamp DESC
                        ) as rn
                    FROM private_messages
                    WHERE sender = ? OR receiver = ?
                )
                SELECT 
                    sender, 
                    receiver, 
                    compressed_message,
                    timestamp,
                    read
                FROM LastMessages
                WHERE rn = 1
                ORDER BY timestamp DESC
                """, (username, username))
                
                rows = c.fetchall()
                
                # Получаем список всех непрочитанных сообщений для подсчета
                c.execute("""
                SELECT 
                    sender,
                    COUNT(*) as unread_count
                FROM private_messages
                WHERE receiver = ? AND read = 0
                GROUP BY sender
                """, (username,))
                
                unread_counts = {row['sender']: row['unread_count'] for row in c.fetchall()}
                
                # Получаем информацию о пользователях
                user_ids = set()
                for row in rows:
                    if row['sender'] != username:
                        user_ids.add(row['sender'])
                    if row['receiver'] != username:
                        user_ids.add(row['receiver'])
                
                user_info = {}
                if user_ids:
                    user_list = list(user_ids)
                    placeholders = ','.join(['?'] * len(user_list))
                    c.execute(f"""
                    SELECT id, username, name as display_name, avatar_url
                    FROM users
                    WHERE username IN ({placeholders})
                    """, user_list)
                    
                    user_rows = c.fetchall()
                    user_info = {row['username']: {
                        'id': row['id'],
                        'username': row['username'],
                        'display_name': row['display_name'] or row['username'],
                        'avatar_url': row['avatar_url'] or '/static/img/default-avatar.png'
                    } for row in user_rows}
                
                # Формируем список чатов
                chats = []
                for row in rows:
                    try:
                        other_user = row['receiver'] if row['sender'] == username else row['sender']
                        
                        # Проверяем, что other_user не None
                        if other_user is None:
                            print(f"Пропускаем чат с null пользователем для {username}")
                            continue
                            
                        chat_id = f"private_{username}_{other_user}" if username < other_user else f"private_{other_user}_{username}"
                        
                        # Get basic message data that will always work
                        last_message_data = {
                            'sender': row['sender'],
                            'timestamp': row['timestamp'],
                            'text': '[Сообщение недоступно]'  # Default fallback text
                        }
                        
                        comp = row['compressed_message']
                        if comp:
                            try:
                                if isinstance(comp, bytes):
                                    msg_bytes = compression.decompress(comp)
                                    last_message_data['text'] = msg_bytes.decode('utf-8', errors='replace')
                                else:
                                    print(f"Ошибка: сжатое сообщение не в формате bytes: {type(comp)}")
                            except Exception as decomp_error:
                                print(f"Ошибка декомпрессии сообщения в списке чатов: {decomp_error}")
                                error_message = "Ошибка декомпрессии некоторых сообщений. Отображается текст по умолчанию."
                                # Keep the default fallback text
                        else:
                            last_message_data['text'] = '[Пустое сообщение]'
                        
                        chat = {
                            'id': chat_id,
                            'type': 'private',
                            'partner': other_user,
                            'name': other_user,
                            'user': user_info.get(other_user, {
                                'username': other_user,
                                'display_name': other_user,
                                'avatar_url': '/static/img/default-avatar.png'
                            }),
                            'last_message': last_message_data,
                            'unread_count': unread_counts.get(other_user, 0),
                            'is_favorite': False,
                            'is_blocked': False,
                            'status': 'offline'
                        }
                        
                        chats.append(chat)
                    except Exception as chat_error:
                        print(f"Ошибка обработки чата: {chat_error}")
                        error_message = "Ошибка обработки некоторых чатов."
                        # Continue processing other chats even if one fails
                
                response = {
                    'success': True,
                    'chats': chats,
                    'count': len(chats)
                }
                
                if error_message:
                    response['error_message'] = error_message
                
                return jsonify(response)
                
            finally:
                conn.close()
                
        except sqlite3.Error as db_error:
            print(f"Ошибка базы данных при получении списка чатов: {db_error}")
            traceback.print_exc()
            return jsonify({
                'success': True,
                'error_message': f'Ошибка базы данных: {str(db_error)}',
                'chats': [],
                'count': 0
            })
            
    except Exception as e:
        print(f"Общая ошибка при получении списка чатов: {e}")
        traceback.print_exc()
        return jsonify({
            'success': True,
            'error_message': f'Ошибка сервера: {str(e)}',
            'chats': [],
            'count': 0
        })

@app.route('/api/user')
def api_user():
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Требуется авторизация'})
    
    username = session['username']
    
    try:
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
        
        # Обновляем время последнего посещения
        last_seen = time.time()
        conn = get_db_connection()
        conn.execute('UPDATE users SET last_seen = ?, status = ? WHERE username = ?', 
                     (last_seen, 'online', username))
        conn.commit()
        conn.close()
        
        user_data = {
            'id': user['id'],
            'username': user['username'],
            'name': user['name'],
            'last_name': user['last_name'],
            'email': user['email'],
            'avatar_url': user['avatar_url'],
            'birthdate': user['birthdate'],
            'city': user['city'],
            'bio': user['bio'],
            'status': 'online',
            'last_seen': last_seen
        }
        
        return jsonify({'success': True, 'user': user_data})
        
    except Exception as e:
        print(f"Ошибка при получении данных пользователя: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/update_user_status', methods=['POST'])
def update_user_status():
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Требуется авторизация'})
    
    username = session['username']
    status = request.json.get('status', 'online')
    
    try:
        conn = get_db_connection()
        conn.execute('UPDATE users SET status = ?, last_seen = ? WHERE username = ?', 
                     (status, time.time(), username))
        conn.commit()
        conn.close()
        
        # Оповещаем пользователей о смене статуса через сокеты
        socketio.emit('user_status_changed', {
            'username': username,
            'status': status,
            'last_seen': time.time()
        })
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Ошибка при обновлении статуса пользователя: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/mark_messages_read', methods=['POST'])
def mark_messages_read():
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Требуется авторизация'})
    
    current_user = session['username']
    sender = request.json.get('sender')
    
    if not sender:
        return jsonify({'success': False, 'error': 'Отсутствует отправитель'})
    
    try:
        conn = get_db_connection()
        conn.execute('''
            UPDATE private_messages 
            SET read = 1 
            WHERE sender = ? AND receiver = ? AND read = 0
        ''', (sender, current_user))
        conn.commit()
        
        # Получаем количество обновленных строк
        updated_count = conn.total_changes
        conn.close()
        
        return jsonify({'success': True, 'updated': updated_count})
        
    except Exception as e:
        print(f"Ошибка при отметке сообщений как прочитанных: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/delete_message', methods=['POST'])
def delete_message():
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Требуется авторизация'})
    
    current_user = session['username']
    message_id = request.json.get('message_id')
    delete_for = request.json.get('delete_for', 'self')  # self, everyone
    
    if not message_id:
        return jsonify({'success': False, 'error': 'Отсутствует ID сообщения'})
    
    try:
        conn = get_db_connection()
        
        # Проверяем, существует ли сообщение и имеет ли пользователь право его удалять
        message = conn.execute('''
            SELECT sender, receiver FROM private_messages WHERE id = ?
        ''', (message_id,)).fetchone()
        
        if not message:
            return jsonify({'success': False, 'error': 'Сообщение не найдено'})
        
        # Проверяем, является ли пользователь отправителем или получателем
        if message['sender'] != current_user and message['receiver'] != current_user:
            return jsonify({'success': False, 'error': 'У вас нет прав для удаления этого сообщения'})
        
        if delete_for == 'everyone' and message['sender'] == current_user:
            # Если пользователь является отправителем и хочет удалить для всех
            conn.execute('''
                UPDATE private_messages 
                SET deleted_for_sender = 1, deleted_for_receiver = 1 
                WHERE id = ?
            ''', (message_id,))
        elif delete_for == 'self' and message['sender'] == current_user:
            # Если пользователь является отправителем и хочет удалить только у себя
            conn.execute('''
                UPDATE private_messages 
                SET deleted_for_sender = 1 
                WHERE id = ?
            ''', (message_id,))
        elif delete_for == 'self' and message['receiver'] == current_user:
            # Если пользователь является получателем и хочет удалить у себя
            conn.execute('''
                UPDATE private_messages 
                SET deleted_for_receiver = 1 
                WHERE id = ?
            ''', (message_id,))
        else:
            return jsonify({'success': False, 'error': 'Недопустимый параметр delete_for'})
        
        conn.commit()
        conn.close()
        
        # Оповещаем пользователей об удалении сообщения через сокеты
        if delete_for == 'everyone':
            room = f"{message['sender']}_{message['receiver']}"
            if message['sender'] > message['receiver']:
                room = f"{message['receiver']}_{message['sender']}"
                
            socketio.emit('message_deleted', {
                'message_id': message_id,
                'deleted_by': current_user
            }, room=room)
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Ошибка при удалении сообщения: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/search_users', methods=['GET', 'POST'])
def api_search_users():
    if 'username' not in session:
        return jsonify({"success": False, "error": "Требуется авторизация"})
    
    try:
        query = request.args.get('query') if request.method == 'GET' else request.form.get('query', '')
        
        if not query:
            return jsonify({"success": False, "error": "Не указан поисковый запрос"})
        
        conn = get_db_connection()
        results = conn.execute(
            "SELECT username, name, avatar_url, status FROM users WHERE (username LIKE ? OR name LIKE ?) AND username != ?",
            (f'%{query}%', f'%{query}%', session['username'])
        ).fetchall()
        conn.close()
        
        users = []
        for user in results:
            avatar_url = user['avatar_url'] if user['avatar_url'] else '/static/img/default-avatar.png'
            users.append({
                'username': user['username'],
                'name': user['name'] if user['name'] else user['username'],
                'avatar_url': avatar_url,
                'status': user['status'] if user['status'] else 'offline'
            })
        
        return jsonify({"success": True, "users": users})
    except Exception as e:
        print(f"Ошибка при поиске пользователей: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/message_compression_info/<int:message_id>', methods=['GET'])
def get_message_compression_info(message_id):
    """API для получения информации о сжатии конкретного сообщения"""
    if 'username' not in session:
        return jsonify({"success": False, "error": "Требуется авторизация"})
    
    current_user = session['username']
    
    try:
        conn = get_db_connection()
        
        # Проверяем, имеет ли пользователь право просматривать это сообщение
        message = conn.execute("""
            SELECT id, sender, receiver, timestamp, compressed_message 
            FROM private_messages 
            WHERE id = ? AND (sender = ? OR receiver = ?)
        """, (message_id, current_user, current_user)).fetchone()
        
        if not message:
            return jsonify({"success": False, "error": "Сообщение не найдено или нет доступа"})
        
        # Получаем размер сжатого сообщения
        compressed_size = len(message['compressed_message'])
        
        # Декомпрессируем сообщение для получения исходного размера
        decompressed_msg = compression.decompress(message['compressed_message'])
        original_size = len(decompressed_msg)
        
        # Вычисляем соотношение сжатия
        compression_ratio = 0
        if original_size > 0:
            compression_ratio = ((original_size - compressed_size) / original_size) * 100
        
        # Формируем и возвращаем результат
        result = {
            "success": True,
            "message_id": message_id,
            "original_size": original_size,
            "compressed_size": compressed_size,
            "compression_ratio": round(compression_ratio, 2),
            "compression_method": "BWT+MTF+RLE+Huffman" if message['compressed_message'][0] == 1 else "MTF+RLE+Huffman",
            "timestamp": message['timestamp'],
            "sender": message['sender'],
            "text": decompressed_msg.decode('utf-8')[:100] + ('...' if len(decompressed_msg) > 100 else '')
        }
        
        conn.close()
        return jsonify(result)
        
    except Exception as e:
        print(f"Ошибка при получении информации о сжатии сообщения: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    socketio.run(app, debug=True)