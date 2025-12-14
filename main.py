from fastapi import FastAPI, Depends, HTTPException, status
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from pydantic import BaseModel
import uvicorn
from typing import List, Optional, Dict, Set
from database import engine, get_db, Base
import models, schemas, auth, crud
from sqlalchemy import text
import os
try:
    from pywebpush import webpush, WebPushException
except Exception:
    webpush = None

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="BrainBuzz API", version="1.0.0")

# Best-effort lightweight migration for new columns on existing DBs
@app.on_event("startup")
def _ensure_announcement_columns():
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE announcements ADD COLUMN type VARCHAR"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE announcements ADD COLUMN class_link VARCHAR"))
        except Exception:
            pass
        try:
            conn.execute(text("UPDATE announcements SET type='communication' WHERE type IS NULL"))
        except Exception:
            pass
 
# Simple in-memory WS connection manager per course for announcements
class AnnouncementWSManager:
    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, course_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.setdefault(course_id, set()).add(websocket)

    def disconnect(self, course_id: int, websocket: WebSocket):
        if course_id in self.active_connections and websocket in self.active_connections[course_id]:
            self.active_connections[course_id].remove(websocket)
            if not self.active_connections[course_id]:
                del self.active_connections[course_id]

    async def broadcast_new(self, course_id: int, payload: dict):
        for ws in self.active_connections.get(course_id, set()):
            try:
                await ws.send_json({"type": "announcement:new", **payload})
            except Exception:
                # best-effort
                pass

ws_manager = AnnouncementWSManager()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authentication endpoints
@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = auth.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "role": user.role
    }

@app.get("/users/me/", response_model=schemas.UserInDB)
async def read_users_me(current_user: schemas.UserInDB = Depends(auth.get_current_active_user)):
    return current_user

# User endpoints
@app.post("/users/", response_model=schemas.UserInDB)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = auth.get_user(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        full_name=user.full_name,
        role=user.role
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# Course endpoints
@app.get("/courses", response_model=List[schemas.Course])
def read_courses(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db),
    current_user: schemas.UserInDB = Depends(auth.get_current_active_user)
):
    """Get all courses (for teachers/admins) or enrolled courses (for students)"""
    if current_user.role in ["teacher", "admin"]:
        courses = db.query(models.Course).offset(skip).limit(limit).all()
    else:
        # For students, only return their enrolled courses
        courses = current_user.enrolled_courses
    return courses

