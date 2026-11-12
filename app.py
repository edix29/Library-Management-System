import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps
from flask import Flask, g, render_template, request, redirect, url_for, session, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "library.db")
app = Flask(__name__)
app.secret_key = os.environ.get("LIBRARY_SECRET_KEY", "change-this-secret-key-before-deployment")
LOAN_DAYS = 14

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT UNIQUE,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        department TEXT DEFAULT '',
        year TEXT DEFAULT '',
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'student' CHECK(role IN ('admin','student')),
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        isbn TEXT UNIQUE,
        title TEXT NOT NULL,
        author TEXT NOT NULL,
        category TEXT DEFAULT '',
        publisher TEXT DEFAULT '',
        published_year INTEGER,
        total_copies INTEGER NOT NULL DEFAULT 1 CHECK(total_copies >= 0),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS upcoming_books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        author TEXT DEFAULT '',
        expected_date TEXT DEFAULT '',
        notes TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS book_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        book_id INTEGER NOT NULL REFERENCES books(id),
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','cancelled','issued')),
        requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        librarian_note TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS loans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        book_id INTEGER NOT NULL REFERENCES books(id),
        request_id INTEGER REFERENCES book_requests(id),
        issue_date TEXT NOT NULL,
        due_date TEXT NOT NULL,
        returned_date TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'issued' CHECK(status IN ('issued','returned'))
    );
    """)
    admin = db.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
    if not admin:
        db.execute(
            "INSERT INTO users(student_id,name,email,department,year,password_hash,role) VALUES(NULL,?,?,?,?,?,?)",
            ("Library Admin", "admin@library.local", "", "", generate_password_hash("Admin@123"), "admin")
        )
    student = db.execute("SELECT id FROM users WHERE student_id='BSC2026001'").fetchone()
    if not student:
        db.execute(
            "INSERT INTO users(student_id,name,email,department,year,password_hash,role) VALUES(?,?,?,?,?,?,?)",
            ("BSC2026001", "Demo Student", "student@library.local", "Computer Science", "BSc Year 2", generate_password_hash("Student@123"), "student")
        )
    count = db.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    if count == 0:
        db.executemany("""INSERT INTO books(isbn,title,author,category,publisher,published_year,total_copies)
                          VALUES(?,?,?,?,?,?,?)""", [
            ("9780135166307","Introduction to Algorithms","Thomas H. Cormen et al.","Computer Science","MIT Press",2022,3),
            ("9780134685991","Effective Java","Joshua Bloch","Programming","Addison-Wesley",2018,2),
            ("9780131103627","The C Programming Language","Brian W. Kernighan and Dennis M. Ritchie","Programming","Prentice Hall",1988,4),
            ("9789355423489","Database Management Systems","Raghu Ramakrishnan","Database","McGraw Hill",2014,2),
            ("9780078022159","Operating System Concepts","Abraham Silberschatz et al.","Operating Systems","Wiley",2018,2),
        ])
        db.executemany("INSERT INTO upcoming_books(title,author,expected_date,notes) VALUES(?,?,?,?)", [
            ("Computer Networking: A Top-Down Approach","James Kurose","2026-11-15","Expected new edition"),
            ("Artificial Intelligence: A Modern Approach","Stuart Russell and Peter Norvig","2026-12-01","Purchase request submitted"),
        ])
    db.commit()
    db.close()

def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("user_id"):
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("You do not have permission to access that page.", "danger")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator

@app.context_processor
def inject_globals():
    return {"today": date.today().isoformat(), "current_user": session.get("name")}

@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("""SELECT * FROM users WHERE (student_id=? OR email=?) AND active=1""",
                          (identity, identity)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            session["student_id"] = user["student_id"]
            flash("Welcome back, " + user["name"] + "!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid ID/email or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required()
def dashboard():
    db = get_db()
    if session["role"] == "admin":
        stats = {
            "books": db.execute("SELECT COUNT(*) FROM books").fetchone()[0],
            "copies": db.execute("SELECT COALESCE(SUM(total_copies),0) FROM books").fetchone()[0],
            "students": db.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0],
            "issued": db.execute("SELECT COUNT(*) FROM loans WHERE status='issued'").fetchone()[0],
            "pending": db.execute("SELECT COUNT(*) FROM book_requests WHERE status='pending'").fetchone()[0],
            "overdue": db.execute("SELECT COUNT(*) FROM loans WHERE status='issued' AND due_date < ?", (today_iso(),)).fetchone()[0],
        }
        pending = db.execute("""SELECT r.id, u.name, u.student_id, b.title, r.requested_at
          FROM book_requests r JOIN users u ON u.id=r.user_id JOIN books b ON b.id=r.book_id
          WHERE r.status='pending' ORDER BY r.requested_at DESC LIMIT 8""").fetchall()
        return render_template("admin_dashboard.html", stats=stats, pending=pending)
    user_id = session["user_id"]
    loans = db.execute("""SELECT l.*, b.title, b.author FROM loans l JOIN books b ON b.id=l.book_id
                          WHERE l.user_id=? AND l.status='issued' ORDER BY l.due_date""", (user_id,)).fetchall()
    requests = db.execute("""SELECT r.*, b.title, b.author FROM book_requests r JOIN books b ON b.id=r.book_id
                             WHERE r.user_id=? ORDER BY r.requested_at DESC LIMIT 8""", (user_id,)).fetchall()
    stats = {
        "issued": len(loans),
        "pending": db.execute("SELECT COUNT(*) FROM book_requests WHERE user_id=? AND status='pending'", (user_id,)).fetchone()[0],
        "history": db.execute("SELECT COUNT(*) FROM loans WHERE user_id=? AND status='returned'", (user_id,)).fetchone()[0]
    }
    return render_template("student_dashboard.html", stats=stats, loans=loans, requests=requests)

def today_iso():
    return date.today().isoformat()

def book_counts(db, book_id):
    total = db.execute("SELECT total_copies FROM books WHERE id=?", (book_id,)).fetchone()
    if not total:
        return 0, 0
    issued = db.execute("SELECT COUNT(*) FROM loans WHERE book_id=? AND status='issued'", (book_id,)).fetchone()[0]
    approved = db.execute("SELECT COUNT(*) FROM book_requests WHERE book_id=? AND status='approved'", (book_id,)).fetchone()[0]
    return total["total_copies"], max(0, total["total_copies"] - issued - approved)

@app.route("/books")
@login_required()
def books():
    db = get_db()
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    sql = "SELECT * FROM books WHERE (title LIKE ? OR author LIKE ? OR isbn LIKE ? OR category LIKE ?)"
    args = [f"%{q}%"] * 4
    if category:
        sql += " AND category=?"
        args.append(category)
    sql += " ORDER BY title"
    rows = db.execute(sql, args).fetchall()
    result = []
    for b in rows:
        total, available = book_counts(db, b["id"])
        result.append({"book": b, "total": total, "available": available})
    categories = [r["category"] for r in db.execute("SELECT DISTINCT category FROM books WHERE category<>'' ORDER BY category")]
    return render_template("books.html", rows=result, q=q, categories=categories, selected_category=category)

@app.route("/books/add", methods=["GET", "POST"])
@login_required("admin")
def add_book():
    if request.method == "POST":
        form = book_form()
        try:
            get_db().execute("""INSERT INTO books(isbn,title,author,category,publisher,published_year,total_copies)
                              VALUES(?,?,?,?,?,?,?)""", form)
            get_db().commit()
            flash("Book added to the catalog.", "success")
            return redirect(url_for("books"))
        except sqlite3.IntegrityError:
            flash("ISBN already exists. Use a unique ISBN or leave it blank.", "danger")
    return render_template("book_form.html", book=None)

@app.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
@login_required("admin")
def edit_book(book_id):
    db = get_db()
    book = db.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
    if not book:
        flash("Book not found.", "danger")
        return redirect(url_for("books"))
    if request.method == "POST":
        form = book_form()
        try:
            db.execute("""UPDATE books SET isbn=?,title=?,author=?,category=?,publisher=?,published_year=?,total_copies=?
                           WHERE id=?""", (*form, book_id))
            db.commit()
            flash("Book details updated.", "success")
            return redirect(url_for("books"))
        except sqlite3.IntegrityError:
            flash("ISBN already exists. Use a unique ISBN or leave it blank.", "danger")
    return render_template("book_form.html", book=book)

def book_form():
    f = request.form
    isbn = f.get("isbn", "").strip() or None
    year = f.get("published_year", "").strip()
    copies = int(f.get("total_copies", "1") or 1)
    if copies < 0:
        raise ValueError("Copies cannot be negative")
    return (isbn, f.get("title", "").strip(), f.get("author", "").strip(),
            f.get("category", "").strip(), f.get("publisher", "").strip(),
            int(year) if year else None, copies)

@app.route("/books/<int:book_id>/delete", methods=["POST"])
@login_required("admin")
def delete_book(book_id):
    db = get_db()
    related = db.execute("SELECT COUNT(*) FROM loans WHERE book_id=?", (book_id,)).fetchone()[0]
    related += db.execute("SELECT COUNT(*) FROM book_requests WHERE book_id=?", (book_id,)).fetchone()[0]
    if related:
        flash("This book has borrowing/request history and cannot be deleted. Edit it instead.", "warning")
    else:
        db.execute("DELETE FROM books WHERE id=?", (book_id,))
        db.commit()
        flash("Book deleted.", "success")
    return redirect(url_for("books"))

@app.route("/request-book/<int:book_id>", methods=["POST"])
@login_required("student")
def request_book(book_id):
    db = get_db()
    book = db.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
    if not book:
        flash("Book not found.", "danger")
        return redirect(url_for("books"))
    total, available = book_counts(db, book_id)
    if available <= 0:
        flash("No copies are currently available. You can check again later.", "warning")
        return redirect(url_for("books"))
    existing = db.execute("""SELECT COUNT(*) FROM book_requests WHERE user_id=? AND book_id=?
                              AND status IN ('pending','approved')""", (session["user_id"], book_id)).fetchone()[0]
    active_loan = db.execute("""SELECT COUNT(*) FROM loans WHERE user_id=? AND book_id=? AND status='issued'""",
                             (session["user_id"], book_id)).fetchone()[0]
    if existing or active_loan:
        flash("You already have an active request or loan for this book.", "warning")
    else:
        db.execute("INSERT INTO book_requests(user_id,book_id) VALUES(?,?)", (session["user_id"], book_id))
        db.commit()
        flash("Request sent. Wait for librarian approval before collecting the book.", "success")
    return redirect(url_for("books"))

@app.route("/requests")
@login_required()
def requests_page():
    db = get_db()
    if session["role"] == "admin":
        rows = db.execute("""SELECT r.*,u.name,u.student_id,b.title,b.author FROM book_requests r
          JOIN users u ON u.id=r.user_id JOIN books b ON b.id=r.book_id ORDER BY
          CASE r.status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END, r.requested_at DESC""").fetchall()
    else:
        rows = db.execute("""SELECT r.*,b.title,b.author FROM book_requests r JOIN books b ON b.id=r.book_id
                             WHERE r.user_id=? ORDER BY r.requested_at DESC""", (session["user_id"],)).fetchall()
    return render_template("requests.html", rows=rows)

@app.route("/requests/<int:req_id>/decision", methods=["POST"])
@login_required("admin")
def request_decision(req_id):
    db = get_db()
    r = db.execute("SELECT * FROM book_requests WHERE id=?", (req_id,)).fetchone()
    action = request.form.get("action")
    note = request.form.get("note", "").strip()
    if not r or r["status"] != "pending":
        flash("This request is no longer pending.", "warning")
        return redirect(url_for("requests_page"))
    if action == "approve":
        _, available = book_counts(db, r["book_id"])
        if available < 1:
            flash("No available copies remain, so this request cannot be approved.", "danger")
        else:
            db.execute("UPDATE book_requests SET status='approved',librarian_note=? WHERE id=?", (note, req_id))
            db.commit()
            flash("Request approved. Student can collect the book from the library; record the issue when handed over.", "success")
    elif action == "reject":
        db.execute("UPDATE book_requests SET status='rejected',librarian_note=? WHERE id=?", (note, req_id))
        db.commit()
        flash("Request rejected.", "info")
    return redirect(url_for("requests_page"))

@app.route("/requests/<int:req_id>/cancel", methods=["POST"])
@login_required("student")
def cancel_request(req_id):
    db = get_db()
    r = db.execute("SELECT * FROM book_requests WHERE id=? AND user_id=?", (req_id, session["user_id"])).fetchone()
    if r and r["status"] == "pending":
        db.execute("UPDATE book_requests SET status='cancelled' WHERE id=?", (req_id,))
        db.commit()
        flash("Request cancelled.", "success")
    else:
        flash("Only pending requests can be cancelled.", "warning")
    return redirect(url_for("requests_page"))

@app.route("/loans")
@login_required()
def loans_page():
    db = get_db()
    if session["role"] == "admin":
        rows = db.execute("""SELECT l.*,u.name,u.student_id,b.title,b.author FROM loans l
          JOIN users u ON u.id=l.user_id JOIN books b ON b.id=l.book_id ORDER BY
          CASE WHEN l.status='issued' AND l.due_date < ? THEN 0 ELSE 1 END, l.due_date""",
                          (today_iso(),)).fetchall()
        return render_template("loans.html", rows=rows, students=None, approved=None)
    rows = db.execute("""SELECT l.*,b.title,b.author FROM loans l JOIN books b ON b.id=l.book_id
                         WHERE l.user_id=? ORDER BY l.issue_date DESC""", (session["user_id"],)).fetchall()
    return render_template("loans.html", rows=rows, students=None, approved=None)

@app.route("/loans/issue", methods=["POST"])
@login_required("admin")
def issue_loan():
    db = get_db()
    req_id = request.form.get("request_id", type=int)
    r = db.execute("SELECT * FROM book_requests WHERE id=? AND status='approved'", (req_id,)).fetchone()
    if not r:
        flash("Choose an approved request.", "danger")
        return redirect(url_for("requests_page"))
    total_row = db.execute("SELECT total_copies FROM books WHERE id=?", (r["book_id"],)).fetchone()
    issued_count = db.execute("SELECT COUNT(*) FROM loans WHERE book_id=? AND status='issued'", (r["book_id"],)).fetchone()[0]
    other_approved = db.execute("SELECT COUNT(*) FROM book_requests WHERE book_id=? AND status='approved' AND id<>?",
                                (r["book_id"], req_id)).fetchone()[0]
    available_for_this_request = (total_row["total_copies"] if total_row else 0) - issued_count - other_approved
    if available_for_this_request < 1:
        flash("No available copies remain for this request.", "danger")
        return redirect(url_for("requests_page"))
    issue = date.today()
    due = issue + timedelta(days=LOAN_DAYS)
    db.execute("""INSERT INTO loans(user_id,book_id,request_id,issue_date,due_date,status)
                  VALUES(?,?,?,?,?,'issued')""", (r["user_id"], r["book_id"], req_id, issue.isoformat(), due.isoformat()))
    db.execute("UPDATE book_requests SET status='issued' WHERE id=?", (req_id,))
    db.commit()
    flash(f"Book issued successfully. Return by {due.isoformat()}.", "success")
    return redirect(url_for("loans_page"))

@app.route("/loans/<int:loan_id>/return", methods=["POST"])
@login_required("admin")
def return_loan(loan_id):
    db = get_db()
    loan = db.execute("SELECT * FROM loans WHERE id=? AND status='issued'", (loan_id,)).fetchone()
    if not loan:
        flash("Active loan not found.", "warning")
    else:
        db.execute("UPDATE loans SET status='returned',returned_date=? WHERE id=?", (date.today().isoformat(), loan_id))
        db.commit()
        flash("Book return recorded. Copy is now available.", "success")
    return redirect(url_for("loans_page"))

@app.route("/students")
@login_required("admin")
def students():
    q = request.args.get("q", "").strip()
    rows = get_db().execute("""SELECT * FROM users WHERE role='student' AND
      (name LIKE ? OR student_id LIKE ? OR email LIKE ?) ORDER BY name""",
      (f"%{q}%", f"%{q}%", f"%{q}%")).fetchall()
    return render_template("students.html", rows=rows, q=q)

@app.route("/students/add", methods=["GET", "POST"])
@login_required("admin")
def add_student():
    if request.method == "POST":
        f = request.form
        try:
            get_db().execute("""INSERT INTO users(student_id,name,email,department,year,password_hash,role)
              VALUES(?,?,?,?,?,?, 'student')""",
              (f.get("student_id","").strip(), f.get("name","").strip(), f.get("email","").strip(),
               f.get("department","").strip(), f.get("year","").strip(),
               generate_password_hash(f.get("password","Student@123"))))
            get_db().commit()
            flash("Student account created.", "success")
            return redirect(url_for("students"))
        except sqlite3.IntegrityError:
            flash("Student ID or email already exists.", "danger")
    return render_template("student_form.html")

@app.route("/students/<int:user_id>/toggle", methods=["POST"])
@login_required("admin")
def toggle_student(user_id):
    db = get_db()
    student = db.execute("SELECT * FROM users WHERE id=? AND role='student'", (user_id,)).fetchone()
    if student:
        db.execute("UPDATE users SET active=? WHERE id=?", (0 if student["active"] else 1, user_id))
        db.commit()
        flash("Student account status updated.", "success")
    return redirect(url_for("students"))

@app.route("/upcoming", methods=["GET", "POST"])
@login_required()
def upcoming():
    db = get_db()
    if request.method == "POST" and session["role"] == "admin":
        f = request.form
        db.execute("INSERT INTO upcoming_books(title,author,expected_date,notes) VALUES(?,?,?,?)",
                   (f.get("title","").strip(), f.get("author","").strip(),
                    f.get("expected_date","").strip(), f.get("notes","").strip()))
        db.commit()
        flash("Upcoming book added.", "success")
        return redirect(url_for("upcoming"))
    rows = db.execute("SELECT * FROM upcoming_books ORDER BY expected_date").fetchall()
    return render_template("upcoming.html", rows=rows)

@app.route("/upcoming/<int:item_id>/delete", methods=["POST"])
@login_required("admin")
def delete_upcoming(item_id):
    get_db().execute("DELETE FROM upcoming_books WHERE id=?", (item_id,))
    get_db().commit()
    flash("Upcoming book removed.", "success")
    return redirect(url_for("upcoming"))

@app.route("/reports.csv")
@login_required("admin")
def reports_csv():
    db = get_db()
    rows = db.execute("""SELECT l.id,u.student_id,u.name,b.title,l.issue_date,l.due_date,
                         COALESCE(l.returned_date,'') AS returned_date,l.status
                         FROM loans l JOIN users u ON u.id=l.user_id JOIN books b ON b.id=l.book_id
                         ORDER BY l.issue_date DESC""").fetchall()
    lines = ["Loan ID,Student ID,Student Name,Book,Issue Date,Due Date,Return Date,Status"]
    import csv, io
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Loan ID","Student ID","Student Name","Book","Issue Date","Due Date","Return Date","Status"])
    for r in rows:
        writer.writerow([r["id"],r["student_id"],r["name"],r["title"],r["issue_date"],r["due_date"],r["returned_date"],r["status"]])
    return Response(buffer.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":"attachment; filename=library-loans.csv"})

@app.errorhandler(500)
def internal_error(error):
    get_db().rollback()
    return render_template("error.html", message="Something went wrong. Check the terminal for the error details."), 500

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
