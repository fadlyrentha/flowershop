"""Halaman staff: admin, kantor, gudang."""
from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)
from werkzeug.security import generate_password_hash

import db as database
import helpers

bp = Blueprint("staff", __name__, url_prefix="/staff")

STAFF_ROLES = ("staff_admin", "staff_kantor", "staff_gudang", "administrator")

# Endpoint staff yang juga dibuka untuk Staff Keuangan: konfirmasi order & data pesanan.
KEUANGAN_ENDPOINTS = ("orders", "confirm_orders", "confirm_item", "confirm_order",
                      "order_detail", "order_status", "order_delete", "order_label",
                      "order_qc_list")


@bp.before_request
def guard():
    user = helpers.current_user()
    if user is None:
        flash("Silakan masuk terlebih dahulu.", "warning")
        return redirect(url_for("auth.login", next=request.path))
    if user["role"] in STAFF_ROLES:
        return
    if user["role"] == "staff_keuangan" and request.endpoint \
            and request.endpoint.split(".")[-1] in KEUANGAN_ENDPOINTS:
        return
    abort(403)


@bp.route("/")
def dashboard():
    stats = {
        "pesanan": database.query("SELECT COUNT(*) AS c FROM orders", one=True)["c"],
        "baru": database.query("SELECT COUNT(*) AS c FROM orders WHERE status = 'Menunggu Konfirmasi'", one=True)["c"],
        "pelanggan": database.query("SELECT COUNT(*) AS c FROM users WHERE role = 'pelanggan'", one=True)["c"],
        "komplain": database.query("SELECT COUNT(*) AS c FROM complaints WHERE status = 'Baru'", one=True)["c"],
        "omzet": database.query("SELECT COALESCE(SUM(total),0) AS s FROM orders WHERE status = 'Selesai'", one=True)["s"],
        "stok_menipis": database.query(
            "SELECT COUNT(*) AS c FROM products WHERE aktif = 1 AND stok <= stok_minimum", one=True)["c"],
    }
    return render_template(
        "staff/dashboard.html", stats=stats,
        orders=database.query("SELECT * FROM orders ORDER BY id DESC LIMIT 8"),
        menipis=database.query(
            "SELECT * FROM products WHERE aktif = 1 AND stok <= stok_minimum ORDER BY stok LIMIT 6"))


# ------------------------------------------------------------- pelanggan ----
@bp.route("/pelanggan")
@helpers.feature_required("pelanggan")
def customers():
    q = request.args.get("q", "").strip()
    sql = "SELECT * FROM users WHERE role = 'pelanggan'"
    args = []
    if q:
        sql += " AND (nama LIKE ? OR username LIKE ? OR telepon LIKE ?)"
        args += ["%" + q + "%"] * 3
    sql += " ORDER BY id DESC"
    return render_template("staff/customers.html", rows=database.query(sql, args), q=q)


@bp.route("/pelanggan/simpan", methods=["POST"])
@helpers.feature_required("pelanggan")
def customer_save():
    uid = request.form.get("id")
    nama = request.form.get("nama", "").strip()
    username = request.form.get("username", "").strip()
    telepon = request.form.get("telepon", "").strip()
    email = request.form.get("email", "").strip()
    alamat = request.form.get("alamat", "").strip()
    aktif = 1 if request.form.get("aktif") else 0
    password = request.form.get("password", "")

    if not nama or not username:
        flash("Nama dan username wajib diisi.", "danger")
        return redirect(url_for("staff.customers"))

    if uid:
        database.execute(
            "UPDATE users SET nama = ?, username = ?, telepon = ?, email = ?, alamat = ?, aktif = ? WHERE id = ?",
            (nama, username, telepon, email, alamat, aktif, uid))
        if password:
            database.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                             (generate_password_hash(password), uid))
        flash("Data pelanggan diperbarui.", "success")
    else:
        if database.query("SELECT id FROM users WHERE username = ?", (username,), one=True):
            flash("Username sudah digunakan.", "danger")
            return redirect(url_for("staff.customers"))
        database.execute(
            "INSERT INTO users (username, password_hash, nama, role, telepon, email, alamat, aktif, created_at)"
            " VALUES (?, ?, ?, 'pelanggan', ?, ?, ?, ?, ?)",
            (username, generate_password_hash(password or "pelanggan123"), nama, telepon, email,
             alamat, aktif, database.now()))
        flash("Pelanggan baru ditambahkan (password default: pelanggan123).", "success")
    return redirect(url_for("staff.customers"))


