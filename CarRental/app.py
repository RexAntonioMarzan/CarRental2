from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    flash,
    url_for,
    jsonify,
)
from math import ceil
import os
import requests
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename   # ← ADD THIS
import random
import smtplib
from email.message import EmailMessage

from db import get_db, init_db

app = Flask(__name__)  # ← siguraduhin _name_ ito, hindi name
app.secret_key = "supersecretkey"

# PayMongo config (TEST MODE ONLY)
PAYMONGO_SECRET_KEY = os.getenv(
    "PAYMONGO_SECRET_KEY", "sk_test_GQLNE9qwrTM4vmbBNAankw6y"
)
PAYMONGO_SUCCESS_URL = "http://127.0.0.1:5000/payment/success"
PAYMONGO_CANCEL_URL = "http://127.0.0.1:5000/payment/cancel"

# Add-on prices (PHP)
CHILD_SEAT_PER_DAY = 250.0
DASHCAM_PER_DAY = 100.0
TOLL_RFID_PER_DAY = 500.0

# Discount rate (20%)
DISCOUNT_RATE = 0.20

# Simple upload folder
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
# ---------- OTP + EMAIL HELPERS ----------


def generate_otp_code():
    """Generate a 6-digit OTP code as a string."""
    return f"{random.randint(100000, 999999)}"


def send_otp_email(recipient_email, otp_code):
    """
    Send a 6-digit OTP code to the given email.
    Uses Gmail SMTP with an app password (NOT normal Gmail password).
    """

    smtp_email = "rexantoniomarzan@gmail.com"
    smtp_password = "ykqb xqqp evgf gxni"  # <-- palitan ng bagong app password mo

    msg = EmailMessage()
    msg["Subject"] = "Your Drive Car Rental verification code"
    msg["From"] = smtp_email
    msg["To"] = recipient_email

    msg.set_content(
        f"""Hi,

Here is your 6-digit verification code for Drive Car Rental:

    {otp_code}

If you did not request this, you can ignore this email.

Thanks,
Drive Car Rental
"""
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(smtp_email, smtp_password)
        smtp.send_message(msg)


# ---------- HELPERS ----------


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "info")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Administrator access required.", "danger")
            return redirect(url_for("index"))
        return view(*args, **kwargs)

    return wrapped


@app.context_processor
def inject_user_state():
    return {
        "is_authenticated": "user_id" in session,
        "is_admin": session.get("is_admin", False),
        "current_username": session.get("username"),
        "current_year": datetime.utcnow().year,
    }


# ---------- AUTH ----------


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("home"))
    return redirect(url_for("login"))

@app.route("/home")
@login_required
def home():
    current_username = session.get("username")
    return render_template("home.html", current_username=current_username)

@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    # Total counts
    cursor.execute("SELECT COUNT(*) AS c FROM users")
    users_count = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM cars")
    cars_count = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM bookings")
    bookings_count = cursor.fetchone()["c"]

    # Recent bookings (latest 5)
    cursor.execute(
        """
        SELECT b.id, b.days, b.total_price,
               u.username,
               c.name AS car_name
        FROM bookings b
        LEFT JOIN users u ON b.user_id = u.id
        LEFT JOIN cars c ON b.car_id = c.id
        ORDER BY b.id DESC
        LIMIT 5
        """
    )
    recent_bookings = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "admin_dashboard.html",
        users_count=users_count,
        cars_count=cars_count,
        bookings_count=bookings_count,
        recent_bookings=recent_bookings,
    )

@app.route("/admin/cars")
@admin_required
def admin_cars():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM cars ORDER BY id ASC")
    cars = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("admin_cars.html", cars=cars)


@app.route("/admin/cars/new", methods=["GET", "POST"])
@admin_required
def admin_car_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        car_type = request.form.get("car_type", "").strip()
        price_per_day = request.form.get("price_per_day", 0)
        image_url = request.form.get("image_url", "").strip()

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO cars (name, car_type, price_per_day, image_url)
            VALUES (%s, %s, %s, %s)
            """,
            (name, car_type, price_per_day, image_url),
        )
        conn.commit()
        cursor.close()
        conn.close()

        flash("Car added successfully.", "success")
        return redirect(url_for("admin_cars"))

    return render_template("admin_car_form.html", car=None)


@app.route("/admin/cars/<int:car_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_car_edit(car_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        car_type = request.form.get("car_type", "").strip()
        price_per_day = request.form.get("price_per_day", 0)
        image_url = request.form.get("image_url", "").strip()

        cursor.execute(
            """
            UPDATE cars
            SET name=%s, car_type=%s, price_per_day=%s, image_url=%s
            WHERE id=%s
            """,
            (name, car_type, price_per_day, image_url, car_id),
        )
        conn.commit()
        cursor.close()
        conn.close()

        flash("Car updated successfully.", "success")
        return redirect(url_for("admin_cars"))

    # GET – load car
    cursor.execute("SELECT * FROM cars WHERE id = %s", (car_id,))
    car = cursor.fetchone()
    cursor.close()
    conn.close()

    if not car:
        flash("Car not found.", "danger")
        return redirect(url_for("admin_cars"))

    return render_template("admin_car_form.html", car=car)


@app.route("/admin/cars/<int:car_id>/delete", methods=["POST"])
@admin_required
def admin_car_delete(car_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cars WHERE id = %s", (car_id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("Car deleted.", "info")
    return redirect(url_for("admin_cars"))

@app.route("/admin/bookings")
@admin_required
def admin_bookings():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT b.id, b.days, b.total_price,
               u.username, u.email,
               c.name AS car_name, c.car_type
        FROM bookings b
        LEFT JOIN users u ON b.user_id = u.id
        LEFT JOIN cars c ON b.car_id = c.id
        ORDER BY b.id DESC
        """
    )
    bookings = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("admin_bookings.html", bookings=bookings)

