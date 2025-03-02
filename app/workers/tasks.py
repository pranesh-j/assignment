from app.workers import celery
from app.services.image_processor import ImageProcessor
from app.models.database import db, Request, Product
from flask import current_app
import requests
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import time
import logging
import random
from datetime import datetime

logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

engine = create_engine(os.getenv('DATABASE_URL'))
Session = sessionmaker(bind=engine)

def send_webhook_with_retry(webhook_url, payload, max_retries=3, initial_delay=1):
    for attempt in range(max_retries):
        try:
            logger.info(f"Sending webhook to {webhook_url} (attempt {attempt+1}/{max_retries})")
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=10
            )
            logger.info(f"Webhook response: {response.status_code} - {response.text}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending webhook (attempt {attempt+1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                backoff_delay = initial_delay * (2 ** attempt)
                jitter = backoff_delay * 0.2 * random.uniform(-1, 1)
                delay = max(0.1, backoff_delay + jitter)  
                logger.info(f"Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                logger.error(f"Max retries reached. Webhook delivery failed.")
                return False

@celery.task
def send_webhook_notification(request_id):
    session = Session()
    
    try:
        request = session.query(Request).filter_by(request_id=request_id).first()
        if not request or not request.webhook_url:
            logger.warning(f"Request {request_id} not found or no webhook URL")
            return False
            
        logger.info(f"Sending webhook notification for request {request_id} to {request.webhook_url}")
        
        products = session.query(Product).filter_by(request_id=request_id).all()
        total_products = len(products)
        completed_products = sum(1 for p in products if p.status == 'COMPLETED')
        failed_products = sum(1 for p in products if p.status == 'FAILED')
        in_progress = sum(1 for p in products if p.status == 'PROCESSING')
        
        progress = (completed_products / total_products * 100) if total_products > 0 else 0
        
        payload = {
            'request_id': request_id,
            'status': request.status,
            'progress': progress,
            'details': {
                'total': total_products,
                'completed': completed_products,
                'failed': failed_products,
                'in_progress': in_progress
            },
            'message': f'Image processing {request.status.lower()}',
            'timestamp': str(datetime.utcnow())
        }
        
        success = send_webhook_with_retry(request.webhook_url, payload)
        return success
        
    except Exception as e:
        logger.exception(f"Error sending webhook notification: {str(e)}")
        return False
    finally:
        session.close()

@celery.task
def process_images(request_id):
    session = Session()
    
    try:
        request = session.query(Request).filter_by(request_id=request_id).first()
        if not request:
            logger.warning(f"Request {request_id} not found")
            return
        
        logger.info(f"Starting processing for request {request_id}")
        logger.info(f"Request webhook URL: {request.webhook_url}")
        
        request.status = 'PROCESSING'
        session.commit()
        
        products = session.query(Product).filter_by(request_id=request_id).all()
        
        for product in products:
            try:
                product.status = 'PROCESSING'
                session.commit()
                
                input_urls = product.input_image_urls.split(',')
                output_urls = []
                
                for url in input_urls:
                    url = url.strip()
                    if url:
                        try:
                            logger.info(f"Processing image: {url}")
                            compressed_path = ImageProcessor.compress_image(url)
                            
                            input_filename = url.split('/')[-1]
                            output_url = f"https://www.public-image-output-{input_filename}"
                            output_urls.append(output_url)
                            
                            if os.path.exists(compressed_path):
                                os.remove(compressed_path)
                                
                        except Exception as e:
                            logger.error(f"Error processing image {url}: {str(e)}")
                
                product.output_image_urls = ','.join(output_urls)
                product.status = 'COMPLETED'
                session.commit()
                
            except Exception as e:
                logger.error(f"Error processing product {product.id}: {str(e)}")
                product.status = 'FAILED'
                session.commit()
        
        all_products = session.query(Product).filter_by(request_id=request_id).all()
        statuses = [p.status for p in all_products]
        
        if all(status == 'COMPLETED' for status in statuses):
            request.status = 'COMPLETED'
        elif any(status == 'FAILED' for status in statuses):
            request.status = 'PARTIALLY_COMPLETED'
        session.commit()
        
        if request.webhook_url:
            logger.info(f"Scheduling webhook notification for request {request_id}")
            send_webhook_notification.delay(request_id)
        else:
            logger.info(f"No webhook URL registered for request {request_id}")
    
    except Exception as e:
        logger.exception(f"Error processing request {request_id}: {str(e)}")
        request = session.query(Request).filter_by(request_id=request_id).first()
        if request:
            request.status = 'FAILED'
            session.commit()
            
            if request.webhook_url:
                send_webhook_notification.delay(request_id)
    
    finally:
        session.close()