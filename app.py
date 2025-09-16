# app.py
import streamlit as st
from datetime import date, datetime, timedelta
import pandas as pd
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import requests
from sqlalchemy import func, case, and_, or_

# Import database and models
from database import db_session, init_db, verify_password, get_db_session, close_db
from models import User, Account, Transaction, ExchangeRate, Category, TransactionType, TransactionSplit

# --- Page Configuration ---
st.set_page_config(
    page_title="RoV Finance Portal",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Session State Initialization ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.role = None
    st.session_state.user_id = None
    st.session_state.force_rerun = False  # Flag to control reruns

# --- Helper Functions ---
def get_latest_exchange_rate():
    """Fetches and returns the latest USD to INR rate from the database."""
    session = get_db_session()
    try:
        latest_rate = session.query(ExchangeRate).order_by(ExchangeRate.date.desc()).first()
        if latest_rate:
            return latest_rate.usd_to_inr
        else:
            return fetch_and_store_exchange_rate()
    finally:
        session.close()

def fetch_and_store_exchange_rate():
    """Fetches the current USD/INR rate from Frankfurter.app and stores it in the DB."""
    try:
        response = requests.get("https://api.frankfurter.app/latest?from=USD&to=INR")
        response.raise_for_status()
        data = response.json()
        current_rate = data['rates']['INR']
        
        session = get_db_session()
        try:
            today = date.today()
            existing_rate = session.query(ExchangeRate).filter(ExchangeRate.date == today).first()
            if not existing_rate:
                new_rate = ExchangeRate(date=today, usd_to_inr=current_rate)
                session.add(new_rate)
                session.commit()
                st.success(f"Fetched and stored new exchange rate: 1 USD = {current_rate} INR")
            else:
                existing_rate.usd_to_inr = current_rate
                session.commit()
            return current_rate
        finally:
            session.close()
    except requests.RequestException as e:
        st.error(f"Failed to fetch exchange rate: {e}")
        return 83.0
    except Exception as e:
        st.error(f"An error occurred: {e}")
        return 83.0

def get_account_balance(account_id):
    """Calculates the current balance for a given account ID."""
    session = get_db_session()
    try:
        account = session.query(Account).filter(Account.id == account_id).first()
        if account:
            return account.balance
        return 0.0
    finally:
        session.close()

def get_profit_loss_data(months=6):
    """Gets Income and Expense data for the last 'n' months for the chart."""
    session = get_db_session()
    try:
        start_date = date.today() - timedelta(days=30*months)
        
        results = session.query(
            func.strftime("%Y-%m", Transaction.date).label('month'),
            Transaction.type,
            func.sum(Transaction.amount).label('total_amount')
        ).filter(
            Transaction.date >= start_date,
            Transaction.is_void == False
        ).group_by('month', Transaction.type).all()

        df = pd.DataFrame(results, columns=['month', 'type', 'total_amount'])
        
        if not df.empty:
            df_pivot = df.pivot(index='month', columns='type', values='total_amount').fillna(0)
            for t in [TransactionType.INCOME.value, TransactionType.EXPENSE.value]:
                if t not in df_pivot.columns:
                    df_pivot[t] = 0.0
            return df_pivot
        else:
            return pd.DataFrame(columns=['month', TransactionType.INCOME.value, TransactionType.EXPENSE.value])
    finally:
        session.close()

def get_income_by_counterparty():
    """Gets data for the Income Sources pie chart."""
    session = get_db_session()
    try:
        results = session.query(
            Transaction.counterparty,
            func.sum(Transaction.amount).label('total_income')
        ).filter(
            Transaction.type == TransactionType.INCOME.value,
            Transaction.is_void == False,
            Transaction.counterparty.isnot(None),
            Transaction.counterparty != ''
        ).group_by(Transaction.counterparty).all()
        
        return pd.DataFrame(results, columns=['counterparty', 'total_income'])
    finally:
        session.close()

def get_expenses_by_category():
    """Gets data for the Expenses pie chart."""
    session = get_db_session()
    try:
        results = session.query(
            Category.name,
            func.sum(Transaction.amount).label('total_expense')
        ).join(Transaction.category).filter(
            Transaction.type == TransactionType.EXPENSE.value,
            Transaction.is_void == False,
            Category.name.notlike('%Transfer%')
        ).group_by(Category.name).all()
        
        return pd.DataFrame(results, columns=['category', 'total_expense'])
    finally:
        session.close()

def get_all_categories():
    """Returns a list of all categories for dropdowns."""
    session = get_db_session()
    try:
        categories = session.query(Category).order_by(Category.name).all()
        return {cat.name: cat.id for cat in categories}
    finally:
        session.close()

def get_all_accounts():
    """Returns a list of all accounts for dropdowns."""
    session = get_db_session()
    try:
        accounts = session.query(Account).order_by(Account.name).all()
        return {f"{acc.name} ({acc.currency_code})": acc.id for acc in accounts}
    finally:
        session.close()

def void_transaction(transaction_id):
    """Soft-deletes a transaction by marking it as void."""
    session = get_db_session()
    try:
        transaction = session.query(Transaction).filter(Transaction.id == transaction_id).first()
        if transaction:
            transaction.is_void = True
            session.commit()
            st.success("Transaction voided successfully.")
            st.session_state.force_rerun = True  # Set flag to trigger rerun
        else:
            st.error("Transaction not found.")
    except Exception as e:
        session.rollback()
        st.error(f"Error voiding transaction: {e}")
    finally:
        session.close()

# --- Page Functions ---
def login_page():
    """Displays the login form and handles authentication."""
    st.title("RoV Finance Portal - Login")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Login")
        
        if submit_button:
            session = get_db_session()
            try:
                user = session.query(User).filter(User.username == username).first()
                if user and verify_password(user.password_hash, password):
                    st.session_state.authenticated = True
                    st.session_state.username = user.username
                    st.session_state.role = user.role
                    st.session_state.user_id = user.id
                    st.success("Login successful!")
                    st.session_state.force_rerun = True  # Set flag to trigger rerun
                else:
                    st.error("Invalid username or password.")
            finally:
                session.close()

def logout():
    """Clears the session state and logs the user out."""
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.role = None
    st.session_state.user_id = None
    st.session_state.force_rerun = True  # Set flag to trigger rerun

def dashboard_page():
    """Displays the main dashboard with charts and metrics."""
    st.title("Financial Dashboard")
    
    usd_balance = get_account_balance(1)
    inr_balance = get_account_balance(2)
    latest_rate = get_latest_exchange_rate()
    total_combined_usd = usd_balance + (inr_balance / latest_rate)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("USD Balance", f"${usd_balance:,.2f}")
    with col2:
        st.metric("INR Balance", f"₹{inr_balance:,.2f}")
    with col3:
        st.metric("Total Combined", f"${total_combined_usd:,.2f}")
    with col4:
        st.metric("USD/INR Rate", f"{latest_rate:.2f}")
    
    profit_loss_df = get_profit_loss_data()
    income_df = get_income_by_counterparty()
    expenses_df = get_expenses_by_category()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Profit & Loss Trend")
        if not profit_loss_df.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=profit_loss_df.index, y=profit_loss_df[TransactionType.INCOME.value], 
                                    mode='lines+markers', name='Income', line=dict(color='green')))
            fig.add_trace(go.Scatter(x=profit_loss_df.index, y=profit_loss_df[TransactionType.EXPENSE.value], 
                                    mode='lines+markers', name='Expenses', line=dict(color='red')))
            fig.update_layout(xaxis_title='Month', yaxis_title='Amount')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No transaction data available for the chart.")
    
    with col2:
        st.subheader("Cash Flow")
        if not profit_loss_df.empty:
            profit_loss_df['net_cashflow'] = profit_loss_df[TransactionType.INCOME.value] - profit_loss_df[TransactionType.EXPENSE.value]
            fig = go.Figure(go.Bar(x=profit_loss_df.index, y=profit_loss_df['net_cashflow'],
                                  marker_color=profit_loss_df['net_cashflow'].apply(lambda x: 'green' if x >= 0 else 'red')))
            fig.update_layout(xaxis_title='Month', yaxis_title='Net Cash Flow')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No transaction data available for the chart.")
    
    col3, col4 = st.columns(2)
    
    with col3:
        st.subheader("Income Sources")
        if not income_df.empty:
            fig = px.pie(income_df, values='total_income', names='counterparty')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No income data available.")
    
    with col4:
        st.subheader("Expense Breakdown")
        if not expenses_df.empty:
            fig = px.pie(expenses_df, values='total_expense', names='category')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No expense data available.")
    
    st.sidebar.info("💾 **Remember to backup** the database file (`instance/app.db`) to Google Drive.")

