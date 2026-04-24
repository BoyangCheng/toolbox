import os
import sqlite3
import socket
import uuid
import secrets
from datetime import datetime, timedelta
from flask import (
    Flask, request, render_template, redirect, url_for,
    send_from_directory, jsonify, abort, session
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "data.db")
SECRET_KEY_FILE = os.path.join(BASE_DIR, ".secret_key")
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

os.makedirs(UPLOAD_DIR, exist_ok=True)


def _load_or_create_secret_key():
    """持久化 secret key：重启后 session 不失效。"""
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
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)  # session 30 天有效


# ---------- DB ----------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
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
    # Migrate: add ip column to older DBs if missing
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
    # Honor X-Forwarded-For if a proxy is in front; otherwise fall back to remote_addr.
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"


def log_action(action, ip, detail=""):
    print(f"[{now_str()}] {action} from {ip} {detail}", flush=True)


# ---------- routes ----------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/submit", methods=["POST"])
def submit():
    title = (request.form.get("title") or "").strip()
    content = (request.form.get("content") or "").strip()
    author = (request.form.get("author") or "").strip()

    if not title or not content or not author:
        return render_template(
            "index.html",
            error="标题、内容、上传人都不能为空",
            form={"title": title, "content": content, "author": author},
        ), 400

    image_name = None
    file = request.files.get("image")
    if file and file.filename:
        if not allowed_file(file.filename):
            return render_template(
                "index.html",
                error="图片格式不支持 (仅 png/jpg/jpeg/gif/webp/bmp)",
                form={"title": title, "content": content, "author": author},
            ), 400
        ext = file.filename.rsplit(".", 1)[1].lower()
        image_name = f"{uuid.uuid4().hex}.{ext}"
        file.save(os.path.join(UPLOAD_DIR, image_name))

    ip = client_ip()
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO requirements (title, content, author, image, created_at, ip) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (title, content, author, image_name, now_str(), ip),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    session["name"] = author          # 记住名字到 session
    session.permanent = True
    log_action("SUBMIT requirement", ip, f"id={new_id} author={author!r} title={title!r}")
    return redirect(url_for("list_requirements"))


@app.route("/requirements")
def list_requirements():
    conn = get_db()
    rows = conn.execute(
        "SELECT r.*, "
        "(SELECT COUNT(*) FROM comments c WHERE c.requirement_id = r.id) AS comment_count "
        "FROM requirements r ORDER BY r.id DESC"
    ).fetchall()
    conn.close()
    return render_template("list.html", items=rows)


@app.route("/requirements/<int:rid>")
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
    return render_template("detail.html", req=req, comments=comments)


@app.route("/requirements/<int:rid>/like", methods=["POST"])
def like(rid):
    conn = get_db()
    cur = conn.execute("SELECT likes FROM requirements WHERE id = ?", (rid,))
    row = cur.fetchone()
    if not row:
        conn.close()
        abort(404)
    new_likes = row["likes"] + 1
    conn.execute("UPDATE requirements SET likes = ? WHERE id = ?", (new_likes, rid))
    conn.commit()
    conn.close()
    return jsonify({"likes": new_likes})


@app.route("/requirements/<int:rid>/comment", methods=["POST"])
def add_comment(rid):
    author = (request.form.get("author") or "").strip()
    content = (request.form.get("content") or "").strip()
    if not author or not content:
        return redirect(url_for("requirement_detail", rid=rid) + "?err=1")
    conn = get_db()
    exists = conn.execute(
        "SELECT 1 FROM requirements WHERE id = ?", (rid,)
    ).fetchone()
    if not exists:
        conn.close()
        abort(404)
    ip = client_ip()
    conn.execute(
        "INSERT INTO comments (requirement_id, author, content, created_at, ip) "
        "VALUES (?, ?, ?, ?, ?)",
        (rid, author, content, now_str(), ip),
    )
    conn.commit()
    conn.close()
    session["name"] = author          # 记住名字到 session
    session.permanent = True
    log_action("COMMENT", ip, f"rid={rid} author={author!r}")
    return redirect(url_for("requirement_detail", rid=rid))


@app.route("/requirements/<int:rid>/status", methods=["POST"])
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
    port = 5000
    print("=" * 50)
    print(" 我觉得系统应该是这样的 !")
    print("=" * 50)
    print(f" 本机访问:  http://127.0.0.1:{port}")
    print(f" 局域网访问: http://{ip}:{port}")
    print("=" * 50)
    app.run(host="0.0.0.0", port=port, debug=False)
