from PIL import Image, ImageDraw
import os

def create_default_avatar():
    # Создаем директорию, если она не существует
    avatar_path = 'static/img/default-avatar.png'
    os.makedirs(os.path.dirname(avatar_path), exist_ok=True)
    
    # Создаем простую аватарку
    img_size = 200
    img = Image.new('RGB', (img_size, img_size), color=(100, 149, 237))  # Голубой фон
    draw = ImageDraw.Draw(img)
    
    # Рисуем круг для аватарки
    draw.ellipse([(0, 0), (img_size, img_size)], fill=(70, 130, 180))
    
    # Сохраняем изображение
    img.save(avatar_path)
    print(f"Создана дефолтная аватарка по пути: {avatar_path}")

if __name__ == "__main__":
    create_default_avatar() 