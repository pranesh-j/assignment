from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, Integer, String, DateTime, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from datetime import datetime

db = SQLAlchemy()

class Request(db.Model):
    __tablename__ = 'requests'
    
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(36), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='PENDING')  # PENDING, PROCESSING, COMPLETED, FAILED
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    webhook_url = db.Column(db.String(255), nullable=True)

class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(36), db.ForeignKey('requests.request_id'), nullable=False)
    serial_number = db.Column(db.Integer, nullable=False)
    product_name = db.Column(db.String(255), nullable=False)
    input_image_urls = db.Column(db.Text, nullable=False) 
    output_image_urls = db.Column(db.Text, nullable=True) 
    status = db.Column(db.String(20), nullable=False, default='PENDING')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

def init_db(app):
    db.init_app(app)
    with app.app_context():
        db.create_all()