@bp.route("/pelanggan/<int:uid>/hapus", methods=["POST"])
@helpers.feature_required("pelanggan")
def customer_delete(uid):
    if database.query("SELECT COUNT(*) AS c FROM orders WHERE user_id = ?", (uid,), one=True)["c"]:
        flash("Pelanggan memiliki riwayat pesanan, nonaktifkan saja akunnya.", "warning")
    else:
        database.execute("DELETE FROM users WHERE id = ? AND role = 'pelanggan'", (uid,))
        flash("Pelanggan dihapus.", "info")
    return redirect(url_for("staff.customers"))


# --------------------------------------------------------------- pesanan ----
@bp.route("/pesanan")
@helpers.feature_required("pesanan")
def orders():
    status = request.args.get("status", "")
    q = request.args.get("q", "").strip()
    sql = ("SELECT o.*, (SELECT COUNT(*) FROM order_items i WHERE i.order_id = o.id) AS jumlah_item"
           " FROM orders o WHERE 1=1")
    args = []
    if status:
        sql += " AND o.status = ?"
        args.append(status)
    if q:
        sql += " AND (o.kode LIKE ? OR o.nama_pelanggan LIKE ?)"
        args += ["%" + q + "%"] * 2
    sql += " ORDER BY o.id DESC"
    rows = database.query(sql, args)
    items = {}
    if helpers.current_user()["role"] == "staff_gudang":
        order_ids = [r["id"] for r in rows]
        if order_ids:
            placeholders = ",".join("?" * len(order_ids))
            for item in database.query(
                    "SELECT * FROM order_items WHERE order_id IN (%s) ORDER BY id" % placeholders,
                    order_ids):
                items.setdefault(item["order_id"], []).append(item)
    return render_template("staff/orders.html", rows=rows, status=status, q=q, items=items)


@bp.route("/konfirmasi-order")
@helpers.feature_required("konfirmasi_order")
def confirm_orders():
    q = request.args.get("q", "").strip()
    sql = ("SELECT o.*, (SELECT COUNT(*) FROM order_items i WHERE i.order_id = o.id) AS jumlah_item"
           " FROM orders o WHERE o.status = 'Menunggu Konfirmasi'")
    args = []
    if q:
        sql += " AND (o.kode LIKE ? OR o.nama_pelanggan LIKE ?)"
        args += ["%" + q + "%"] * 2
    sql += " ORDER BY o.id"
    rows = database.query(sql, args)
    items = {}
    order_ids = [r["id"] for r in rows]
    if order_ids:
        placeholders = ",".join("?" * len(order_ids))
        for item in database.query(
                "SELECT * FROM order_items WHERE order_id IN (%s) ORDER BY id" % placeholders,
                order_ids):
            items.setdefault(item["order_id"], []).append(item)
    products = database.query("SELECT * FROM products WHERE aktif = 1 ORDER BY nama")
    stok = {p["id"]: p["stok"] for p in products}

    # Tandai pesanan yang produknya kosong atau stoknya kurang dari jumlah order.
    kurang = {}
    for order_id, baris in items.items():
        for it in baris:
            sisa = stok.get(it["product_id"]) if it["product_id"] else None
            if sisa is None or sisa < it["qty"]:
                kurang[order_id] = True
                break

    return render_template(
        "staff/confirm_orders.html", rows=rows, items=items, q=q,
        products=products, stok=stok, kurang=kurang)


