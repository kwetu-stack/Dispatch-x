import os
from datetime import date, datetime
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dispatch-x-local-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(DATA_DIR, "app.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(40), unique=True, nullable=False)
    role = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    dispatches = db.relationship("Dispatch", foreign_keys="Dispatch.driver_id", backref="driver")


class Dispatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    route_name = db.Column(db.String(160), nullable=False)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    vehicle_number = db.Column(db.String(60), nullable=False)
    status = db.Column(db.String(30), default="draft", nullable=False)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime)
    deleted_by = db.Column(db.Integer, db.ForeignKey("user.id"))

    stops = db.relationship(
        "Stop",
        backref="dispatch",
        cascade="all, delete-orphan",
        order_by="Stop.sequence",
    )
    gps_logs = db.relationship(
        "GPSLog",
        backref="dispatch",
        cascade="all, delete-orphan",
        order_by="GPSLog.recorded_at.desc()",
    )


class Stop(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dispatch_id = db.Column(db.Integer, db.ForeignKey("dispatch.id"), nullable=False)
    sequence = db.Column(db.Integer, nullable=False)
    customer_name = db.Column(db.String(160), nullable=False)
    invoice_number = db.Column(db.String(80), nullable=False)
    invoice_value = db.Column(db.Float, nullable=False, default=0)
    status = db.Column(db.String(30), default="pending", nullable=False)
    delivered_at = db.Column(db.DateTime)
    returned_reason = db.Column(db.String(160))
    proof_photo = db.Column(db.String(255))
    proof_lat = db.Column(db.Float)
    proof_lng = db.Column(db.Float)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class GPSLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dispatch_id = db.Column(db.Integer, db.ForeignKey("dispatch.id"), nullable=False)
    driver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    driver = db.relationship("User")


def current_user():
    user_id = session.get("user_id")
    return db.session.get(User, user_id) if user_id else None


@app.context_processor
def inject_user():
    return {
        "current_user": current_user(),
        "can_edit_dispatch": can_edit_dispatch,
        "can_archive_dispatch": can_archive_dispatch,
    }


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)

    return wrapper


def roles_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("login", next=request.path))
            if user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def admin_or_clerk():
    return roles_required("admin", "clerk")


def admin_required():
    return roles_required("admin")


def active_dispatch_query():
    return Dispatch.query.filter(Dispatch.is_deleted.is_(False))


def active_dispatch_or_404(id):
    return active_dispatch_query().filter(Dispatch.id == id).first_or_404()


def can_edit_dispatch(dispatch):
    return dispatch.status in {"draft", "assigned"}


def can_archive_dispatch(dispatch):
    return dispatch.status in {"draft", "assigned", "completed"}


