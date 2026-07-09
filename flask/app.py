from flask import Flask, render_template, request, redirect, session, url_for, flash, Response
import sqlite3
from datetime import datetime, date
from calendar import month_name
from werkzeug.security import generate_password_hash, check_password_hash
import csv
import io

app = Flask(__name__)
app.secret_key = "smart_finance_secret_key"

DB_PATH = "finance.db"

CATEGORIES = ["Food", "Travel", "Shopping", "Bills", "Entertainment", "Health", "Education", "Others"]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS income (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT,
        source TEXT,
        amount REAL,
        date TEXT,
        description TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS expense (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT,
        category TEXT,
        amount REAL,
        date TEXT,
        description TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS budget (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT,
        category TEXT,
        amount REAL,
        month TEXT
    )
    """)

    conn.commit()
    conn.close()


init_db()


def login_required_redirect():
    if "user" not in session:
        return redirect("/login")
    return None


def current_month_str():
    return datetime.now().strftime("%Y-%m")


def prev_month_str():
    now = datetime.now()
    year = now.year
    month = now.month - 1
    if month == 0:
        month = 12
        year -= 1
    return f"{year:04d}-{month:02d}"


def week_bucket(day):
    if day <= 7:
        return "Week 1"
    elif day <= 14:
        return "Week 2"
    elif day <= 21:
        return "Week 3"
    else:
        return "Week 4"


def month_label(ym):
    try:
        y, m = ym.split("-")
        return f"{month_name[int(m)][:3]} {y}"
    except Exception:
        return ym


def last_n_months(n=6):
    months = []
    now = datetime.now()
    y, m = now.year, now.month
    for _ in range(n):
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(months))


def get_totals(email):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(amount),0) AS t FROM income WHERE user_email=?", (email,))
    total_income = cur.fetchone()["t"]
    cur.execute("SELECT COALESCE(SUM(amount),0) AS t FROM expense WHERE user_email=?", (email,))
    total_expense = cur.fetchone()["t"]
    conn.close()
    return total_income, total_expense


def get_month_totals(email, ym):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(amount),0) AS t FROM income WHERE user_email=? AND date LIKE ?",
                (email, ym + "%"))
    inc = cur.fetchone()["t"]
    cur.execute("SELECT COALESCE(SUM(amount),0) AS t FROM expense WHERE user_email=? AND date LIKE ?",
                (email, ym + "%"))
    exp = cur.fetchone()["t"]
    conn.close()
    return inc, exp


def get_category_totals(email, ym=None):
    conn = get_db()
    cur = conn.cursor()
    if ym:
        cur.execute("""SELECT category, COALESCE(SUM(amount),0) AS t FROM expense
                       WHERE user_email=? AND date LIKE ? GROUP BY category ORDER BY t DESC""",
                    (email, ym + "%"))
    else:
        cur.execute("""SELECT category, COALESCE(SUM(amount),0) AS t FROM expense
                       WHERE user_email=? GROUP BY category ORDER BY t DESC""", (email,))
    rows = cur.fetchall()
    conn.close()
    return {r["category"]: r["t"] for r in rows}


def get_budget_map(email, ym):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM budget WHERE user_email=? AND month=?", (email, ym))
    rows = cur.fetchall()
    conn.close()
    return {r["category"]: r["amount"] for r in rows}, rows


@app.route("/")
def home():
    if "user" in session:
        return redirect("/dashboard")
    return redirect("/login")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("Please fill in all fields.", "danger")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return render_template("register.html")

        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                        (name, email, generate_password_hash(password)))
            conn.commit()
        except sqlite3.IntegrityError:
            flash("An account with this email already exists.", "danger")
            conn.close()
            return render_template("register.html")
        conn.close()

        flash("Registration successful! You can now login.", "success")
        return redirect("/login")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=?", (email,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user"] = user["email"]
            session["name"] = user["name"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect("/dashboard")
        else:
            flash("Invalid email or password.", "danger")
            return render_template("login.html")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect("/login")


@app.route("/dashboard")
def dashboard():
    redir = login_required_redirect()
    if redir:
        return redir

    email = session["user"]
    ym = current_month_str()

    total_income, total_expense = get_totals(email)
    month_income, month_expense = get_month_totals(email, ym)
    savings = total_income - total_expense
    month_savings = month_income - month_expense

    budget_map, _ = get_budget_map(email, ym)
    total_budget = sum(budget_map.values())
    cat_totals = get_category_totals(email, ym)

    # Only count spending in categories that have a budget
    total_spent_this_month = sum(cat_totals.get(category, 0) for category in budget_map.keys())
    budget_pct = min(round((total_spent_this_month / total_budget) * 100), 100) if total_budget > 0 else 0

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""SELECT 'Income' AS type, source AS label, amount, date, id FROM income WHERE user_email=?
                   UNION ALL
                   SELECT 'Expense' AS type, category AS label, amount, date, id FROM expense WHERE user_email=?
                   ORDER BY date DESC, id DESC LIMIT 8""", (email, email))
    recent = cur.fetchall()
    conn.close()

    weeks = ["Week 1", "Week 2", "Week 3", "Week 4"]
    week_income = {w: 0 for w in weeks}
    week_expense = {w: 0 for w in weeks}

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT amount, date FROM income WHERE user_email=? AND date LIKE ?", (email, ym + "%"))
    for r in cur.fetchall():
        try:
            d = int(r["date"].split("-")[2])
            week_income[week_bucket(d)] += r["amount"]
        except Exception:
            pass
    cur.execute("SELECT amount, date FROM expense WHERE user_email=? AND date LIKE ?", (email, ym + "%"))
    for r in cur.fetchall():
        try:
            d = int(r["date"].split("-")[2])
            week_expense[week_bucket(d)] += r["amount"]
        except Exception:
            pass
    conn.close()

    chart_data = {
        "weeks": weeks,
        "income": [round(week_income[w], 2) for w in weeks],
        "expense": [round(week_expense[w], 2) for w in weeks],
        "cat_labels": list(cat_totals.keys()),
        "cat_values": [round(v, 2) for v in cat_totals.values()],
    }

    return render_template(
        "dashboard.html",
        active="dashboard",
        user_name=session["name"],
        income=total_income,
        expense=total_expense,
        savings=savings,
        month_income=month_income,
        month_expense=month_expense,
        month_savings=month_savings,
        total_budget=total_budget,
        budget_pct=budget_pct,
        total_spent_this_month=total_spent_this_month,
        recent=recent,
        chart_data=chart_data,
        month_label=month_label(ym),
    )


@app.route("/income", methods=["GET", "POST"])
def income():
    redir = login_required_redirect()
    if redir:
        return redir

    email = session["user"]
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        source = request.form.get("source", "").strip()
        amount = request.form.get("amount", "0")
        date_val = request.form.get("date", "")
        description = request.form.get("description", "")

        try:
            amount = float(amount)
        except ValueError:
            amount = 0

        if source and amount > 0 and date_val:
            cur.execute("""INSERT INTO income (user_email, source, amount, date, description)
                           VALUES (?, ?, ?, ?, ?)""", (email, source, amount, date_val, description))
            conn.commit()
            flash("Income added successfully!", "success")
        else:
            flash("Please fill all required fields with valid values.", "danger")

    cur.execute("SELECT * FROM income WHERE user_email=? ORDER BY date DESC, id DESC", (email,))
    incomes = cur.fetchall()
    cur.execute("SELECT COALESCE(SUM(amount),0) AS t FROM income WHERE user_email=?", (email,))
    total = cur.fetchone()["t"]
    conn.close()

    return render_template("income.html", active="income", user_name=session["name"],
                            incomes=incomes, total=total)


@app.route("/income/edit/<int:income_id>", methods=["POST"])
def edit_income(income_id):
    redir = login_required_redirect()
    if redir:
        return redir
    email = session["user"]

    source = request.form.get("source", "").strip()
    amount = request.form.get("amount", "0")
    date_val = request.form.get("date", "")
    description = request.form.get("description", "")

    try:
        amount = float(amount)
    except ValueError:
        amount = 0

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""UPDATE income SET source=?, amount=?, date=?, description=?
                   WHERE id=? AND user_email=?""", (source, amount, date_val, description, income_id, email))
    conn.commit()
    conn.close()
    flash("Income updated successfully!", "success")
    return redirect("/income")


@app.route("/income/delete/<int:income_id>", methods=["POST"])
def delete_income(income_id):
    redir = login_required_redirect()
    if redir:
        return redir
    email = session["user"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM income WHERE id=? AND user_email=?", (income_id, email))
    conn.commit()
    conn.close()
    flash("Income record deleted.", "info")
    return redirect("/income")


@app.route("/expense", methods=["GET", "POST"])
def expense():
    redir = login_required_redirect()
    if redir:
        return redir

    email = session["user"]
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        category = request.form.get("category", "").strip()
        amount = request.form.get("amount", "0")
        date_val = request.form.get("date", "")
        description = request.form.get("description", "")

        try:
            amount = float(amount)
        except ValueError:
            amount = 0

        if category and amount > 0 and date_val:
            cur.execute("""INSERT INTO expense (user_email, category, amount, date, description)
                           VALUES (?, ?, ?, ?, ?)""", (email, category, amount, date_val, description))
            conn.commit()
            flash("Expense added successfully!", "success")
        else:
            flash("Please fill all required fields with valid values.", "danger")

    cur.execute("SELECT * FROM expense WHERE user_email=? ORDER BY date DESC, id DESC", (email,))
    expenses = cur.fetchall()
    cur.execute("SELECT COALESCE(SUM(amount),0) AS t FROM expense WHERE user_email=?", (email,))
    total = cur.fetchone()["t"]
    conn.close()

    return render_template("expense.html", active="expense", user_name=session["name"],
                            expenses=expenses, total=total, categories=CATEGORIES)


@app.route("/expense/edit/<int:expense_id>", methods=["POST"])
def edit_expense(expense_id):
    redir = login_required_redirect()
    if redir:
        return redir
    email = session["user"]

    category = request.form.get("category", "").strip()
    amount = request.form.get("amount", "0")
    date_val = request.form.get("date", "")
    description = request.form.get("description", "")

    try:
        amount = float(amount)
    except ValueError:
        amount = 0

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""UPDATE expense SET category=?, amount=?, date=?, description=?
                   WHERE id=? AND user_email=?""", (category, amount, date_val, description, expense_id, email))
    conn.commit()
    conn.close()
    flash("Expense updated successfully!", "success")
    return redirect("/expense")