@bp.route("/konfirmasi-order/<int:order_id>/produk", methods=["POST"])
@helpers.feature_required("konfirmasi_order")
def confirm_item(order_id):
    """Tambah / ubah / hapus produk pesanan sebelum order dikonfirmasi."""
    order = database.query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    if order is None:
        abort(404)
    if order["status"] != "Menunggu Konfirmasi":
        flash("Produk hanya bisa diubah selama pesanan menunggu konfirmasi.", "warning")
        return redirect(url_for("staff.confirm_orders"))

    aksi = request.form.get("aksi", "tambah")
    if aksi == "hapus":
        return _confirm_item_hapus(order)
    if aksi == "ubah":
        return _confirm_item_ubah(order)
    return _confirm_item_tambah(order)


def _baca_produk_qty():
    """Ambil produk + qty dari form. Mengembalikan (product, qty, pesan_error)."""
    product = database.query("SELECT * FROM products WHERE id = ? AND aktif = 1",
                             (request.form.get("product_id"),), one=True)
    if product is None:
        return None, 0, "Produk wajib dipilih."
    try:
        qty = int(request.form.get("qty") or 0)
    except (TypeError, ValueError):
        qty = 0
    if qty <= 0:
        return None, 0, "Jumlah harus lebih dari nol."
    return product, qty, ""


def _hitung_ulang_pesanan(order):
    items = database.query("SELECT * FROM order_items WHERE order_id = ?", (order["id"],))
    subtotal = sum(i["subtotal"] for i in items)
    ongkir = database.ongkir_untuk(order["pengiriman"], subtotal)
    total = subtotal + ongkir
    database.execute(
        "UPDATE orders SET subtotal = ?, ongkir = ?, total = ?, updated_at = ? WHERE id = ?",
        (subtotal, ongkir, total, database.now(), order["id"]))
    database.execute("UPDATE invoices SET total = ? WHERE order_id = ?", (total, order["id"]))
    return total


def _confirm_item_tambah(order):
    product, qty, pesan = _baca_produk_qty()
    if pesan:
        flash(pesan, "danger")
        return redirect(url_for("staff.confirm_orders"))
    if qty > product["stok"]:
        flash("Stok %s tidak mencukupi: diminta %d, tersedia %d."
              % (product["nama"], qty, product["stok"]), "danger")
        return redirect(url_for("staff.confirm_orders"))

    subtotal = product["harga"] * qty
    database.execute(
        "INSERT INTO order_items (order_id, product_id, nama_produk, harga, qty, subtotal,"
        " qc_status, qc_catatan) VALUES (?, ?, ?, ?, ?, ?, 'Belum Dicek', ?)",
        (order["id"], product["id"], product["nama"], product["harga"], qty, subtotal,
         "Ditambahkan Staff Admin."))
    database.execute("UPDATE products SET stok = MAX(0, stok - ?) WHERE id = ?", (qty, product["id"]))
    database.execute(
        "INSERT INTO stock_moves (product_id, tipe, qty, keterangan, referensi, dibuat_oleh, created_at)"
        " VALUES (?, 'keluar', ?, 'Tambah produk konfirmasi order', ?, ?, ?)",
        (product["id"], qty, order["kode"], helpers.current_user()["id"], database.now()))
    total = _hitung_ulang_pesanan(order)
    flash("%s × %d ditambahkan. Total pesanan kini %s."
          % (product["nama"], qty, helpers.rupiah(total)), "success")
    return redirect(url_for("staff.confirm_orders"))


