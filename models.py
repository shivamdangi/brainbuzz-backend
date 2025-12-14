from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Table
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    role = Column(String)  # 'student', 'teacher', or 'admin'
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    courses_teaching = relationship("Course", back_populates="teacher")
    enrollments = relationship("Enrollment", back_populates="student")
    enrolled_courses = relationship(
        "Course",
        secondary="enrollments",
        primaryjoin="User.id == Enrollment.student_id",
        secondaryjoin="Course.id == Enrollment.course_id",
        back_populates="students"
    )

class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(String)
    teacher_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    teacher = relationship("User", back_populates="courses_teaching")
    enrollments = relationship("Enrollment", back_populates="course")
    students = relationship(
        "User",
        secondary="enrollments",
        primaryjoin="Course.id == Enrollment.course_id",
        secondaryjoin="User.id == Enrollment.student_id",
        back_populates="enrolled_courses"
    )
    announcements = relationship("Announcement", back_populates="course")
    materials = relationship("CourseMaterial", back_populates="course")

class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"))
    course_id = Column(Integer, ForeignKey("courses.id"))
    enrolled_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    student = relationship("User", back_populates="enrollments", overlaps="enrolled_courses")
    course = relationship("Course", back_populates="enrollments", overlaps="students,enrolled_courses")

class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    content = Column(String)
    type = Column(String, default="communication")  # 'communication' or 'class_schedule'
    class_link = Column(String, nullable=True)
    course_id = Column(Integer, ForeignKey("courses.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    course = relationship("Course", back_populates="announcements")

class AnnouncementRead(Base):
    __tablename__ = "announcement_reads"

    id = Column(Integer, primary_key=True, index=True)
    announcement_id = Column(Integer, ForeignKey("announcements.id"), index=True)
    student_id = Column(Integer, ForeignKey("users.id"), index=True)
    read_at = Column(DateTime, default=datetime.utcnow)

class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    endpoint = Column(String)
    p256dh = Column(String)
    auth = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class CourseMaterial(Base):
    __tablename__ = "course_materials"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(String)
    file_path = Column(String)
    course_id = Column(Integer, ForeignKey("courses.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    material_type = Column(String)  # 'note', 'file', 'link', etc.

    # Relationships
    course = relationship("Course", back_populates="materials")
