"""
User model. A single `users` table holds both Faculty and Student accounts,
distinguished by `role`. This is a deliberate normalization choice: Faculty
and Student share almost every column (auth fields, name, email) and only
differ in a few optional attributes, so one table with nullable
role-specific columns avoids a join on every auth check while still keeping
the schema simple to extend later (see docs/README.md > Database Design).
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Enum, Boolean
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class UserRole(str, enum.Enum):
    FACULTY = "faculty"
    STUDENT = "student"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(String(150), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Student-specific (nullable for faculty)
    roll_number = Column(String(50), nullable=True, index=True)
    division = Column(String(20), nullable=True)
    batch = Column(String(20), nullable=True)

    # Faculty-specific (nullable for students)
    department = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"