def _confirm_item_ubah(order):
    item = database.query("SELECT * FROM order_items WHERE id = ? AND order_id = ?",
                          (request.form.get("item_id"), order["id"]), one=True)
    if item is None:
        abort(404)
    product, qty, pesan = _baca_produk_qty()
    if pesan:
        flash(pesan, "danger")
        return redirect(url_for("staff.confirm_orders"))

    # Kembalikan stok lama lebih dulu agar stok produk yang sama bisa dipakai ulang.
    if item["product_id"]:
        database.execute("UPDATE products SET stok = stok + ? WHERE id = ?",
                         (item["qty"], item["product_id"]))
    sisa = database.query("SELECT stok FROM products WHERE id = ?", (product["id"],), one=True)["stok"]
    if sisa < qty:
        if item["product_id"]:
            database.execute("UPDATE products SET stok = MAX(0, stok - ?) WHERE id = ?",
                             (item["qty"], item["product_id"]))
        flash("Stok %s tidak mencukupi: diminta %d, tersedia %d."
              % (product["nama"], qty, sisa), "danger")
        return redirect(url_for("staff.confirm_orders"))

    if item["product_id"]:
        database.execute(
            "INSERT INTO stock_moves (product_id, tipe, qty, keterangan, referensi, dibuat_oleh,"
            " created_at) VALUES (?, 'masuk', ?, 'Ubah produk konfirmasi order', ?, ?, ?)",
            (item["product_id"], item["qty"], order["kode"], helpers.current_user()["id"],
             database.now()))
    database.execute("UPDATE products SET stok = MAX(0, stok - ?) WHERE id = ?", (qty, product["id"]))
    database.execute(
        "INSERT INTO stock_moves (product_id, tipe, qty, keterangan, referensi, dibuat_oleh, created_at)"
        " VALUES (?, 'keluar', ?, 'Ubah produk konfirmasi order', ?, ?, ?)",
        (product["id"], qty, order["kode"], helpers.current_user()["id"], database.now()))
    database.execute(
        "UPDATE order_items SET product_id = ?, nama_produk = ?, harga = ?, qty = ?, subtotal = ?,"
        " qc_status = 'Belum Dicek' WHERE id = ?",
        (product["id"], product["nama"], product["harga"], qty, product["harga"] * qty, item["id"]))
    total = _hitung_ulang_pesanan(order)
    flash("Item diubah menjadi %s × %d. Total pesanan kini %s."
          % (product["nama"], qty, helpers.rupiah(total)), "success")
    return redirect(url_for("staff.confirm_orders"))


def _confirm_item_hapus(order):
    item = database.query("SELECT * FROM order_items WHERE id = ? AND order_id = ?",
                          (request.form.get("item_id"), order["id"]), one=True)
    if item is None:
        abort(404)
    sisa = database.query("SELECT COUNT(*) AS c FROM order_items WHERE order_id = ?",
                          (order["id"],), one=True)["c"]
    if sisa <= 1:
        flash("Pesanan harus memiliki minimal satu produk. Tolak pesanan bila pelanggan membatalkan.",
              "warning")
        return redirect(url_for("staff.confirm_orders"))
    if item["product_id"]:
        database.execute("UPDATE products SET stok = stok + ? WHERE id = ?",
                         (item["qty"], item["product_id"]))
        database.execute(
            "INSERT INTO stock_moves (product_id, tipe, qty, keterangan, referensi, dibuat_oleh,"
            " created_at) VALUES (?, 'masuk', ?, 'Hapus produk konfirmasi order', ?, ?, ?)",
            (item["product_id"], item["qty"], order["kode"], helpers.current_user()["id"],
             database.now()))
    database.execute("DELETE FROM order_items WHERE id = ?", (item["id"],))
    total = _hitung_ulang_pesanan(order)
    flash("%s dihapus dari pesanan. Total pesanan kini %s."
          % (item["nama_produk"], helpers.rupiah(total)), "success")
    return redirect(url_for("staff.confirm_orders"))


@bp.route("/konfirmasi-order/<int:order_id>", methods=["POST"])
@helpers.feature_required("konfirmasi_order")
def confirm_order(order_id):
    order = database.query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    if order is None:
        abort(404)
    aksi = request.form.get("aksi", "terima")
    if aksi == "tolak":
        if order["status"] != "Dibatalkan":
            helpers.restore_stock(order_id)
        database.execute("UPDATE orders SET status = 'Dibatalkan', updated_at = ? WHERE id = ?",
                         (database.now(), order_id))
        pesan = "Pesanan %s ditolak." % order["kode"]
        status_baru = "Dibatalkan"
    else:
        database.execute("UPDATE orders SET status = 'Diproses', updated_at = ? WHERE id = ?",
                         (database.now(), order_id))
        pesan = "Pesanan %s dikonfirmasi." % order["kode"]
        status_baru = "Diproses"
    if order["user_id"]:
        helpers.notify("Status pesanan %s" % order["kode"], "Status terbaru: %s." % status_baru,
                       url_for("customer.order_detail", order_id=order_id), user_id=order["user_id"])
    flash(pesan, "success")
    return redirect(url_for("staff.confirm_orders"))


