from flask import request, jsonify, Blueprint, send_file
from werkzeug.utils import secure_filename
import uuid
import os
import pandas as pd
import tempfile
import requests
import re
import logging
import threading
import shutil
from datetime import datetime
from app.models.database import db, Request, Product
from app.workers.tasks import process_images, send_webhook_notification
from app.utils.utils_generator import generate_output_csv

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)

@api_bp.route('/upload', methods=['POST'])
def upload_csv():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file and file.filename.endswith('.csv'):
        request_id = str(uuid.uuid4())
        
        temp_dir = tempfile.gettempdir()
        filename = secure_filename(file.filename)
        temp_path = os.path.join(temp_dir, filename)
        file.save(temp_path)
        
        try:
            df = pd.read_csv(temp_path)
            required_columns = ['S. No.', 'Product Name', 'Input Image Urls']
            if not all(col in df.columns for col in required_columns):
                return jsonify({'error': 'CSV missing required columns'}), 400
            
            new_request = Request(request_id=request_id, status='PENDING')
            db.session.add(new_request)
            db.session.commit()
            
            for _, row in df.iterrows():
                product = Product(
                    request_id=request_id,
                    serial_number=row['S. No.'],
                    product_name=row['Product Name'],
                    input_image_urls=row['Input Image Urls'],
                    status='PENDING'
                )
                db.session.add(product)
            
            db.session.commit()
            logger.info(f"Request {request_id} created successfully")
            
            process_images.delay(request_id)
            
            return jsonify({'request_id': request_id}), 201
            
        except Exception as e:
            db.session.rollback()
            logger.exception(f"Error processing CSV upload: {str(e)}")
            return jsonify({'error': f'Invalid CSV format: {str(e)}'}), 400
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    return jsonify({'error': 'Invalid file type. Only CSV files are allowed.'}), 400

@api_bp.route('/status/<request_id>', methods=['GET'])
def check_status(request_id):
    req = Request.query.filter_by(request_id=request_id).first()
    
    if not req:
        return jsonify({'error': 'Request not found'}), 404
    
    products = Product.query.filter_by(request_id=request_id).all()
    
    total_products = len(products)
    completed_products = sum(1 for p in products if p.status == 'COMPLETED')
    failed_products = sum(1 for p in products if p.status == 'FAILED')
    in_progress = sum(1 for p in products if p.status == 'PROCESSING')
    
    progress = (completed_products / total_products * 100) if total_products > 0 else 0
    
    logger.info(f"Status check for request {request_id}: progress {progress:.1f}%")
    
    return jsonify({
        'request_id': request_id,
        'status': req.status,
        'progress': progress,
        'details': {
            'total': total_products,
            'completed': completed_products,
            'failed': failed_products,
            'in_progress': in_progress
        },
        'created_at': req.created_at,
        'updated_at': req.updated_at,
        'webhook_url': req.webhook_url
    }), 200

def validate_webhook_url(url):
    url_pattern = re.compile(
        r'^https?://'  
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  
        r'localhost|'  
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  
        r'(?::\d+)?'  
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return bool(url_pattern.match(url))

@api_bp.route('/webhook', methods=['POST'])
def register_webhook():
    data = request.json
    
    if not data or 'request_id' not in data or 'webhook_url' not in data:
        return jsonify({'error': 'Missing required fields: request_id and webhook_url'}), 400
    
    if not validate_webhook_url(data['webhook_url']):
        return jsonify({'error': 'Invalid webhook URL format'}), 400
    
    req = Request.query.filter_by(request_id=data['request_id']).first()
    
    if not req:
        return jsonify({'error': 'Request not found'}), 404
    
    req.webhook_url = data['webhook_url']
    db.session.commit()
    
    logger.info(f"Webhook registered for request {data['request_id']}: {req.webhook_url}")
    
    try:
        test_response = requests.post(
            data['webhook_url'],
            json={'test': 'Webhook registration test', 'request_id': data['request_id']},
            timeout=5
        )
        logger.info(f"Webhook test response: {test_response.status_code}")
    except Exception as e:
        logger.error(f"Webhook test failed: {str(e)}")
    
    if req.status in ['COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED']:
        send_webhook_notification.delay(data['request_id'])
        trigger_message = "Processing already complete. Webhook notification queued."
    else:
        trigger_message = "Webhook will be triggered when processing completes."
    
    return jsonify({
        'message': 'Webhook registered successfully',
        'trigger_status': trigger_message,
        'request_id': data['request_id'],
        'webhook_url': req.webhook_url
    }), 200

@api_bp.route('/trigger-webhook/<request_id>', methods=['POST'])
def trigger_webhook(request_id):
    req = Request.query.filter_by(request_id=request_id).first()
    
    if not req:
        return jsonify({'error': 'Request not found'}), 404
    
    if not req.webhook_url:
        return jsonify({'error': 'No webhook URL registered for this request'}), 400
    
    logger.info(f"Manually triggering webhook for request {request_id}")
    send_webhook_notification.delay(request_id)
    
    return jsonify({
        'message': 'Webhook notification queued',
        'request_id': request_id,
        'webhook_url': req.webhook_url
    }), 200

@api_bp.route('/test-webhook', methods=['POST'])
def test_webhook():
    data = request.json
    
    if not data or 'webhook_url' not in data:
        return jsonify({'error': 'Missing required field: webhook_url'}), 400
    
    try:
        payload = {
            'test': True,
            'message': 'This is a test webhook from the image processor',
            'timestamp': str(datetime.utcnow())
        }
        
        logger.info(f"Sending test webhook to {data['webhook_url']}")
        response = requests.post(
            data['webhook_url'],
            json=payload,
            timeout=10
        )
        
        return jsonify({
            'success': True,
            'status_code': response.status_code,
            'response': response.text
        }), 200
    except Exception as e:
        logger.exception(f"Error sending test webhook: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def cleanup_temp_dir(temp_dir):
    import time
    time.sleep(60)
    try:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temporary directory: {temp_dir}")
    except Exception as e:
        logger.error(f"Error cleaning up temporary directory: {str(e)}")

@api_bp.route('/download/<request_id>', methods=['GET'])
def download_csv(request_id):
    try:
        req = Request.query.filter_by(request_id=request_id).first()
        if not req:
            return jsonify({'error': 'Request not found'}), 404
        
        if req.status not in ['COMPLETED', 'PARTIALLY_COMPLETED']:
            return jsonify({'error': 'Request processing not complete'}), 400
        
        temp_dir = tempfile.mkdtemp()
        output_path = os.path.join(temp_dir, f'processed_data_{request_id}.csv')
        
        logger.info(f"Generating CSV for request {request_id}")
        success = generate_output_csv(request_id, output_path)
        
        if not success:
            return jsonify({'error': 'Failed to generate CSV'}), 500
        
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            logger.error(f"Generated CSV file is empty or missing: {output_path}")
            return jsonify({'error': 'Generated CSV file is empty or missing'}), 500
        
        logger.info(f"Sending CSV file for request {request_id}")
        response = send_file(
            output_path,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'processed_data_{request_id}.csv'
        )
        
        threading.Thread(target=cleanup_temp_dir, args=(temp_dir,)).start()
        
        return response
    
    except Exception as e:
        logger.exception(f"Error in download endpoint: {str(e)}")
        return jsonify({'error': f'Download failed: {str(e)}'}), 500