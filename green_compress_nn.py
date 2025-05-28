# green_compress_nn.py
import io
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image

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

# Заглушки для текст, аудио и видео:
def compress_text(text_bytes: bytes) -> bytes:
    return text_bytes

def decompress_text(comp_bytes: bytes) -> bytes:
    return comp_bytes

def compress_audio(audio_bytes: bytes) -> bytes:
    return audio_bytes

def decompress_audio(comp_bytes: bytes) -> bytes:
    return comp_bytes

def compress_video(video_bytes: bytes) -> bytes:
    return video_bytes

def decompress_video(comp_bytes: bytes) -> bytes:
    return comp_bytes

class GreenCompressUltraNN:
    def __init__(self, device='cpu'):
        self.device = device
        self.image_autoencoder = SimpleImageAutoencoder().to(self.device)
        self.image_autoencoder.eval()
        # Для текст, аудио, видео пока используются заглушки.
    def compress(self, data: bytes, data_type: str) -> bytes:
        if data_type == 'text':
            return compress_text(data)
        elif data_type == 'image':
            return self.compress_image(data)
        elif data_type == 'audio':
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
        elif data_type == 'audio':
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
            return None
        image = image.resize((64, 64))
        img_array = np.array(image, dtype=np.float32) / 255.0
        img_tensor = torch.tensor(img_array).unsqueeze(0).unsqueeze(0).to(self.device)
        with torch.no_grad():
            decoded, encoded = self.image_autoencoder(img_tensor)
        latent = encoded.cpu().numpy().astype(np.float32)
        return latent.tobytes()
    def decompress_image(self, comp_bytes: bytes) -> bytes:
        latent = np.frombuffer(comp_bytes, dtype=np.float32)
        try:
            latent = latent.reshape((1, 64, 16, 16))
        except Exception as e:
            print("Ошибка при декомпрессии изображения:", e)
            return None
        latent_tensor = torch.tensor(latent).to(self.device)
        with torch.no_grad():
            reconstructed = self.image_autoencoder.decoder(latent_tensor)
        recon_np = reconstructed.cpu().numpy()[0, 0]
        recon_np = (recon_np * 255).astype('uint8')
        output = io.BytesIO()
        img = Image.fromarray(recon_np, mode='L')
        img.save(output, format='PNG')
        return output.getvalue()

if __name__ == '__main__':
    compressor = GreenCompressUltraNN()
    test_text = "Это тестовое сообщение для нейросетевого сжатия."
    comp_text = compressor.compress(test_text.encode('utf-8'), 'text')
    decom_text = compressor.decompress(comp_text, 'text')
    print("Текстовое сжатие:")
    print("Исходный текст:", test_text)
    print("Сжатые байты (первые 50):", comp_text[:50])
    print("Восстановленный текст:", decom_text.decode('utf-8'))
    
    try:
        with open("image.jpg", "rb") as f:
            img_data = f.read()
        comp_img = compressor.compress(img_data, 'image')
        print("Изображение сжато, первые 50 байт:", comp_img[:50])
        decom_img = compressor.decompress(comp_img, 'image')
        with open("reconstructed_image.png", "wb") as f:
            f.write(decom_img)
        print("Изображение восстановлено и сохранено как 'reconstructed_image.png'")
    except Exception as e:
        print("Ошибка при обработке изображения:", e)