@bp.route("/pesanan/baru", methods=["GET", "POST"])
@helpers.feature_required("pesanan_baru")
def new_order():
    products = database.query("SELECT * FROM products WHERE aktif = 1 ORDER BY nama")
    customers_list = database.query("SELECT * FROM users WHERE role = 'pelanggan' ORDER BY nama")
    if request.method == "POST":
        items = helpers.parse_items(request.form)
        if not items:
            flash("Pilih minimal satu produk.", "danger")
            return render_template("staff/new_order.html", products=products,
                                   customers_list=customers_list, form=request.form)
        for item in items:
            if item["qty"] > item["product"]["stok"]:
                flash("Stok %s tidak mencukupi." % item["product"]["nama"], "danger")
                return render_template("staff/new_order.html", products=products,
                                       customers_list=customers_list, form=request.form)
        user_id = request.form.get("user_id") or None
        nama = request.form.get("nama_pelanggan", "").strip()
        if user_id and not nama:
            cust = database.query("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
            nama = cust["nama"] if cust else ""
        kode_tagihan = request.form.get("kode_tagihan", "Reguler")
        if kode_tagihan not in database.KODE_TAGIHAN:
            kode_tagihan = "Reguler"
        order_id, kode = helpers.create_order(
            items, nama or "Pelanggan Umum",
            request.form.get("telepon", "").strip(),
            request.form.get("alamat", "").strip(),
            request.form.get("catatan", "").strip(),
            request.form.get("metode_bayar", "Transfer Bank"),
            database.pengiriman_pilihan(request.form.get("pengiriman", "")),
            user_id=user_id, dibuat_oleh=helpers.current_user()["id"],
            kode_tagihan=kode_tagihan)
        flash("Pesanan %s dibuat." % kode, "success")
        return redirect(url_for("staff.order_detail", order_id=order_id))
    return render_template("staff/new_order.html", products=products,
                           customers_list=customers_list, form={})


@bp.route("/pesanan/<int:order_id>")
@helpers.feature_required("pesanan")
def order_detail(order_id):
    order = database.query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    if order is None:
        abort(404)
    items = database.query("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    invoice = database.query("SELECT * FROM invoices WHERE order_id = ?", (order_id,), one=True)
    return render_template("staff/order_detail.html", order=order, items=items, invoice=invoice)


@bp.route("/pesanan/<int:order_id>/status", methods=["POST"])
@helpers.feature_required("pesanan")
def order_status(order_id):
    status = request.form.get("status", "")
    if status not in database.ORDER_STATUS:
        abort(400)
    order = database.query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    if order is None:
        abort(404)
    if status == "Dibatalkan" and order["status"] != "Dibatalkan":
        helpers.restore_stock(order_id)
    database.execute("UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
                     (status, database.now(), order_id))
    if order["user_id"]:
        helpers.notify("Status pesanan %s" % order["kode"], "Status terbaru: %s." % status,
                       url_for("customer.order_detail", order_id=order_id), user_id=order["user_id"])
    if status == "Quality Kontrol":
        helpers.notify_roles(["staff_qc", "administrator"], "Pesanan siap QC",
                             "%s menunggu pengecekan kualitas." % order["kode"], url_for("qc.orders"))
    flash("Status pesanan diperbarui menjadi %s." % status, "success")
    return redirect(url_for("staff.order_detail", order_id=order_id))


@bp.route("/pesanan/<int:order_id>/hapus", methods=["POST"])
@helpers.feature_required("pesanan")
def order_delete(order_id):
    order = database.query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    if order is None:
        abort(404)
    if order["status"] != "Dibatalkan":
        helpers.restore_stock(order_id)
    database.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    database.execute("DELETE FROM invoices WHERE order_id = ?", (order_id,))
    flash("Pesanan %s dihapus." % order["kode"], "info")
    return redirect(url_for("staff.orders"))


@bp.route("/pesanan/<int:order_id>/label")
@helpers.feature_required("label")
def order_label(order_id):
    order = database.query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    if order is None:
        abort(404)
    items = database.query("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    return render_template("shared/label.html", order=order, items=items)


@bp.route("/pesanan/<int:order_id>/qc-list")
@helpers.feature_required("qc_list")
def order_qc_list(order_id):
    order = database.query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    if order is None:
        abort(404)
    items = database.query("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    return render_template("shared/qc_list.html", order=order, items=items)


# ---------------------------------------------------------------- produk ----
@bp.route("/produk", methods=["GET", "POST"])
@helpers.feature_required("produk")
def products():
    if request.method == "POST":
        pid = request.form.get("id")
        data = (
            request.form.get("nama", "").strip(),
            request.form.get("deskripsi", "").strip(),
            request.form.get("kategori", "Bunga Potong").strip(),
            int(request.form.get("harga") or 0),
            int(request.form.get("stok") or 0),
            int(request.form.get("stok_minimum") or 5),
            request.form.get("satuan", "ikat").strip(),
            1 if request.form.get("aktif") else 0,
        )
        gambar = helpers.save_image(request.files.get("gambar"), "products")
        if not data[0]:
            flash("Nama produk wajib diisi.", "danger")
        elif pid:
            lama = database.query("SELECT gambar FROM products WHERE id = ?", (pid,), one=True)
            if gambar:
                database.execute(
                    "UPDATE products SET nama=?, deskripsi=?, kategori=?, harga=?, stok=?, stok_minimum=?,"
                    " satuan=?, aktif=?, gambar=? WHERE id=?", data + (gambar, pid))
                if lama and lama["gambar"]:
                    helpers.delete_upload(lama["gambar"])
            else:
                database.execute(
                    "UPDATE products SET nama=?, deskripsi=?, kategori=?, harga=?, stok=?, stok_minimum=?,"
                    " satuan=?, aktif=? WHERE id=?", data + (pid,))
            flash("Produk diperbarui.", "success")
        else:
            database.execute(
                "INSERT INTO products (nama, deskripsi, kategori, harga, stok, stok_minimum, satuan, aktif,"
                " gambar, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                data + (gambar, database.now()))
            flash("Produk baru ditambahkan.", "success")
        return redirect(url_for("staff.products"))
    q = request.args.get("q", "").strip()
    sql = "SELECT * FROM products WHERE 1=1"
    args = []
    if q:
        sql += " AND (nama LIKE ? OR kategori LIKE ?)"
        args += ["%" + q + "%"] * 2
    sql += " ORDER BY nama"
    return render_template("staff/products.html", rows=database.query(sql, args), q=q)


@bp.route("/produk/<int:pid>/hapus", methods=["POST"])
@helpers.feature_required("produk")
def product_delete(pid):
    used = database.query("SELECT COUNT(*) AS c FROM order_items WHERE product_id = ?", (pid,), one=True)["c"]
    if used:
        database.execute("UPDATE products SET aktif = 0 WHERE id = ?", (pid,))
        flash("Produk dinonaktifkan karena memiliki riwayat pesanan.", "warning")
    else:
        produk = database.query("SELECT gambar FROM products WHERE id = ?", (pid,), one=True)
        database.execute("DELETE FROM products WHERE id = ?", (pid,))
        if produk:
            helpers.delete_upload(produk["gambar"])
        flash("Produk dihapus.", "info")
    return redirect(url_for("staff.products"))


@bp.route("/produk/<int:pid>/foto/hapus", methods=["POST"])
@helpers.feature_required("produk")
def product_photo_delete(pid):
    """Hapus foto produk tanpa menghapus produknya."""
    produk = database.query("SELECT gambar FROM products WHERE id = ?", (pid,), one=True)
    if produk is None:
        abort(404)
    if produk["gambar"]:
        helpers.delete_upload(produk["gambar"])
        database.execute("UPDATE products SET gambar = '' WHERE id = ?", (pid,))
        flash("Foto produk dihapus.", "info")
    else:
        flash("Produk ini belum memiliki foto.", "warning")
    return redirect(url_for("staff.products"))


# ------------------------------------------------------------------ stok ----
@bp.route("/stok", methods=["GET", "POST"])
@helpers.feature_required("stok")
def stock():
    if request.method == "POST":
        if not database.feature_enabled(helpers.current_user()["role"], "stok_mutasi"):
            abort(403)
        pid = request.form.get("product_id")
        tipe = request.form.get("tipe", "masuk")
        qty = int(request.form.get("qty") or 0)
        keterangan = request.form.get("keterangan", "").strip()
        if not pid or qty <= 0:
            flash("Produk dan jumlah wajib diisi dengan benar.", "danger")
        else:
            product = database.query("SELECT * FROM products WHERE id = ?", (pid,), one=True)
            if tipe == "keluar" and qty > product["stok"]:
                flash("Jumlah keluar melebihi stok tersedia (%d)." % product["stok"], "danger")
            else:
                delta = qty if tipe == "masuk" else -qty
                database.execute("UPDATE products SET stok = MAX(0, stok + ?) WHERE id = ?", (delta, pid))
                database.execute(
                    "INSERT INTO stock_moves (product_id, tipe, qty, keterangan, referensi, dibuat_oleh,"
                    " created_at) VALUES (?, ?, ?, ?, 'MANUAL', ?, ?)",
                    (pid, tipe, qty, keterangan, helpers.current_user()["id"], database.now()))
                flash("Mutasi stok %s dicatat." % tipe, "success")
        return redirect(url_for("staff.stock"))
    return render_template(
        "staff/stock.html",
        products=database.query("SELECT * FROM products ORDER BY nama"),
        moves=database.query(
            "SELECT m.*, p.nama AS produk FROM stock_moves m JOIN products p ON p.id = m.product_id"
            " ORDER BY m.id DESC LIMIT 60"))


# -------------------------------------------------------------- komplain ----
@bp.route("/komplain")
@helpers.feature_required("komplain")
def complaints():
    status = request.args.get("status", "")
    sql = "SELECT * FROM complaints WHERE 1=1"
    args = []
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY id DESC"
    return render_template("staff/complaints.html", rows=database.query(sql, args), status=status)


@bp.route("/komplain/<int:cid>/tanggapi", methods=["POST"])
@helpers.feature_required("komplain")
def complaint_reply(cid):
    status = request.form.get("status", "Proses")
    tanggapan = request.form.get("tanggapan", "").strip()
    complaint = database.query("SELECT * FROM complaints WHERE id = ?", (cid,), one=True)
    if complaint is None:
        abort(404)
    database.execute("UPDATE complaints SET status = ?, tanggapan = ?, updated_at = ? WHERE id = ?",
                     (status, tanggapan, database.now(), cid))
    if complaint["user_id"]:
        helpers.notify("Tanggapan komplain %s" % complaint["kode"], tanggapan or "Status: %s" % status,
                       url_for("customer.complaints"), user_id=complaint["user_id"])
    flash("Komplain ditanggapi.", "success")
    return redirect(url_for("staff.complaints"))


# ----------------------------------------------------------- notifikasi ----
@bp.route("/notifikasi")
@helpers.feature_required("notifikasi")
def notifications():
    user = helpers.current_user()
    rows = database.query(
        "SELECT * FROM notifications WHERE user_id = ? OR role = ? ORDER BY id DESC LIMIT 100",
        (user["id"], user["role"]))
    database.execute("UPDATE notifications SET dibaca = 1 WHERE user_id = ? OR role = ?",
                     (user["id"], user["role"]))
    return render_template("staff/notifications.html", rows=rows)


# --------------------------------------------------------------- laporan ----
@bp.route("/laporan")
@helpers.feature_required("laporan")
def reports():
    rows = database.query(
        "SELECT o.*, (SELECT COUNT(*) FROM order_items i WHERE i.order_id = o.id) AS jumlah_item"
        " FROM orders o ORDER BY o.id DESC")
    total = sum(r["total"] for r in rows)
    return render_template("staff/reports.html", rows=rows, total=total)
