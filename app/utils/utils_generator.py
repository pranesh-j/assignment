import pandas as pd
import logging
from app.models.database import Product

logger = logging.getLogger(__name__)

def generate_output_csv(request_id, output_path):
    """
    Generate an output CSV for a completed request.
    
    Args:
        request_id (str): The request ID
        output_path (str): Path to save the output CSV
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        import os
        
        engine = create_engine(os.getenv('DATABASE_URL'))
        Session = sessionmaker(bind=engine)
        session = Session()
        
        products = session.query(Product).filter_by(request_id=request_id).all()
        
        if not products:
            logger.warning(f"No products found for request {request_id}")
            return False
            
        logger.info(f"Found {len(products)} products for request {request_id}")
        
        data = []
        for product in products:
            # Debug output
            logger.debug(f"Product {product.id}: Output URLs: {product.output_image_urls}")
            
            data.append({
                'S. No.': product.serial_number,
                'Product Name': product.product_name,
                'Input Image Urls': product.input_image_urls,
                'Output Image Urls': product.output_image_urls or ''  # Ensure not None
            })
        
        df = pd.DataFrame(data)
        
        # Print debugging info
        logger.info(f"Writing CSV with {len(df)} rows to {output_path}")
        df.to_csv(output_path, index=False)
        
        session.close()
        return True
    
    except Exception as e:
        logger.exception(f"Error generating output CSV: {str(e)}")
        import traceback
        traceback.print_exc()
        return False