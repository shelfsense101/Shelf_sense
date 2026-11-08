
import os
import sqlite3
import secrets
from pathlib import Path
from datetime import date
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, g
)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "shelfsense_v2.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", secrets.token_hex(32)
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


# DATABASE

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA foreign_keys = ON")

    db.executescript("""
    CREATE TABLE IF NOT EXISTS stores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        store_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        FOREIGN KEY(store_id) REFERENCES stores(id)
    );

    CREATE TABLE IF NOT EXISTS store_products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        store_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        brand TEXT,
        category TEXT,
        quantity INTEGER NOT NULL,
        stocked_on TEXT NOT NULL,
        expiry_date TEXT NOT NULL,
        cost_price REAL NOT NULL DEFAULT 0,
        selling_price REAL NOT NULL DEFAULT 0,
        notes TEXT,
        FOREIGN KEY(store_id) REFERENCES stores(id)
    );

    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        store_id INTEGER NOT NULL,
        product_id INTEGER,
        product_name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        unit_cost REAL NOT NULL,
        discount_percent REAL NOT NULL,
        revenue REAL NOT NULL,
        sold_on TEXT NOT NULL,
        FOREIGN KEY(store_id) REFERENCES stores(id),
        FOREIGN KEY(product_id) REFERENCES store_products(id)
        ON DELETE SET NULL
    );

    CREATE INDEX IF NOT EXISTS idx_products_store
    ON store_products(store_id);

    CREATE INDEX IF NOT EXISTS idx_sales_store
    ON sales(store_id);
    """)

    db.commit()
    db.close()


# SECURITY

@app.before_request
def prepare_csrf():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    if request.method == "POST":
        supplied = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")

        if not supplied or not secrets.compare_digest(
            supplied, expected
        ):
            return "Security check failed. Refresh and try again.", 400


@app.context_processor
def inject_csrf():
    return {"csrf_token": session.get("csrf_token", "")}


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return function(*args, **kwargs)
    return wrapper


def store_id():
    return session.get("store_id")


# EXPIRY ENGINE

def expiry_status(expiry):
    days = (date.fromisoformat(expiry) - date.today()).days

    if days < 0:
        return "Expired", days, 0
    elif days <= 3:
        return "Urgent", days, 30
    elif days <= 7:
        return "Expiring soon", days, 20
    elif days <= 30:
        return "Watch", days, 5
    else:
        return "Fresh", days, 0


# HOME

@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


