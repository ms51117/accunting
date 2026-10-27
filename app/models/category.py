from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(100), nullable=False)
    type = Column(String(20), default="BOTH", nullable=False)  # INCOME, EXPENSE, BOTH
    color = Column(String(20), default="#3b82f6", nullable=False)  # Hex color code for badges/charts
    icon = Column(String(50), default="tag", nullable=False)  # Bootstrap icon name
    description = Column(Text, nullable=True)

    created_at = Column(DateTime, default=func.now())

    # روابط (Relationships)
    user = relationship("User", back_populates="categories")
    transactions = relationship("Transaction", back_populates="category_rel")
