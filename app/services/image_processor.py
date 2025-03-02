from PIL import Image
import requests
from io import BytesIO
import os
import tempfile
import uuid
import logging

logger = logging.getLogger(__name__)

class ImageProcessor:
    @staticmethod
    def compress_image(image_url, quality=50, max_retries=3):
        retry_count = 0
        last_error = None
        
        while retry_count < max_retries:
            try:
                logger.info(f"Downloading image from {image_url} (attempt {retry_count+1}/{max_retries})")
                response = requests.get(image_url.strip(), timeout=10)
                response.raise_for_status()
                
                img = Image.open(BytesIO(response.content))
                
                filename = f"{uuid.uuid4()}.jpg"
                output_path = os.path.join(tempfile.gettempdir(), filename)
                
                if img.mode == 'RGBA':
                    img = img.convert('RGB')
                
                img.save(output_path, 'JPEG', quality=quality)
                logger.info(f"Image compressed successfully: {output_path}")
                
                return output_path
            
            except requests.exceptions.RequestException as e:
                retry_count += 1
                last_error = f"Download error: {str(e)}"
                logger.warning(f"Error downloading image {image_url}: {last_error}. Retry {retry_count}/{max_retries}")
                
            except Exception as e:
                retry_count += 1
                last_error = f"Processing error: {str(e)}"
                logger.warning(f"Error processing image {image_url}: {last_error}. Retry {retry_count}/{max_retries}")

        error_msg = f"Failed to process image after {max_retries} attempts: {last_error}"
        logger.error(error_msg)
        raise Exception(error_msg)