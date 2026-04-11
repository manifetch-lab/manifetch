import uuid
from datetime import timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from backend.db.base import get_db
from backend.db.models import User
from backend.db.enums import Role
from backend.api.auth import require_admin

router      = APIRouter(prefix="/admin", tags=["admin"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserCreateDTO(BaseModel):
    username:     str
    password:     str
    role:         str
    display_name: str


# DÜZELTME: UserUpdateDTO artık gerçek bir PATCH endpoint'e sahip
class UserUpdateDTO(BaseModel):
    display_name: Optional[str] = None
    role:         Optional[str] = None


class UserResponseDTO(BaseModel):
    user_id:      str
    username:     str
    role:         str
    display_name: str
    is_active:    bool


@router.get("/users", response_model=list[UserResponseDTO])
def get_users(
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_admin),
):
    users = db.query(User).all()
    return [
        UserResponseDTO(
            user_id      = u.user_id,
            username     = u.username,
            role         = u.role,
            display_name = u.display_name,
            is_active    = u.is_active,
        )
        for u in users
    ]


@router.post("/users", response_model=UserResponseDTO, status_code=201)
def create_user(
    payload:      UserCreateDTO,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_admin),
):
    if payload.role not in [r.value for r in Role]:
        raise HTTPException(status_code=400, detail=f"Geçersiz rol: {payload.role}")

    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="Bu kullanıcı adı zaten mevcut.")

    user = User(
        user_id       = str(uuid.uuid4()),
        username      = payload.username,
        password_hash = pwd_context.hash(payload.password),
        role          = payload.role,
        is_active     = True,
    )
    user.display_name = payload.display_name   # setter → şifreli
    db.add(user)
    db.commit()

    return UserResponseDTO(
        user_id      = user.user_id,
        username     = user.username,
        role         = user.role,
        display_name = user.display_name,
        is_active    = user.is_active,
    )


# DÜZELTME: UserUpdateDTO için endpoint eklendi — daha önce dead code'du
@router.patch("/users/{user_id}", response_model=UserResponseDTO)
def update_user(
    user_id:      str,
    payload:      UserUpdateDTO,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_admin),
):
    """Kullanıcı bilgilerini güncelle — sadece ADMINISTRATOR."""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

    if payload.display_name is not None:
        user.display_name = payload.display_name  # setter → şifreli

    if payload.role is not None:
        if payload.role not in [r.value for r in Role]:
            raise HTTPException(status_code=400, detail=f"Geçersiz rol: {payload.role}")
        user.role = payload.role

    db.commit()
    return UserResponseDTO(
        user_id      = user.user_id,
        username     = user.username,
        role         = user.role,
        display_name = user.display_name,
        is_active    = user.is_active,
    )


@router.patch("/users/{user_id}/deactivate")
def deactivate_user(
    user_id:      str,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_admin),
):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    if user.user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Kendinizi deaktif edemezsiniz.")
    user.is_active = False
    db.commit()
    return {"status": "deactivated", "user_id": user_id}


@router.patch("/users/{user_id}/activate")
def activate_user(
    user_id:      str,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_admin),
):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    user.is_active = True
    db.commit()
    return {"status": "activated", "user_id": user_id}