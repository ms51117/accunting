from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class Person(Base):
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)  # <-- شناسه کاربر مالک

    full_name = Column(String(150), nullable=False, index=True)
    phone = Column(String(30), nullable=True)
    sheba = Column(String(34), nullable=True)      # شماره شبا
    card_number = Column(String(20), nullable=True)# شماره کارت
    bank_name = Column(String(50), nullable=True)  # نام بانک حساب طرف
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    cheques = relationship("Cheque", back_populates="person")
    debts = relationship("Debt", back_populates="person")
    user = relationship("User", back_populates="person")

