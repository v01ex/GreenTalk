# green_compress_nn.py
import io
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
import zlib
import base64
import os
import json

# --- Простой сверточный автоэнкодер для изображений на PyTorch ---
class SimpleImageAutoencoder(nn.Module):
    def __init__(self):
        super(SimpleImageAutoencoder, self).__init__()
        # Encoder: (1, 64, 64) -> (64, 16, 16)
        self.encoder = nn.Sequential(
            nn.Conv2d(1, 32, 3, stride=2, padding=1),  # -> (32, 32, 32)
            nn.ReLU(),
            nn.Conv2d(32, 64, 3, stride=2, padding=1), # -> (64, 16, 16)
            nn.ReLU(),
        )
        # Decoder: (64, 16, 16) -> (1, 64, 64)
        self.decoder = nn.Sequential(
            nn.ConvTranspose2d(64, 32, 3, stride=2, padding=1, output_padding=1),  # -> (32, 32, 32)
            nn.ReLU(),
            nn.ConvTranspose2d(32, 1, 3, stride=2, padding=1, output_padding=1),   # -> (1, 64, 64)
            nn.Sigmoid(),
        )
    def forward(self, x):
        encoded = self.encoder(x)
        decoded = self.decoder(encoded)
        return decoded, encoded

# Функции для сжатия текста - используем стандартный zlib
def compress_text(text_bytes: bytes) -> bytes:
    compressed_data = zlib.compress(text_bytes, level=9)
    header = f"TXT_ZLIB:{len(text_bytes)}:".encode('utf-8')
    return header + compressed_data

def decompress_text(comp_bytes: bytes) -> bytes:
    try:
        # Проверяем формат и получаем параметры
        header = comp_bytes[:comp_bytes.find(b':') + 1].decode('utf-8')
        if not header.startswith("TXT_ZLIB:"):
            return comp_bytes  # Возвращаем оригинал, если формат неизвестен
        
        # Извлекаем информацию из заголовка
        _, original_size_str, _ = header.split(":")
        original_size = int(original_size_str)
        
        # Получаем данные без заголовка
        data_start = comp_bytes.find(b':') + 1
        data_start = comp_bytes.find(b':', data_start) + 1
        compressed_data = comp_bytes[data_start:]
        
        # Распаковываем данные
        decompressed_data = zlib.decompress(compressed_data)
        
        return decompressed_data
    except Exception as e:
        print(f"Ошибка при декомпрессии текста: {e}")
        return comp_bytes  # В случае ошибки возвращаем оригинал

