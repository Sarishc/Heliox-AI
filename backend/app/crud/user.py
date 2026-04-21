"""CRUD operations for User model."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.auth.security import get_password_hash

_PASSWORD_RESET_EXPIRE_MINUTES = 60
_VERIFICATION_EXPIRE_HOURS = 24


def _hash_token(raw_token: str) -> str:
    """SHA-256 hash a raw token before storing — safe even if column leaks."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


class CRUDUser(CRUDBase[User, UserCreate, UserUpdate]):
    """CRUD operations for User model."""

    def get_by_email(self, db: Session, *, email: str) -> Optional[User]:
        """
        Get a user by email.

        Args:
            db: Database session
            email: User email

        Returns:
            User instance or None if not found
        """
        return db.query(User).filter(User.email == email).first()

    def create(self, db: Session, *, obj_in: UserCreate) -> User:
        """
        Create a new user with hashed password.

        Args:
            db: Database session
            obj_in: UserCreate schema

        Returns:
            Created User instance
        """
        db_obj = User(
            email=obj_in.email,
            hashed_password=get_password_hash(obj_in.password),
            full_name=obj_in.full_name,
            is_active=obj_in.is_active,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, *, db_obj: User, obj_in: UserUpdate) -> User:
        """
        Update user with password hashing if password is changed.

        Args:
            db: Database session
            db_obj: Existing User instance
            obj_in: UserUpdate schema

        Returns:
            Updated User instance
        """
        update_data = obj_in.model_dump(exclude_unset=True)

        # Hash password if it's being updated
        if "password" in update_data:
            update_data["hashed_password"] = get_password_hash(update_data["password"])
            del update_data["password"]

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def authenticate(self, db: Session, *, email: str, password: str) -> Optional[User]:
        """
        Authenticate a user.

        Args:
            db: Database session
            email: User email
            password: Plain text password

        Returns:
            User instance if authentication successful, None otherwise
        """
        from app.auth.security import verify_password

        user = self.get_by_email(db, email=email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    def is_active(self, user: User) -> bool:
        """Check if user is active."""
        return user.is_active

    # ------------------------------------------------------------------
    # Password reset
    # ------------------------------------------------------------------

    def create_password_reset_token(self, db: Session, *, user: User) -> str:
        """
        Generate a password reset token, store its SHA-256 hash, return the raw token.

        The raw token is sent to the user via email.  Only the hash is persisted
        so that a DB leak cannot be used directly to reset passwords.
        """
        raw_token = secrets.token_urlsafe(48)
        user.password_reset_token = _hash_token(raw_token)
        user.password_reset_token_expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=_PASSWORD_RESET_EXPIRE_MINUTES
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return raw_token

    def get_by_password_reset_token(self, db: Session, *, raw_token: str) -> Optional[User]:
        """Look up a user by a raw (unhashed) reset token."""
        hashed = _hash_token(raw_token)
        return db.query(User).filter(User.password_reset_token == hashed).first()

    def reset_password(self, db: Session, *, user: User, new_password: str) -> User:
        """Apply new password and invalidate the reset token."""
        user.hashed_password = get_password_hash(new_password)
        user.password_reset_token = None
        user.password_reset_token_expires_at = None
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    # ------------------------------------------------------------------
    # Email verification
    # ------------------------------------------------------------------

    def create_email_verification_token(self, db: Session, *, user: User) -> str:
        """Generate an email verification token, store hash, return raw token."""
        raw_token = secrets.token_urlsafe(48)
        user.email_verification_token = _hash_token(raw_token)
        user.email_verified = False
        db.add(user)
        db.commit()
        db.refresh(user)
        return raw_token

    def get_by_email_verification_token(self, db: Session, *, raw_token: str) -> Optional[User]:
        """Look up a user by a raw (unhashed) verification token."""
        hashed = _hash_token(raw_token)
        return db.query(User).filter(User.email_verification_token == hashed).first()

    def mark_email_verified(self, db: Session, *, user: User) -> User:
        """Mark the user's email as verified and clear the token."""
        user.email_verified = True
        user.email_verification_token = None
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


user = CRUDUser(User)
