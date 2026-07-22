from flask import Flask, render_template, request, redirect, url_for, session, send_file
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
from flask import make_response
from reportlab.pdfgen import canvas
from io import BytesIO
from flask import flash
import os

app = Flask(__name__)
app.secret_key = "smart_expense_tracker_2026"

# MySQL Configuration
app.config['MYSQL_HOST'] = '127.0.0.1'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'Mounika@0821'   
app.config['MYSQL_DB'] = 'expense_tracker'

# Initialize MySQL
mysql = MySQL(app)

# Print paths (for debugging)
print("Current Working Directory:", os.getcwd())
print("Templates Folder:", app.template_folder)

# Home Page
@app.route('/')
def home():
    return render_template('index.html')

# Login Page
@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        email = request.form['email']
        password = request.form['password']

        cur = mysql.connection.cursor()

        # Get user by email only
        cur.execute(
            "SELECT * FROM users WHERE email=%s",
            (email,)
        )

        user = cur.fetchone()
        print("User from DB:", user)

        if user:
            print("Password Check:", check_password_hash(user[3], password))

        cur.close()

        # Verify hashed password
        if user and check_password_hash(user[3], password):

            session['user_id'] = user[0]
            session['user_name'] = user[1]

            return redirect(url_for('dashboard'))

        else:
            flash("Invalid Email or Password!", "danger")
            redirect(url_for('login'))

    return render_template('login.html')

# Register Page
@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        hashed_password = generate_password_hash(password)

        cur = mysql.connection.cursor()

        cur.execute(
            "INSERT INTO users(name,email,password) VALUES(%s,%s,%s)",
            (name, email, hashed_password)
        )

        mysql.connection.commit()

        cur.close()

        flash("Registration Successful!", "success")
        return redirect(url_for('login'))

    return render_template("register.html")
# Dashboard Page
@app.route('/dashboard')
def dashboard():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()

    # Total Income
    cur.execute("SELECT SUM(amount) FROM income WHERE user_id=%s", (session['user_id'],))
    total_income = cur.fetchone()[0] or 0

    # Total Expense
    cur.execute("SELECT SUM(amount) FROM expense WHERE user_id=%s", (session['user_id'],))
    total_expense = cur.fetchone()[0] or 0

    balance = total_income - total_expense

    # Savings Goal
    cur.execute("""
    SELECT goal_amount
    FROM savings_goal
    WHERE user_id=%s
    """, (session['user_id'],))

    goal = cur.fetchone()

    if goal:
        savings_goal = float(goal[0])
    else:
        savings_goal = 0.0

    # Convert balance to float
    balance = float(balance)

    # Calculate Progress
    if savings_goal > 0:
        progress = min((balance / savings_goal) * 100, 100)
    else:
        progress = 0

    # Monthly Budget
    cur.execute(
        "SELECT monthly_budget FROM budget WHERE user_id=%s",
        (session['user_id'],)
    )

    budget_data = cur.fetchone()

    if budget_data:
        monthly_budget = budget_data[0]
    else:
        monthly_budget = 0

    remaining_budget = monthly_budget - total_expense

    # Budget Insight
    if monthly_budget > 0:

        used_percentage = (float(total_expense) / float(monthly_budget)) * 100

        if used_percentage >= 100:
            insight = "🚨 Budget Exceeded!"

        elif used_percentage >= 80:
            insight = "⚠️ Warning! You have used more than 80% of your budget."

        else:
            insight = "🎉 Great! You are managing your budget well."

    else:
        insight = "Set your monthly budget to see insights."

    if remaining_budget >= 0:
        budget_status = "Within Budget ✅"
    else:
        budget_status = "Budget Exceeded ❌"

    # Income History
    cur.execute("""
        SELECT id, category, amount, date
        FROM income
        WHERE user_id=%s
        ORDER BY date DESC
    """, (session['user_id'],))
    incomes = cur.fetchall()

    # Expense History
    #cur.execute("""
        #SELECT id, category, amount, date
        #FROM expense
        #WHERE user_id=%s
        #ORDER BY date DESC
    #""", (session['user_id'],))
    #expenses = cur.fetchall()

    # Expense Search and Date Filter
    search = request.args.get('search')
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    query = """
    SELECT id, category, amount, date
    FROM expense
    WHERE user_id=%s
    """
    params = [session['user_id']]

    # Search by category
    if search:
        query += " AND category LIKE %s"
        params.append("%" + search + "%")

    # Filter by From Date
    if from_date:
        query += " AND date >= %s"
        params.append(from_date)

    # Filter by To Date
    if to_date:
        query += " AND date <= %s"
        params.append(to_date)
    query += " ORDER BY date DESC"
    cur.execute(query, tuple(params))
    expenses = cur.fetchall()

    # Expense Chart Data
    cur.execute("""
    SELECT category, SUM(amount)
    FROM expense
    WHERE user_id=%s
    GROUP BY category
    """, (session['user_id'],))
    expense_chart = cur.fetchall()

    # Monthly Expense Data
    cur.execute("""
    SELECT MONTHNAME(date), SUM(amount)
    FROM expense
    WHERE user_id=%s
    GROUP BY MONTH(date), MONTHNAME(date)
    ORDER BY MONTH(date)
    """, (session['user_id'],))
    monthly_expense = cur.fetchall()

    cur.close()

    #Render Template
    return render_template(
    "dashboard.html",
    total_income=total_income,
    total_expense=total_expense,
    balance=balance,
    incomes=incomes,
    expenses=expenses,
    expense_chart=expense_chart,
    monthly_expense=monthly_expense,
    monthly_budget=monthly_budget,
    remaining_budget=remaining_budget,
    budget_status=budget_status,
    savings_goal=savings_goal,
    progress=progress,
    insight=insight
)

