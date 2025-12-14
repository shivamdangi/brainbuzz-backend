import sys
import os
from sqlalchemy.orm import Session
from database import engine, Base, SessionLocal
import models
import bcrypt

def init_db():
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Create a session
    db = SessionLocal()
    
    try:
        # Check if admin user already exists
        admin = db.query(models.User).filter(models.User.email == "admin@brainbuzz.com").first()
        if admin:
            print("Admin user already exists!")
            return
            
        # Create admin user
        password = "admin123"  # Default password, should be changed after first login
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        admin_user = models.User(
            username="admin",
            email="admin@brainbuzz.com",
            full_name="Admin User",
            role="admin",
            hashed_password=hashed_password.decode('utf-8'),
            is_active=True
        )
        
        db.add(admin_user)
        db.commit()
        print("Database initialized successfully!")
        print(f"Admin credentials:")
        print(f"Email: admin@brainbuzz.com")
        print(f"Password: {password}")
        
    except Exception as e:
        print(f"Error initializing database: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("Initializing database...")
    init_db()
