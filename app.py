from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = 'expense_tracker_secret_key'
DB_NAME = 'expenses.db'

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Categories table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            icon TEXT NOT NULL,
            color TEXT NOT NULL
        )
    ''')

    # Expenses table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            category_id INTEGER,
            remark TEXT,
            date TEXT NOT NULL,
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    ''')

    # Incomes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS incomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            source TEXT NOT NULL,
            date TEXT NOT NULL
        )
    ''')

    # Budgets table (category_id is NULL for overall budget)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            amount REAL NOT NULL,
            month TEXT NOT NULL,
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    ''')

    # Insert default categories if none exist
    cursor.execute('SELECT COUNT(*) FROM categories')
    if cursor.fetchone()[0] == 0:
        default_categories = [
            ('Food & Dining', 'fa-utensils', '#3b82f6'),
            ('Transportation', 'fa-car', '#10b981'),
            ('Shopping', 'fa-shopping-bag', '#f59e0b'),
            ('Bills & Utilities', 'fa-bolt', '#ef4444'),
            ('Entertainment', 'fa-film', '#8b5cf6'),
            ('Healthcare', 'fa-heartbeat', '#ec4899'),
            ('Others', 'fa-ellipsis-h', '#6b7280')
        ]
        cursor.executemany('INSERT INTO categories (name, icon, color) VALUES (?, ?, ?)', default_categories)

    conn.commit()
    conn.close()

@app.route('/')
def home():
    conn = get_db_connection()
    selected_month = request.args.get('month', datetime.now().strftime('%Y-%m'))

    categories = conn.execute('SELECT * FROM categories ORDER BY name').fetchall()

    expenses = conn.execute('''
        SELECT e.*, c.name as category_name, c.icon as category_icon, c.color as category_color
        FROM expenses e
        LEFT JOIN categories c ON e.category_id = c.id
        ORDER BY e.date DESC, e.id DESC
        LIMIT 30
    ''').fetchall()

    incomes = conn.execute('''
        SELECT * FROM incomes
        ORDER BY date DESC, id DESC
        LIMIT 20
    ''').fetchall()

    total_expense = conn.execute('SELECT SUM(amount) FROM expenses').fetchone()[0] or 0.0
    total_income = conn.execute('SELECT SUM(amount) FROM incomes').fetchone()[0] or 0.0
    net_balance = total_income - total_expense

    month_expense = conn.execute("SELECT SUM(amount) FROM expenses WHERE strftime('%Y-%m', date) = ?", (selected_month,)).fetchone()[0] or 0.0
    month_income = conn.execute("SELECT SUM(amount) FROM incomes WHERE strftime('%Y-%m', date) = ?", (selected_month,)).fetchone()[0] or 0.0

    conn.close()

    return render_template('home.html',
                           active_tab='home',
                           categories=categories,
                           expenses=expenses,
                           incomes=incomes,
                           total_expense=total_expense,
                           total_income=total_income,
                           net_balance=net_balance,
                           month_expense=month_expense,
                           month_income=month_income,
                           selected_month=selected_month,
                           today=date.today().strftime('%Y-%m-%d'))

@app.route('/overview')
def overview():
    conn = get_db_connection()
    selected_month = request.args.get('month', datetime.now().strftime('%Y-%m'))

    cat_breakdown = conn.execute('''
        SELECT c.name, c.color, SUM(e.amount) as total
        FROM expenses e
        JOIN categories c ON e.category_id = c.id
        WHERE strftime('%Y-%m', e.date) = ?
        GROUP BY c.id
        ORDER BY total DESC
    ''', (selected_month,)).fetchall()

    daily_data = conn.execute('''
        SELECT date, SUM(amount) as amount, 'expense' as type
        FROM expenses
        WHERE strftime('%Y-%m', date) = ?
        GROUP BY date
        UNION ALL
        SELECT date, SUM(amount) as amount, 'income' as type
        FROM incomes
        WHERE strftime('%Y-%m', date) = ?
        GROUP BY date
        ORDER BY date ASC
    ''', (selected_month, selected_month)).fetchall()

    month_expense = conn.execute("SELECT SUM(amount) FROM expenses WHERE strftime('%Y-%m', date) = ?", (selected_month,)).fetchone()[0] or 0.0
    month_income = conn.execute("SELECT SUM(amount) FROM incomes WHERE strftime('%Y-%m', date) = ?", (selected_month,)).fetchone()[0] or 0.0

    conn.close()

    return render_template('overview.html',
                           active_tab='overview',
                           cat_breakdown=cat_breakdown,
                           daily_data=daily_data,
                           selected_month=selected_month,
                           month_expense=month_expense,
                           month_income=month_income)