def compress_audio(audio_bytes: bytes) -> bytes:
    try:
        # Создаем временный файл для входных данных
        # Используем абсолютные пути
        import tempfile
        temp_dir = tempfile.gettempdir()
        temp_input = os.path.join(temp_dir, f"temp_input_{uuid.uuid4().hex}.webm")
        temp_output = os.path.join(temp_dir, f"temp_output_{uuid.uuid4().hex}.ogg")
        
        with open(temp_input, "wb") as f:
            f.write(audio_bytes)
        
        print(f"Сохранен временный файл: {temp_input}, размер: {len(audio_bytes)} байт")
        
        # Используем ffmpeg для транскодирования с пониженным битрейтом
        import subprocess
        cmd = [
            "ffmpeg", "-y", "-i", temp_input,
            "-c:a", "libvorbis",     # кодек Vorbis
            "-b:a", "24k",           # битрейт 24 кбит/с (еще ниже)
            "-ac", "1",              # моно (1 канал)
            "-ar", "8000",           # частота дискретизации 8кГц (еще ниже)
            "-f", "ogg",             # формат Ogg
            temp_output
        ]
        
        print(f"Запуск FFmpeg: {' '.join(cmd)}")
        
        # Запускаем процесс ffmpeg
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        
        stderr_text = stderr.decode('utf-8', errors='ignore')
        print(f"FFmpeg stdout: {stdout.decode('utf-8', errors='ignore')}")
        print(f"FFmpeg stderr: {stderr_text}")
        
        if process.returncode != 0:
            print(f"Ошибка FFmpeg (код {process.returncode}): {stderr_text}")
            raise Exception(f"Ошибка FFmpeg при транскодировании (код {process.returncode})")
        
        # Проверяем, создался ли выходной файл
        if not os.path.exists(temp_output):
            print(f"Выходной файл не создан: {temp_output}")
            raise Exception("FFmpeg не создал выходной файл")
        
        # Читаем сжатый файл
        with open(temp_output, "rb") as f:
            compressed_data = f.read()
        
        print(f"Размер после сжатия FFmpeg: {len(compressed_data)} байт")
        
        # Удаляем временные файлы
        try:
            if os.path.exists(temp_input):
                os.remove(temp_input)
            if os.path.exists(temp_output):
                os.remove(temp_output)
        except Exception as e:
            print(f"Ошибка при удалении временных файлов: {e}")
        
        # Проверяем результат сжатия
        if len(compressed_data) < len(audio_bytes):
            compression_ratio = (1 - len(compressed_data) / len(audio_bytes)) * 100
            print(f"Успешное сжатие FFmpeg: {compression_ratio:.2f}%")
            # Добавляем заголовок с информацией о сжатии
            header = f"AUDIO_OGG:{len(audio_bytes)}:".encode('utf-8')
            return header + compressed_data
        else:
            print("FFmpeg не дал выигрыша в размере")
            # Если сжатие не дало выигрыша, возвращаем оригинал с заголовком
            header = f"AUDIO_ORIG:{len(audio_bytes)}:".encode('utf-8')
            return header + audio_bytes
    except Exception as e:
        print(f"Ошибка при сжатии аудио: {e}")
        traceback.print_exc()
        
        # Если что-то пошло не так, пробуем zlib с максимальным сжатием
        try:
            compressed_data = zlib.compress(audio_bytes, level=9)
            compression_ratio = (1 - len(compressed_data) / len(audio_bytes)) * 100
            print(f"Сжатие zlib: {compression_ratio:.2f}%")
            
            if len(compressed_data) < len(audio_bytes):
                header = f"AUDIO_ZLIB:{len(audio_bytes)}:".encode('utf-8')
                return header + compressed_data
        except Exception as e2:
            print(f"Ошибка при сжатии zlib: {e2}")
        
        # В случае ошибки возвращаем оригинал с заголовком
        header = f"AUDIO_ORIG:{len(audio_bytes)}:".encode('utf-8')
        return header + audio_bytes

# Функции для сжатия видео - простое zlib-сжатие
def compress_video(video_bytes: bytes) -> bytes:
    try:
        # Используем простое zlib-сжатие с низким уровнем сжатия для скорости
        compressed_data = zlib.compress(video_bytes, level=1)
        
        # Проверяем, дало ли сжатие выигрыш
        if len(compressed_data) < len(video_bytes):
            # Добавляем заголовок с информацией о сжатии
            header = f"VIDEO_ZLIB:{len(video_bytes)}:".encode('utf-8')
            return header + compressed_data
        else:
            # Если сжатие не дало выигрыша, возвращаем оригинал с заголовком
            header = f"VIDEO_ORIG:{len(video_bytes)}:".encode('utf-8')
            return header + video_bytes
    except Exception as e:
        print(f"Ошибка при сжатии видео: {e}")
        # В случае ошибки возвращаем оригинал с заголовком
        header = f"VIDEO_ORIG:{len(video_bytes)}:".encode('utf-8')
        return header + video_bytes

def decompress_video(comp_bytes: bytes) -> bytes:
    try:
        # Проверяем формат и получаем параметры
        header_str = comp_bytes[:50].decode('utf-8', errors='ignore')  # Берем первые 50 байт для поиска заголовка
        
        # Находим позицию первого двоеточия
        first_colon = header_str.find(':')
        if first_colon == -1:
            return comp_bytes  # Возвращаем оригинал, если формат неизвестен
        
        # Получаем тип сжатия
        compression_type = header_str[:first_colon]
        
        # Если это оригинал, просто возвращаем данные без заголовка
        if compression_type == "VIDEO_ORIG":
            # Находим второе двоеточие
            second_colon = header_str.find(':', first_colon + 1)
            if second_colon == -1:
                return comp_bytes  # Возвращаем оригинал при ошибке формата
            
            # Вычисляем позицию начала данных
            data_start_pos = second_colon + 1
            return comp_bytes[data_start_pos:]
        
        # Если это zlib-сжатие
        elif compression_type == "VIDEO_ZLIB":
            # Находим второе двоеточие
            second_colon = header_str.find(':', first_colon + 1)
            if second_colon == -1:
                return comp_bytes  # Возвращаем оригинал при ошибке формата
            
            # Вычисляем позицию начала данных
            data_start_pos = second_colon + 1
            
            # Распаковываем данные zlib
            compressed_data = comp_bytes[data_start_pos:]
            return zlib.decompress(compressed_data)
        
        # Если неизвестный формат, возвращаем как есть
        return comp_bytes
    except Exception as e:
        print(f"Ошибка при декомпрессии видео: {e}")
        return comp_bytes  # В случае ошибки возвращаем оригинал