# Add Income Page
@app.route('/add_income', methods=['GET', 'POST'])
def add_income():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':

        category = request.form['category']
        amount = request.form['amount']
        date = request.form['income_date']

        cur = mysql.connection.cursor()

        cur.execute("""
        INSERT INTO income(user_id, amount, category, date)
        VALUES(%s, %s, %s, %s)
        """,
        (session['user_id'], amount, category, date))

        mysql.connection.commit()
        cur.close()

        flash("Income Added Successfully! 🎉", "success")
        return redirect(url_for('dashboard'))
    return render_template("add_income.html")

#Add Expenses page
@app.route('/add_expense', methods=['GET', 'POST'])
def add_expense():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':

        category = request.form['category']
        amount = request.form['amount']
        date = request.form['date']
        description = request.form['description']

        cur = mysql.connection.cursor()

        cur.execute("""
        INSERT INTO expense(user_id, amount, category, date, description)
        VALUES(%s, %s, %s, %s, %s)
        """,
        (session['user_id'], amount, category, date, description))

        mysql.connection.commit()
        cur.close()

        flash("Expense Added Successfully! 🎉", "success")
        return redirect(url_for('dashboard'))

    return render_template("add_expense.html")

# Delete Income
@app.route('/delete_income/<int:id>')
def delete_income(id):

    cur = mysql.connection.cursor()

    cur.execute(
    "DELETE FROM income WHERE id=%s AND user_id=%s",
    (id, session['user_id'])
)

    mysql.connection.commit()
    
    cur.close()

    flash("Income Deleted Successfully!", "success")
    return redirect(url_for('dashboard'))

# Delete Expense
@app.route('/delete_expense/<int:id>')
def delete_expense(id):

    cur = mysql.connection.cursor()

    cur.execute(
    "DELETE FROM expense WHERE id=%s AND user_id=%s",
    (id, session['user_id'])
)

    mysql.connection.commit()

    cur.close()

    flash("Expense Deleted Successfully!", "success")
    return redirect(url_for('dashboard'))

#Edit Expense page
@app.route('/edit_expense/<int:id>', methods=['GET', 'POST'])
def edit_expense(id):

    cur = mysql.connection.cursor()

    if request.method == 'POST':

        category = request.form['category']
        amount = request.form['amount']
        date = request.form['date']
        description = request.form['description']

        cur.execute("""
        UPDATE expense
        SET amount=%s,
            category=%s,
            date=%s,
            description=%s
        WHERE id=%s
        """,
        (amount, category, date, description, id))

        mysql.connection.commit()
        
        cur.close()
        
        flash("Expense Updated Successfully!", "info")
        return redirect(url_for('dashboard'))

    cur.execute("SELECT * FROM expense WHERE id=%s", (id,))

    expense = cur.fetchone()

    cur.close()

    return render_template(
        "edit_expense.html",
        expense=expense
    )
# Edit Income
@app.route('/edit_income/<int:id>', methods=['GET', 'POST'])
def edit_income(id):

    cur = mysql.connection.cursor()

    if request.method == 'POST':

        category = request.form['category']
        amount = request.form['amount']
        date = request.form['date']

        cur.execute("""
        UPDATE income
        SET amount=%s,
            category=%s,
            date=%s
        WHERE id=%s
        """,
        (amount, category, date, id))

        mysql.connection.commit()
        
        cur.close()

        flash("Income Updated Successfully!", "info")
        return redirect(url_for('dashboard'))

    cur.execute("SELECT * FROM income WHERE id=%s", (id,))

    income = cur.fetchone()

    cur.close()

    return render_template(
        "edit_income.html",
        income=income
    )

