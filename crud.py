from sqlalchemy.orm import Session
from typing import List
import models
import schemas
import bcrypt

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def create_user(db: Session, user: schemas.UserCreate):
    # Hash the password
    hashed_password = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt())
    
    # Create user object
    db_user = models.User(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        hashed_password=hashed_password.decode('utf-8'),
        is_active=True
    )
    
    # Add to database
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def create_course(db: Session, course: schemas.CourseCreate):
    db_course = models.Course(**course.dict())
    db.add(db_course)
    db.commit()
    db.refresh(db_course)
    return db_course

def add_students_to_course(db: Session, course_id: int, student_ids: List[int]):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        return None
    
    # Get existing student IDs to avoid duplicates
    existing_student_ids = {s.id for s in course.students}
    
    # Get new students to add
    new_students = db.query(models.User).filter(
        models.User.id.in_(student_ids),
        models.User.role == "student",
        ~models.User.id.in_(existing_student_ids)
    ).all()
    
    # Add new enrollments
    for student in new_students:
        enrollment = models.Enrollment(
            student_id=student.id,
            course_id=course.id
        )
        db.add(enrollment)
    
    db.commit()
    db.refresh(course)
    return course

def assign_teacher_to_course(db: Session, course_id: int, teacher_id: int):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    teacher = db.query(models.User).filter(models.User.id == teacher_id, models.User.role == "teacher").first()
    if not course or not teacher:
        return None
    course.teacher = teacher
    db.commit()
    db.refresh(course)
    return course

def get_course(db: Session, course_id: int):
    return db.query(models.Course).filter(models.Course.id == course_id).first()

def remove_student_from_course(db: Session, course_id: int, student_id: int):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        return None
    # Delete enrollment record(s) for this student and course
    db.query(models.Enrollment).filter(
        models.Enrollment.course_id == course_id,
        models.Enrollment.student_id == student_id
    ).delete(synchronize_session=False)
    db.commit()
    db.refresh(course)
    return course

def unassign_teacher_from_course(db: Session, course_id: int):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        return None
    course.teacher = None
    db.commit()
    db.refresh(course)
    return course