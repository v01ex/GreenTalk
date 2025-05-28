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
import ffmpeg
import tempfile

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

# --- Вспомогательные функции для конвертации ---
def convert_audio_to_ogg(input_bytes):
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as in_file:
        in_file.write(input_bytes)
        in_file.flush()
        out_file = tempfile.NamedTemporaryFile(suffix='.ogg', delete=False)
        out_file.close()
        (
            ffmpeg
            .input(in_file.name)
            .output(out_file.name, acodec='libvorbis', audio_bitrate='96k')
            .run(overwrite_output=True, quiet=True)
        )
        with open(out_file.name, 'rb') as f:
            ogg_bytes = f.read()
    return ogg_bytes

def convert_video_to_webm(input_bytes):
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as in_file:
        in_file.write(input_bytes)
        in_file.flush()
        out_file = tempfile.NamedTemporaryFile(suffix='.webm', delete=False)
        out_file.close()
        (
            ffmpeg
            .input(in_file.name)
            .output(out_file.name, vcodec='libvpx-vp9', acodec='libopus', video_bitrate='1M', audio_bitrate='96k')
            .run(overwrite_output=True, quiet=True)
        )
        with open(out_file.name, 'rb') as f:
            webm_bytes = f.read()
    return webm_bytes

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
                    except Exception as e:
                        print(f"Ошибка при PIL-компрессии: {e}")
                        traceback.print_exc()
                        # Если ошибка, сохраняем оригинал
                        final_data = b'O' + file_data
                        ext_final = ext_original
                        compression_ratio = 0
                        comp_type = "Original"
                elif (file_type == "audio" or file_type == "voice") and ext_original == 'mp3':
                    # Конвертация MP3 в OGG
                    print(f"Попытка конвертации MP3 в OGG для файла: {file.filename}")
                    try:
                        ogg_data = convert_audio_to_ogg(file_data)
                        print("Конвертация в OGG успешна.")
                        final_data = b'O' + ogg_data
                        ext_final = 'ogg'
                        comp_type = "MP3->OGG"
                        compressed_size = len(final_data)
                        compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
                        print(f"Размер после конвертации в OGG: {compressed_size} байт ({compressed_size/1024:.2f} КБ)")
                        print(f"Степень сжатия: {compression_ratio:.2f}% (экономия {original_size - compressed_size} байт)")
                    except Exception as e:
                        print(f"Ошибка при конвертации MP3 в OGG: {e}")
                        traceback.print_exc()
                        final_data = b'O' + file_data
                        ext_final = ext_original
                        comp_type = "Original"
                        compression_ratio = 0
                elif file_type == "video" and ext_original == 'mp4':
                    # Конвертация MP4 в WebM
                    try:
                        webm_data = convert_video_to_webm(file_data)
                        final_data = b'O' + webm_data
                        ext_final = 'webm'
                        comp_type = "MP4->WebM"
                        compressed_size = len(final_data)
                        compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
                        print(f"Размер после конвертации в WebM: {compressed_size} байт ({compressed_size/1024:.2f} КБ)")
                        print(f"Степень сжатия: {compression_ratio:.2f}% (экономия {original_size - compressed_size} байт)")
                    except Exception as e:
                        print(f"Ошибка при конвертации MP4 в WebM: {e}")
                        traceback.print_exc()
                        final_data = b'O' + file_data
                        ext_final = ext_original
                        comp_type = "Original"
                        compression_ratio = 0
                elif file_type in ["video", "voice"]:
                    # Для других видео и голоса - используем оригинал с маркером O
                    final_data = b'O' + file_data
                    ext_final = ext_original
                    compressed_size = len(final_data)
                    compression_ratio = 0  # Нет сжатия
                    comp_type = "Original"
                    print(f"Сохраняем оригинальное медиа, размер: {compressed_size} байт ({compressed_size/1024:.2f} КБ)")
                else:
                    # Для прочих файлов - zlib
                    z_data = zlib.compress(file_data)
                    compressed_size = len(z_data)
                    compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
                    
                    if compressed_size < original_size:
                        final_data = b'Z' + z_data
                        print(f"Размер после zlib: {compressed_size} байт ({compressed_size/1024:.2f} КБ)")
                        print(f"Степень сжатия: {compression_ratio:.2f}% (экономия {original_size - compressed_size} байт)")
                        comp_type = "zlib"
                    else:
                        final_data = b'O' + file_data
                        compression_ratio = 0
                        comp_type = "Original"
                        print("zlib не дал выигрыш, сохраняем оригинал")
                    # Оставляем расширение
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
        
        # Обработка сжатых данных
        if len(data) > 0:
            header = data[0:1]
            payload = data[1:]
            
            if header == b'P':
                # PIL JPEG
                content = payload
                mimetype = 'image/jpeg'
            elif header == b'Z':
                # zlib
                try:
                    content = zlib.decompress(payload)
                except Exception as e:
                    print(f"Ошибка декомпрессии zlib: {e}")
                    return "Ошибка декомпрессии", 500
                
                # Определяем MIME-тип по расширению файла
                if '.jpg' in filename.lower() or '.jpeg' in filename.lower():
                    mimetype = 'image/jpeg'
                elif '.png' in filename.lower():
                    mimetype = 'image/png'
                elif '.gif' in filename.lower():
                    mimetype = 'image/gif'
                elif '.mp4' in filename.lower():
                    mimetype = 'video/mp4'
                elif '.webm' in filename.lower():
                    mimetype = 'video/webm'
                elif '.mp3' in filename.lower():
                    mimetype = 'audio/mpeg'
                elif '.wav' in filename.lower():
                    mimetype = 'audio/wav'
                elif '.ogg' in filename.lower():
                    mimetype = 'audio/ogg'
                else:
                    mimetype = 'application/octet-stream'
            elif header == b'O':
                # Оригинал
                content = payload
                
                # Определяем MIME-тип по расширению файла
                ext = filename.split('.')[-2].lower() if '.' in filename else ''
                if ext in ['jpg', 'jpeg']:
                    mimetype = 'image/jpeg'
                elif ext == 'png':
                    mimetype = 'image/png'
                elif ext == 'gif':
                    mimetype = 'image/gif'
                elif ext == 'mp4':
                    mimetype = 'video/mp4'
                elif ext == 'webm':
                    mimetype = 'video/webm'
                elif ext == 'mp3':
                    mimetype = 'audio/mpeg'
                elif ext == 'wav':
                    mimetype = 'audio/wav'
                elif ext == 'ogg':
                    mimetype = 'audio/ogg'
                else:
                    mimetype = 'application/octet-stream'
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
            'type': file['filename'].split('.')[-2].lower() if '.' in file['filename'] else '',
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