class GreenCompressUltraNN:
    def __init__(self, device='cpu'):
        self.device = device
        self.image_autoencoder = SimpleImageAutoencoder().to(self.device)
        self.image_autoencoder.eval()
        # Для текст, аудио, видео используются функции выше
    
    def compress(self, data: bytes, data_type: str) -> bytes:
        if data_type == 'text':
            return compress_text(data)
        elif data_type == 'image':
            return self.compress_image(data)
        elif data_type == 'audio' or data_type == 'voice':
            return compress_audio(data)
        elif data_type == 'video':
            return compress_video(data)
        else:
            raise ValueError("Неподдерживаемый тип данных")
    
    def decompress(self, comp_data: bytes, data_type: str) -> bytes:
        if data_type == 'text':
            return decompress_text(comp_data)
        elif data_type == 'image':
            return self.decompress_image(comp_data)
        elif data_type == 'audio' or data_type == 'voice':
            return decompress_audio(comp_data)
        elif data_type == 'video':
            return decompress_video(comp_data)
        else:
            raise ValueError("Неподдерживаемый тип данных")
    
    def compress_image(self, image_bytes: bytes) -> bytes:
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert('L')
        except Exception as e:
            print("Ошибка при чтении изображения:", e)
            return image_bytes
        
        try:
            image = image.resize((64, 64))
            img_array = np.array(image, dtype=np.float32) / 255.0
            img_tensor = torch.tensor(img_array).unsqueeze(0).unsqueeze(0).to(self.device)
            
            with torch.no_grad():
                decoded, encoded = self.image_autoencoder(img_tensor)
            
            latent = encoded.cpu().numpy().astype(np.float32)
            return latent.tobytes()
        except Exception as e:
            print("Ошибка при сжатии изображения через нейросеть:", e)
            return image_bytes
    
    def decompress_image(self, comp_bytes: bytes) -> bytes:
        try:
            latent = np.frombuffer(comp_bytes, dtype=np.float32)
            latent = latent.reshape((1, 64, 16, 16))
            
            latent_tensor = torch.tensor(latent).to(self.device)
            
            with torch.no_grad():
                reconstructed = self.image_autoencoder.decoder(latent_tensor)
            
            recon_np = reconstructed.cpu().numpy()[0, 0]
            recon_np = (recon_np * 255).astype('uint8')
            
            output = io.BytesIO()
            img = Image.fromarray(recon_np, mode='L')
            img.save(output, format='PNG')
            
            return output.getvalue()
        except Exception as e:
            print(f"Ошибка при декомпрессии изображения: {e}")
            return comp_bytes

if __name__ == '__main__':
    compressor = GreenCompressUltraNN()
    
    # Тест сжатия текста
    test_text = "Это тестовое сообщение для нейросетевого сжатия."
    comp_text = compressor.compress(test_text.encode('utf-8'), 'text')
    decom_text = compressor.decompress(comp_text, 'text')
    
    print("Текстовое сжатие:")
    print("Исходный текст:", test_text)
    print("Сжатые байты (первые 50):", comp_text[:50])
    print("Степень сжатия: {:.2f}%".format((1 - len(comp_text) / len(test_text.encode('utf-8'))) * 100))
    print("Восстановленный текст:", decom_text.decode('utf-8'))
    
    # Тест сжатия изображения
    try:
        with open("image.jpg", "rb") as f:
            img_data = f.read()
        
        comp_img = compressor.compress(img_data, 'image')
        print("\nИзображение сжато:")
        print("Исходный размер: {:.2f} KB".format(len(img_data) / 1024))
        print("Сжатый размер: {:.2f} KB".format(len(comp_img) / 1024))
        print("Степень сжатия: {:.2f}%".format((1 - len(comp_img) / len(img_data)) * 100))
        
        decom_img = compressor.decompress(comp_img, 'image')
        with open("reconstructed_image.png", "wb") as f:
            f.write(decom_img)
        print("Изображение восстановлено и сохранено как 'reconstructed_image.png'")
    except Exception as e:
        print("Ошибка при обработке изображения:", e)