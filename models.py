# models.py
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, Boolean, ForeignKey, Enum
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, scoped_session
from sqlalchemy.ext.hybrid import hybrid_property
from datetime import date
import enum
import os

# --- Define the Base Class ---
Base = declarative_base()

# --- Database Engine Setup (will be fully configured in database.py) ---
# The engine URL will be set elsewhere. This is just for the model definitions.

# --- Enum for Transaction Types ---
class TransactionType(enum.Enum):
    INCOME = "income"
    EXPENSE = "expense"

# --- Database Models ---

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    # In a real application, store a HASHED password, not plain text.
    # We will use cryptography for this.
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum('admin', 'viewer', name='user_roles'), nullable=False)

    def __repr__(self):
        return f'<User {self.username}>'

class Account(Base):
    __tablename__ = 'accounts'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    currency_code = Column(String(3), nullable=False)  # E.g., 'USD', 'INR'

    # Relationships
    transactions = relationship("Transaction", back_populates="account")

    def __repr__(self):
        return f'<Account {self.name} ({self.currency_code})>'

    # This is a "hybrid property". It can be used in Python and in database queries.
    @hybrid_property
    def balance(self):
        # Calculate the balance by summing all non-voided transactions for this account.
        # This is the Python-side calculation.
        total = 0.0
        for transaction in self.transactions:
            if not transaction.is_void:
                if transaction.type == TransactionType.INCOME.value:
                    total += transaction.amount
                else: # EXPENSE
                    total -= transaction.amount
        return total
    # Note: A more advanced implementation would add a SQL expression for this hybrid.

class ExchangeRate(Base):
    __tablename__ = 'exchange_rates'
    id = Column(Integer, primary_key=True)
    date = Column(Date, default=date.today, nullable=False)
    usd_to_inr = Column(Float, nullable=False)

    def __repr__(self):
        return f'<ExchangeRate {self.date}: 1 USD = {self.usd_to_inr} INR>'

class Category(Base):
    __tablename__ = 'categories'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)

    # Relationships
    transactions = relationship("Transaction", back_populates="category")
    split_transactions = relationship("TransactionSplit", back_populates="category")

    def __repr__(self):
        return f'<Category {self.name}>'

class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(Integer, primary_key=True)
    date = Column(Date, default=date.today, nullable=False)
    type = Column(Enum(TransactionType), nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String(255))
    counterparty = Column(String(100))
    is_void = Column(Boolean, default=False)

    # For Transfers: Lock the rate used and link the pair of transactions
    exchange_rate = Column(Float, nullable=True)
    transfer_id = Column(Integer, nullable=True)

    # Foreign Keys
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    category_id = Column(Integer, ForeignKey('categories.id'), nullable=False)

    # Relationships
    account = relationship("Account", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")
    splits = relationship("TransactionSplit", back_populates="parent_transaction", cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Transaction {self.date} {self.type.value} {self.amount} ({self.account.currency_code})>'

class TransactionSplit(Base):
    __tablename__ = 'transaction_splits'
    id = Column(Integer, primary_key=True)
    amount = Column(Float, nullable=False)
    description = Column(String(255))

    # Foreign Keys
    transaction_id = Column(Integer, ForeignKey('transactions.id'), nullable=False)
    category_id = Column(Integer, ForeignKey('categories.id'), nullable=False)

    # Relationships
    parent_transaction = relationship("Transaction", back_populates="splits")
    category = relationship("Category", back_populates="split_transactions")

    def __repr__(self):
        return f'<Split {self.amount} for {self.description}>'