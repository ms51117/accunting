from sqlalchemy import Column, Integer, String, BigInteger, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)  # <-- شناسه کاربر مالک

    title = Column(String(100), nullable=False) # مثلا: بانک ملی، پاسارگاد، صندوق منزل
    bank_name = Column(String(50), nullable=True)
    account_number = Column(String(30), nullable=True)
    card_number = Column(String(20), nullable=True)
    sheba = Column(String(34), nullable=True)
    balance = Column(BigInteger, default=0) # موجودی به ریال
    created_at = Column(DateTime, default=func.now())

    # transactions = relationship("Transaction", back_populates="account")
    cheques = relationship("Cheque", back_populates="account")

    # ✅ اصلاح این خط: اضافه کردن foreign_keys="Transaction.account_id"
    transactions = relationship(
        "Transaction",
        foreign_keys="Transaction.account_id",
        back_populates="account"
    )
    user = relationship("User", back_populates="accounts")

