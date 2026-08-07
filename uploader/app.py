"""Standalone phone-to-laptop photo receiver.

Zero-install way to get phone photos onto this machine: run this script,
scan the printed QR code from a phone on the same WiFi network, enter the
printed PIN once, then upload photos through the browser. Non-HEIC
originals land unmodified in photos/. HEIC/HEIF originals are converted
to a full-resolution JPEG and discarded, because Qt (and so the Happy Boy
Atelier app) can't decode HEIC at all -- keeping the untouched HEIC around
would just be unusable clutter. A small JPEG thumbnail is generated for
every photo for the gallery only.

Deliberately standalone — not part of the Happy Boy Atelier PySide6 app.
Run with its own venv: pip install -r requirements.txt && python app.py
"""

import secrets
import socket
import time
import uuid
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from PIL import Image
import pillow_heif

pillow_heif.register_heif_opener()

BASE_DIR = Path(__file__).resolve().parent
PHOTOS_DIR = BASE_DIR / "photos"
THUMBS_DIR = PHOTOS_DIR / ".thumbnails"
PHOTOS_DIR.mkdir(exist_ok=True)
THUMBS_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "heic", "heif", "webp"}
HEIC_EXTENSIONS = {"heic", "heif"}
THUMBNAIL_MAX_DIM = 480
THUMBNAIL_QUALITY = 82
CONVERTED_JPEG_QUALITY = 95
PORT = 5000

PIN = f"{secrets.randbelow(1_000_000):06d}"

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)


def allowed_file(filename):
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def make_thumbnail(source_path, dest_path):
    with Image.open(source_path) as image:
        image = image.convert("RGB")
        image.thumbnail((THUMBNAIL_MAX_DIM, THUMBNAIL_MAX_DIM))
        image.save(dest_path, "JPEG", quality=THUMBNAIL_QUALITY)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if secrets.compare_digest(request.form.get("pin", ""), PIN):
            session["authenticated"] = True
            return redirect(url_for("index"))
        error = "Incorrect PIN."
    return render_template("login.html", error=error)


@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    file = request.files.get("file")
    if file is None or file.filename == "":
        return jsonify(ok=False, error="No file provided."), 400
    if not allowed_file(file.filename):
        return jsonify(ok=False, error="Unsupported file type."), 400

    ext = file.filename.rsplit(".", 1)[1].lower()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    stem = f"{stamp}-{uuid.uuid4().hex[:6]}"
    dest_path = PHOTOS_DIR / f"{stem}.{ext}"
    # Save the original first and independently of conversion/thumbnailing,
    # so a later failure (corrupt file, unsupported HEIC variant) never
    # prevents the original from landing.
    file.save(dest_path)
    filename = dest_path.name

    thumbnail = None
    warning = None
    try:
        if ext in HEIC_EXTENSIONS:
            # Qt has no HEIC decoder, so a raw .heic file can't be
            # imported into the atelier app at all -- convert to a
            # full-resolution JPEG and drop the original rather than
            # leaving an unusable file behind.
            converted_path = PHOTOS_DIR / f"{stem}.jpg"
            with Image.open(dest_path) as image:
                image.convert("RGB").save(converted_path, "JPEG", quality=CONVERTED_JPEG_QUALITY)
            dest_path.unlink()
            dest_path = converted_path
            filename = dest_path.name

        thumb_name = f"{dest_path.stem}.jpg"
        make_thumbnail(dest_path, THUMBS_DIR / thumb_name)
        thumbnail = thumb_name
    except Exception as exc:
        warning = f"Conversion/thumbnail generation failed: {exc}"

    response = {"ok": True, "filename": filename, "thumbnail": thumbnail}
    if warning:
        response["warning"] = warning
    return jsonify(response)


@app.route("/photos")
@login_required
def photos():
    entries = []
    for path in PHOTOS_DIR.iterdir():
        if not path.is_file() or not allowed_file(path.name):
            continue
        thumb_path = THUMBS_DIR / f"{path.stem}.jpg"
        entries.append(
            {
                "filename": path.name,
                "thumbnail": thumb_path.name if thumb_path.exists() else None,
                "mtime": path.stat().st_mtime,
            }
        )
    entries.sort(key=lambda entry: entry["mtime"], reverse=True)
    return jsonify(entries)


@app.route("/photos_dir/<filename>")
@login_required
def photos_dir(filename):
    return send_from_directory(PHOTOS_DIR, filename)


@app.route("/thumbnails/<filename>")
@login_required
def thumbnails(filename):
    return send_from_directory(THUMBS_DIR, filename)


def get_lan_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def print_startup_banner(url):
    print("=" * 60)
    print("Happy Boy Atelier - Upload From Phone")
    print("=" * 60)
    print(f"  URL: {url}")
    print(f"  PIN: {PIN}")
    print("=" * 60)
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make()
        qr.print_ascii(invert=True)
    except ImportError:
        pass
    except UnicodeEncodeError:
        # Some Windows terminals default to a legacy codepage (cp1252)
        # that can't render the QR code's block characters. The QR code
        # is a convenience, not a requirement (the URL is printed above
        # regardless), so fall back to typing the URL instead of crashing.
        print("(QR code couldn't be rendered in this terminal - type the URL above instead.)")
    print("Scan the QR code (or type the URL), then enter the PIN above.")
    print("Press Ctrl+C to stop.")


if __name__ == "__main__":
    lan_ip = get_lan_ip()
    server_url = f"http://{lan_ip}:{PORT}"
    print_startup_banner(server_url)
    app.run(host="0.0.0.0", port=PORT)
