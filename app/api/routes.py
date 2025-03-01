from flask import request, jsonify, Blueprint, send_file
from werkzeug.utils import secure_filename
import uuid
import os
import pandas as pd
import tempfile
from app.models.database import db, Request, Product
from app.workers.tasks import process_images
from app.utils.utils_generator import generate_output_csv

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
            
            process_images.delay(request_id)
            
            return jsonify({'request_id': request_id}), 201
            
        except Exception as e:
            db.session.rollback()
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
        'updated_at': req.updated_at
    }), 200

@api_bp.route('/webhook', methods=['POST'])
def register_webhook():
    data = request.json
    
    if not data or 'request_id' not in data or 'webhook_url' not in data:
        return jsonify({'error': 'Missing required fields: request_id and webhook_url'}), 400
    
    req = Request.query.filter_by(request_id=data['request_id']).first()
    
    if not req:
        return jsonify({'error': 'Request not found'}), 404
    
    req.webhook_url = data['webhook_url']
    db.session.commit()
    
    return jsonify({'message': 'Webhook registered successfully'}), 200

@api_bp.route('/download/<request_id>', methods=['GET'])
def download_csv(request_id):
    req = Request.query.filter_by(request_id=request_id).first()
    if not req:
        return jsonify({'error': 'Request not found'}), 404
    
    if req.status not in ['COMPLETED', 'PARTIALLY_COMPLETED']:
        return jsonify({'error': 'Request processing not complete'}), 400
    
    temp_file = tempfile.NamedTemporaryFile(suffix='.csv', delete=False)
    temp_file.close()
    
    if generate_output_csv(request_id, temp_file.name):
        return send_file(
            temp_file.name,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'processed_data_{request_id}.csv'
        )
    
    return jsonify({'error': 'Failed to generate CSV'}), 500