@app.route("/admin/users")
@admin_required
def admin_users():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, username, email, is_admin FROM users ORDER BY id ASC"
    )
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("admin_users.html", users=users)


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "danger")
            return redirect(url_for("login"))

        if not session.get("is_admin"):
            flash("You do not have permission to access the admin area.", "danger")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    # If already logged in, just send the user where they belong
    if "user_id" in session:
        if session.get("is_admin"):
            return redirect(url_for("admin_dashboard"))
        else:
            return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user or not check_password_hash(user["password"], password):
            flash("Incorrect username or password.", "danger")
            return render_template("login.html")

        # ✅ Save user info in session
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["email"] = user.get("email")          # <-- needed for PayMongo billing.email
        session["is_admin"] = bool(user["is_admin"])

        flash("Successfully logged in.", "success")

        # ✅ Redirect based on role (now safe, key definitely exists)
        if session["is_admin"]:
            return redirect(url_for("admin_dashboard"))
        else:
            return redirect(url_for("home"))

    # GET request: just show the login page
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """
    Step 1: Collect username, email, password.
    - generate 6-digit OTP
    - send to email
    - store pending user in session
    - redirect to /verify-otp
    """
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]

        if not username or not email or not password:
            flash("Username, email, and password are required.", "danger")
            return render_template("register.html")

        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        # Check if username already exists
        cursor.execute("SELECT 1 FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            conn.close()
            flash("Username already exists.", "danger")
            return render_template("register.html")

        # Check if email already used
        cursor.execute("SELECT 1 FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            conn.close()
            flash("Email is already registered.", "danger")
            return render_template("register.html")

        conn.close()

        # Generate OTP and store temporarily in session
        otp_code = generate_otp_code()
        session["pending_user"] = {
            "username": username,
            "email": email,
            "password_hash": generate_password_hash(password),
            "otp_code": otp_code,
            "created_at": datetime.utcnow().isoformat(),
        }

        try:
            send_otp_email(email, otp_code)
        except Exception:
            session.pop("pending_user", None)
            flash("Failed to send verification email. Please try again later.", "danger")
            return render_template("register.html")

        flash(
            "We sent a 6-digit code to your email. Please enter it to verify your account.",
            "info",
        )
        return redirect(url_for("verify_otp"))

    return render_template("register.html")


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    """
    Step 2: User enters OTP.
    If correct and not expired, create user record.
    """
    pending = session.get("pending_user")
    if not pending:
        flash("No registration is pending. Please register again.", "danger")
        return redirect(url_for("register"))

    # Expire after 10 minutes
    try:
        created_at = datetime.fromisoformat(pending["created_at"])
        if datetime.utcnow() - created_at > timedelta(minutes=10):
            session.pop("pending_user", None)
            flash("Your verification code has expired. Please register again.", "danger")
            return redirect(url_for("register"))
    except Exception:
        session.pop("pending_user", None)
        flash("Something went wrong. Please register again.", "danger")
        return redirect(url_for("register"))

    if request.method == "POST":
        entered_code = request.form.get("otp", "").strip()

        if entered_code != pending["otp_code"]:
            flash("Invalid verification code. Please try again.", "danger")
            return render_template("verify_otp.html")

        # OTP valid → create user
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "INSERT INTO users (username, email, password, is_admin) "
            "VALUES (%s, %s, %s, 0)",
            (pending["username"], pending["email"], pending["password_hash"]),
        )
        conn.commit()
        conn.close()

        session.pop("pending_user", None)
        flash("Account verified and created successfully. You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("verify_otp.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


# ---------- USER SIDE ----------


@app.route("/home")
@login_required
def user_home():
    return render_template("home.html")


@app.route("/gallery")
@login_required
def gallery():
    # 1. Get all cars from DB
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM cars ORDER BY name")
    cars = cursor.fetchall()
    conn.close()

    # 2. Specs per car (for filters + display)
    specs = {
        "BMW 3 Series": {
            "seaters_label": "5",
            "seaters_min": 5,
            "seaters_max": 5,
            "transmission_label": "Automatic (most variants; manual rare in newer models)",
            "transmission_type": "Automatic",
        },
        "Ford Everest": {
            "seaters_label": "7",
            "seaters_min": 7,
            "seaters_max": 7,
            "transmission_label": "Automatic",
            "transmission_type": "Automatic",
        },
        "Ford Ranger": {
            "seaters_label": "5",
            "seaters_min": 5,
            "seaters_max": 5,
            "transmission_label": "Automatic or Manual (both available)",
            "transmission_type": "Automatic or Manual",
        },
        "Honda BR-V": {
            "seaters_label": "7",
            "seaters_min": 7,
            "seaters_max": 7,
            "transmission_label": "Automatic (CVT)",
            "transmission_type": "Automatic",
        },
        "Honda Civic": {
            "seaters_label": "5",
            "seaters_min": 5,
            "seaters_max": 5,
            "transmission_label": "Automatic (CVT)",
            "transmission_type": "Automatic",
        },
        "Honda CR-V": {
            "seaters_label": "5–7",
            "seaters_min": 5,
            "seaters_max": 7,
            "transmission_label": "Automatic",
            "transmission_type": "Automatic",
        },
        "Hyundai Staria": {
            "seaters_label": "7–11",
            "seaters_min": 7,
            "seaters_max": 11,
            "transmission_label": "Automatic",
            "transmission_type": "Automatic",
        },
        "Isuzu D-Max": {
            "seaters_label": "5",
            "seaters_min": 5,
            "seaters_max": 5,
            "transmission_label": "Manual or Automatic",
            "transmission_type": "Automatic or Manual",
        },
        "Mazda CX-5": {
            "seaters_label": "5",
            "seaters_min": 5,
            "seaters_max": 5,
            "transmission_label": "Automatic",
            "transmission_type": "Automatic",
        },
        "Mercedes-Benz GLC": {
            "seaters_label": "5",
            "seaters_min": 5,
            "seaters_max": 5,
            "transmission_label": "Automatic",
            "transmission_type": "Automatic",
        },
        "Mitsubishi L300": {
            "seaters_label": "3–17",
            "seaters_min": 3,
            "seaters_max": 17,
            "transmission_label": "Manual",
            "transmission_type": "Manual",
        },
        "Nissan Almera": {
            "seaters_label": "5",
            "seaters_min": 5,
            "seaters_max": 5,
            "transmission_label": "Automatic or Manual",
            "transmission_type": "Automatic or Manual",
        },
        "Nissan Navara": {
            "seaters_label": "5",
            "seaters_min": 5,
            "seaters_max": 5,
            "transmission_label": "Manual or Automatic",
            "transmission_type": "Automatic or Manual",
        },
        "Subaru Forester": {
            "seaters_label": "5",
            "seaters_min": 5,
            "seaters_max": 5,
            "transmission_label": "Automatic (CVT)",
            "transmission_type": "Automatic",
        },
        "Suzuki Ertiga": {
            "seaters_label": "7",
            "seaters_min": 7,
            "seaters_max": 7,
            "transmission_label": "Manual or Automatic",
            "transmission_type": "Automatic or Manual",
        },
        "Toyota Camry": {
            "seaters_label": "5",
            "seaters_min": 5,
            "seaters_max": 5,
            "transmission_label": "Automatic",
            "transmission_type": "Automatic",
        },
        "Toyota Fortuner": {
            "seaters_label": "7",
            "seaters_min": 7,
            "seaters_max": 7,
            "transmission_label": "Automatic or Manual",
            "transmission_type": "Automatic or Manual",
        },
        "Toyota Hiace": {
            "seaters_label": "10–15",
            "seaters_min": 10,
            "seaters_max": 15,
            "transmission_label": "Manual or Automatic",
            "transmission_type": "Automatic or Manual",
        },
        "Toyota Innova": {
            "seaters_label": "7–8",
            "seaters_min": 7,
            "seaters_max": 8,
            "transmission_label": "Manual or Automatic",
            "transmission_type": "Automatic or Manual",
        },
        "Toyota Vios": {
            "seaters_label": "5",
            "seaters_min": 5,
            "seaters_max": 5,
            "transmission_label": "Manual or Automatic",
            "transmission_type": "Automatic or Manual",
        },
    }

    # enrich cars with specs (for display AND filtering)
    for car in cars:
        spec = specs.get(car["name"])
        if spec:
            car.update(spec)
        else:
            car.setdefault("seaters_label", "")
            car.setdefault("seaters_min", None)
            car.setdefault("seaters_max", None)
            car.setdefault("transmission_label", "")
            car.setdefault("transmission_type", "")

    # 3. Read filters from query string
    car_type_filter = (request.args.get("car_type") or "").strip()
    seaters_filter = (request.args.get("seaters") or "").strip()
    transmission_filter = (request.args.get("transmission") or "").strip()
    min_price_str = (request.args.get("min_price") or "").strip()
    max_price_str = (request.args.get("max_price") or "").strip()

    min_price = None
    max_price = None
    try:
        if min_price_str:
            min_price = float(min_price_str)
    except ValueError:
        min_price = None

    try:
        if max_price_str:
            max_price = float(max_price_str)
    except ValueError:
        max_price = None

    # 4. Apply filters in Python
    filtered_cars = []
    for car in cars:
        # type
        if car_type_filter and car["car_type"] != car_type_filter:
            continue

        # price
        price = float(car["price_per_day"])
        if min_price is not None and price < min_price:
            continue
        if max_price is not None and price > max_price:
            continue

        # transmission
        if transmission_filter:
            if car["transmission_type"] != transmission_filter:
                continue

        # seaters
        if seaters_filter:
            if car["seaters_min"] is None or car["seaters_max"] is None:
                continue

            if seaters_filter == "9-18":
                # any car whose range overlaps 9–18
                if car["seaters_max"] < 9 or car["seaters_min"] > 18:
                    continue
            else:
                try:
                    needed = int(seaters_filter)
                except ValueError:
                    needed = None

                if needed is not None:
                    if not (car["seaters_min"] <= needed <= car["seaters_max"]):
                        continue

        filtered_cars.append(car)

    return render_template("gallery.html", cars=filtered_cars)


# ---------- BOOKING + PAYMENT FLOW ----------


@app.route("/book/<int:car_id>", methods=["GET", "POST"])
@login_required
def book(car_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM cars WHERE id = %s", (car_id,))
    car = cursor.fetchone()

    if not car:
        conn.close()
        flash("Car not found.", "danger")
        return redirect(url_for("gallery"))

    if request.method == "GET":
        conn.close()
        return render_template("book.html", car=car)

    # ---------- 1. BASIC FIELDS ----------
    pickup_date = request.form.get("pickup_date", "").strip()
    pickup_time = request.form.get("pickup_time", "").strip()
    return_date = request.form.get("return_date", "").strip()
    return_time = request.form.get("return_time", "").strip()

    if not (pickup_date and pickup_time and return_date and return_time):
        conn.close()
        flash("Please complete pickup and return date & time.", "danger")
        return render_template("book.html", car=car)

    if not request.form.get("agree_terms"):
        conn.close()
        flash("You must agree to the rental terms and conditions to continue.", "danger")
        return render_template("book.html", car=car)

    # ---------- 2. PARSE DATES ----------
    try:
        pickup_dt = datetime.strptime(f"{pickup_date} {pickup_time}", "%Y-%m-%d %H:%M")
        return_dt = datetime.strptime(f"{return_date} {return_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        conn.close()
        flash("Invalid date or time format.", "danger")
        return render_template("book.html", car=car)

    if return_dt <= pickup_dt:
        conn.close()
        flash("Return date & time must be after pickup date & time.", "danger")
        return render_template("book.html", car=car)

    # rental days
    diff_hours = (return_dt - pickup_dt).total_seconds() / 3600.0
    rental_days = max(1, ceil(diff_hours / 24))

    price_per_day = float(car["price_per_day"])
    rental_fee = rental_days * price_per_day

    # ---------- 3. ADD-ONS ----------
    has_child = bool(request.form.get("addon_child_seat"))
    has_toll = bool(request.form.get("addon_toll_rfid"))
    has_dashcam = bool(request.form.get("addon_dashcam"))

    addons_daily = 0.0
    if has_child:
        addons_daily += CHILD_SEAT_PER_DAY
    if has_toll:
        addons_daily += TOLL_RFID_PER_DAY
    if has_dashcam:
        addons_daily += DASHCAM_PER_DAY

    addons_total = addons_daily * rental_days

    # ---------- 4. LICENSE (REQUIRED) ----------
    license_file = request.files.get("license_file")
    if not license_file or license_file.filename.strip() == "":
        conn.close()
        flash("Please upload your driver's license ID before proceeding.", "danger")
        return render_template("book.html", car=car)

    license_filename = secure_filename(license_file.filename)
    license_path = os.path.join(app.config["UPLOAD_FOLDER"], license_filename)
    license_file.save(license_path)

    # ---------- 5. DISCOUNT (OPTIONAL, 20%) ----------
    # Basahin yung hidden fields galing sa form
    discount_choice = request.form.get("wants_discount", "no").lower()
    wants_discount = discount_choice == "yes"

    discount_type = request.form.get("discount_type", "").lower()

    discount_id_file = request.files.get("discount_id_file")
    discount_id_filename = None

    if wants_discount:
        # Must choose type + upload ID
        if discount_type not in {"senior", "pwd", "student"}:
            conn.close()
            flash("Please select a valid discount type (Senior / PWD / Student).", "danger")
            return render_template("book.html", car=car)

        if not discount_id_file or discount_id_file.filename.strip() == "":
            conn.close()
            flash("Please upload your discount ID to apply the discount.", "danger")
            return render_template("book.html", car=car)

        discount_id_filename = secure_filename(discount_id_file.filename)
        discount_id_path = os.path.join(app.config["UPLOAD_FOLDER"], discount_id_filename)
        discount_id_file.save(discount_id_path)

    # compute discount
    subtotal = rental_fee + addons_total
    discount_amount = 0.0
    if wants_discount and subtotal > 0:
        discount_amount = DISCOUNT_RATE * subtotal

    total_amount = subtotal - discount_amount

    summary = {
        "car_id": car_id,
        "car_name": car["name"],
        "car_type": car["car_type"],
        "price_per_day": price_per_day,
        "pickup_iso": pickup_dt.isoformat(),
        "return_iso": return_dt.isoformat(),
        "rental_days": rental_days,
        "rental_fee": rental_fee,
        "addons_daily": addons_daily,
        "addons": {
            "child_seat": has_child,
            "toll_rfid": has_toll,
            "dashcam": has_dashcam,
        },
        "addons_total": addons_total,
        "discount_applied": wants_discount,
        "discount_type": discount_type,
        "discount_rate": DISCOUNT_RATE if wants_discount else 0.0,
        "discount_amount": discount_amount,
        "total_amount": total_amount,
        "license_file": license_filename,
        "discount_id_file": discount_id_filename,
    }
    session["pending_payment"] = summary
    conn.close()

    return render_template(
        "payment_summary.html",
        car=car,
        summary=summary,
        pickup_dt=pickup_dt,
        return_dt=return_dt,
    )
@app.route("/payment/checkout", methods=["POST"])
@login_required
def payment_checkout():
    summary = session.get("pending_payment")
    if not summary:
        flash("No pending payment found. Please start a new booking.", "danger")
        return redirect(url_for("gallery"))

    payment_method = request.form.get("payment_method")
    if payment_method not in {"gcash", "maya", "card"}:
        flash("Please choose a payment method.", "danger")
        return redirect(url_for("book", car_id=summary["car_id"]))

    # Map to PayMongo payment_method_types
    if payment_method == "gcash":
        method_types = ["gcash"]
    elif payment_method == "maya":
        # Sa PayMongo docs ang ginagamit ay 'paymaya'
        method_types = ["paymaya"]
    else:
        method_types = ["card"]

    rental_days = summary["rental_days"]
    price_per_day = summary["price_per_day"]
    addons_total = summary["addons_total"]
    discount_amount = summary.get("discount_amount", 0.0)
    subtotal = summary["rental_fee"] + addons_total
    total_amount = summary["total_amount"]  # already discounted

    amount_centavos = int(round(total_amount * 100))

    # Optional: pro-rate discount across line items so PayMongo total matches
    factor = 1.0
    if subtotal > 0 and discount_amount > 0:
        factor = (subtotal - discount_amount) / subtotal

    rental_fee_discounted = summary["rental_fee"] * factor
    addons_total_discounted = addons_total * factor

    rental_unit_amount = int(round((rental_fee_discounted / rental_days) * 100))
    addons_unit_amount = int(round(addons_total_discounted * 100))

    line_items = [
        {
            "name": f"{summary['car_name']} rental",
            "amount": rental_unit_amount,
            "currency": "PHP",
            "quantity": rental_days,
            "description": f"{rental_days} day(s) x ₱{price_per_day:,.2f}",
        }
    ]

    if addons_total > 0:
        line_items.append(
            {
                "name": "Add-ons",
                "amount": addons_unit_amount,
                "currency": "PHP",
                "quantity": 1,
                "description": "Rental add-ons",
            }
        )

    attributes = {
        "line_items": line_items,
        "payment_method_types": method_types,
        "amount": amount_centavos,
        "currency": "PHP",
        "description": f"Car rental - {summary['car_name']}",
        "success_url": PAYMONGO_SUCCESS_URL,
        "cancel_url": PAYMONGO_CANCEL_URL,
        "show_line_items": True,
        "show_description": True,
        "metadata": {
            "user_id": str(session["user_id"]),
            "car_id": str(summary["car_id"]),
            "pickup": summary["pickup_iso"],
            "return": summary["return_iso"],
            "discount_applied": str(summary.get("discount_applied", False)),
            "discount_type": summary.get("discount_type") or "",
        },
    }

    # ✅ Only add billing if we have a non-empty email
    billing_email = session.get("email")
    if billing_email:
        attributes["billing"] = {
            "name": session.get("username", ""),
            "email": billing_email,
            "phone": None,
            "address": None,
        }

    payload = {
        "data": {
            "attributes": {
                "line_items": line_items,
                "payment_method_types": method_types,
                "amount": amount_centavos,
                "currency": "PHP",
                "description": f"Car rental - {summary['car_name']}",
                "success_url": PAYMONGO_SUCCESS_URL,
                "cancel_url": PAYMONGO_CANCEL_URL,
                "show_line_items": True,
                "show_description": True,
                "billing": {
                    "name": session.get("username", ""),
                    "email": session.get("email", ""),
                    "phone": None,
                    "address": None,
                },
                "metadata": {
                    "user_id": str(session["user_id"]),
                    "car_id": str(summary["car_id"]),
                    "pickup": summary["pickup_iso"],
                    "return": summary["return_iso"],
                    "discount_applied": str(summary.get("discount_applied", False)),
                    "discount_type": summary.get("discount_type") or "",
                },
            }
        }
    }

    # Headers + auth (Basic)
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
    }

    try:
        response = requests.post(
            "https://api.paymongo.com/v1/checkout_sessions",
            json=payload,
            headers=headers,
            auth=(PAYMONGO_SECRET_KEY, ""),  # Secret key as Basic Auth username
            timeout=15,
        )
    except requests.RequestException as e:
        print("PayMongo connection error:", e)
        flash("Failed to connect to PayMongo. Please try again later.", "danger")
        return redirect(url_for("book", car_id=summary["car_id"]))

    # 👇 NEW: show real PayMongo error so makita mo kung ano ang problema
    if response.status_code >= 400:
        try:
            error_body = response.json()
            print("PayMongo error response:", error_body)

            detail = ""
            if isinstance(error_body, dict) and "errors" in error_body:
                first_err = error_body["errors"][0]
                detail = first_err.get("detail") or first_err.get("title") or ""

            if detail:
                flash(
                    f"Payment error ({response.status_code}): {detail}",
                    "danger",
                )
            else:
                flash(
                    f"Payment session could not be created. "
                    f"HTTP {response.status_code}",
                    "danger",
                )
        except Exception:
            # fallback if JSON parse fails
            print("PayMongo raw error:", response.text)
            flash(
                f"Payment session could not be created. "
                f"HTTP {response.status_code}",
                "danger",
            )

        return redirect(url_for("book", car_id=summary["car_id"]))

    data = response.json()
    checkout_url = data.get("data", {}).get("attributes", {}).get("checkout_url")

    if not checkout_url:
        print("PayMongo response without checkout_url:", data)
        flash("Unexpected error from payment gateway.", "danger")
        return redirect(url_for("book", car_id=summary["car_id"]))

    return redirect(checkout_url)

@app.route("/payment/success")
@login_required
def payment_success():
    # In test mode, treat success as paid and create booking from summary
    summary = session.pop("pending_payment", None)

    if summary:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "INSERT INTO bookings (user_id, car_id, days, total_price) "
            "VALUES (%s, %s, %s, %s)",
            (
                session["user_id"],
                summary["car_id"],
                summary["rental_days"],
                summary["total_amount"],
            ),
        )
        conn.commit()
        conn.close()
        flash("Payment completed (test). Your booking is recorded.", "success")
    else:
        flash("Payment completed, but no pending booking was found.", "warning")

    return redirect(url_for("history"))


@app.route("/payment/cancel")
@login_required
def payment_cancel():
    flash("Payment was cancelled. You can try again anytime.", "info")
    return redirect(url_for("gallery"))


@app.route("/history")
@login_required
def history():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT b.id, c.name AS car_name, c.car_type, b.days, b.total_price
        FROM bookings b
        JOIN cars c ON b.car_id = c.id
        WHERE b.user_id = %s
        ORDER BY b.id DESC
        """,
        (session["user_id"],),
    )
    bookings = cursor.fetchall()
    conn.close()
    return render_template("history.html", bookings=bookings)


@app.route("/cancel/<int:booking_id>", methods=["POST"])
@login_required
def cancel_booking(booking_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "DELETE FROM bookings WHERE id = %s AND user_id = %s",
        (booking_id, session["user_id"]),
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted:
        flash("Booking cancelled.", "info")
    else:
        flash("Unable to cancel booking.", "danger")

    return redirect(url_for("history"))


@app.route("/profile")
@login_required
def user_profile():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, username, is_admin FROM users WHERE id = %s",
        (session["user_id"],),
    )
    user = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) AS cnt FROM bookings WHERE user_id = %s", (session["user_id"],))
    booking_count = cursor.fetchone()["cnt"]

    cursor.execute(
        "SELECT IFNULL(SUM(total_price), 0) AS total FROM bookings WHERE user_id = %s",
        (session["user_id"],),
    )
    total_spent = cursor.fetchone()["total"] or 0

    cursor.execute(
        """
        SELECT b.id, c.name AS car_name, b.days, b.total_price
        FROM bookings b
        JOIN cars c ON b.car_id = c.id
        WHERE b.user_id = %s
        ORDER BY b.id DESC
        LIMIT 5
        """,
        (session["user_id"],),
    )
    recent = cursor.fetchall()
    conn.close()

    stats = {"booking_count": booking_count, "total_spent": total_spent}
    return render_template("user_profile.html", user=user, stats=stats, recent=recent)




@app.route("/admin/cars/new", methods=["GET", "POST"])
@admin_required
def admin_add_car():
    if request.method == "POST":
        name = request.form["name"].strip()
        car_type = request.form["car_type"].strip()
        price_raw = request.form["price_per_day"].strip()
        image_url = request.form.get("image_url", "").strip() or None

        if not name or not car_type or not price_raw:
            flash("All fields except image URL are required.", "danger")
            return render_template(
                "admin_car_form.html",
                action="Add",
                car={
                    "name": name,
                    "car_type": car_type,
                    "price_per_day": price_raw,
                    "image_url": image_url or "",
                },
            )

        try:
            price = float(price_raw)
        except ValueError:
            flash("Enter a valid price.", "danger")
            return render_template(
                "admin_car_form.html",
                action="Add",
                car={
                    "name": name,
                    "car_type": car_type,
                    "price_per_day": price_raw,
                    "image_url": image_url or "",
                },
            )

        if price <= 0:
            flash("Price must be greater than zero.", "danger")
            return render_template(
                "admin_car_form.html",
                action="Add",
                car={
                    "name": name,
                    "car_type": car_type,
                    "price_per_day": price_raw,
                    "image_url": image_url or "",
                },
            )

        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "INSERT INTO cars (name, car_type, price_per_day, image_url) "
            "VALUES (%s, %s, %s, %s)",
            (name, car_type, price, image_url),
        )
        conn.commit()
        conn.close()
        flash(f"{name} added to inventory.", "success")
        return redirect(url_for("admin_cars"))

    return render_template("admin_car_form.html", action="Add", car=None)


@app.route("/admin/cars/<int:car_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_car(car_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM cars WHERE id = %s", (car_id,))
    car = cursor.fetchone()

    if not car:
        conn.close()
        flash("Car not found.", "danger")
        return redirect(url_for("admin_cars"))

    if request.method == "POST":
        name = request.form["name"].strip()
        car_type = request.form["car_type"].strip()
        price_raw = request.form["price_per_day"].strip()
        image_url = request.form.get("image_url", "").strip() or None

        if not name or not car_type or not price_raw:
            flash("All fields except image URL are required.", "danger")
            return render_template(
                "admin_car_form.html",
                action="Edit",
                car={
                    "id": car_id,
                    "name": name,
                    "car_type": car_type,
                    "price_per_day": price_raw,
                    "image_url": image_url or "",
                },
            )

        try:
            price = float(price_raw)
        except ValueError:
            flash("Enter a valid price.", "danger")
            return render_template(
                "admin_car_form.html",
                action="Edit",
                car={
                    "id": car_id,
                    "name": name,
                    "car_type": car_type,
                    "price_per_day": price_raw,
                    "image_url": image_url or "",
                },
            )

        if price <= 0:
            flash("Price must be greater than zero.", "danger")
            return render_template(
                "admin_car_form.html",
                action="Edit",
                car={
                    "id": car_id,
                    "name": name,
                    "car_type": car_type,
                    "price_per_day": price_raw,
                    "image_url": image_url or "",
                },
            )

        cursor.execute(
            """
            UPDATE cars
            SET name = %s, car_type = %s, price_per_day = %s, image_url = %s
            WHERE id = %s
            """,
            (name, car_type, price, image_url, car_id),
        )
        conn.commit()
        conn.close()
        flash(f"{name} updated.", "success")
        return redirect(url_for("admin_cars"))

    car_dict = dict(car)
    conn.close()
    return render_template("admin_car_form.html", action="Edit", car=car_dict)


@app.route("/admin/cars/<int:car_id>/delete", methods=["POST"])
@admin_required
def admin_delete_car(car_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("DELETE FROM cars WHERE id = %s", (car_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted:
        flash("Car removed from inventory.", "info")
    else:
        flash("Car not found.", "danger")

    return redirect(url_for("admin_cars"))


# -------------------- JSON API ENDPOINTS --------------------


@app.route("/api/cars", methods=["GET"])
@login_required
def api_list_cars():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM cars ORDER BY name")
    cars = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(cars), 200


@app.route("/api/cars/<int:car_id>", methods=["GET"])
@login_required
def api_get_car(car_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM cars WHERE id = %s", (car_id,))
    car = cursor.fetchone()
    conn.close()
    if not car:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(car)), 200


@app.route("/api/cars", methods=["POST"])
@admin_required
def api_create_car():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    car_type = (payload.get("car_type") or "").strip()
    price_per_day = payload.get("price_per_day")
    image_url = (payload.get("image_url") or "").strip() or None
    if not name or not car_type or price_per_day is None:
        return jsonify({"error": "name, car_type, price_per_day required"}), 400
    try:
        price = float(price_per_day)
        if price <= 0:
            raise ValueError()
    except Exception:
        return jsonify({"error": "price_per_day must be a positive number"}), 400

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "INSERT INTO cars (name, car_type, price_per_day, image_url) "
        "VALUES (%s, %s, %s, %s)",
        (name, car_type, price, image_url),
    )
    conn.commit()
    new_id = cursor.lastrowid
    cursor.execute("SELECT * FROM cars WHERE id = %s", (new_id,))
    created = dict(cursor.fetchone())
    conn.close()
    return jsonify(created), 201


@app.route("/api/cars/<int:car_id>", methods=["PUT", "PATCH"])
@admin_required
def api_update_car(car_id):
    payload = request.get_json(silent=True) or {}
    fields = []
    values = []

    for key in ("name", "car_type", "image_url"):
        if key in payload:
            fields.append(f"{key} = %s")
            values.append((payload.get(key) or "").strip() or None)

    if "price_per_day" in payload:
        try:
            price = float(payload.get("price_per_day"))
            if price <= 0:
                raise ValueError()
        except Exception:
            return jsonify({"error": "price_per_day must be a positive number"}), 400
        fields.append("price_per_day = %s")
        values.append(price)

    if not fields:
        return jsonify({"error": "No valid fields to update"}), 400

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    values.append(car_id)
    cursor.execute(f"UPDATE cars SET {', '.join(fields)} WHERE id = %s", values)
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    conn.commit()
    cursor.execute("SELECT * FROM cars WHERE id = %s", (car_id,))
    updated = dict(cursor.fetchone())
    conn.close()
    return jsonify(updated), 200


@app.route("/api/cars/<int:car_id>", methods=["DELETE"])
@admin_required
def api_delete_car(car_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("DELETE FROM cars WHERE id = %s", (car_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    if not deleted:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"status": "deleted"}), 200


@app.route("/api/my/bookings", methods=["GET"])
@login_required
def api_my_bookings():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT b.id, c.name AS car_name, c.car_type, b.days, b.total_price
        FROM bookings b
        JOIN cars c ON b.car_id = c.id
        WHERE b.user_id = %s
        ORDER BY b.id DESC
        """,
        (session["user_id"],),
    )
    data = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(data), 200


@app.route("/api/bookings", methods=["GET"])
@admin_required
def api_all_bookings():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT b.id, u.username, c.name AS car_name, b.days, b.total_price
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN cars c ON b.car_id = c.id
        ORDER BY b.id DESC
        """
    )
    data = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(data), 200


@app.route("/api/bookings", methods=["POST"])
@login_required
def api_create_booking():
    payload = request.get_json(silent=True) or {}
    car_id = payload.get("car_id")
    days = payload.get("days")
    try:
        car_id = int(car_id)
        days = int(days)
    except Exception:
        return jsonify({"error": "car_id and days must be integers"}), 400
    if days <= 0:
        return jsonify({"error": "days must be at least 1"}), 400

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM cars WHERE id = %s", (car_id,))
    car = cursor.fetchone()
    if not car:
        conn.close()
        return jsonify({"error": "Car not found"}), 404

    total = days * float(car["price_per_day"])
    cursor.execute(
        "INSERT INTO bookings (user_id, car_id, days, total_price) "
        "VALUES (%s, %s, %s, %s)",
        (session["user_id"], car_id, days, total),
    )
    conn.commit()
    booking_id = cursor.lastrowid
    cursor.execute(
        "SELECT id, user_id, car_id, days, total_price FROM bookings "
        "WHERE id = %s",
        (booking_id,),
    )
    created = dict(cursor.fetchone())
    conn.close()
    return jsonify(created), 201


@app.route("/api/my/bookings/<int:booking_id>", methods=["DELETE"])
@login_required
def api_cancel_my_booking(booking_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "DELETE FROM bookings WHERE id = %s AND user_id = %s",
        (booking_id, session["user_id"]),
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    if not deleted:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"status": "cancelled"}), 200


# ---------- ENTRY POINT ----------


if __name__ == "__main__":
    # Ensure DB/tables exist before running
    init_db()
    app.run(debug=True, use_reloader=False)