@app.get("/student/courses", response_model=List[schemas.Course])
def get_student_courses(
    skip: int = 0, 
    limit: int = 100, 
    current_user: schemas.UserInDB = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all courses for the logged-in student"""
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can access this endpoint"
        )
    return db.query(models.Course).join(
        models.Enrollment, 
        models.Enrollment.course_id == models.Course.id
    ).filter(
        models.Enrollment.student_id == current_user.id
    ).offset(skip).limit(limit).all()

@app.get("/teacher/courses", response_model=List[schemas.Course])
def get_teacher_courses(
    skip: int = 0,
    limit: int = 100,
    current_user: schemas.UserInDB = Depends(auth.get_current_teacher),
    db: Session = Depends(get_db)
):
    """Get all courses taught by the logged-in teacher"""
    try:
        print(f"Fetching courses for teacher ID: {current_user.id}")
        courses = db.query(models.Course).filter(
            models.Course.teacher_id == current_user.id
        ).offset(skip).limit(limit).all()
        
        print(f"Found {len(courses)} courses for teacher {current_user.id}")
        for course in courses:
            print(f"Course: {course.title}, ID: {course.id}")
            
        return courses
    except Exception as e:
        print(f"Error in get_teacher_courses: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/teacher/courses/{course_id}/students", response_model=List[schemas.User])
def teacher_list_students(
    course_id: int,
    current_user: schemas.UserInDB = Depends(auth.get_current_teacher),
    db: Session = Depends(get_db)
):
    """List students enrolled in a course (teacher who owns the course or admin)"""
    course = crud.get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if current_user.role != "admin" and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this course")
    return course.students

@app.post("/courses/", response_model=schemas.Course)
def create_course(
    course: schemas.CourseCreate, 
    db: Session = Depends(get_db),
    current_user: schemas.UserInDB = Depends(auth.get_current_teacher)
):
    db_course = models.Course(**course.dict(), teacher_id=current_user.id)
    db.add(db_course)
    db.commit()
    db.refresh(db_course)
    return db_course

# Admin endpoints
@app.get("/admin/users", response_model=List[schemas.User])
def get_all_users(
    current_user: schemas.UserInDB = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    """Get all users (admin only)"""
    return db.query(models.User).all()

@app.post("/admin/users", response_model=schemas.User)
def create_user_admin(
    user: schemas.UserCreate,
    current_user: schemas.UserInDB = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    """Create a new user (admin only)"""
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db=db, user=user)

@app.get("/admin/stats")
def get_admin_stats(
    current_user: schemas.UserInDB = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    """Return aggregate platform stats for admin dashboard"""
    total_users = db.query(models.User).count()
    total_students = db.query(models.User).filter(models.User.role == "student").count()
    total_teachers = db.query(models.User).filter(models.User.role == "teacher").count()
    total_courses = db.query(models.Course).count()
    return {
        "total_users": total_users,
        "total_students": total_students,
        "total_teachers": total_teachers,
        "total_courses": total_courses,
    }

@app.post("/admin/courses", response_model=schemas.Course)
def create_course(
    course: schemas.CourseCreate,
    current_user: schemas.UserInDB = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    """Create a new course (admin only)"""
    return crud.create_course(db=db, course=course)

class StudentIds(BaseModel):
    student_ids: List[int]

@app.post("/admin/courses/{course_id}/students", response_model=schemas.Course)
def add_students_to_course(
    course_id: int,
    student_data: StudentIds,
    current_user: schemas.UserInDB = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    """Add students to a course (admin only)"""
    return crud.add_students_to_course(db=db, course_id=course_id, student_ids=student_data.student_ids)

@app.get("/admin/courses/{course_id}", response_model=schemas.Course)
def get_course_details(
    course_id: int,
    current_user: schemas.UserInDB = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    """Get a single course with its teacher and students (admin only)"""
    course = crud.get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course

# ---------------------- Announcement Endpoints ----------------------

@app.get("/teacher/courses/{course_id}/announcements", response_model=List[schemas.Announcement])
def teacher_list_announcements(
    course_id: int,
    current_user: schemas.UserInDB = Depends(auth.get_current_teacher),
    db: Session = Depends(get_db)
):
    course = crud.get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if current_user.role != "admin" and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this course")
    return db.query(models.Announcement).filter(models.Announcement.course_id == course_id).order_by(models.Announcement.created_at.desc()).all()


@app.post("/teacher/courses/{course_id}/announcements", response_model=schemas.Announcement)
async def teacher_create_announcement(
    course_id: int,
    payload: schemas.AnnouncementCreate,
    current_user: schemas.UserInDB = Depends(auth.get_current_teacher),
    db: Session = Depends(get_db)
):
    course = crud.get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if current_user.role != "admin" and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this course")
    if payload.type not in ["communication", "class_schedule"]:
        raise HTTPException(status_code=422, detail="Invalid announcement type")
    if payload.type == "class_schedule" and not payload.class_link:
        raise HTTPException(status_code=422, detail="class_link is required for class_schedule")

    db_item = models.Announcement(
        title=payload.title,
        content=payload.content,
        type=payload.type,
        class_link=payload.class_link,
        course_id=course_id,
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    # notify WS clients
    await ws_manager.broadcast_new(course_id, {
        "announcement": {
            "id": db_item.id,
            "title": db_item.title,
            "content": db_item.content,
            "type": db_item.type,
            "class_link": db_item.class_link,
            "course_id": db_item.course_id,
            "created_at": db_item.created_at.isoformat(),
        }
    })

    # send Web Push to enrolled students (best-effort)
    try:
        await _send_push_to_course(db, course_id, db_item)
    except Exception:
        pass
    return db_item


@app.get("/student/courses/{course_id}/announcements", response_model=List[schemas.AnnouncementOut])
def student_list_announcements(
    course_id: int,
    current_user: schemas.UserInDB = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can access this endpoint")
    # Ensure enrolled
    enrolled = db.query(models.Enrollment).filter(
        models.Enrollment.course_id == course_id,
        models.Enrollment.student_id == current_user.id
    ).first()
    if not enrolled:
        raise HTTPException(status_code=403, detail="Not enrolled in this course")

    anns = db.query(models.Announcement).filter(models.Announcement.course_id == course_id).order_by(models.Announcement.created_at.desc()).all()
    read_map = {
        r.announcement_id: r for r in db.query(models.AnnouncementRead).filter(
            models.AnnouncementRead.student_id == current_user.id,
            models.AnnouncementRead.announcement_id.in_([a.id for a in anns])
        ).all()
    }
    out: List[schemas.AnnouncementOut] = []
    for a in anns:
        r = read_map.get(a.id)
        out.append(schemas.AnnouncementOut(
            id=a.id,
            title=a.title,
            content=a.content,
            type=a.type,
            class_link=a.class_link,
            course_id=a.course_id,
            created_at=a.created_at,
            updated_at=a.updated_at,
            read=bool(r),
            read_at=r.read_at if r else None
        ))
    return out


@app.post("/student/courses/{course_id}/announcements/{announcement_id}/read")
def student_mark_read(
    course_id: int,
    announcement_id: int,
    current_user: schemas.UserInDB = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can access this endpoint")
    # Ensure announcement exists and belongs to course
    ann = db.query(models.Announcement).filter(
        models.Announcement.id == announcement_id,
        models.Announcement.course_id == course_id
    ).first()
    if not ann:
        raise HTTPException(status_code=404, detail="Announcement not found")

    # Upsert read record
    existing = db.query(models.AnnouncementRead).filter(
        models.AnnouncementRead.announcement_id == announcement_id,
        models.AnnouncementRead.student_id == current_user.id
    ).first()
    if not existing:
        read = models.AnnouncementRead(announcement_id=announcement_id, student_id=current_user.id)
        db.add(read)
        db.commit()
    return {"status": "ok"}


@app.websocket("/ws/courses/{course_id}/announcements")
async def announcements_ws(websocket: WebSocket, course_id: int):
    await ws_manager.connect(course_id, websocket)
    try:
        while True:
            # Keep connection alive; we don't expect messages from clients now
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(course_id, websocket)

# ---------------------- SPA catch-alls (frontend reload) ----------------------

@app.get("/teacher/dashboard/{rest_of_path:path}")
def spa_teacher_catch_all(rest_of_path: str):
    return {"spa": True, "path": f"/teacher/dashboard/{rest_of_path}"}

@app.get("/student/dashboard/{rest_of_path:path}")
def spa_student_catch_all(rest_of_path: str):
    return {"spa": True, "path": f"/student/dashboard/{rest_of_path}"}

# ---------------------- Web Push endpoints ----------------------

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "BMRhTXv_NwvWrmvl027uq38yixTx41uzx_Wy5J3G_Mt462ueDW4o64GK3rXd7Td41Umtmqy8LuV-YZyMSDRjuqI")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "Jymh4kq_h_0NMoshejapR8KAJ3KGqKEnnqRHcJaxdwc")
VAPID_CLAIMS = {"sub": os.getenv("VAPID_SUBJECT", "mailto:info.brainbuzz.academy@gmail.com")}

@app.get("/push/public-key")
def get_push_public_key():
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=404, detail="VAPID public key not configured")
    return {"publicKey": VAPID_PUBLIC_KEY}

@app.post("/push/subscribe")
def push_subscribe(
    payload: schemas.PushSubscriptionIn,
    current_user: schemas.UserInDB = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    # upsert by endpoint for this user
    existing = db.query(models.PushSubscription).filter(
        models.PushSubscription.user_id == current_user.id,
        models.PushSubscription.endpoint == payload.endpoint
    ).first()
    if existing:
        existing.p256dh = payload.keys.p256dh
        existing.auth = payload.keys.auth
    else:
        sub = models.PushSubscription(
            user_id=current_user.id,
            endpoint=payload.endpoint,
            p256dh=payload.keys.p256dh,
            auth=payload.keys.auth,
        )
        db.add(sub)
    db.commit()
    return {"status": "subscribed"}

@app.delete("/push/subscribe")
def push_unsubscribe(
    endpoint: str,
    current_user: schemas.UserInDB = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    db.query(models.PushSubscription).filter(
        models.PushSubscription.user_id == current_user.id,
        models.PushSubscription.endpoint == endpoint
    ).delete(synchronize_session=False)
    db.commit()
    return {"status": "unsubscribed"}

def _webpush_send(subscription: dict, data: dict):
    if not webpush or not VAPID_PUBLIC_KEY or not VAPID_PRIVATE_KEY:
        return
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(data),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS,
        )
    except Exception:
        pass

import json
async def _send_push_to_course(db: Session, course_id: int, ann: models.Announcement):
    # Find enrolled student IDs
    student_ids = [e.student_id for e in db.query(models.Enrollment).filter(models.Enrollment.course_id == course_id).all()]
    if not student_ids:
        return
    subs = db.query(models.PushSubscription).filter(models.PushSubscription.user_id.in_(student_ids)).all()
    if not subs:
        return
    title = "Class scheduled: {}".format(ann.title) if ann.type == "class_schedule" else "New announcement: {}".format(ann.title)
    body = (ann.content or "")
    url = ann.class_link if ann.class_link else None
    payload = {"title": title, "body": body, "url": url}
    for s in subs:
        _webpush_send({
            "endpoint": s.endpoint,
            "keys": {"p256dh": s.p256dh, "auth": s.auth}
        }, payload)

@app.delete("/admin/courses/{course_id}/students/{student_id}", response_model=schemas.Course)
def remove_student_from_course(
    course_id: int,
    student_id: int,
    current_user: schemas.UserInDB = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    """Remove a student from a course (admin only)"""
    course = crud.remove_student_from_course(db, course_id, student_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course

class TeacherAssignment(BaseModel):
    teacher_id: int

@app.post("/admin/courses/{course_id}/teacher", response_model=schemas.Course)
def assign_teacher_to_course(
    course_id: int,
    teacher_data: TeacherAssignment,
    current_user: schemas.UserInDB = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    """Assign teacher to a course (admin only)"""
    return crud.assign_teacher_to_course(db=db, course_id=course_id, teacher_id=teacher_data.teacher_id)

@app.delete("/admin/courses/{course_id}/teacher", response_model=schemas.Course)
def unassign_teacher(
    course_id: int,
    current_user: schemas.UserInDB = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    """Remove the assigned teacher from a course (admin only)"""
    course = crud.unassign_teacher_from_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
