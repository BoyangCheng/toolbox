import os
import json
import sqlite3
import socket
import uuid
import secrets
import threading
import time
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Flask, request, render_template, redirect, url_for,
    send_from_directory, jsonify, abort, session
)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "data.db")
DATA_DIR = os.path.join(BASE_DIR, "data")
STATE_FILE = os.path.join(DATA_DIR, "flowchart_state.json")
SECRET_KEY_FILE = os.path.join(BASE_DIR, ".secret_key")
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)


def _load_or_create_secret_key():
    if os.path.exists(SECRET_KEY_FILE):
        return open(SECRET_KEY_FILE).read().strip()
    key = secrets.token_hex(32)
    with open(SECRET_KEY_FILE, "w") as f:
        f.write(key)
    return key


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["SECRET_KEY"] = _load_or_create_secret_key()
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)


# ---------- DB ----------
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            department TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS requirements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            author TEXT NOT NULL,
            image TEXT,
            status TEXT NOT NULL DEFAULT '待处理',
            likes INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            ip TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requirement_id INTEGER NOT NULL,
            author TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            ip TEXT,
            FOREIGN KEY (requirement_id) REFERENCES requirements(id) ON DELETE CASCADE
        )
    """)
    for table in ("requirements", "comments"):
        cols = [r["name"] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        if "ip" not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN ip TEXT")
    conn.commit()
    conn.close()


# ---------- helpers ----------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def client_ip():
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"


def log_action(action, ip, detail=""):
    print(f"[{now_str()}] {action} from {ip} {detail}", flush=True)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


# ---------- AUTH ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        phone = (request.form.get("phone") or "").strip()
        password = (request.form.get("password") or "").strip()
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session.permanent = True
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_department"] = user["department"]
            next_url = request.args.get("next")
            return redirect(next_url or url_for("dashboard"))
        error = "手机号或密码不正确"
    return render_template("login.html", error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    error = None
    form = {}
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        phone = (request.form.get("phone") or "").strip()
        department = (request.form.get("department") or "").strip()
        password = (request.form.get("password") or "").strip()
        form = {"name": name, "phone": phone, "department": department}
        if not all([name, phone, department, password]):
            error = "所有字段均为必填"
        elif len(password) < 6:
            error = "密码至少6位"
        else:
            try:
                conn = get_db()
                conn.execute(
                    "INSERT INTO users (name, phone, department, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                    (name, phone, department, generate_password_hash(password), now_str()),
                )
                conn.commit()
                conn.close()
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                error = "该手机号已注册"
    return render_template("register.html", error=error, form=form)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- DASHBOARD ----------
@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html")


# ---------- FLOWCHART ----------
@app.route("/flowchart")
@login_required
def flowchart():
    return render_template("flowchart.html")


# ---------- Flowchart state (versioned) & presence ----------
_flowchart_lock = threading.Lock()
_presence = {}  # user_id -> (name, last_seen_ts)
PRESENCE_TTL = 15  # seconds


def _load_flowchart_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


@app.route("/flowchart/api/state", methods=["GET", "POST"])
@login_required
def flowchart_state():
    if request.method == "GET":
        data = _load_flowchart_state()
        if "_version" not in data:
            data["_version"] = 0
        return jsonify(data)

    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "bad_json"}), 400
    if not isinstance(payload, dict):
        return jsonify({"error": "bad_json"}), 400

    client_version = payload.pop("_clientVersion", 0)
    force = bool(payload.pop("_force", False))

    with _flowchart_lock:
        current = _load_flowchart_state()
        server_version = int(current.get("_version", 0))
        if not force and client_version != server_version:
            return jsonify({
                "error": "version_conflict",
                "serverVersion": server_version,
            }), 409
        payload["_version"] = server_version + 1
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, STATE_FILE)
    return jsonify({"ok": True, "version": payload["_version"]})


@app.route("/flowchart/api/presence", methods=["POST"])
@login_required
def flowchart_presence():
    now = time.time()
    uid = session["user_id"]
    uname = session["user_name"]
    with _flowchart_lock:
        _presence[uid] = (uname, now)
        # purge stale
        for k in list(_presence.keys()):
            if now - _presence[k][1] > PRESENCE_TTL:
                del _presence[k]
        active = [
            {"id": k, "name": v[0]}
            for k, v in _presence.items()
            if k != uid
        ]
    return jsonify({"active": active})


# ---------- REQUESTS ----------
@app.route("/requests")
@login_required
def list_requirements():
    conn = get_db()
    rows = conn.execute(
        "SELECT r.*, "
        "(SELECT COUNT(*) FROM comments c WHERE c.requirement_id = r.id) AS comment_count "
        "FROM requirements r ORDER BY r.id DESC"
    ).fetchall()
    conn.close()
    return render_template("requests_list.html", items=rows)


@app.route("/requests/new")
@login_required
def new_requirement():
    return render_template("requests_index.html")


@app.route("/requests/submit", methods=["POST"])
@login_required
def submit():
    title = (request.form.get("title") or "").strip()
    content = (request.form.get("content") or "").strip()
    author = session["user_name"]

    if not title or not content:
        return render_template(
            "requests_index.html",
            error="标题和内容不能为空",
            form={"title": title, "content": content},
        ), 400

    image_name = None
    file = request.files.get("image")
    if file and file.filename:
        if not allowed_file(file.filename):
            return render_template(
                "requests_index.html",
                error="图片格式不支持 (仅 png/jpg/jpeg/gif/webp/bmp)",
                form={"title": title, "content": content},
            ), 400
        ext = file.filename.rsplit(".", 1)[1].lower()
        image_name = f"{uuid.uuid4().hex}.{ext}"
        file.save(os.path.join(UPLOAD_DIR, image_name))

    ip = client_ip()
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO requirements (title, content, author, image, created_at, ip) VALUES (?, ?, ?, ?, ?, ?)",
        (title, content, author, image_name, now_str(), ip),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    log_action("SUBMIT requirement", ip, f"id={new_id} author={author!r} title={title!r}")
    return redirect(url_for("list_requirements"))


@app.route("/requests/<int:rid>")
@login_required
def requirement_detail(rid):
    conn = get_db()
    req = conn.execute("SELECT * FROM requirements WHERE id = ?", (rid,)).fetchone()
    if not req:
        conn.close()
        abort(404)
    comments = conn.execute(
        "SELECT * FROM comments WHERE requirement_id = ? ORDER BY id ASC", (rid,)
    ).fetchall()
    conn.close()
    return render_template("requests_detail.html", req=req, comments=comments)


@app.route("/requests/<int:rid>/like", methods=["POST"])
@login_required
def like(rid):
    conn = get_db()
    row = conn.execute("SELECT likes FROM requirements WHERE id = ?", (rid,)).fetchone()
    if not row:
        conn.close()
        abort(404)
    new_likes = row["likes"] + 1
    conn.execute("UPDATE requirements SET likes = ? WHERE id = ?", (new_likes, rid))
    conn.commit()
    conn.close()
    return jsonify({"likes": new_likes})


@app.route("/requests/<int:rid>/comment", methods=["POST"])
@login_required
def add_comment(rid):
    author = session["user_name"]
    content = (request.form.get("content") or "").strip()
    if not content:
        return redirect(url_for("requirement_detail", rid=rid) + "?err=1")
    conn = get_db()
    if not conn.execute("SELECT 1 FROM requirements WHERE id = ?", (rid,)).fetchone():
        conn.close()
        abort(404)
    ip = client_ip()
    conn.execute(
        "INSERT INTO comments (requirement_id, author, content, created_at, ip) VALUES (?, ?, ?, ?, ?)",
        (rid, author, content, now_str(), ip),
    )
    conn.commit()
    conn.close()
    log_action("COMMENT", ip, f"rid={rid} author={author!r}")
    return redirect(url_for("requirement_detail", rid=rid))


@app.route("/requests/<int:rid>/status", methods=["POST"])
@login_required
def update_status(rid):
    status = (request.form.get("status") or "").strip()
    if status not in ("待处理", "进行中", "已完成", "已搁置"):
        abort(400)
    conn = get_db()
    conn.execute("UPDATE requirements SET status = ? WHERE id = ?", (status, rid))
    conn.commit()
    conn.close()
    return redirect(url_for("requirement_detail", rid=rid))


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


if __name__ == "__main__":
    init_db()
    ip = get_lan_ip()
    port = int(os.environ.get("PORT", 5000))
    mode = os.environ.get("SERVER_MODE", "dev").lower()
    print("=" * 50)
    print(" 荣信工具箱")
    print("=" * 50)
    print(f" 本机访问:  http://127.0.0.1:{port}")
    print(f" 局域网访问: http://{ip}:{port}")
    print(f" 模式: {mode}")
    print("=" * 50)
    if mode == "prod":
        from waitress import serve
        serve(app, host="0.0.0.0", port=port, threads=8)
    else:
        app.run(host="0.0.0.0", port=port, debug=False)
