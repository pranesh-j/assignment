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

load_dotenv()

engine = create_engine(os.getenv('DATABASE_URL'))
Session = sessionmaker(bind=engine)

@celery.task
def process_images(request_id):
    session = Session()
    
    try:
        request = session.query(Request).filter_by(request_id=request_id).first()
        if not request:
            print(f"Request {request_id} not found")
            return
        
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
                            compressed_path = ImageProcessor.compress_image(url)
                            
                            input_filename = url.split('/')[-1]
                            output_url = f"https://www.public-image-output-{input_filename}"
                            output_urls.append(output_url)
                            
                            if os.path.exists(compressed_path):
                                os.remove(compressed_path)
                                
                        except Exception as e:
                            print(f"Error processing image {url}: {str(e)}")
                
                product.output_image_urls = ','.join(output_urls)
                product.status = 'COMPLETED'
                session.commit()
                
            except Exception as e:
                print(f"Error processing product {product.id}: {str(e)}")
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
            try:
                requests.post(
                    request.webhook_url,
                    json={
                        'request_id': request_id,
                        'status': request.status,
                        'message': 'Processing completed'
                    },
                    timeout=10
                )
            except Exception as e:
                print(f"Error triggering webhook: {str(e)}")
        
    except Exception as e:
        print(f"Error processing request {request_id}: {str(e)}")
        request = session.query(Request).filter_by(request_id=request_id).first()
        if request:
            request.status = 'FAILED'
            session.commit()
    
    finally:
        session.close()