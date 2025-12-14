import sys
import bcrypt
from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models

def get_password_hash(password: str) -> str:
    # Truncate password to 72 bytes if it's too long (bcrypt limit)
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    # Direct bcrypt hashing
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def create_user(username: str, email: str, password: str, full_name: str, role: str = "student"):
    """
    Create a new user in the database with the given credentials.
    
    Args:
        username (str): Unique username
        email (str): User's email address
        password (str): Plain text password (will be hashed)
        full_name (str): User's full name
        role (str): User role (student, teacher, or admin)
    """
    db = SessionLocal()
    
    try:
        # Check if user already exists
        if db.query(models.User).filter(models.User.username == username).first():
            print(f"❌ Error: Username '{username}' already exists.")
            return False
            
        if db.query(models.User).filter(models.User.email == email).first():
            print(f"❌ Error: Email '{email}' is already registered.")
            return False
        
        # Create new user with hashed password
        hashed_password = get_password_hash(password)
        db_user = models.User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
            role=role,
            is_active=True
        )
        
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        print(f"✅ Successfully created {role} user: {username}")
        return True
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error creating user: {str(e)}")
        return False
        
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python create_user.py <username> <email> <password> <full_name> [role]")
        print("Example: python create_user.py admin admin@example.com admin123 Admin User admin")
        sys.exit(1)
        
    username = sys.argv[1]
    email = sys.argv[2]
    password = sys.argv[3]
    full_name = sys.argv[4]
    role = sys.argv[5] if len(sys.argv) > 5 else "student"
    
    # Validate role
    if role not in ["student", "teacher", "admin"]:
        print("❌ Error: Role must be one of: student, teacher, admin")
        sys.exit(1)
    
    create_user(username, email, password, full_name, role)
