# database.py
from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.exc import IntegrityError
import os
from models import Base, User, Account, Category, TransactionType
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64
import secrets

# --- Define the database file path ---
# Create an 'instance' directory if it doesn't exist
basedir = os.path.abspath(os.path.dirname(__file__))
instance_path = os.path.join(basedir, 'instance')
os.makedirs(instance_path, exist_ok=True)

# Path to the SQLite database file
database_path = os.path.join(instance_path, 'app.db')
database_url = f'sqlite:///{database_path}'

# --- Create the SQLAlchemy engine and session factory ---
# The engine is the entry point to the database
engine = create_engine(database_url, connect_args={"check_same_thread": False})

# SessionFactory: a factory for creating new Session objects
SessionFactory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# ScopedSession: ensures a unique session per thread (important for web apps)
db_session = scoped_session(SessionFactory)

# --- Password Hashing Utility Functions ---
# Salt generation
def generate_salt():
    return secrets.token_bytes(16)

# Password hashing function
def hash_password(password, salt=None):
    if salt is None:
        salt = generate_salt()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    key = kdf.derive(password.encode())
    # Store the salt and the key together in a single string
    stored = base64.b64encode(salt + key).decode('utf-8')
    return stored

# Password verification function
def verify_password(stored_hash, provided_password):
    """Verify a provided password against a stored hash."""
    try:
        decoded = base64.b64decode(stored_hash)
        salt_from_db = decoded[:16] # First 16 bytes are the salt
        key_from_db = decoded[16:]  # The rest is the derived key

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt_from_db,
            iterations=100000,
            backend=default_backend()
        )
        new_key = kdf.derive(provided_password.encode())
        return new_key == key_from_db
    except Exception:
        return False

def fix_enum_data(session):
    """Fix enum values in the database if they're lowercase"""
    try:
        # Check if we have lowercase enum values
        result = session.execute(text("SELECT id, type FROM transactions WHERE type IN ('income', 'expense')"))
        problematic_records = result.fetchall()
        
        if problematic_records:
            print(f"Found {len(problematic_records)} records with lowercase enum values. Fixing...")
            
            # Update to uppercase
            session.execute(text("UPDATE transactions SET type = 'INCOME' WHERE type = 'income'"))
            session.execute(text("UPDATE transactions SET type = 'EXPENSE' WHERE type = 'expense'"))
            session.commit()
            print("Database enum values fixed!")
    except Exception as e:
        print(f"Error fixing enum data: {e}")
        session.rollback()

# --- Database Initialization Function ---
def init_db():
    """
    Creates all database tables and populates them with initial data.
    This function should be called once when the application is first set up.
    """
    # Import models to ensure they are registered with Base.metadata
    from models import Base, User, Account, Category

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create a new session for adding initial data
    session = db_session()

    try:
        # Fix any existing enum data issues first
        fix_enum_data(session)

        # --- 1. Create Default Accounts ---
        usd_account = session.query(Account).filter_by(currency_code='USD').first()
        inr_account = session.query(Account).filter_by(currency_code='INR').first()

        if not usd_account:
            usd_account = Account(name="US Business Account", currency_code="USD")
            session.add(usd_account)
            print("Created USD Account.")

        if not inr_account:
            inr_account = Account(name="India Business Account", currency_code="INR")
            session.add(inr_account)
            print("Created INR Account.")

        # --- 2. Create Default Categories ---
        default_categories = [
            "Client Revenue",
            "Software Expense",
            "Salary",
            "Office Supplies",
            "Marketing",
            "Contractor Fees",
            "Inter-Account Transfer In",  # Special category for transfers
            "Inter-Account Transfer Out", # Special category for transfers
            "Other Income",
            "Other Expense"
        ]

        for cat_name in default_categories:
            category = session.query(Category).filter_by(name=cat_name).first()
            if not category:
                category = Category(name=cat_name)
                session.add(category)
        print("Created default categories.")

        # --- 3. Create Default Users (Admin & Viewer) ---
        # Check if users already exist first
        admin_user = session.query(User).filter_by(username='admin').first()
        viewer_user = session.query(User).filter_by(username='viewer').first()

        # Hash the passwords
        admin_password_hash = hash_password("admin123")
        viewer_password_hash = hash_password("view123")

        if not admin_user:
            admin_user = User(
                username='admin',
                password_hash=admin_password_hash,
                role='admin'
            )
            session.add(admin_user)
            print("Created admin user.")

        if not viewer_user:
            viewer_user = User(
                username='viewer',
                password_hash=viewer_password_hash,
                role='viewer'
            )
            session.add(viewer_user)
            print("Created viewer user.")

        # Commit all changes to the database
        session.commit()
        print("Database initialized successfully.")

    except IntegrityError as e:
        session.rollback()
        print(f"An error occurred during initialization: {e}")
    except Exception as e:
        session.rollback()
        print(f"An unexpected error occurred: {e}")
    finally:
        session.close()

# Function to get a new database session
def get_db_session():
    """Provides a new database session from the scoped session."""
    return db_session()

# Function to close the database session
def close_db(e=None):
    """Closes the current database session. Important for cleaning up."""
    db_session.remove()

# If this script is run directly, initialize the database.
if __name__ == '__main__':
    init_db()
    print(f"Database created at: {database_path}")
    print("You can now run 'streamlit run app.py'")