from PIL import Image, ImageDraw
import os

# Create a default group avatar
def create_default_group_avatar():
    # Path for the default group avatar
    avatar_path = 'static/img/default-group.png'
    
    # Create directories if they don't exist
    os.makedirs(os.path.dirname(avatar_path), exist_ok=True)
    
    # Create a simple avatar with a letter "G" (for group)
    img_size = 200
    img = Image.new('RGB', (img_size, img_size), color=(75, 139, 190))  # Bluish background
    draw = ImageDraw.Draw(img)
    
    # Draw a circle for the avatar
    draw.ellipse([(0, 0), (img_size, img_size)], fill=(60, 120, 165))
    
    # Save the image
    img.save(avatar_path)
    print(f"Created default group avatar at: {avatar_path}")

if __name__ == "__main__":
    create_default_group_avatar() 