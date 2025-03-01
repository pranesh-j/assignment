from celery import Celery
import os
from dotenv import load_dotenv

load_dotenv()

celery = Celery(
    'image_processor',
    broker=os.getenv('CELERY_BROKER_URL'),
    backend=os.getenv('CELERY_RESULT_BACKEND')
)

celery.config_from_object('celeryconfig')

from app.workers.tasks import *