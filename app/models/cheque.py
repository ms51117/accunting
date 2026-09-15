from sqlalchemy import Column, Integer, String, BigInteger, Date, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Cheque(Base):
    __tablename__ = "cheques"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(20), nullable=False)  # 'RECEIVABLE' (دریافتی), 'PAYABLE' (پرداختی)
    cheque_number = Column(String(50), nullable=False)
    sayad_number = Column(String(50), nullable=True)  # شناسه صیاد
    bank_name = Column(String(50), nullable=True)
    amount = Column(BigInteger, nullable=False)
    issue_date = Column(Date, nullable=False)  # تاریخ صدور
    due_date = Column(Date, nullable=False)  # تاریخ سررسید

    # وضعیت چک:
    # 'PENDING' (در جریان وصول)
    # 'CLEARED' (وصول شده)
    # 'BOUNCED' (برگشت خورده)
    # 'CANCELLED' (باطل شده)
    status = Column(String(20), default="PENDING")

    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"),
                        nullable=True)  # حسابی که چک به آن واریز یا از آن کسر می‌شود
    description = Column(Text, nullable=True)
    cleared_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=func.now())

    person = relationship("Person", back_populates="cheques")
    account = relationship("Account", back_populates="cheques")
