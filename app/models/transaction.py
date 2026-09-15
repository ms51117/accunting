from sqlalchemy import Column, Integer, String, BigInteger, Date, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    type = Column(String(20), nullable=False) # 'INCOME' (درآمد), 'EXPENSE' (هزینه), 'TRANSFER' (انتقال)
    category = Column(String(50), nullable=False) # دسته بندی: حقوق، فروش ملک، اجاره، سوپرمارکت و...
    amount = Column(BigInteger, nullable=False) # ریال
    trans_date = Column(Date, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    account = relationship("Account", back_populates="transactions")
