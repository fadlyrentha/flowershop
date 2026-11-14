"""Halaman Quality Kontrol."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

import db as database
import helpers

bp = Blueprint("qc", __name__, url_prefix="/qc")


@bp.before_request
@helpers.role_required("staff_qc", "administrator")
def guard():
    pass


@bp.route("/")
def dashboard():
    stats = {
        "masuk": database.query(
            "SELECT COUNT(DISTINCT order_id) AS c FROM order_items i JOIN orders o ON o.id = i.order_id"
            " WHERE o.status IN ('Quality Kontrol','Diproses')", one=True)["c"],
        "belum": database.query(
            "SELECT COUNT(*) AS c FROM order_items WHERE qc_status = 'Belum Dicek'", one=True)["c"],
        "lolos": database.query(
            "SELECT COUNT(*) AS c FROM order_items WHERE qc_status = 'Lolos QC'", one=True)["c"],
        "komplain": database.query("SELECT COUNT(*) AS c FROM complaints", one=True)["c"],
    }
    return render_template(
        "qc/dashboard.html", stats=stats,
        orders=database.query(
            "SELECT o.*, (SELECT COUNT(*) FROM order_items i WHERE i.order_id = o.id) AS jumlah_item,"
            " (SELECT COUNT(*) FROM order_items i WHERE i.order_id = o.id AND i.qc_status = 'Belum Dicek')"
            " AS belum FROM orders o WHERE o.status IN ('Diproses','Quality Kontrol','Siap Kirim')"
            " ORDER BY o.id DESC LIMIT 10"),
        recent=database.query(
            "SELECT q.*, i.nama_produk, o.kode FROM qc_checks q"
            " JOIN order_items i ON i.id = q.order_item_id"
            " JOIN orders o ON o.id = i.order_id ORDER BY q.id DESC LIMIT 8"))


@bp.route("/pesanan")
def orders():
    status = request.args.get("status", "")
    sql = ("SELECT o.*, (SELECT COUNT(*) FROM order_items i WHERE i.order_id = o.id) AS jumlah_item,"
           " (SELECT COUNT(*) FROM order_items i WHERE i.order_id = o.id AND i.qc_status = 'Belum Dicek')"
           " AS belum FROM orders o WHERE 1=1")
    args = []
    if status:
        sql += " AND o.status = ?"
        args.append(status)
    else:
        sql += " AND o.status NOT IN ('Dibatalkan')"
    sql += " ORDER BY o.id DESC"
    return render_template("qc/orders.html", rows=database.query(sql, args), status=status)


@bp.route("/pesanan/<int:order_id>", methods=["GET", "POST"])
def verify(order_id):
    order = database.query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    if order is None:
        abort(404)
    if request.method == "POST":
        changed = 0
        for item in database.query("SELECT * FROM order_items WHERE order_id = ?", (order_id,)):
            status = request.form.get("status_%d" % item["id"], "").strip()
            catatan = request.form.get("catatan_%d" % item["id"], "").strip()
            if not status:
                continue
            foto = helpers.save_upload(request.files.get("foto_%d" % item["id"]), "qc")
            video = helpers.save_upload(request.files.get("video_%d" % item["id"]), "qc")
            if not foto and not video:
                existing = database.query(
                    "SELECT foto, video FROM qc_checks WHERE order_item_id = ? ORDER BY id DESC LIMIT 1",
                    (item["id"],), one=True)
                if existing:
                    foto, video = existing["foto"], existing["video"]
            database.execute(
                "INSERT INTO qc_checks (order_item_id, status, catatan, foto, video, dicek_oleh, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (item["id"], status, catatan, foto, video, helpers.current_user()["id"], database.now()))
            database.execute("UPDATE order_items SET qc_status = ?, qc_catatan = ? WHERE id = ?",
                             (status, catatan, item["id"]))
            changed += 1
        if changed:
            sisa = database.query(
                "SELECT COUNT(*) AS c FROM order_items WHERE order_id = ? AND qc_status = 'Belum Dicek'",
                (order_id,), one=True)["c"]
            gagal = database.query(
                "SELECT COUNT(*) AS c FROM order_items WHERE order_id = ? AND qc_status != 'Lolos QC'",
                (order_id,), one=True)["c"]
            new_status = "Siap Kirim" if sisa == 0 and gagal == 0 else "Quality Kontrol"
            database.execute("UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
                             (new_status, database.now(), order_id))
            if sisa == 0:
                helpers.notify_roles(
                    ["staff_keuangan", "staff_admin", "administrator"],
                    "Verifikasi QC selesai %s" % order["kode"],
                    "Silakan periksa checklist produk sebelum faktur dibuat.",
                    url_for("finance.qc_list"))
            if order["user_id"]:
                helpers.notify("Pemeriksaan kualitas %s" % order["kode"],
                               "Status: %s." % new_status,
                               url_for("customer.order_detail", order_id=order_id),
                               user_id=order["user_id"])
            flash("Hasil pemeriksaan disimpan. Status pesanan: %s." % new_status, "success")
        else:
            flash("Tidak ada perubahan status yang dikirim.", "warning")
        return redirect(url_for("qc.verify", order_id=order_id))

    items = database.query("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    checks = {}
    for c in database.query(
            "SELECT q.* FROM qc_checks q JOIN order_items i ON i.id = q.order_item_id"
            " WHERE i.order_id = ? ORDER BY q.id DESC", (order_id,)):
        checks.setdefault(c["order_item_id"], c)
    return render_template("qc/verify.html", order=order, items=items, checks=checks)


@bp.route("/ganti-produk", methods=["GET", "POST"])
@helpers.feature_required("ganti_produk")
def replace_product():
    if request.method == "POST":
        aksi = request.form.get("aksi", "ganti")
        if aksi == "tambah":
            return _tambah_produk_pesanan()
        item_id = request.form.get("item_id")
        new_pid = request.form.get("product_id")
        try:
            qty = int(request.form.get("qty") or 0)
        except (TypeError, ValueError):
            qty = 0
        alasan = request.form.get("alasan", "").strip()
        item = database.query("SELECT * FROM order_items WHERE id = ?", (item_id,), one=True)
        if item is None:
            abort(404)
        product = database.query("SELECT * FROM products WHERE id = ?", (new_pid,), one=True)
        if product is None or qty <= 0:
            flash("Produk pengganti dan jumlah wajib diisi.", "danger")
            return redirect(url_for("qc.replace_product", order_id=item["order_id"]))
        if qty > product["stok"]:
            flash("Stok %s tidak mencukupi (tersedia %d)." % (product["nama"], product["stok"]),
                  "danger")
            return redirect(url_for("qc.replace_product", order_id=item["order_id"]))

        order = database.query("SELECT * FROM orders WHERE id = ?", (item["order_id"],), one=True)
        # Kembalikan stok produk lama, kurangi stok produk pengganti.
        if item["product_id"]:
            database.execute("UPDATE products SET stok = stok + ? WHERE id = ?",
                             (item["qty"], item["product_id"]))
            database.execute(
                "INSERT INTO stock_moves (product_id, tipe, qty, keterangan, referensi, dibuat_oleh,"
                " created_at) VALUES (?, 'masuk', ?, ?, ?, ?, ?)",
                (item["product_id"], item["qty"], "Ganti produk QC: " + (alasan or "-"),
                 order["kode"], helpers.current_user()["id"], database.now()))
        database.execute("UPDATE products SET stok = MAX(0, stok - ?) WHERE id = ?",
                         (qty, product["id"]))
        database.execute(
            "INSERT INTO stock_moves (product_id, tipe, qty, keterangan, referensi, dibuat_oleh,"
            " created_at) VALUES (?, 'keluar', ?, ?, ?, ?, ?)",
            (product["id"], qty, "Ganti produk QC: " + (alasan or "-"), order["kode"],
             helpers.current_user()["id"], database.now()))

        subtotal = product["harga"] * qty
        database.execute(
            "UPDATE order_items SET product_id = ?, nama_produk = ?, harga = ?, qty = ?, subtotal = ?,"
            " qc_status = 'Belum Dicek', qc_catatan = ? WHERE id = ?",
            (product["id"], product["nama"], product["harga"], qty, subtotal,
             "Diganti dari %s. %s" % (item["nama_produk"], alasan), item_id))

        items = database.query("SELECT * FROM order_items WHERE order_id = ?", (order["id"],))
        new_subtotal = sum(i["subtotal"] for i in items)
        ongkir = 0 if (new_subtotal >= 500000 or order["pengiriman"] == "Diambil") else 25000
        new_total = new_subtotal + ongkir
        database.execute(
            "UPDATE orders SET subtotal = ?, ongkir = ?, total = ?, updated_at = ? WHERE id = ?",
            (new_subtotal, ongkir, new_total, database.now(), order["id"]))
        database.execute("UPDATE invoices SET total = ? WHERE order_id = ?",
                         (new_total, order["id"]))
        if order["user_id"]:
            helpers.notify(
                "Produk pesanan %s diganti" % order["kode"],
                "%s diganti dengan %s. Total pesanan kini %s." % (
                    item["nama_produk"], product["nama"], helpers.rupiah(new_total)),
                url_for("customer.order_detail", order_id=order["id"]), user_id=order["user_id"])
        flash("Produk %s diganti dengan %s." % (item["nama_produk"], product["nama"]), "success")
        return redirect(url_for("qc.replace_product", order_id=order["id"]))

    order_id = request.args.get("order_id", type=int)
    order = None
    items = []
    if order_id:
        order = database.query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
        if order is None:
            abort(404)
        items = database.query("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    return render_template(
        "qc/replace_product.html", order=order, items=items,
        orders=database.query(
            "SELECT id, kode, nama_pelanggan, status FROM orders"
            " WHERE status NOT IN ('Selesai','Dibatalkan') ORDER BY id DESC"),
        products=database.query("SELECT * FROM products WHERE aktif = 1 ORDER BY nama"))


def _tambah_produk_pesanan():
    """Tambah produk baru ke pesanan yang sedang ditangani QC."""
    order_id = request.form.get("order_id", type=int)
    product_id = request.form.get("product_id")
    try:
        qty = int(request.form.get("qty") or 0)
    except (TypeError, ValueError):
        qty = 0
    catatan = request.form.get("catatan", "").strip()

    order = database.query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    if order is None:
        abort(404)
    product = database.query("SELECT * FROM products WHERE id = ? AND aktif = 1",
                             (product_id,), one=True)
    if product is None or qty <= 0:
        flash("Produk dan jumlah wajib diisi.", "danger")
        return redirect(url_for("qc.replace_product", order_id=order_id))
    if qty > product["stok"]:
        flash("Stok %s tidak mencukupi (tersedia %d)." % (product["nama"], product["stok"]),
              "danger")
        return redirect(url_for("qc.replace_product", order_id=order_id))

    subtotal = product["harga"] * qty
    database.execute(
        "INSERT INTO order_items (order_id, product_id, nama_produk, harga, qty, subtotal,"
        " qc_status, qc_catatan) VALUES (?, ?, ?, ?, ?, ?, 'Belum Dicek', ?)",
        (order_id, product["id"], product["nama"], product["harga"], qty, subtotal,
         "Ditambahkan QC. " + catatan))
    database.execute("UPDATE products SET stok = MAX(0, stok - ?) WHERE id = ?",
                     (qty, product["id"]))
    database.execute(
        "INSERT INTO stock_moves (product_id, tipe, qty, keterangan, referensi, dibuat_oleh,"
        " created_at) VALUES (?, 'keluar', ?, ?, ?, ?, ?)",
        (product["id"], qty, "Tambah produk QC: " + (catatan or "-"), order["kode"],
         helpers.current_user()["id"], database.now()))

    items = database.query("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    new_subtotal = sum(i["subtotal"] for i in items)
    ongkir = 0 if (new_subtotal >= 500000 or order["pengiriman"] == "Diambil") else 25000
    new_total = new_subtotal + ongkir
    database.execute(
        "UPDATE orders SET subtotal = ?, ongkir = ?, total = ?, updated_at = ? WHERE id = ?",
        (new_subtotal, ongkir, new_total, database.now(), order_id))
    database.execute("UPDATE invoices SET total = ? WHERE order_id = ?", (new_total, order_id))
    if order["user_id"]:
        helpers.notify(
            "Produk ditambahkan ke pesanan %s" % order["kode"],
            "%s × %d ditambahkan. Total pesanan kini %s." % (
                product["nama"], qty, helpers.rupiah(new_total)),
            url_for("customer.order_detail", order_id=order_id), user_id=order["user_id"])
    flash("%s × %d ditambahkan ke pesanan %s." % (product["nama"], qty, order["kode"]),
          "success")
    return redirect(url_for("qc.replace_product", order_id=order_id))


@bp.route("/komplain")
def complaints():
    return render_template(
        "qc/complaints.html",
        rows=database.query("SELECT * FROM complaints ORDER BY id DESC"))


@bp.route("/pengiriman", methods=["GET", "POST"])
def shipments():
    if request.method == "POST":
        sid = request.form.get("id")
        data = (
            request.form.get("order_id") or None,
            request.form.get("nama_penerima", "").strip(),
            request.form.get("alamat", "").strip(),
            request.form.get("kurir", "").strip(),
            request.form.get("status", "Menunggu Diambil").strip(),
            request.form.get("keterangan", "").strip(),
            database.now(),
        )
        if sid:
            database.execute(
                "UPDATE shipments SET order_id=?, nama_penerima=?, alamat=?, kurir=?, status=?, keterangan=?,"
                " updated_at=? WHERE id=?", data + (sid,))
            flash("Data pengiriman diperbarui.", "success")
        else:
            database.execute(
                "INSERT INTO shipments (order_id, nama_penerima, alamat, kurir, status, keterangan,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                data[:6] + (database.now(),) + (database.now(),))
            flash("Data pengiriman ditambahkan.", "success")
        return redirect(url_for("qc.shipments"))

    return render_template(
        "qc/shipments.html",
        rows=database.query("SELECT * FROM shipments ORDER BY id DESC"),
        orders=database.query(
            "SELECT id, kode, nama_pelanggan FROM orders WHERE status IN ('Siap Kirim','Dikirim','Selesai')"
            " ORDER BY id DESC"))


@bp.route("/pengiriman/<int:sid>/hapus", methods=["POST"])
def shipment_delete(sid):
    database.execute("DELETE FROM shipments WHERE id = ?", (sid,))
    flash("Data pengiriman dihapus.", "info")
    return redirect(url_for("qc.shipments"))


@bp.route("/pengiriman/cetak")
def shipments_print():
    return render_template("qc/shipments_print.html",
                           rows=database.query("SELECT * FROM shipments ORDER BY id DESC"))


@bp.route("/notifikasi")
def notifications():
    user = helpers.current_user()
    rows = database.query(
        "SELECT * FROM notifications WHERE user_id = ? OR role = ? ORDER BY id DESC LIMIT 100",
        (user["id"], user["role"]))
    database.execute("UPDATE notifications SET dibaca = 1 WHERE user_id = ? OR role = ?",
                     (user["id"], user["role"]))
    return render_template("staff/notifications.html", rows=rows)
