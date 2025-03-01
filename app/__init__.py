from flask import Flask
from dotenv import load_dotenv
import os
from app.models.database import init_db
from app.api.routes import api_bp

load_dotenv()

def create_app():
    app = Flask(__name__)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    init_db(app)
    
    app.register_blueprint(api_bp, url_prefix='/api')
    
    return app