# Добавьте эти маршруты в server_flask.py перед строкой if __name__ == '__main__':

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
    
    # Получаем данные из базы данных по файлам
    conn = get_db_connection()
    file_results = conn.execute("""
        SELECT filename, original_size, compressed_size, compression_type, 
               (original_size - compressed_size) * 100.0 / original_size as compression_ratio,
               date_created
        FROM file_stats
    """).fetchall()
    
    # Получаем данные о сжатии сообщений
    msg_results = conn.execute("""
        SELECT sender, receiver, length(compressed_message) as compressed_size, 
               timestamp
        FROM private_messages
    """).fetchall()
    conn.close()
    
    # Преобразуем в формат для графиков
    data = []
    
    # Обработка данных по файлам
    for row in file_results:
        # Пропускаем записи с нулевым размером
        if row['original_size'] <= 0 or row['compressed_size'] <= 0:
            continue
            
        # Определяем тип данных по расширению
        extension = row['filename'].split('.')[-1] if '.' in row['filename'] else 'unknown'
        data_type = 'unknown'
        if extension.lower() in ['jpg', 'jpeg', 'png', 'gif']:
            data_type = 'image'
        elif extension.lower() in ['mp3', 'wav', 'ogg']:
            data_type = 'audio'
        elif extension.lower() in ['mp4', 'avi', 'webm']:
            data_type = 'video'
        else:
            data_type = 'other'
        
        # Расчет степени сжатия
        compression_ratio = (row['original_size'] - row['compressed_size']) * 100.0 / row['original_size']
        
        # Расчет времени обработки на основе размера файла (эмуляция)
        processing_time = int(row['original_size'] / 1024 * 5)  # 5 мс на каждый КБ данных (условно)
        
        data.append({
            "algorithm": row['compression_type'],
            "dataType": data_type,
            "dataSize": round(row['original_size'] / 1024, 2),  # КБ
            "compressionRatio": round(float(compression_ratio), 2),
            "processingTime": processing_time
        })
    
    # Обработка данных по сообщениям
    # Предполагаем, что среднее сообщение без сжатия занимает 2 байта на символ
    # Это грубая оценка, так как мы не храним исходный размер сообщений
    for msg in msg_results:
        # Оцениваем исходный размер - для примера берем размер сжатого * 2.5
        # В реальности вам нужно адаптировать эту логику под вашу систему
        compressed_size = msg['compressed_size']
        if compressed_size <= 0:
            continue
            
        estimated_original_size = compressed_size * 2.5  # Очень грубая оценка
        
        if estimated_original_size > 0:
            compression_ratio = ((estimated_original_size - compressed_size) / estimated_original_size) * 100
            
            data.append({
                "algorithm": "bwt+mtf+rle+huffman",  # Предполагаем, что используется этот алгоритм
                "dataType": "text",
                "dataSize": round(estimated_original_size / 1024, 2),  # КБ
                "compressionRatio": round(compression_ratio, 2),
                "processingTime": int(estimated_original_size / 1024 * 3)  # 3 мс на КБ (условно)
            })
    
    return jsonify({"data": data})

@app.route('/api/reset_compression_data', methods=['POST'])
def reset_compression_data():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db_connection()
    conn.execute("DELETE FROM file_stats")
    conn.execute("DELETE FROM private_messages")
    conn.commit()
    conn.close()
    return jsonify({"success": True})

if __name__ == '__main__':
    socketio.run(app, debug=True)