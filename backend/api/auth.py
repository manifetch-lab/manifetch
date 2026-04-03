from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.db.models import User
from backend.db.enums import Role

import os
from dotenv import load_dotenv
load_dotenv()

# ── Konfigürasyon ─────────────────────────────────────────────────────────────
SECRET_KEY    = os.getenv("MANIFETCH_SECRET_KEY", "fallback_secret_key_change_in_prod")
ALGORITHM     = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 saat

pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
router        = APIRouter(prefix="/auth", tags=["auth"])


# ── Pydantic Modelleri ────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type:   str
    role:         str
    display_name: str
    user_id:      str


class TokenData(BaseModel):
    user_id:  Optional[str] = None
    username: Optional[str] = None
    role:     Optional[str] = None


class UserResponse(BaseModel):
    user_id:      str
    username:     str
    role:         str
    display_name: str
    is_active:    bool


# ── Yardımcı Fonksiyonlar ─────────────────────────────────────────────────────

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire    = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = get_user_by_username(db, username)
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


# ── Token Doğrulama ───────────────────────────────────────────────────────────

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db:    Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Kimlik doğrulaması başarısız.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload   = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id   = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


# ── RBAC Dependency'leri ──────────────────────────────────────────────────────

def require_any_role(current_user: User = Depends(get_current_user)) -> User:
    """Tüm roller erişebilir."""
    return current_user


def require_doctor(current_user: User = Depends(get_current_user)) -> User:
    """Sadece DOCTOR."""
    if current_user.role != Role.DOCTOR.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için doktor yetkisi gereklidir.",
        )
    return current_user


def require_nurse(current_user: User = Depends(get_current_user)) -> User:
    """DOCTOR veya NURSE."""
    if current_user.role not in [Role.DOCTOR.value, Role.NURSE.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için hemşire veya doktor yetkisi gereklidir.",
        )
    return current_user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Sadece ADMINISTRATOR."""
    if current_user.role != Role.ADMINISTRATOR.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için yönetici yetkisi gereklidir.",
        )
    return current_user


# ── Endpoint'ler ──────────────────────────────────────────────────────────────

@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db:        Session = Depends(get_db),
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanıcı adı veya şifre hatalı.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hesap aktif değil.",
        )

    token = create_access_token(data={
        "sub":      user.user_id,
        "username": user.username,
        "role":     user.role,
    })

    return Token(
        access_token = token,
        token_type   = "bearer",
        role         = user.role,
        display_name = user.display_name,
        user_id      = user.user_id,
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        user_id      = current_user.user_id,
        username     = current_user.username,
        role         = current_user.role,
        display_name = current_user.display_name,
        is_active    = current_user.is_active,
    )