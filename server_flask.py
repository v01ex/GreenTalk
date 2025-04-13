import os
import uuid
import time
import sqlite3
import traceback
import shutil  # Для сброса статистики (удаления файлов)
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort
from flask_socketio import SocketIO, emit, join_room
from werkzeug.utils import secure_filename
import compression  # Использует ваш compression.py для текстов
from PIL import Image
import io
import zlib

# Импортируем новые модули сжатия
try:
    from video_compression import compress_video, decompress_video_blocks
    from audio_compression import compress_audio, decompress_audio_blocks
    COMPRESSION_MODULES_AVAILABLE = True
    print("Модули сжатия видео и аудио успешно загружены")
except ImportError as e:
    COMPRESSION_MODULES_AVAILABLE = False
    print(f"Внимание: модули сжатия не загружены: {e}")

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
            password TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS private_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT,
            receiver TEXT,
            timestamp REAL,
            compressed_message BLOB
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
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    if 'username' in session:
        # Если пользователь авторизован, показываем главную страницу
        return render_template('home.html')
    # Иначе отправляем на страницу входа
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('private_chats'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()
        if user:
            session['username'] = username
            return redirect(url_for('private_chats'))
        else:
            flash('Неверное имя пользователя или пароль', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'username' in session:
        return redirect(url_for('private_chats'))
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
            return redirect(url_for('private_chats'))
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
    return render_template('private_chats.html', username=session['username'])

@app.route('/favorites')
def favorites():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('favorites.html', username=session['username'])

@app.route('/api/private_chats')
def api_private_chats():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    username = session['username']
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        SELECT 
            CASE WHEN sender = ? THEN receiver ELSE sender END AS partner,
            MAX(timestamp) as last_ts
        FROM private_messages
        WHERE sender = ? OR receiver = ?
        GROUP BY partner
        ORDER BY last_ts DESC
    ''', (username, username, username))
    chats = c.fetchall()
    conn.close()
    chat_list = []
    for chat in chats:
        partner = chat["partner"]
        last_ts = chat["last_ts"]
        label = "Избранное" if partner == username else partner
        chat_list.append({"partner": partner, "last_ts": last_ts, "label": label})
    if not any(item["partner"] == username for item in chat_list):
        chat_list.append({"partner": username, "last_ts": 0, "label": "Избранное"})
    chat_list.sort(key=lambda x: x["last_ts"], reverse=True)
    return jsonify({"chats": chat_list})

@app.route('/api/clear_chat', methods=['POST'])
def clear_chat():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    username = session['username']
    data = request.json
    
    # Получаем информацию о чате
    chat_partner = data.get('partner')
    
    if not chat_partner:
        return jsonify({"error": "Отсутствует параметр partner"}), 400
    
    try:
        conn = get_db_connection()
        
        # Удаляем сообщения между пользователями
        if chat_partner == username:
            # В случае с избранным, удаляем сообщения, отправленные самому себе
            conn.execute("DELETE FROM private_messages WHERE sender = ? AND receiver = ?", 
                       (username, username))
            deleted_count = conn.execute("SELECT changes()").fetchone()[0]
            print(f"Удалено {deleted_count} сообщений из избранного пользователя {username}")
        else:
            # Удаляем все сообщения между текущим пользователем и выбранным собеседником
            conn.execute("""
                DELETE FROM private_messages 
                WHERE (sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?)
            """, (username, chat_partner, chat_partner, username))
            deleted_count = conn.execute("SELECT changes()").fetchone()[0]
            print(f"Удалено {deleted_count} сообщений между {username} и {chat_partner}")
        
        conn.commit()
        conn.close()
        
        return jsonify({
            "success": True, 
            "deleted_count": deleted_count, 
            "message": f"Удалено {deleted_count} сообщений"
        })
    except Exception as e:
        print(f"Ошибка при очистке чата: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Ошибка сервера: {str(e)}"}), 500

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
def upload():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    file_type = request.form.get('file_type', '')  # image, video, voice, text, etc.
    file_mode = request.form.get('file_mode', 'compressed')  # 'compressed' или 'document'
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file and allowed_file(file.filename):
        try:
            file_data = file.read()
            original_size = len(file_data)
            print(f"Исходный размер файла: {original_size} байт ({original_size/1024:.2f} КБ)")
            ext_original = file.filename.rsplit('.', 1)[1].lower()

            if file_mode == 'compressed':
                if file_type == "image":
                    # Сжимаем изображение через PIL, сохраняем как JPEG
                    try:
                        image = Image.open(io.BytesIO(file_data))
                        image = image.convert("RGB")
                        max_size = 1024
                        image.thumbnail((max_size, max_size))
                        out_io = io.BytesIO()
                        image.save(out_io, format="JPEG", quality=75)
                        recompressed_data = out_io.getvalue()
                        print(f"Размер после PIL-компрессии: {len(recompressed_data)} байт ({len(recompressed_data)/1024:.2f} КБ)")
                        compression_ratio = (1 - len(recompressed_data) / original_size) * 100 if original_size > 0 else 0
                        print(f"Степень сжатия: {compression_ratio:.2f}% (экономия {original_size - len(recompressed_data)} байт)")
                        # Первый байт 'P' - PIL JPEG
                        final_data = b'P' + recompressed_data
                        # Меняем расширение на .jpg, так как это теперь JPEG
                        ext_final = 'jpg'
                        comp_type = "PIL JPEG"
                        compressed_size = len(recompressed_data)
                    except Exception as e:
                        print(f"Ошибка при PIL-компрессии: {e}")
                        traceback.print_exc()
                        # Если ошибка, сохраняем оригинал
                        final_data = b'O' + file_data
                        ext_final = ext_original
                        compression_ratio = 0
                        comp_type = "Original"
                        compressed_size = original_size
                        
                elif file_type == "video":
                    # Используем улучшенное сжатие видео, если доступны модули
                    if COMPRESSION_MODULES_AVAILABLE:
                        try:
                            print("Используем улучшенное сжатие видео...")
                            compression_result = compress_video(file_data, original_size)
                            
                            if compression_result['ratio'] > 0.5:  # Снижаем порог до 0.5% для тестирования
                                print(f"Успешное сжатие видео методом {compression_result['method']}")
                                print(f"Сжатый размер: {compression_result['size']} байт ({compression_result['size']/1024:.2f} КБ)")
                                print(f"Степень сжатия: {compression_result['ratio']:.2f}%")
                                
                                # Проверяем метод сжатия
                                if 'video-blocks' in compression_result['method']:
                                    # Используем маркер 'V' для блочно-сжатых видео
                                    final_data = b'V' + compression_result['data']
                                elif 'partial-mp4' in compression_result['method']:
                                    # Используем маркер 'M' для частично сжатых MP4
                                    final_data = b'M' + compression_result['data']
                                elif 'partial-webm' in compression_result['method']:
                                    # Используем маркер 'W' для частично сжатых WebM
                                    final_data = b'W' + compression_result['data']
                                else:
                                    # Используем маркер 'Z' для обычных zlib-сжатых видео
                                    final_data = b'Z' + compression_result['data']
                                    
                                compressed_size = compression_result['size']
                                compression_ratio = compression_result['ratio']
                                comp_type = f"video-{compression_result['method']}"
                                ext_final = ext_original
                            else:
                                print(f"Видео не удалось эффективно сжать (ratio = {compression_result['ratio']:.2f}%), попробуем минимальное сжатие")
                                
                                # Пробуем минимальное сжатие zlib уровня 1
                                try:
                                    z_data = zlib.compress(file_data, level=1)
                                    z_size = len(z_data)
                                    min_ratio = (1 - z_size / original_size) * 100
                                    
                                    if z_size < original_size:
                                        print(f"Достигнуто минимальное сжатие: {min_ratio:.2f}%")
                                        final_data = b'Z' + z_data
                                        compressed_size = z_size
                                        compression_ratio = min_ratio
                                        comp_type = "zlib-minimal"
                                        ext_final = ext_original
                                    else:
                                        print("Видео не сжимается, используем оригинал")
                                        final_data = b'O' + file_data
                                        compression_ratio = 0
                                        compressed_size = original_size
                                        comp_type = "Original"
                                        ext_final = ext_original
                                except Exception as e:
                                    print(f"Ошибка при минимальном сжатии видео: {e}")
                                    final_data = b'O' + file_data
                                    compression_ratio = 0
                                    compressed_size = original_size
                                    comp_type = "Original"
                                    ext_final = ext_original
                        except Exception as e:
                            print(f"Ошибка при сжатии видео: {e}")
                            traceback.print_exc()
                            final_data = b'O' + file_data
                            compression_ratio = 0
                            compressed_size = original_size
                            comp_type = "Original"
                            ext_final = ext_original
                    else:
                        # Fallback: простое zlib сжатие
                        try:
                            z_data = zlib.compress(file_data, level=1)  # Используем низкий уровень для скорости
                            if len(z_data) < original_size:
                                print(f"Используем zlib для видео, размер: {len(z_data)} байт ({len(z_data)/1024:.2f} КБ)")
                                final_data = b'Z' + z_data
                                compressed_size = len(z_data)
                                compression_ratio = (1 - compressed_size / original_size) * 100
                                comp_type = "zlib-video"
                                ext_final = ext_original
                            else:
                                print("Видео не сжимается через zlib, используем оригинал")
                                final_data = b'O' + file_data
                                compression_ratio = 0
                                compressed_size = original_size
                                comp_type = "Original"
                                ext_final = ext_original
                        except Exception as e:
                            print(f"Ошибка при сжатии видео: {e}")
                            traceback.print_exc()
                            final_data = b'O' + file_data
                            compression_ratio = 0
                            compressed_size = original_size
                            comp_type = "Original"
                            ext_final = ext_original
                        
                elif file_type == "voice" or file_type == "audio":
                    # Используем улучшенное сжатие аудио, если доступны модули
                    if COMPRESSION_MODULES_AVAILABLE:
                        try:
                            print("Используем улучшенное сжатие аудио...")
                            compression_result = compress_audio(file_data, original_size)
                            
                            if compression_result['ratio'] > 2:  # Если сжатие более 2%
                                print(f"Успешное сжатие аудио методом {compression_result['method']}")
                                print(f"Сжатый размер: {compression_result['size']} байт ({compression_result['size']/1024:.2f} КБ)")
                                print(f"Степень сжатия: {compression_result['ratio']:.2f}%")
                                
                                # Проверяем метод сжатия
                                if 'blocks' in compression_result['method']:
                                    # Используем маркер 'B' для блочного сжатия
                                    final_data = b'B' + compression_result['data']
                                elif 'partial-mp3' in compression_result['method']:
                                    # Используем маркер 'M' для частичного сжатия MP3
                                    final_data = b'M' + compression_result['data']
                                else:
                                    # Для обычного zlib сжатия
                                    final_data = b'Z' + compression_result['data']
                                
                                compressed_size = compression_result['size']
                                compression_ratio = compression_result['ratio']
                                comp_type = f"audio-{compression_result['method']}"
                                ext_final = ext_original
                            else:
                                print("Аудио не удалось эффективно сжать, используем оригинал")
                                final_data = b'O' + file_data
                                compression_ratio = 0
                                compressed_size = original_size
                                comp_type = "Original"
                                ext_final = ext_original
                        except Exception as e:
                            print(f"Ошибка при сжатии аудио: {e}")
                            traceback.print_exc()
                            final_data = b'O' + file_data
                            compression_ratio = 0
                            compressed_size = original_size
                            comp_type = "Original"
                            ext_final = ext_original
                    else:
                        # Fallback: простое zlib сжатие
                        try:
                            z_data = zlib.compress(file_data, level=9)
                            z_size = len(z_data)
                            
                            if z_size < original_size:
                                print(f"Используем zlib для аудио, размер: {z_size} байт ({z_size/1024:.2f} КБ)")
                                final_data = b'Z' + z_data
                                compression_ratio = (1 - z_size / original_size) * 100
                                compressed_size = z_size
                                comp_type = "zlib audio"
                                ext_final = ext_original
                            else:
                                print("Аудио не сжимается, используем оригинал")
                                final_data = b'O' + file_data
                                compression_ratio = 0
                                compressed_size = original_size
                                comp_type = "Original"
                                ext_final = ext_original
                        except Exception as e:
                            print(f"Ошибка при сжатии аудио: {e}")
                            traceback.print_exc()
                            final_data = b'O' + file_data
                            compression_ratio = 0
                            compressed_size = original_size
                            comp_type = "Original"
                            ext_final = ext_original

                # Формируем уникальное имя для файла
                unique_filename = f"{uuid.uuid4().hex}.{ext_final}"
                save_path = os.path.join(app.config['COMPRESSED_UPLOAD_FOLDER'], unique_filename)
                with open(save_path, "wb") as f_out:
                    f_out.write(final_data)
                
                print(f"Файл сохранён по пути: {save_path}")
                print(f"Расширение файла: {ext_final}")
                
                # Финальный размер с учетом заголовка
                final_size = len(final_data)
                actual_compression_ratio = (1 - final_size / original_size) * 100 if original_size > 0 else 0
                print(f"Финальный размер: {final_size} байт ({final_size/1024:.2f} КБ)")
                print(f"Итоговое сжатие: {actual_compression_ratio:.2f}%")
                
                # Создаем URL для файла (статический маршрут)
                file_url = url_for('static', filename=f'compressed_uploads/{unique_filename}')
                print(f"URL для файла: {file_url}")
                
                # Сохраняем статистику файла в базу данных
                try:
                    conn = get_db_connection()
                    conn.execute(
                        "INSERT INTO file_stats (filename, original_size, compressed_size, compression_type, date_created) VALUES (?, ?, ?, ?, ?)",
                        (unique_filename, original_size, final_size, comp_type, time.time())
                    )
                    conn.commit()
                    conn.close()
                    print(f"Статистика сжатия файла {unique_filename} сохранена в базу данных")
                except Exception as e:
                    print(f"Ошибка при сохранении статистики файла: {e}")
                    traceback.print_exc()
            else:
                # Режим document - без изменений
                unique_filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                with open(save_path, "wb") as f_out:
                    f_out.write(file_data)
                    
                print(f"Файл документа сохранён по пути: {save_path}")
                file_url = url_for('static', filename=f'uploads/{unique_filename}')
                print(f"URL для документа: {file_url}")
                final_size = original_size
                actual_compression_ratio = 0

            # Возвращаем информацию о загруженном файле
            return jsonify({
                "file_url": file_url,
                "file_type": file_type,
                "file_mode": file_mode,
                "filename": unique_filename,
                "extension": ext_final,
                "original_size": original_size,
                "compressed_size": final_size,
                "compression_ratio": actual_compression_ratio
            })
        except Exception as e:
            print("Ошибка при загрузке файла:")
            traceback.print_exc()
            return jsonify({"error": f"Server error: {str(e)}"}), 500
    else:
        return jsonify({"error": "File type not allowed"}), 400

# Вспомогательная функция для определения MIME типа на основе расширения и типа файла
def get_mime_type(filename, file_type=None):
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    
    # Изображения
    if ext in ['jpg', 'jpeg']:
        return 'image/jpeg'
    elif ext == 'png':
        return 'image/png'
    elif ext == 'gif':
        return 'image/gif'
    
    # Видео
    elif ext == 'mp4':
        return 'video/mp4'
    elif ext == 'webm' and file_type != 'voice' and file_type != 'audio':
        return 'video/webm'
    
    # Аудио
    elif ext == 'mp3':
        return 'audio/mpeg'
    elif ext == 'wav':
        return 'audio/wav'
    elif ext == 'ogg':
        return 'audio/ogg'
    elif ext == 'opus':
        return 'audio/opus'
    elif ext == 'webm' or file_type == 'voice' or file_type == 'audio':
        return 'audio/webm'
    
    # По умолчанию
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
                    # Здесь нам нужно определить, где заканчиваются метаданные
                    
                    # Мы ожидаем, что первые X байт - это сжатые метаданные
                    # Оставшиеся байты - несжатые данные
                    
                    # Пытаемся определить размер сжатых метаданных
                    # Обычно это не более 128КБ
                    
                    # Извлекаем сжатые метаданные (не более 128 КБ)
                    header_size = min(len(payload), 131072)
                    header_compressed = payload[:header_size]
                    body_data = payload[header_size:]
                    
                    try:
                        # Распаковываем метаданные
                        header_data = zlib.decompress(header_compressed)
                        # Собираем файл
                        content = header_data + body_data
                        print(f"Успешно распаковано частично сжатое MP4, размер: {len(content)} байт")
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
                # WebM с частичным сжатием метаданных
                try:
                    print("Обработка частично сжатого WebM...")
                    # Восстанавливаем структуру файла WebM
                    # Здесь логика аналогична MP4, но размер метаданных может быть больше
                    
                    # Извлекаем сжатые метаданные (не более 200 КБ)
                    header_size = min(len(payload), 204800)
                    header_compressed = payload[:header_size]
                    body_data = payload[header_size:]
                    
                    try:
                        # Распаковываем метаданные
                        header_data = zlib.decompress(header_compressed)
                        # Собираем файл
                        content = header_data + body_data
                        print(f"Успешно распаковано частично сжатое WebM, размер: {len(content)} байт")
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
                try:
                    print("Распаковка zlib данных...")
                    content = zlib.decompress(payload)
                    print(f"Успешно распаковано {len(content)} байт")
                except Exception as e:
                    print(f"Ошибка декомпрессии zlib: {e}")
                    return "Ошибка декомпрессии", 500
                
                # Определяем MIME-тип с помощью нашей вспомогательной функции
                mimetype = get_mime_type(filename, file_type)
            elif header == b'B':
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
@socketio.on('join_private')
def handle_join_private(data):
    room = data.get('room')
    join_room(room)
    print(f"Пользователь присоединился к комнате: {room}")

@socketio.on('send_private_message')
def handle_send_private_message(data):
    if 'username' not in session:
        print("Ошибка: пользователь не авторизован")
        return
    
    sender = session['username']
    receiver = data.get('receiver')
    message = data.get('message', '')
    room = data.get('room')
    timestamp = time.time()
    
    print(f"Отправка сообщения от {sender} к {receiver} в комнату {room}: {message[:30]}...")
    
    try:
        compressed_msg = compression.compress(message.encode('utf-8'), use_bwt=True)
        print(f"Сообщение сжато, размер: {len(compressed_msg)} байт")
    except Exception as e:
        print(f"Ошибка сжатия сообщения: {e}")
        traceback.print_exc()
        return
    
    try:
        conn = get_db_connection()
        conn.execute("INSERT INTO private_messages (sender, receiver, timestamp, compressed_message) VALUES (?, ?, ?, ?)",
                    (sender, receiver, timestamp, compressed_msg))
        conn.commit()
        conn.close()
        print(f"Сообщение сохранено в базе данных")
    except Exception as e:
        print(f"Ошибка сохранения сообщения в базе данных: {e}")
        traceback.print_exc()
        return
    
    try:
        decompressed_msg = compression.decompress(compressed_msg).decode('utf-8', errors='replace')
        print(f"Сообщение декомпрессировано для отправки: {decompressed_msg[:30]}...")
    except Exception as e:
        print(f"Ошибка декомпрессии для отправки: {e}")
        decompressed_msg = "[Ошибка декомпрессии]"
    
    print(f"Отправка сообщения в комнату: {room}")
    socketio.emit('receive_private_message',
                  {'sender': sender, 'message': decompressed_msg, 'timestamp': timestamp},
                  room=room)

@socketio.on('send_file_message')
def handle_send_file_message(data):
    if 'username' not in session:
        return
    
    sender = session['username']
    receiver = data.get('receiver')
    file_type = data.get('file_type')
    file_url = data.get('file_url')
    room = data.get('room')
    timestamp = time.time()
    
    print(f"Отправка файлового сообщения:")
    print(f"От: {sender}, Кому: {receiver}")
    print(f"Тип файла: {file_type}")
    print(f"URL файла: {file_url}")
    print(f"Комната: {room}")
    
    # Формируем сообщение в формате FILE:type:url
    message_text = f"FILE:{file_type}:{file_url}"
    print(f"Текст сообщения: {message_text}")
    
    try:
        compressed_msg = compression.compress(message_text.encode('utf-8'), use_bwt=True)
        print(f"Сообщение с файлом сжато, размер: {len(compressed_msg)} байт")
    except Exception as e:
        print(f"Ошибка сжатия сообщения с файлом: {e}")
        traceback.print_exc()
        return
    
    try:
        conn = get_db_connection()
        conn.execute("INSERT INTO private_messages (sender, receiver, timestamp, compressed_message) VALUES (?, ?, ?, ?)",
                    (sender, receiver, timestamp, compressed_msg))
        conn.commit()
        conn.close()
        print(f"Сообщение с файлом сохранено в базе данных")
    except Exception as e:
        print(f"Ошибка сохранения сообщения с файлом в базе данных: {e}")
        traceback.print_exc()
        return
    
    try:
        decompressed_msg = compression.decompress(compressed_msg).decode('utf-8', errors='replace')
        print(f"Сообщение с файлом декомпрессировано для отправки: {decompressed_msg}")
    except Exception as e:
        print(f"Ошибка декомпрессии для отправки файла: {e}")
        decompressed_msg = "[Ошибка декомпрессии]"
    
    print(f"Отправка сообщения с файлом в комнату: {room}")
    socketio.emit('receive_private_message',
                  {'sender': sender, 'message': decompressed_msg, 'timestamp': timestamp},
                  room=room)

@socketio.on('load_private_history')
def handle_load_private_history(data):
    room = data.get('room')
    print(f"Загрузка истории для комнаты: {room}")
    
    parts = room.split('_')
    if len(parts) != 2:
        print(f"Неверный формат комнаты: {room}")
        return
    
    user1, user2 = parts
    conn = get_db_connection()
    c = conn.cursor()
    print(f"Запрос истории для пользователей {user1} и {user2}")
    
    c.execute("""
        SELECT sender, receiver, timestamp, compressed_message
        FROM private_messages
        WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)
        ORDER BY id ASC
    """, (user1, user2, user2, user1))
    
    rows = c.fetchall()
    conn.close()
    
    print(f"Найдено {len(rows)} сообщений в базе данных")
    
    messages = []
    for row in rows:
        sender, receiver, timestamp, comp = row['sender'], row['receiver'], row['timestamp'], row['compressed_message']
        try:
            print(f"Декомпрессия сообщения от {sender} для {receiver}, размер: {len(comp)} байт")
            msg_text = compression.decompress(comp).decode('utf-8', errors='replace')
            print(f"Декомпрессированное сообщение: {msg_text[:50]}...")
        except Exception as e:
            print(f"Ошибка декомпрессии сообщения: {e}")
            traceback.print_exc()
            msg_text = "[Ошибка декомпрессии]"
        
        messages.append({'sender': sender, 'message': msg_text, 'timestamp': timestamp})
    
    print(f"Отправляем {len(messages)} сообщений в комнату {room}")
    emit('load_private_history', messages)

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
    room = data.get('room')
    user = data.get('user')
    socketio.emit('someone_stopped_typing', {'user': user}, room=room)

if __name__ == '__main__':
    socketio.run(app, debug=True)