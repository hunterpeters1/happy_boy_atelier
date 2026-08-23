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

import hashlib
import json
import os
import secrets
import socket
import threading
import time
import uuid
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
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

# -- "remember this device" --------------------------------------------
# The PIN (and the Flask session it unlocks) is deliberately short-lived —
# a fresh random PIN every process start, and app.secret_key below is
# regenerated every start too, which invalidates any old session cookie a
# browser might still be holding. That's the right model for the PIN
# itself, but it means a phone would have to re-enter a new PIN on *every*
# single launch of the uploader, forever — real friction for something
# meant to be a day-to-day tool, not a one-off.
#
# So "remembering" a device is deliberately a separate, independent trust
# layer bolted on top, not a side effect of extending the PIN session:
# on successful login (with the "remember this device" box checked), the
# server hands the browser a long-lived, high-entropy token in its own
# cookie, and remembers that token (hashed, not in plaintext -- so a
# leaked trusted_devices.json can't be replayed directly) in a small JSON
# file next to photos/. That file survives process restarts, so a
# remembered phone skips the PIN screen entirely on every future launch,
# while the PIN/session mechanism protecting *first-time* pairing is
# completely unchanged. "Forget this device" (the gallery page) removes
# just that one token, without touching the PIN model at all.
TRUSTED_DEVICES_PATH = BASE_DIR / "trusted_devices.json"
REMEMBER_COOKIE_NAME = "hba_device"
REMEMBER_COOKIE_MAX_AGE = 180 * 24 * 60 * 60  # ~6 months

# A manual `python app.py` run always generates its own random PIN. When
# launched by the desktop app instead (Help > Upload From Phone…, see
# app/dialogs/phone_upload_dialog.py), the launcher needs to know the PIN
# up front to show it/render a QR code — so it generates one itself and
# passes it through this env var, which takes priority here if present.
PIN = os.environ.get("HAPPY_BOY_UPLOADER_PIN") or f"{secrets.randbelow(1_000_000):06d}"

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


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _load_trusted_hashes() -> set:
    if not TRUSTED_DEVICES_PATH.exists():
        return set()
    try:
        data = json.loads(TRUSTED_DEVICES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()  # a corrupt file is treated as "no remembered devices", never a crash
    return set(data.get("tokens", []))


def _save_trusted_hashes() -> None:
    TRUSTED_DEVICES_PATH.write_text(
        json.dumps({"tokens": sorted(_trusted_hashes)}, indent=2), encoding="utf-8"
    )


# Loaded once at process start and kept in memory rather than re-read from
# disk on every request (every photo grid poll, every thumbnail) -- this
# is always a single process, so there's no cross-process cache to
# invalidate; _save_trusted_hashes() persists it on every actual change.
_trusted_hashes = _load_trusted_hashes()


def _is_remembered_device() -> bool:
    token = request.cookies.get(REMEMBER_COOKIE_NAME)
    return bool(token) and _hash_token(token) in _trusted_hashes


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("authenticated") or _is_remembered_device():
            return view(*args, **kwargs)
        return redirect(url_for("login"))

    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET" and _is_remembered_device():
        # A remembered phone hitting /login directly (e.g. an old
        # bookmark, or the session cookie expired but the device is still
        # trusted) shouldn't have to see the PIN screen at all.
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        if secrets.compare_digest(request.form.get("pin", ""), PIN):
            session["authenticated"] = True
            response = redirect(url_for("index"))
            if request.form.get("remember") == "on":
                token = secrets.token_urlsafe(32)
                _trusted_hashes.add(_hash_token(token))
                _save_trusted_hashes()
                response.set_cookie(
                    REMEMBER_COOKIE_NAME, token, max_age=REMEMBER_COOKIE_MAX_AGE,
                    httponly=True, samesite="Lax",
                )
            return response
        error = "Incorrect PIN."
    return render_template("login.html", error=error)


@app.route("/forget-device", methods=["POST"])
def forget_device():
    """Un-remembers *this* device only -- removes its one token from the
    trusted store and clears its cookie, without touching the PIN model
    or any other remembered device. Reachable from the gallery page
    itself (index.html), so an artist who uploaded from a borrowed/shared
    phone has a real way to revoke it again.
    """
    token = request.cookies.get(REMEMBER_COOKIE_NAME)
    if token:
        _trusted_hashes.discard(_hash_token(token))
        _save_trusted_hashes()
    session.pop("authenticated", None)
    response = redirect(url_for("login"))
    response.delete_cookie(REMEMBER_COOKIE_NAME)
    return response


def _delayed_exit() -> None:
    # A brief delay so the HTTP response below actually reaches the
    # caller before the process disappears. os._exit() (not
    # sys.exit()/a raised SystemExit, which a request-handling thread
    # can't cleanly unwind the whole server with anyway) skips Python
    # cleanup entirely -- deliberately, since the classic
    # `request.environ["werkzeug.server.shutdown"]` hook this used to
    # rely on was removed from newer werkzeug versions, and a hard exit
    # needs nothing from that API to work identically across versions.
    time.sleep(0.3)
    os._exit(0)


@app.route("/internal/shutdown", methods=["POST"])
def internal_shutdown():
    """Lets a newly-launched instance of this same tool ask a stale one
    still holding this port to get out of the way -- the self-service
    recovery path behind PhoneUploadDialog's "port already in use"
    handling (previously a dead end: close the dialog, hunt down the
    leftover process by hand, try again).

    Deliberately unauthenticated -- a new instance has no way to know an
    old instance's PIN, that's the whole reason this route exists -- but
    restricted to loopback callers only, so a phone on the LAN can never
    reach it even by guessing the URL. The desktop app is always the
    caller, and it's always running on this same machine.
    """
    if request.remote_addr not in ("127.0.0.1", "::1"):
        abort(403)
    threading.Thread(target=_delayed_exit, daemon=True).start()
    return jsonify(ok=True)


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
