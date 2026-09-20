import enum
from sqlalchemy import Column, Integer, String, BigInteger, Date, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class TransactionType(str, enum.Enum):
    INCOME = "INCOME"       # درآمد
    EXPENSE = "EXPENSE"     # هزینه
    TRANSFER = "TRANSFER"   # انتقال


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)

    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    destination_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)

    # کلیدهای خارجی اسناد و اشخاص
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # <-- شناسه کاربر مالک

    person_id = Column(Integer, ForeignKey("persons.id"), nullable=True)
    debt_id = Column(Integer, ForeignKey("debts.id"), nullable=True)
    cheque_id = Column(Integer, ForeignKey("cheques.id"), nullable=True)

    # اطلاعات تراکنش
    type = Column(String(20), nullable=False)  # INCOME, EXPENSE, TRANSFER
    category = Column(String(50), nullable=False)
    amount = Column(BigInteger, nullable=False)
    trans_date = Column(Date, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    # --- روابط (Relationships) ---
    # ۱. حساب مبدأ (با رفع خطای تایپ با استفاده از رشته)
    account = relationship("Account", foreign_keys="Transaction.account_id", back_populates="transactions")

    # ۲. حساب مقصد (برای تراکنش‌های انتقال)
    destination_account = relationship("Account", foreign_keys="Transaction.destination_account_id")

    # ۳. طرف حساب
    person = relationship("Person", foreign_keys="Transaction.person_id")

    # ۴. بدهی / طلب مرتبط (در صورت تسویه)
    debt = relationship("Debt", foreign_keys="Transaction.debt_id")

    # ۵. چک مرتبط (در صورت وصول/خرج چک)
    cheque = relationship("Cheque", foreign_keys="Transaction.cheque_id")

    user = relationship("User", back_populates="transactions")