def view_transactions_page():
    """Displays a filterable table of all transactions with edit/delete options."""
    st.title("View All Transactions")
    
    session = get_db_session()
    try:
        # Get filter options
        accounts = get_all_accounts()
        categories = get_all_categories()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            filter_account = st.selectbox("Filter by Account", ["All"] + list(accounts.keys()))
        with col2:
            filter_category = st.selectbox("Filter by Category", ["All"] + list(categories.keys()))
        with col3:
            filter_voided = st.selectbox("Show Voided", ["No", "Yes"])
        
        # Build query
        query = session.query(Transaction).join(Transaction.account).join(Transaction.category)
        
        if filter_account != "All":
            query = query.filter(Transaction.account_id == accounts[filter_account])
        if filter_category != "All":
            query = query.filter(Transaction.category_id == categories[filter_category])
        if filter_voided == "No":
            query = query.filter(Transaction.is_void == False)
        
        transactions = query.order_by(Transaction.date.desc()).all()
        
        # Display transactions in a dataframe
        transaction_data = []
        for t in transactions:
            transaction_data.append({
                "ID": t.id,
                "Date": t.date,
                "Type": t.type.value,
                "Account": f"{t.account.name} ({t.account.currency_code})",
                "Amount": t.amount,
                "Category": t.category.name,
                "Counterparty": t.counterparty,
                "Description": t.description,
                "Voided": "Yes" if t.is_void else "No"
            })
        
        if transaction_data:
            df = pd.DataFrame(transaction_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Edit/Delete options for admins
            if st.session_state.role == 'admin':
                st.subheader("Manage Transaction")
                selected_id = st.number_input("Enter Transaction ID to manage", min_value=1, step=1)
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Void Transaction", type="secondary"):
                        if st.session_state.role == 'admin':
                            void_transaction(selected_id)
                        else:
                            st.error("Insufficient permissions.")
                with col2:
                    if st.button("Edit Transaction (TODO)", disabled=True):
                        st.info("Edit feature coming soon.")
        else:
            st.info("No transactions found matching your filters.")
            
    finally:
        session.close()

def add_transaction_page():
    """Form to add a new income or expense transaction."""
    st.title("Add New Transaction")
    
    accounts = get_all_accounts()
    categories = get_all_categories()
    
    with st.form("add_transaction_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            trans_date = st.date_input("Date", value=date.today())
            trans_type = st.radio("Type", [TransactionType.INCOME.value, TransactionType.EXPENSE.value])
            account_name = st.selectbox("Account", options=list(accounts.keys()))
            amount = st.number_input("Amount", min_value=0.0, format="%.2f")
        with col2:
            category_name = st.selectbox("Category", options=list(categories.keys()))
            counterparty = st.text_input("Counterparty (Who is this from/to?)")
            description = st.text_area("Description")
        
        # Split transaction feature
        with st.expander("Split this transaction (optional)"):
            st.warning("Splitting is not yet implemented. Coming soon!")
        
        submitted = st.form_submit_button("Add Transaction")
        
        if submitted:
            session = get_db_session()
            try:
                new_transaction = Transaction(
                    date=trans_date,
                    type=trans_type,
                    amount=amount,
                    description=description,
                    counterparty=counterparty,
                    account_id=accounts[account_name],
                    category_id=categories[category_name],
                    is_void=False
                )
                session.add(new_transaction)
                session.commit()
                st.success("Transaction added successfully!")
            except Exception as e:
                session.rollback()
                st.error(f"Error adding transaction: {e}")
            finally:
                session.close()

def transfer_funds_page():
    """Form to transfer money between USD and INR accounts."""
    st.title("Transfer Funds Between Accounts")
    
    accounts = get_all_accounts()
    latest_rate = get_latest_exchange_rate()
    st.info(f"Current USD/INR Rate: **1 USD = {latest_rate:.2f} INR**")
    
    with st.form("transfer_funds_form"):
        col1, col2 = st.columns(2)
        with col1:
            trans_date = st.date_input("Date", value=date.today())
            from_account_name = st.selectbox("From Account", options=list(accounts.keys()), index=0)
        with col2:
            amount = st.number_input("Amount to Transfer", min_value=0.01, format="%.2f")
            to_account_name = st.selectbox("To Account", options=list(accounts.keys()), index=1)
        
        # Calculate estimated conversion
        if from_account_name != to_account_name:
            from_acc_id = accounts[from_account_name]
            to_acc_id = accounts[to_account_name]
            
            # Simple logic for demo: Assume first account is USD, second is INR
            if "USD" in from_account_name and "INR" in to_account_name:
                converted_amount = amount * latest_rate
                st.write(f"**{amount:,.2f} USD** will be converted to **₹{converted_amount:,.2f} INR**")
            elif "INR" in from_account_name and "USD" in to_account_name:
                converted_amount = amount / latest_rate
                st.write(f"**₹{amount:,.2f} INR** will be converted to **${converted_amount:,.2f} USD**")
            else:
                st.warning("Please select different accounts for transfer.")
        else:
            st.error("Cannot transfer between the same account.")
        
        description = st.text_input("Description", value="Inter-Account Transfer")
        
        submitted = st.form_submit_button("Execute Transfer")
        
        if submitted and from_account_name != to_account_name:
            session = get_db_session()
            try:
                # Create withdrawal transaction
                withdrawal = Transaction(
                    date=trans_date,
                    type=TransactionType.EXPENSE.value,
                    amount=amount,
                    description=description,
                    counterparty="Internal Transfer",
                    account_id=from_acc_id,
                    category_id=get_all_categories()["Inter-Account Transfer Out"],
                    exchange_rate=latest_rate,
                    is_void=False
                )
                
                # Create deposit transaction
                deposit_amount = amount * latest_rate if "USD" in from_account_name else amount / latest_rate
                deposit = Transaction(
                    date=trans_date,
                    type=TransactionType.INCOME.value,
                    amount=deposit_amount,
                    description=description,
                    counterparty="Internal Transfer",
                    account_id=to_acc_id,
                    category_id=get_all_categories()["Inter-Account Transfer In"],
                    exchange_rate=latest_rate,
                    is_void=False
                )
                
                session.add(withdrawal)
                session.add(deposit)
                session.commit()
                st.success("Funds transferred successfully!")
                
            except Exception as e:
                session.rollback()
                st.error(f"Error transferring funds: {e}")
            finally:
                session.close()

def reports_page():
    """Placeholder for the reports page."""
    st.title("Financial Reports")
    st.info("This section is under development. Coming soon!")
    st.write("Future features will include:")
    st.write("- Profit & Loss Statement generation")
    st.write("- Balance Sheet")
    st.write("- Export to CSV/PDF")
    st.write("- Custom date range reports")

def main_app():
    """Main application interface after login."""
    st.sidebar.title(f"Welcome, {st.session_state.username}")
    st.sidebar.write(f"Role: **{st.session_state.role}**")
    
    # Navigation
    if st.session_state.role == 'admin':
        pages = {
            "Dashboard": dashboard_page,
            "View Transactions": view_transactions_page,
            "Add Transaction": add_transaction_page,
            "Transfer Funds": transfer_funds_page,
            "Reports": reports_page,
        }
    else:  # viewer
        pages = {
            "Dashboard": dashboard_page,
            "View Transactions": view_transactions_page,
            "Reports": reports_page,
        }
    
    selected_page = st.sidebar.radio("Navigation", list(pages.keys()))
    pages[selected_page]()
    
    if st.sidebar.button("Logout"):
        logout()

# --- Main Application Logic ---
def main():
    init_db()
    
    # Check if we need to rerun due to state changes (login/logout)
    if st.session_state.get('force_rerun', False):
        st.session_state.force_rerun = False
        st.rerun()
    
    if not st.session_state.authenticated:
        login_page()
    else:
        main_app()

if __name__ == "__main__":
    main()