#Budget Route Page
@app.route('/set_budget', methods=['GET', 'POST'])
def set_budget():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()

    if request.method == 'POST':

        budget = request.form['budget']

        cur.execute("SELECT * FROM budget WHERE user_id=%s",
                    (session['user_id'],))

        data = cur.fetchone()

        if data:
            cur.execute("""
                UPDATE budget
                SET monthly_budget=%s
                WHERE user_id=%s
            """, (budget, session['user_id']))
        else:
            cur.execute("""
                INSERT INTO budget(user_id, monthly_budget)
                VALUES(%s,%s)
            """, (session['user_id'], budget))

        mysql.connection.commit()
        cur.close()

        return redirect(url_for('dashboard'))

    cur.execute(
        "SELECT monthly_budget FROM budget WHERE user_id=%s",
        (session['user_id'],)
    )

    budget = cur.fetchone()

    cur.close()

    return render_template(
        "set_budget.html",
        budget=budget
    )
#Set Goal Page
@app.route('/set_goal', methods=['GET', 'POST'])
def set_goal():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()

    if request.method == 'POST':

        goal = request.form['goal']

        # Check if goal already exists
        cur.execute(
            "SELECT * FROM savings_goal WHERE user_id=%s",
            (session['user_id'],)
        )

        data = cur.fetchone()

        if data:

            cur.execute("""
                UPDATE savings_goal
                SET goal_amount=%s
                WHERE user_id=%s
            """, (goal, session['user_id']))

        else:

            cur.execute("""
                INSERT INTO savings_goal(user_id, goal_amount)
                VALUES(%s,%s)
            """, (session['user_id'], goal))

        mysql.connection.commit()

        cur.close()

        return redirect(url_for('dashboard'))

    # Show existing goal
    cur.execute(
        "SELECT goal_amount FROM savings_goal WHERE user_id=%s",
        (session['user_id'],)
    )

    goal = cur.fetchone()

    cur.close()

    return render_template(
        "set_goal.html",
        goal=goal
    )

#Profile Page
@app.route('/profile')
def profile():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()

    cur.execute(
        "SELECT * FROM users WHERE id=%s",
        (session['user_id'],)
    )

    user = cur.fetchone()

    cur.close()

    return render_template(
        "profile.html",
        user=user
    )

#About Page
@app.route('/about')
def about():
    return render_template("about.html")

#Logout Page
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

#Download PDF report
@app.route('/download_report')
def download_report():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()

    # Total Income
    cur.execute("SELECT SUM(amount) FROM income WHERE user_id=%s", (session['user_id'],))
    total_income = cur.fetchone()[0] or 0

    # Total Expense
    cur.execute("SELECT SUM(amount) FROM expense WHERE user_id=%s", (session['user_id'],))
    total_expense = cur.fetchone()[0] or 0

    balance = total_income - total_expense

    # Expense History
    cur.execute("""
        SELECT category, amount, date
        FROM expense
        WHERE user_id=%s
        ORDER BY date DESC
    """, (session['user_id'],))

    expenses = cur.fetchall()

    cur.close()

    # Create PDF
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)

    # ---------------- Title ----------------
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawCentredString(300, 810, "SMART EXPENSE TRACKER")

    # ---------------- Subtitle ----------------
    pdf.setFont("Helvetica", 14)
    pdf.drawCentredString(300, 790, "Expense Summary Report")

    # ---------------- Summary ----------------
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, 755, "Summary")

    pdf.setFont("Helvetica", 12)
    pdf.drawString(60, 735, f"User Name      : {session['user_name']}")
    pdf.drawString(60, 715, f"Total Income   : Rs. {total_income}")
    pdf.drawString(60, 695, f"Total Expense  : Rs. {total_expense}")
    pdf.drawString(60, 675, f"Current Balance: Rs. {balance}")

    
    # Expense History Title
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, 630, "Expense History")

    # Table Heading
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, 615, "Category")
    pdf.drawString(220, 615, "Amount")
    pdf.drawString(380, 615, "Date")

    pdf.line(45, 605, 520, 605)

    # Start printing rows
    pdf.setFont("Helvetica", 12)
    y = 585

    y = 560

    for expense in expenses:
        pdf.drawString(50, y, expense[0])
        pdf.drawString(220, y, "Rs. " + str(expense[1]))
        pdf.drawString(380, y, str(expense[2]))

        y -= 20

        if y < 50:
            pdf.showPage()
            y = 800
            

            pdf.setFont("Helvetica-Bold", 14)
            pdf.drawString(50, 800, "Expense History (Continued)")

            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(50, 780, "Category")
            pdf.drawString(180, 780, "Amount")
            pdf.drawString(300, 780, "Date")

            pdf.line(45, 775, 520, 775)
            pdf.setFont("Helvetica", 12)
            y = 750

    pdf.save()

    pdf_data = buffer.getvalue()
    buffer.close()

    response = make_response(pdf_data)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=Expense_Report.pdf'

    return response

# Run Flask
if __name__ == '__main__':
    app.run(debug=True)