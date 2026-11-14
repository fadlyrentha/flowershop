"""Helper bersama: autentikasi, hak akses, upload, notifikasi, format."""
import os
import uuid
from functools import wraps

from flask import abort, current_app, flash, g, redirect, request, session, url_for
from werkzeug.utils import secure_filename

import db as database

IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
VIDEO_EXT = {"mp4", "mov", "webm", "m4v"}
ALLOWED_EXT = IMAGE_EXT | VIDEO_EXT


def current_user():
    if "user" not in g:
        uid = session.get("user_id")
        g.user = database.query("SELECT * FROM users WHERE id = ?", (uid,), one=True) if uid else None
        if g.user is not None and not g.user["aktif"]:
            g.user = None
            session.clear()
    return g.user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            flash("Silakan masuk terlebih dahulu.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if user is None:
                flash("Silakan masuk terlebih dahulu.", "warning")
                return redirect(url_for("auth.login", next=request.path))
            if user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def feature_required(feature):
    """Pastikan peran pengguna punya fitur ini dan fitur sedang diaktifkan master."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if user is None:
                flash("Silakan masuk terlebih dahulu.", "warning")
                return redirect(url_for("auth.login", next=request.path))
            if not database.feature_enabled(user["role"], feature):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def save_upload(file_storage, subdir=""):
    if not file_storage or not file_storage.filename:
        return ""
    original = secure_filename(file_storage.filename)
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in ALLOWED_EXT:
        flash("Format berkas tidak didukung: %s" % original, "warning")
        return ""
    name = uuid.uuid4().hex + "." + ext
    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], subdir)
    os.makedirs(folder, exist_ok=True)
    file_storage.save(os.path.join(folder, name))
    return (subdir + "/" + name) if subdir else name


def save_image(file_storage, subdir=""):
    """Simpan unggahan gambar saja (foto produk, logo, dsb)."""
    if not file_storage or not file_storage.filename:
        return ""
    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in IMAGE_EXT:
        flash("Format gambar tidak didukung: %s" % file_storage.filename, "warning")
        return ""
    return save_upload(file_storage, subdir)


def delete_upload(name):
    """Hapus berkas unggahan bila ada. Aman untuk nama kosong atau tidak valid."""
    if not name or ".." in name or os.path.isabs(name):
        return
    folder = current_app.config["UPLOAD_FOLDER"]
    path = os.path.normpath(os.path.join(folder, name))
    if not path.startswith(os.path.normpath(folder) + os.sep):
        return
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def is_video(path):
    return bool(path) and path.rsplit(".", 1)[-1].lower() in VIDEO_EXT


def notify(judul, pesan="", link="", role="", user_id=None):
    database.execute(
        "INSERT INTO notifications (role, user_id, judul, pesan, link, dibaca, created_at)"
        " VALUES (?, ?, ?, ?, ?, 0, ?)",
        (role, user_id, judul, pesan, link, database.now()),
    )


def notify_roles(roles, judul, pesan="", link=""):
    for role in roles:
        notify(judul, pesan, link, role=role)


def unread_count():
    user = current_user()
    if not user:
        return 0
    row = database.query(
        "SELECT COUNT(*) AS c FROM notifications WHERE dibaca = 0 AND (user_id = ? OR role = ?)",
        (user["id"], user["role"]), one=True,
    )
    return row["c"] if row else 0


def rupiah(value):
    try:
        value = int(value or 0)
    except (TypeError, ValueError):
        value = 0
    return "Rp " + format(value, ",d").replace(",", ".")


def wa_link(number, text):
    digits = "".join(ch for ch in (number or "") if ch.isdigit())
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    from urllib.parse import quote
    return "https://wa.me/%s?text=%s" % (digits, quote(text))


def next_order_code():
    return database.next_number("nomor_order")


def parse_items(form):
    """Ambil pasangan product_id[] / qty[] dari formulir multi produk."""
    ids = form.getlist("product_id[]")
    qtys = form.getlist("qty[]")
    items = []
    for pid, qty in zip(ids, qtys):
        if not pid:
            continue
        try:
            qty = int(qty)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        product = database.query("SELECT * FROM products WHERE id = ?", (pid,), one=True)
        if not product:
            continue
        items.append({
            "product": product,
            "qty": qty,
            "subtotal": product["harga"] * qty,
        })
    return items


def create_order(items, nama, telepon, alamat, catatan, metode_bayar, pengiriman,
                 user_id=None, dibuat_oleh=None, status="Menunggu Konfirmasi",
                 kode_tagihan="Reguler"):
    subtotal = sum(i["subtotal"] for i in items)
    pengiriman = database.pengiriman_pilihan(pengiriman)
    ongkir = database.ongkir_untuk(pengiriman, subtotal)
    total = subtotal + ongkir
    kode = next_order_code()
    kode_lacak = database.next_number("nomor_lacak")
    created = database.now()
    order_id = database.execute(
        "INSERT INTO orders (kode, kode_lacak, user_id, nama_pelanggan, telepon, alamat, catatan, subtotal,"
        " ongkir, total, metode_bayar, status, status_bayar, pengiriman, dibuat_oleh, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Belum Bayar', ?, ?, ?, ?)",
        (kode, kode_lacak, user_id, nama, telepon, alamat, catatan, subtotal, ongkir, total,
         metode_bayar, status, pengiriman, dibuat_oleh, created, created),
    )
    for item in items:
        product = item["product"]
        database.execute(
            "INSERT INTO order_items (order_id, product_id, nama_produk, harga, qty, subtotal, qc_status)"
            " VALUES (?, ?, ?, ?, ?, ?, 'Belum Dicek')",
            (order_id, product["id"], product["nama"], product["harga"], item["qty"], item["subtotal"]),
        )
        database.execute(
            "UPDATE products SET stok = MAX(0, stok - ?) WHERE id = ?", (item["qty"], product["id"]),
        )
        database.execute(
            "INSERT INTO stock_moves (product_id, tipe, qty, keterangan, referensi, dibuat_oleh, created_at)"
            " VALUES (?, 'keluar', ?, 'Pesanan pelanggan', ?, ?, ?)",
            (product["id"], item["qty"], kode, dibuat_oleh, created),
        )
    database.execute(
        "INSERT INTO invoices (nomor, nomor_invoice, order_id, user_id, nama_pelanggan, total, kode_tagihan,"
        " status, jatuh_tempo, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'Belum Dibayar', ?, ?)",
        (database.next_number("nomor_faktur"), database.next_number("nomor_invoice"),
         order_id, user_id, nama, total, kode_tagihan,
         (database.datetime.now() + database.timedelta(days=7)).strftime("%Y-%m-%d"), created),
    )
    notify_roles(
        ["staff_admin", "staff_kantor", "staff_gudang", "administrator"],
        "Pesanan baru %s" % kode,
        "%s memesan %d produk senilai %s." % (nama, len(items), rupiah(total)),
        url_for("staff.orders"),
    )
    return order_id, kode


def restore_stock(order_id):
    for item in database.query("SELECT * FROM order_items WHERE order_id = ?", (order_id,)):
        if item["product_id"]:
            database.execute("UPDATE products SET stok = stok + ? WHERE id = ?",
                             (item["qty"], item["product_id"]))
            database.execute(
                "INSERT INTO stock_moves (product_id, tipe, qty, keterangan, referensi, dibuat_oleh, created_at)"
                " VALUES (?, 'masuk', ?, 'Pembatalan pesanan', ?, ?, ?)",
                (item["product_id"], item["qty"], "BATAL", current_user()["id"] if current_user() else None,
                 database.now()),
            )
