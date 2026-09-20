from sqlalchemy import Column, Integer, String, BigInteger, Date, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class DebtType(str, enum.Enum):
    RECEIVABLE = "RECEIVABLE"
    PAYABLE = "PAYABLE"

class DebtStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SETTLED = "SETTLED"

class Debt(Base):
    __tablename__ = "debts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)  # <-- شناسه کاربر مالک

    type = Column(String(20), nullable=False) # 'RECEIVABLE' (طلبکاری ما از شخص), 'PAYABLE' (بدهکاری ما به شخص)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    amount = Column(BigInteger, nullable=False)
    paid_amount = Column(BigInteger, default=0) # مقدار تسویه شده
    due_date = Column(Date, nullable=True)
    status = Column(String(20), default="ACTIVE") # 'ACTIVE' (تسویه نشده), 'SETTLED' (کاملا تسویه شده)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    person = relationship("Person", back_populates="debts")
    transactions = relationship("Transaction", back_populates="debt", cascade="all, delete-orphan")
    user = relationship("User", back_populates="debts")


