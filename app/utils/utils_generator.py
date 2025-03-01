import pandas as pd
from app.models.database import Product

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
        
        data = []
        for product in products:
            data.append({
                'S. No.': product.serial_number,
                'Product Name': product.product_name,
                'Input Image Urls': product.input_image_urls,
                'Output Image Urls': product.output_image_urls
            })
        
        df = pd.DataFrame(data)
        
        df.to_csv(output_path, index=False)
        
        session.close()
        return True
    
    except Exception as e:
        print(f"Error generating output CSV: {str(e)}")
        return False