@app.route('/budget', methods=['GET', 'POST'])
def budget():
    conn = get_db_connection()
    selected_month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    categories = conn.execute('SELECT * FROM categories ORDER BY name').fetchall()

    budgets = conn.execute('''
        SELECT b.*, c.name as category_name
        FROM budgets b
        LEFT JOIN categories c ON b.category_id = c.id
        WHERE b.month = ?
    ''', (selected_month,)).fetchall()

    overall_budget = next((b['amount'] for b in budgets if b['category_id'] is None), 0.0)
    category_budgets = {b['category_id']: b['amount'] for b in budgets if b['category_id'] is not None}

    # Calculate actual spending per category for selected month
    cat_spend_rows = conn.execute('''
        SELECT category_id, SUM(amount) as total
        FROM expenses
        WHERE strftime('%Y-%m', date) = ?
        GROUP BY category_id
    ''', (selected_month,)).fetchall()
    cat_spending = {row['category_id']: row['total'] for row in cat_spend_rows}

    month_expense = conn.execute("SELECT SUM(amount) FROM expenses WHERE strftime('%Y-%m', date) = ?", (selected_month,)).fetchone()[0] or 0.0

    conn.close()

    return render_template('budget.html',
                           active_tab='budget',
                           categories=categories,
                           selected_month=selected_month,
                           overall_budget=overall_budget,
                           category_budgets=category_budgets,
                           cat_spending=cat_spending,
                           month_expense=month_expense)

@app.route('/add_expense', methods=['POST'])
def add_expense():
    amount = request.form.get('amount')
    category_id = request.form.get('category_id')
    remark = request.form.get('remark', '')
    exp_date = request.form.get('date', date.today().strftime('%Y-%m-%d'))
    redirect_to = request.form.get('redirect_to', 'home')

    if not amount or not category_id:
        flash('Amount and category are required!', 'error')
        return redirect(url_for(redirect_to))

    try:
        amount = float(amount)
        conn = get_db_connection()
        conn.execute('INSERT INTO expenses (amount, category_id, remark, date) VALUES (?, ?, ?, ?)',
                     (amount, category_id, remark, exp_date))
        conn.commit()
        conn.close()
        flash('Expense added successfully!', 'success')
    except ValueError:
        flash('Invalid amount format!', 'error')

    return redirect(url_for(redirect_to))

@app.route('/add_income', methods=['POST'])
def add_income():
    amount = request.form.get('amount')
    source = request.form.get('source', 'Salary')
    inc_date = request.form.get('date', date.today().strftime('%Y-%m-%d'))

    if not amount or not source:
        flash('Amount and source are required!', 'error')
        return redirect(url_for('home'))

    try:
        amount = float(amount)
        conn = get_db_connection()
        conn.execute('INSERT INTO incomes (amount, source, date) VALUES (?, ?, ?)',
                     (amount, source, inc_date))
        conn.commit()
        conn.close()
        flash('Income added successfully!', 'success')
    except ValueError:
        flash('Invalid amount format!', 'error')

    return redirect(url_for('home'))

@app.route('/set_budget', methods=['POST'])
def set_budget():
    budget_type = request.form.get('budget_type')
    amount = request.form.get('amount')
    category_id = request.form.get('category_id') if budget_type == 'category' else None
    month = request.form.get('month', datetime.now().strftime('%Y-%m'))

    if not amount:
        flash('Budget amount is required!', 'error')
        return redirect(url_for('budget', month=month))

    try:
        amount = float(amount)
        conn = get_db_connection()

        if budget_type == 'overall':
            existing = conn.execute('SELECT id FROM budgets WHERE category_id IS NULL AND month = ?', (month,)).fetchone()
            if existing:
                conn.execute('UPDATE budgets SET amount = ? WHERE id = ?', (amount, existing['id']))
            else:
                conn.execute('INSERT INTO budgets (category_id, amount, month) VALUES (NULL, ?, ?)', (amount, month))
        else:
            if not category_id:
                flash('Please select a category!', 'error')
                conn.close()
                return redirect(url_for('budget', month=month))
            existing = conn.execute('SELECT id FROM budgets WHERE category_id = ? AND month = ?', (category_id, month)).fetchone()
            if existing:
                conn.execute('UPDATE budgets SET amount = ? WHERE id = ?', (amount, existing['id']))
            else:
                conn.execute('INSERT INTO budgets (category_id, amount, month) VALUES (?, ?, ?)', (category_id, amount, month))

        conn.commit()
        conn.close()
        flash('Budget saved successfully!', 'success')
    except ValueError:
        flash('Invalid amount format!', 'error')

    return redirect(url_for('budget', month=month))

@app.route('/delete_expense/<int:id>', methods=['POST'])
def delete_expense(id):
    redirect_to = request.args.get('redirect', 'home')
    conn = get_db_connection()
    conn.execute('DELETE FROM expenses WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Expense deleted.', 'info')
    return redirect(url_for(redirect_to))

@app.route('/delete_income/<int:id>', methods=['POST'])
def delete_income(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM incomes WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Income deleted.', 'info')
    return redirect(url_for('home'))

@app.route('/add_category', methods=['POST'])
def add_category():
    name = request.form.get('name')
    icon = request.form.get('icon', 'fa-tag')
    color = request.form.get('color', '#3b82f6')
    redirect_to = request.form.get('redirect_to', 'home')

    if not name:
        flash('Category name is required!', 'error')
        return redirect(url_for(redirect_to))

    try:
        conn = get_db_connection()
        conn.execute('INSERT INTO categories (name, icon, color) VALUES (?, ?, ?)', (name, icon, color))
        conn.commit()
        conn.close()
        flash('Category added successfully!', 'success')
    except sqlite3.IntegrityError:
        flash('Category already exists!', 'error')

    return redirect(url_for(redirect_to))

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
