from sqlalchemy import Column, Integer, String, DateTime, func, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=True)
    is_admin = Column(Boolean, default=False)
    telegram_chat_id = Column(String(50), nullable=True)  # <-- شناسه چت یا آیدی عددی تلگرام
    last_seen = Column(DateTime, default=func.now(), onupdate=func.now())




    created_at = Column(DateTime, default=func.now())

    debts = relationship("Debt", back_populates="user", cascade="all, delete-orphan")
    cheques = relationship("Cheque", back_populates="user", cascade="all, delete-orphan")
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    person = relationship("Person", back_populates="user", cascade="all, delete-orphan")
