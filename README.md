# Campus Library Management System

A full-stack library management system suitable for a BSc Computer Science project. Built with Python Flask, SQLite, Bootstrap 5 and plain HTML/CSS.

## Features

### Librarian / Admin
- Dashboard statistics: catalog titles, copies, registered students, active loans, pending requests and overdue loans.
- Add and edit books; remove books that have no borrowing history.
- Search/filter the book catalog and see availability.
- Add students and enable/disable student access.
- Approve/reject requests and add a librarian note.
- Record physical collection after approval, creating an issue date and a 14-day due date.
- Record returns and automatically make the copy available again.
- Manage upcoming book announcements.
- Export borrowing history as CSV.

### Student
- Login using student ID or email and password.
- Search catalog by title, author, ISBN or category.
- Request an available book and see request status.
- Cancel a pending request.
- View current loans, due dates, overdue status and borrowing history.
- Browse upcoming books.

## Requirements
- Python 3.10 or newer recommended
- Internet connection for Bootstrap CSS/JS CDN (or download Bootstrap locally for offline use)

## Run on Windows, macOS or Linux

1. Extract the ZIP file.
2. Open a terminal / Command Prompt in the extracted `library_management_system` folder.
3. Create a virtual environment:

   **Windows**
   ```bash
   python -m venv .venv
   .venv\\Scripts\\activate
   ```

   **macOS / Linux**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Start the application:
   ```bash
   python app.py
   ```

6. Open http://127.0.0.1:5000 in your browser.

The SQLite database (`library.db`) is created automatically at first startup and seeded with demo accounts and sample books.

## Demo login credentials

- **Librarian:** `admin@library.local` / `Admin@123`
- **Student:** `BSC2026001` / `Student@123`

The student can also log in with the email `student@library.local`.

## Demo workflow
1. Sign in as the student.
2. Open **Book catalog** and request an available title.
3. Log out and sign in as the librarian.
4. Open **Requests**, approve the pending request.
5. In the same Requests page, click **Record collection / issue** after the student physically collects the book.
6. The new loan appears in **Issued books & returns** with a due date 14 days from issue.
7. Record return when the student brings the book back.
8. Sign in as the student to view the loan and due date.

## Database model

- `users`: librarian and student accounts, role, student ID and password hash.
- `books`: title, author, ISBN, category, publisher and copy count.
- `book_requests`: request lifecycle: pending → approved/rejected/cancelled → issued.
- `loans`: issue date, due date, return date and status.
- `upcoming_books`: planned/pending acquisitions.

Availability is calculated as:

`available copies = total copies - active loans - approved requests awaiting collection`

This prevents the same copy from being promised to multiple students.

## Important notes before deployment
This is an educational project starter, not a production-hardened public service. Before hosting it on the internet:
- Set a long random `LIBRARY_SECRET_KEY` environment variable.
- Change the demo passwords or delete demo accounts.
- Run with `debug=False` behind a production WSGI server.
- Add CSRF protection, password reset, login rate limiting, audit logs and automated backups.
- Use HTTPS and review privacy/security requirements for student data.
- Consider PostgreSQL for a multi-user production deployment.
