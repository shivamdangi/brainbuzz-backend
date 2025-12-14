from pydantic import BaseModel, EmailStr
from typing import Optional, List, ForwardRef
from datetime import datetime

# User schemas
class UserBase(BaseModel):
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    role: str

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = None

class UserInDB(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True

# Add User model that matches the database model
class User(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True

# Token schemas
class Token(BaseModel):
    access_token: str
    token_type: str
    role: str

class TokenData(BaseModel):
    username: Optional[str] = None

# Course schemas
class CourseBase(BaseModel):
    title: str
    description: Optional[str] = None

class CourseCreate(CourseBase):
    pass

class Course(CourseBase):
    id: int
    teacher_id: Optional[int] = None
    teacher: Optional[User] = None
    students: List[User] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

# Update forward references after all models are defined
User.update_forward_refs()
Course.update_forward_refs()

# Enrollment schemas
class EnrollmentBase(BaseModel):
    student_id: int
    course_id: int

class EnrollmentCreate(EnrollmentBase):
    pass

class Enrollment(EnrollmentBase):
    id: int
    enrolled_at: datetime

    class Config:
        orm_mode = True

# Announcement schemas
class AnnouncementBase(BaseModel):
    title: str
    content: str
    type: Optional[str] = "communication"  # 'communication' | 'class_schedule'
    class_link: Optional[str] = None

class AnnouncementCreate(AnnouncementBase):
    pass

class Announcement(AnnouncementBase):
    id: int
    course_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class AnnouncementOut(Announcement):
    read: bool = False
    read_at: Optional[datetime] = None

# Web Push schemas
class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str

class PushSubscriptionIn(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys

# Course Material schemas
class CourseMaterialBase(BaseModel):
    title: str
    description: Optional[str] = None
    file_path: str
    material_type: str

class CourseMaterialCreate(CourseMaterialBase):
    pass

class CourseMaterial(CourseMaterialBase):
    id: int
    course_id: int
    created_at: datetime

    class Config:
        orm_mode = True