@app.route("/expense/delete/<int:expense_id>", methods=["POST"])
def delete_expense(expense_id):
    redir = login_required_redirect()
    if redir:
        return redir
    email = session["user"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM expense WHERE id=? AND user_email=?", (expense_id, email))
    conn.commit()
    conn.close()
    flash("Expense record deleted.", "info")
    return redirect("/expense")


@app.route("/budget", methods=["GET", "POST"])
def budget():
    redir = login_required_redirect()
    if redir:
        return redir

    email = session["user"]
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        category = request.form.get("category", "").strip()
        amount = request.form.get("amount", "0")
        month = request.form.get("month", "")

        try:
            amount = float(amount)
        except ValueError:
            amount = 0

        if category and amount > 0 and month:
            cur.execute("SELECT id FROM budget WHERE user_email=? AND category=? AND month=?",
                        (email, category, month))
            existing = cur.fetchone()
            if existing:
                cur.execute("UPDATE budget SET amount=? WHERE id=?", (amount, existing["id"]))
                flash(f"Budget for {category} updated!", "success")
            else:
                cur.execute("""INSERT INTO budget (user_email, category, amount, month)
                               VALUES (?, ?, ?, ?)""", (email, category, amount, month))
                flash("Budget saved successfully!", "success")
            conn.commit()
        else:
            flash("Please fill all required fields with valid values.", "danger")

    ym = current_month_str()
    budget_map, budget_rows = get_budget_map(email, ym)
    cat_totals = get_category_totals(email, ym)

    overview = []
    for row in budget_rows:
        spent = cat_totals.get(row["category"], 0)
        pct = min(round((spent / row["amount"]) * 100), 100) if row["amount"] > 0 else 0
        if pct >= 100:
            status = "Over Budget"
            color = "bg-danger"
        elif pct >= 80:
            status = "Near Limit"
            color = "bg-warning"
        else:
            status = "On Track"
            color = "bg-success"
        overview.append({
            "id": row["id"],
            "category": row["category"],
            "budget": row["amount"],
            "spent": spent,
            "remaining": row["amount"] - spent,
            "pct": min(pct, 100),
            "status": status,
            "color": color,
        })

    total_budget = sum(b["amount"] for b in budget_rows) if budget_rows else 0
    total_spent = sum(item["spent"] for item in overview)
    conn.close()

    return render_template("budget.html", active="budget", user_name=session["name"],
                            overview=overview, categories=CATEGORIES,
                            total_budget=total_budget, total_spent=total_spent,
                            remaining=total_budget - total_spent, month_label=month_label(ym))


@app.route("/budget/delete/<int:budget_id>", methods=["POST"])
def delete_budget(budget_id):
    redir = login_required_redirect()
    if redir:
        return redir
    email = session["user"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM budget WHERE id=? AND user_email=?", (budget_id, email))
    conn.commit()
    conn.close()
    flash("Budget category removed.", "info")
    return redirect("/budget")


@app.route("/reports")
def reports():
    redir = login_required_redirect()
    if redir:
        return redir

    email = session["user"]
    total_income, total_expense = get_totals(email)
    savings = total_income - total_expense

    months = last_n_months(6)
    trend_income = []
    trend_expense = []
    for m in months:
        inc, exp = get_month_totals(email, m)
        trend_income.append(round(inc, 2))
        trend_expense.append(round(exp, 2))

    cat_totals = get_category_totals(email)

    chart_data = {
        "months": [month_label(m) for m in months],
        "trend_income": trend_income,
        "trend_expense": trend_expense,
        "cat_labels": list(cat_totals.keys()),
        "cat_values": [round(v, 2) for v in cat_totals.values()],
    }

    return render_template("reports.html", active="reports", user_name=session["name"],
                            income=total_income, expense=total_expense, savings=savings,
                            chart_data=chart_data)


@app.route("/ai-insights")
def ai_insights():
    redir = login_required_redirect()
    if redir:
        return redir

    email = session["user"]
    ym = current_month_str()
    pym = prev_month_str()

    month_income, month_expense = get_month_totals(email, ym)
    prev_income, prev_expense = get_month_totals(email, pym)
    month_savings = month_income - month_expense

    cat_this = get_category_totals(email, ym)
    cat_prev = get_category_totals(email, pym)

    budget_map, _ = get_budget_map(email, ym)
    total_budget = sum(budget_map.values())

    insights = []

    top_increase_cat = None
    top_increase_pct = 0
    top_increase_amt = 0
    for cat, amt in cat_this.items():
        prev_amt = cat_prev.get(cat, 0)
        if prev_amt > 0:
            pct_change = ((amt - prev_amt) / prev_amt) * 100
        elif amt > 0:
            pct_change = 100
        else:
            pct_change = 0
        if pct_change > top_increase_pct and amt > 0:
            top_increase_pct = pct_change
            top_increase_cat = cat
            top_increase_amt = amt - prev_amt

    if top_increase_cat and top_increase_pct > 0:
        insights.append({
            "icon": "fa-arrow-trend-up",
            "color": "text-danger",
            "title": "Spending Increase Detected",
            "text": f"Your spending on {top_increase_cat} is {round(top_increase_pct)}% higher compared to last month.",
            "action": f"Suggested Action: Try to reduce {top_increase_cat} expenses by "
                      f"₹{round(abs(top_increase_amt) * 0.5):,.0f} this month to stay balanced."
        })
    elif cat_this:
        top_cat = max(cat_this, key=cat_this.get)
        insights.append({
            "icon": "fa-circle-info",
            "color": "text-primary",
            "title": "Spending Overview",
            "text": f"Your highest spending category this month is {top_cat} at ₹{cat_this[top_cat]:,.0f}.",
            "action": "Suggested Action: Keep monitoring this category to avoid overspending."
        })
    else:
        insights.append({
            "icon": "fa-circle-info",
            "color": "text-primary",
            "title": "No Data Yet",
            "text": "Add some income and expense records to get personalized insights.",
            "action": "Suggested Action: Start by logging your expenses for this month."
        })

    if month_income > 0:
        savings_rate = (month_savings / month_income) * 100
        if savings_rate >= 20:
            insights.append({
                "icon": "fa-piggy-bank",
                "color": "text-success",
                "title": "Healthy Savings",
                "text": f"You are saving {round(savings_rate)}% of your income this month. Great job!",
                "action": "Suggested Action: Consider investing your surplus savings for long-term growth."
            })
        elif savings_rate >= 0:
            insights.append({
                "icon": "fa-scale-balanced",
                "color": "text-warning",
                "title": "Moderate Savings",
                "text": f"You are saving only {round(savings_rate)}% of your income this month.",
                "action": "Suggested Action: Try to cut down on non-essential expenses to boost your savings."
            })
        else:
            insights.append({
                "icon": "fa-triangle-exclamation",
                "color": "text-danger",
                "title": "Spending Exceeds Income",
                "text": "Your expenses this month are higher than your income.",
                "action": "Suggested Action: Review your expense list and cut down discretionary spending immediately."
            })

    total_spent = sum(cat_this.values())
    if total_budget > 0:
        usage_pct = (total_spent / total_budget) * 100
        if usage_pct >= 100:
            insights.append({
                "icon": "fa-bell",
                "color": "text-danger",
                "title": "Budget Exceeded",
                "text": f"You have used {round(usage_pct)}% of your monthly budget.",
                "action": "Suggested Action: Revisit your budget plan and adjust category limits."
            })
        else:
            insights.append({
                "icon": "fa-chart-pie",
                "color": "text-success",
                "title": "Budget on Track",
                "text": f"You have used {round(usage_pct)}% of your total monthly budget of ₹{total_budget:,.0f}.",
                "action": "Suggested Action: Continue tracking expenses to stay within budget."
            })

    score = 100
    if month_income > 0:
        savings_rate = month_savings / month_income
        if savings_rate < 0:
            score -= 40
        elif savings_rate < 0.10:
            score -= 20
        elif savings_rate < 0.20:
            score -= 10
    else:
        score -= 30

    if total_budget > 0:
        usage = total_spent / total_budget
        if usage > 1:
            score -= 25
        elif usage > 0.9:
            score -= 10
        elif usage > 0.75:
            score -= 5
    else:
        score -= 5

    score = max(0, min(100, round(score)))

    if score >= 85:
        status, status_color = "Excellent", "#28a745"
    elif score >= 70:
        status, status_color = "Good", "#28a745"
    elif score >= 50:
        status, status_color = "Fair", "#ffc107"
    else:
        status, status_color = "Needs Improvement", "#dc3545"

    highest_cat = max(cat_this, key=cat_this.get) if cat_this else None
    savings_pct_of_income = round((month_savings / month_income) * 100) if month_income > 0 else 0

    summary = {
        "highest_category": highest_cat,
        "highest_amount": cat_this.get(highest_cat, 0) if highest_cat else 0,
        "total_savings": month_savings,
        "savings_pct": savings_pct_of_income,
    }

    return render_template("ai_insights.html", active="ai", user_name=session["name"],
                            insights=insights, score=score, status=status, status_color=status_color,
                            summary=summary, month_income=month_income, month_expense=month_expense)


@app.route("/profile", methods=["GET", "POST"])
def profile():
    redir = login_required_redirect()
    if redir:
        return redir

    email = session["user"]

    if request.method == "POST":
        new_name = request.form.get("name", "").strip()
        new_password = request.form.get("password", "").strip()

        conn = get_db()
        cur = conn.cursor()
        if new_name:
            cur.execute("UPDATE users SET name=? WHERE email=?", (new_name, email))
            session["name"] = new_name
        if new_password:
            if len(new_password) < 6:
                flash("Password must be at least 6 characters long.", "danger")
                conn.close()
                return redirect("/profile")
            cur.execute("UPDATE users SET password=? WHERE email=?",
                        (generate_password_hash(new_password), email))
        conn.commit()
        conn.close()
        flash("Profile updated successfully!", "success")
        return redirect("/profile")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email=?", (email,))
    user = cur.fetchone()
    total_income, total_expense = get_totals(email)
    conn.close()

    return render_template("profile.html", active="profile", user_name=session["name"],
                            user_email=email, member_id=user["id"],
                            total_income=total_income, total_expense=total_expense)


@app.route("/settings", methods=["GET", "POST"])
def settings():
    redir = login_required_redirect()
    if redir:
        return redir

    email = session["user"]

    if request.method == "POST":
        action = request.form.get("action")

        if action == "change_password":
            new_password = request.form.get("password", "").strip()
            confirm_password = request.form.get("confirm_password", "").strip()

            if new_password != confirm_password:
                flash("Passwords do not match.", "danger")
            elif len(new_password) < 6:
                flash("Password must be at least 6 characters long.", "danger")
            else:
                conn = get_db()
                cur = conn.cursor()
                cur.execute("UPDATE users SET password=? WHERE email=?",
                            (generate_password_hash(new_password), email))
                conn.commit()
                conn.close()
                flash("Password updated successfully!", "success")

        elif action == "delete_account":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("DELETE FROM users WHERE email=?", (email,))
            cur.execute("DELETE FROM income WHERE user_email=?", (email,))
            cur.execute("DELETE FROM expense WHERE user_email=?", (email,))
            cur.execute("DELETE FROM budget WHERE user_email=?", (email,))
            conn.commit()
            conn.close()
            session.clear()
            flash("Your account has been deleted.", "info")
            return redirect("/register")

        return redirect("/settings")

    return render_template("settings.html", active="settings", user_name=session["name"])


@app.route("/export-data")
def export_data():
    redir = login_required_redirect()
    if redir:
        return redir
    email = session["user"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM income WHERE user_email=? ORDER BY date DESC", (email,))
    incomes = cur.fetchall()
    cur.execute("SELECT * FROM expense WHERE user_email=? ORDER BY date DESC", (email,))
    expenses = cur.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Type", "Category/Source", "Amount", "Date", "Description"])
    for r in incomes:
        writer.writerow(["Income", r["source"], r["amount"], r["date"], r["description"]])
    for r in expenses:
        writer.writerow(["Expense", r["category"], r["amount"], r["date"], r["description"]])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=smart_finance_data.csv"}
    )


if __name__ == "__main__":
    app.run(debug=True)