# REGISTER

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        store = request.form.get("store_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not all([name, store, email, password]):
            flash("Please complete all fields.", "error")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
            return redirect(url_for("register"))

        db = get_db()

        try:
            cursor = db.execute(
                "INSERT INTO stores (name) VALUES (?)",
                (store,)
            )

            new_store_id = cursor.lastrowid

            cursor = db.execute("""
                INSERT INTO users
                (store_id, name, email, password_hash)
                VALUES (?, ?, ?, ?)
            """, (
                new_store_id,
                name,
                email,
                generate_password_hash(password)
            ))

            db.commit()

            session.clear()
            session["user_id"] = cursor.lastrowid
            session["store_id"] = new_store_id
            session["user_name"] = name
            session["store_name"] = store
            session["csrf_token"] = secrets.token_urlsafe(32)

            return redirect(url_for("dashboard"))

        except sqlite3.IntegrityError:
            db.rollback()
            flash("This email already has an account.", "error")
            return redirect(url_for("login"))

    return render_template("auth.html", mode="register")


# LOGIN

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = get_db().execute("""
            SELECT users.*, stores.name AS store_name
            FROM users
            JOIN stores ON stores.id = users.store_id
            WHERE users.email = ?
        """, (email,)).fetchone()

        if user and check_password_hash(
            user["password_hash"], password
        ):

            session.clear()
            session["user_id"] = user["id"]
            session["store_id"] = user["store_id"]
            session["user_name"] = user["name"]
            session["store_name"] = user["store_name"]
            session["csrf_token"] = secrets.token_urlsafe(32)

            return redirect(url_for("dashboard"))

        flash("Incorrect email or password.", "error")
        return redirect(url_for("login"))

    return render_template("auth.html", mode="login")


# LOGOUT

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


# DASHBOARD

@app.route("/dashboard")
@login_required
def dashboard():

    db = get_db()
    sid = store_id()

    rows = db.execute("""
        SELECT * FROM store_products
        WHERE store_id = ?
        ORDER BY expiry_date ASC
    """, (sid,)).fetchall()

    products = []

    for row in rows:
        p = dict(row)

        status, days, discount = expiry_status(p["expiry_date"])

        p["status"] = status
        p["days_left"] = days
        p["suggested_discount"] = discount

        products.append(p)

    stats = db.execute("""
        SELECT COUNT(*) AS product_count,
               COALESCE(SUM(quantity), 0) AS units,
               COALESCE(SUM(quantity * cost_price), 0) AS stock_cost
        FROM store_products
        WHERE store_id = ?
    """, (sid,)).fetchone()

    expired_loss = db.execute("""
        SELECT COALESCE(SUM(quantity * cost_price), 0)
        FROM store_products
        WHERE store_id = ? AND expiry_date < ?
    """, (sid, date.today().isoformat())).fetchone()[0]

    sales_stats = db.execute("""
        SELECT COALESCE(SUM(revenue), 0) AS revenue,
               COALESCE(SUM(quantity * unit_cost), 0) AS cost_value,
               COALESCE(SUM(
                   CASE WHEN sold_on <= (
                       SELECT expiry_date
                       FROM store_products
                       WHERE store_products.id = sales.product_id
                   )
                   THEN quantity * unit_cost ELSE 0 END
               ), 0) AS recovered
        FROM sales
        WHERE store_id = ?
    """, (sid,)).fetchone()

    metrics = {
        "product_count": stats["product_count"],
        "units": stats["units"],
        "stock_cost": stats["stock_cost"],
        "soon": sum(
            1 for p in products if 0 <= p["days_left"] <= 7
        ),
        "expired": sum(
            1 for p in products if p["days_left"] < 0
        ),
        "expired_loss": expired_loss,
        "revenue": sales_stats["revenue"],
        "recovered": sales_stats["recovered"],
        "transactions": db.execute(
            "SELECT COUNT(*) FROM sales WHERE store_id = ?",
            (sid,)
        ).fetchone()[0]
    }

    return render_template(
        "dashboard.html",
        products=products,
        metrics=metrics,
        today=date.today().isoformat(),
        store_name=session.get("store_name")
    )


# ADD PRODUCT

@app.route("/products/add", methods=["POST"])
@login_required
def add_product():

    try:
        name = request.form["name"].strip()
        brand = request.form.get("brand", "").strip()
        category = request.form.get("category", "Other")
        quantity = int(request.form["quantity"])
        stocked = request.form["stocked_on"]
        expiry = request.form["expiry_date"]
        cost = float(request.form["cost_price"])
        selling = float(request.form["selling_price"])

        date.fromisoformat(stocked)
        date.fromisoformat(expiry)

        if not name or quantity < 1 or expiry < stocked:
            raise ValueError

        if cost < 0 or selling < 0:
            raise ValueError

    except (ValueError, KeyError):
        flash("Please check the product information.", "error")
        return redirect(url_for("dashboard"))

    get_db().execute("""
        INSERT INTO store_products
        (store_id, name, brand, category, quantity,
         stocked_on, expiry_date, cost_price, selling_price, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        store_id(), name, brand, category, quantity,
        stocked, expiry, cost, selling,
        request.form.get("notes", "")
    ))

    get_db().commit()

    flash(f"{name} added successfully.", "success")
    return redirect(url_for("dashboard"))


# DELETE PRODUCT

@app.route("/products/<int:pid>/delete", methods=["POST"])
@login_required
def delete_product(pid):

    get_db().execute("""
        DELETE FROM store_products
        WHERE id = ? AND store_id = ?
    """, (pid, store_id()))

    get_db().commit()

    flash("Product removed.", "success")
    return redirect(url_for("dashboard"))


# RECORD SALE

@app.route("/products/<int:pid>/sell", methods=["POST"])
@login_required
def sell_product(pid):

    db = get_db()

    product = db.execute("""
        SELECT * FROM store_products
        WHERE id = ? AND store_id = ?
    """, (pid, store_id())).fetchone()

    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("dashboard"))

    try:
        quantity = int(request.form["quantity"])
        discount = float(request.form["discount"])

        if quantity < 1 or quantity > product["quantity"]:
            raise ValueError

        if discount < 0 or discount > 90:
            raise ValueError

    except (ValueError, KeyError):
        flash("Invalid sale quantity or discount.", "error")
        return redirect(url_for("dashboard"))

    if product["expiry_date"] < date.today().isoformat():
        flash("Expired products cannot be sold through ShelfSense.", "error")
        return redirect(url_for("dashboard"))

    final_price = product["selling_price"] * (1 - discount / 100)
    revenue = round(final_price * quantity, 2)

    db.execute("""
        INSERT INTO sales
        (store_id, product_id, product_name, quantity,
         unit_cost, discount_percent, revenue, sold_on)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        store_id(), pid, product["name"], quantity,
        product["cost_price"], discount,
        revenue, date.today().isoformat()
    ))

    db.execute("""
        UPDATE store_products
        SET quantity = quantity - ?
        WHERE id = ? AND store_id = ?
    """, (quantity, pid, store_id()))

    db.commit()

    flash(f"Sale recorded! Revenue: ₹{revenue:.2f}", "success")
    return redirect(url_for("dashboard"))


# SALES HISTORY

@app.route("/sales")
@login_required
def sales():

    rows = get_db().execute("""
        SELECT * FROM sales
        WHERE store_id = ?
        ORDER BY id DESC
    """, (store_id(),)).fetchall()

    return render_template("sales.html", sales=rows)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