def allowed_photo(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in {
        "jpg",
        "jpeg",
        "png",
        "webp",
        "gif",
    }


def latest_driver_points():
    latest_rows = (
        db.session.query(GPSLog.driver_id, db.func.max(GPSLog.recorded_at).label("last_at"))
        .join(Dispatch, Dispatch.id == GPSLog.dispatch_id)
        .filter(Dispatch.status == "in_progress", Dispatch.is_deleted.is_(False))
        .group_by(GPSLog.driver_id)
        .subquery()
    )
    return (
        db.session.query(GPSLog, User, Dispatch)
        .join(latest_rows, (GPSLog.driver_id == latest_rows.c.driver_id) & (GPSLog.recorded_at == latest_rows.c.last_at))
        .join(User, User.id == GPSLog.driver_id)
        .join(Dispatch, Dispatch.id == GPSLog.dispatch_id)
        .filter(Dispatch.is_deleted.is_(False))
        .all()
    )


def refresh_dispatch_status(dispatch):
    if not dispatch.stops:
        return
    if all(stop.status in {"delivered", "returned"} for stop in dispatch.stops):
        dispatch.status = "completed"
        dispatch.completed_at = dispatch.completed_at or datetime.utcnow()


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(phone=phone, is_active=True).first()
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session["user_id"] = user.id
            session["role"] = user.role
            target = request.args.get("next")
            if target:
                return redirect(target)
            return redirect(url_for("driver_home" if user.role == "driver" else "dashboard"))
        flash("Invalid phone or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@admin_or_clerk()
def dashboard():
    today = date.today()
    today_dispatches = active_dispatch_query().filter(Dispatch.date == today).count()
    delivered = Stop.query.join(Dispatch).filter(Dispatch.date == today, Dispatch.is_deleted.is_(False), Stop.status == "delivered").count()
    pending = Stop.query.join(Dispatch).filter(Dispatch.date == today, Dispatch.is_deleted.is_(False), Stop.status == "pending").count()
    returned = Stop.query.join(Dispatch).filter(Dispatch.date == today, Dispatch.is_deleted.is_(False), Stop.status == "returned").count()
    active_drivers = (
        db.session.query(db.func.count(db.distinct(Dispatch.driver_id)))
        .filter(Dispatch.status == "in_progress", Dispatch.is_deleted.is_(False))
        .scalar()
    )
    recent = active_dispatch_query().order_by(Dispatch.created_at.desc()).limit(8).all()
    return render_template(
        "dashboard.html",
        stats={
            "today_dispatches": today_dispatches,
            "delivered": delivered,
            "pending": pending,
            "returned": returned,
            "active_drivers": active_drivers,
        },
        recent=recent,
    )


@app.route("/dispatches")
@admin_or_clerk()
def dispatches():
    rows = active_dispatch_query().order_by(Dispatch.date.desc(), Dispatch.created_at.desc()).all()
    return render_template("dispatches.html", dispatches=rows)


@app.route("/dispatches/new", methods=["GET", "POST"])
@admin_or_clerk()
def dispatch_new():
    drivers = User.query.filter_by(role="driver", is_active=True).order_by(User.name).all()
    if request.method == "POST":
        stop_names = request.form.getlist("customer_name[]")
        invoices = request.form.getlist("invoice_number[]")
        values = request.form.getlist("invoice_value[]")
        cleaned_stops = [
            (name.strip(), invoice.strip(), value.strip())
            for name, invoice, value in zip(stop_names, invoices, values)
            if name.strip() and invoice.strip()
        ]
        if not cleaned_stops:
            flash("Add at least one stop before saving a dispatch.", "error")
            return render_template("dispatch_form.html", drivers=drivers)

        dispatch = Dispatch(
            date=datetime.strptime(request.form["date"], "%Y-%m-%d").date(),
            route_name=request.form["route_name"].strip(),
            driver_id=int(request.form["driver_id"]),
            vehicle_number=request.form["vehicle_number"].strip(),
            status="assigned",
            created_by=current_user().id,
        )
        db.session.add(dispatch)
        db.session.flush()
        for index, (name, invoice, value) in enumerate(cleaned_stops, start=1):
            db.session.add(
                Stop(
                    dispatch_id=dispatch.id,
                    sequence=index,
                    customer_name=name,
                    invoice_number=invoice,
                    invoice_value=float(value or 0),
                )
            )
        db.session.commit()
        flash("Dispatch created and assigned.", "success")
        return redirect(url_for("dispatch_detail", id=dispatch.id))
    return render_template("dispatch_form.html", drivers=drivers)


@app.route("/dispatches/<int:id>", methods=["GET", "POST"])
@admin_or_clerk()
def dispatch_detail(id):
    dispatch = active_dispatch_or_404(id)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "assign":
            if not dispatch.stops:
                flash("Dispatch must have at least one stop before assignment.", "error")
            elif dispatch.status == "draft":
                dispatch.status = "assigned"
                db.session.commit()
                flash("Dispatch assigned.", "success")
        return redirect(url_for("dispatch_detail", id=id))
    return render_template("dispatch_detail.html", dispatch=dispatch)


@app.route("/dispatches/<int:id>/edit", methods=["GET", "POST"])
@admin_required()
def dispatch_edit(id):
    dispatch = active_dispatch_or_404(id)
    if not can_edit_dispatch(dispatch):
        flash("This dispatch can no longer be edited.", "error")
        return redirect(url_for("dispatch_detail", id=id))

    drivers = User.query.filter_by(role="driver", is_active=True).order_by(User.name).all()
    if request.method == "POST":
        dispatch.route_name = request.form["route_name"].strip()
        dispatch.driver_id = int(request.form["driver_id"])
        dispatch.vehicle_number = request.form["vehicle_number"].strip()
        db.session.commit()
        flash("Dispatch updated successfully.", "success")
        return redirect(url_for("dispatch_detail", id=id))
    return render_template("dispatch_form.html", dispatch=dispatch, drivers=drivers, edit_mode=True)


@app.route("/dispatches/<int:id>/archive", methods=["POST"])
@admin_required()
def dispatch_archive(id):
    dispatch = active_dispatch_or_404(id)
    if not can_archive_dispatch(dispatch):
        flash("This dispatch cannot be archived.", "error")
        return redirect(url_for("dispatches"))

    dispatch.is_deleted = True
    dispatch.deleted_at = datetime.utcnow()
    dispatch.deleted_by = current_user().id
    db.session.commit()
    flash("Dispatch archived successfully.", "success")
    return redirect(url_for("dispatches"))


@app.route("/gps")
@admin_or_clerk()
def gps():
    markers = [
        {
            "driver": user.name,
            "route": dispatch.route_name,
            "lat": log.latitude,
            "lng": log.longitude,
            "last_update": log.recorded_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for log, user, dispatch in latest_driver_points()
    ]
    return render_template("gps.html", markers=markers)


@app.route("/driver", methods=["GET", "POST"])
@roles_required("driver")
def driver_home():
    user = current_user()
    dispatch = (
        Dispatch.query.filter(
            Dispatch.driver_id == user.id,
            Dispatch.status.in_(["assigned", "in_progress"]),
            Dispatch.is_deleted.is_(False),
        )
        .order_by(Dispatch.date.asc(), Dispatch.created_at.asc())
        .first()
    )
    if request.method == "POST":
        if not dispatch:
            flash("No assigned dispatch to start.", "error")
        elif not dispatch.stops:
            flash("Dispatch must have at least one stop before starting.", "error")
        elif dispatch.status == "assigned":
            dispatch.status = "in_progress"
            dispatch.started_at = datetime.utcnow()
            db.session.commit()
            flash("Trip started. GPS tracking is active.", "success")
        return redirect(url_for("driver_home"))
    return render_template("driver.html", dispatch=dispatch)


@app.route("/driver/stop/<int:id>", methods=["GET", "POST"])
@roles_required("driver")
def driver_stop(id):
    stop = db.get_or_404(Stop, id)
    user = current_user()
    if stop.dispatch.is_deleted:
        abort(404)
    if stop.dispatch.driver_id != user.id:
        abort(403)
    if stop.dispatch.status != "in_progress":
        flash("Start the trip before updating stops.", "error")
        return redirect(url_for("driver_home"))

    if request.method == "POST":
        action = request.form.get("action")
        if action == "delivered":
            photo = request.files.get("proof_photo")
            lat = request.form.get("proof_lat")
            lng = request.form.get("proof_lng")
            if not photo or not photo.filename:
                flash("Delivery photo is required.", "error")
            elif not allowed_photo(photo.filename):
                flash("Use a JPG, PNG, WEBP, or GIF photo.", "error")
            elif not lat or not lng:
                flash("GPS capture is required before delivery can be saved.", "error")
            else:
                filename = secure_filename(photo.filename)
                stored_name = f"stop_{stop.id}_{int(datetime.utcnow().timestamp())}_{filename}"
                photo.save(os.path.join(app.config["UPLOAD_FOLDER"], stored_name))
                stop.status = "delivered"
                stop.delivered_at = datetime.utcnow()
                stop.proof_photo = stored_name
                stop.proof_lat = float(lat)
                stop.proof_lng = float(lng)
                stop.returned_reason = None
                refresh_dispatch_status(stop.dispatch)
                db.session.commit()
                flash("Delivery saved with photo and GPS.", "success")
                return redirect(url_for("driver_home"))
        elif action == "returned":
            reason = request.form.get("returned_reason", "").strip()
            if not reason:
                flash("Select a return reason.", "error")
            else:
                stop.status = "returned"
                stop.returned_reason = reason
                stop.notes = request.form.get("notes", "").strip()
                refresh_dispatch_status(stop.dispatch)
                db.session.commit()
                flash("Return saved.", "success")
                return redirect(url_for("driver_home"))
    return render_template("stop_detail.html", stop=stop)


@app.route("/api/gps", methods=["POST"])
@roles_required("driver")
def api_gps():
    user = current_user()
    dispatch = Dispatch.query.filter_by(driver_id=user.id, status="in_progress", is_deleted=False).first()
    if not dispatch:
        return jsonify({"ok": False, "message": "No in-progress dispatch."}), 409
    payload = request.get_json(silent=True) or {}
    lat = payload.get("latitude")
    lng = payload.get("longitude")
    if lat is None or lng is None:
        return jsonify({"ok": False, "message": "Latitude and longitude are required."}), 400
    db.session.add(GPSLog(dispatch_id=dispatch.id, driver_id=user.id, latitude=float(lat), longitude=float(lng)))
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.errorhandler(403)
def forbidden(_):
    return render_template("404.html", message="You do not have access to that page."), 403


@app.errorhandler(404)
def page_not_found(_):
    return render_template("404.html", message="That page could not be found."), 404


def seed_data():
    if User.query.first():
        return

    users = [
        User(name="Admin User", phone="0700000001", role="admin", password_hash=generate_password_hash("admin123")),
        User(name="Dispatch Clerk", phone="0700000002", role="clerk", password_hash=generate_password_hash("clerk123")),
        User(name="James Mwangi", phone="0700000003", role="driver", password_hash=generate_password_hash("driver123")),
        User(name="Amina Otieno", phone="0700000004", role="driver", password_hash=generate_password_hash("driver123")),
    ]
    db.session.add_all(users)
    db.session.flush()

    d1 = Dispatch(
        date=date.today(),
        route_name="Nairobi CBD Retail",
        driver_id=users[2].id,
        vehicle_number="KDA 234X",
        status="in_progress",
        started_at=datetime.utcnow(),
        created_by=users[0].id,
    )
    d2 = Dispatch(
        date=date.today(),
        route_name="Westlands FMCG Loop",
        driver_id=users[3].id,
        vehicle_number="KCB 918Q",
        status="assigned",
        created_by=users[1].id,
    )
    db.session.add_all([d1, d2])
    db.session.flush()

    db.session.add_all(
        [
            Stop(dispatch_id=d1.id, sequence=1, customer_name="Kwetu Mini Mart", invoice_number="INV-1001", invoice_value=24850, status="delivered", delivered_at=datetime.utcnow(), proof_lat=-1.286389, proof_lng=36.817223, proof_photo="seed_delivery.txt"),
            Stop(dispatch_id=d1.id, sequence=2, customer_name="Metro Fresh Stores", invoice_number="INV-1002", invoice_value=18300, status="pending"),
            Stop(dispatch_id=d1.id, sequence=3, customer_name="City Basket", invoice_number="INV-1003", invoice_value=9750, status="returned", returned_reason="Shop closed"),
            Stop(dispatch_id=d2.id, sequence=1, customer_name="Parklands Grocer", invoice_number="INV-2001", invoice_value=31400, status="pending"),
            Stop(dispatch_id=d2.id, sequence=2, customer_name="Soko Express", invoice_number="INV-2002", invoice_value=12750, status="pending"),
            Stop(dispatch_id=d2.id, sequence=3, customer_name="Mtaa Essentials", invoice_number="INV-2003", invoice_value=22600, status="pending"),
        ]
    )
    db.session.add_all(
        [
            GPSLog(dispatch_id=d1.id, driver_id=users[2].id, latitude=-1.286389, longitude=36.817223),
            GPSLog(dispatch_id=d1.id, driver_id=users[2].id, latitude=-1.2819, longitude=36.8219),
        ]
    )
    seed_photo = os.path.join(UPLOAD_DIR, "seed_delivery.txt")
    with open(seed_photo, "w", encoding="utf-8") as handle:
        handle.write("Seed proof placeholder. New deliveries save real uploaded photos here.")
    db.session.commit()


def ensure_dispatch_archive_columns():
    existing_columns = {column["name"] for column in inspect(db.engine).get_columns("dispatch")}
    migrations = {
        "is_deleted": "ALTER TABLE dispatch ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0",
        "deleted_at": "ALTER TABLE dispatch ADD COLUMN deleted_at DATETIME",
        "deleted_by": "ALTER TABLE dispatch ADD COLUMN deleted_by INTEGER",
    }
    for column_name, statement in migrations.items():
        if column_name not in existing_columns:
            db.session.execute(text(statement))
    db.session.commit()


def init_db():
    db.create_all()
    ensure_dispatch_archive_columns()
    seed_data()


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(debug=True)
