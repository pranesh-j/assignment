import os
import subprocess
import sys
import time

def setup_database():
    print("Setting up PostgreSQL database...")
    try:
        subprocess.run(["psql", "--version"], check=True, stdout=subprocess.PIPE)
        
        subprocess.run(
            ["psql", "-c", "CREATE DATABASE image_processor;"],
            check=True, 
            stdout=subprocess.PIPE
        )
        
        print("PostgreSQL database 'image_processor' created successfully.")
    except subprocess.CalledProcessError:
        print("Error: PostgreSQL is not installed or not in PATH.")
        print("Please install PostgreSQL and try again.")
        sys.exit(1)
    except Exception as e:
        print(f"Error creating database: {str(e)}")
        print("If the database already exists, you can ignore this error.")

def setup_redis():
    print("Setting up Redis...")
    try:
        subprocess.run(["redis-cli", "ping"], check=True, stdout=subprocess.PIPE)
        print("Redis is running.")
    except subprocess.CalledProcessError:
        print("Error: Redis is not installed or not running.")
        print("Please install Redis and start the Redis server.")
        sys.exit(1)
    except Exception as e:
        print(f"Error checking Redis: {str(e)}")
        sys.exit(1)

def main():
    print("Setting up Image Processing System...")
    
    if not os.path.exists("venv"):
        print("Creating virtual environment...")
        subprocess.run(["python", "-m", "venv", "venv"], check=True)
    
    if sys.platform == 'win32':
        activate_cmd = "venv\\Scripts\\activate"
    else:
        activate_cmd = "source venv/bin/activate"
    
    print("Installing dependencies...")
    try:
        subprocess.run(
            f"{activate_cmd} && pip install -r requirements.txt", 
            shell=True, 
            check=True
        )
    except subprocess.CalledProcessError:
        print("Error installing dependencies.")
        sys.exit(1)
    
    setup_database()
    
    setup_redis()
    
    print("\nSetup completed successfully!")
    print("\nTo start the application:")
    print("1. Start the Flask server:")
    print("   python run.py")
    print("2. In a separate terminal, start the Celery worker:")
    print("   celery -A app.workers worker --loglevel=info")

if __name__ == "__main__":
    main()