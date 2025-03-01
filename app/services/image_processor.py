from PIL import Image
import requests
from io import BytesIO
import os
import tempfile
import uuid

class ImageProcessor:
    @staticmethod
    def compress_image(image_url, quality=50):
        try:
            response = requests.get(image_url.strip(), timeout=10)
            response.raise_for_status()  
            
            img = Image.open(BytesIO(response.content))
            
            filename = f"{uuid.uuid4()}.jpg"
            output_path = os.path.join(tempfile.gettempdir(), filename)
            
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            
            img.save(output_path, 'JPEG', quality=quality)
            
            return output_path
        
        except Exception as e:
            print(f"Error processing image {image_url}: {str(e)}")
            raise