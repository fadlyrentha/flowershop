"""Halaman pelanggan."""
from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)

import db as database
import helpers

bp = Blueprint("customer", __name__, url_prefix="/pelanggan")


@bp.before_request
@helpers.role_required("pelanggan")
def guard():
    pass


def _my_order(order_id):
    order = database.query(
        "SELECT * FROM orders WHERE id = ? AND user_id = ?",
        (order_id, helpers.current_user()["id"]), one=True)
    if order is None:
        abort(404)
    return order


@bp.route("/")
def dashboard():
    user = helpers.current_user()
    orders = database.query(
        "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user["id"],))
    stats = database.query(
        "SELECT COUNT(*) AS total, COALESCE(SUM(total),0) AS nilai,"
        " SUM(CASE WHEN status NOT IN ('Selesai','Dibatalkan') THEN 1 ELSE 0 END) AS aktif"
        " FROM orders WHERE user_id = ?", (user["id"],), one=True)
    return render_template("customer/dashboard.html", orders=orders, stats=stats,
                           produk=database.query(
                               "SELECT * FROM products WHERE aktif = 1 ORDER BY id DESC LIMIT 4"))


@bp.route("/profil")
def profile():
    """Profil pelanggan kini memakai halaman akun bersama agar sama di semua peran."""
    return redirect(url_for("account.profile"))


@bp.route("/pesanan/baru", methods=["GET", "POST"])
def new_order():
    user = helpers.current_user()
    products = database.query("SELECT * FROM products WHERE aktif = 1 ORDER BY nama")
    if request.method == "POST":
        items = helpers.parse_items(request.form)
        if not items:
            flash("Pilih minimal satu produk beserta jumlahnya.", "danger")
            return render_template("customer/new_order.html", products=products, form=request.form)
        for item in items:
            if item["qty"] > item["product"]["stok"]:
                flash("Stok %s tidak mencukupi (tersedia %d)." % (
                    item["product"]["nama"], item["product"]["stok"]), "danger")
                return render_template("customer/new_order.html", products=products, form=request.form)

        nama = request.form.get("nama_pelanggan", "").strip() or user["nama"]
        telepon = request.form.get("telepon", "").strip() or user["telepon"]
        alamat = request.form.get("alamat", "").strip() or user["alamat"]
        catatan = request.form.get("catatan", "").strip()
        metode = request.form.get("metode_bayar", "Transfer Bank")
        pengiriman = database.pengiriman_pilihan(request.form.get("pengiriman", ""))

        order_id, kode = helpers.create_order(
            items, nama, telepon, alamat, catatan, metode, pengiriman,
            user_id=user["id"], dibuat_oleh=user["id"])
        helpers.notify("Pesanan %s diterima" % kode,
                       "Pesanan Anda sedang menunggu konfirmasi admin.",
                       url_for("customer.order_detail", order_id=order_id), user_id=user["id"])
        flash("Pesanan %s berhasil dibuat." % kode, "success")
        return redirect(url_for("customer.order_detail", order_id=order_id))
    return render_template("customer/new_order.html", products=products, form={})


@bp.route("/pesanan")
def orders():
    user = helpers.current_user()
    status = request.args.get("status", "")
    sql = "SELECT * FROM orders WHERE user_id = ?"
    args = [user["id"]]
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY id DESC"
    return render_template("customer/orders.html", orders=database.query(sql, args), status=status)


@bp.route("/pesanan/<int:order_id>")
def order_detail(order_id):
    order = _my_order(order_id)
    items = database.query("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    invoice = database.query("SELECT * FROM invoices WHERE order_id = ?", (order_id,), one=True)
    return render_template("customer/order_detail.html", order=order, items=items, invoice=invoice)


@bp.route("/pesanan/<int:order_id>/batal", methods=["POST"])
def cancel_order(order_id):
    order = _my_order(order_id)
    if order["status"] not in ("Menunggu Konfirmasi", "Diproses"):
        flash("Pesanan pada tahap ini tidak dapat dibatalkan.", "warning")
    else:
        helpers.restore_stock(order_id)
        database.execute("UPDATE orders SET status = 'Dibatalkan', updated_at = ? WHERE id = ?",
                         (database.now(), order_id))
        helpers.notify_roles(["staff_admin", "staff_kantor", "administrator"],
                             "Pesanan dibatalkan", "%s membatalkan %s." % (order["nama_pelanggan"], order["kode"]),
                             url_for("staff.orders"))
        flash("Pesanan %s dibatalkan." % order["kode"], "info")
    return redirect(url_for("customer.order_detail", order_id=order_id))


@bp.route("/lacak")
def track():
    user = helpers.current_user()
    kode = request.args.get("kode", "").strip()
    order = None
    items = []
    if kode:
        order = database.query("SELECT * FROM orders WHERE kode = ? AND user_id = ?",
                               (kode, user["id"]), one=True)
        if order:
            items = database.query("SELECT * FROM order_items WHERE order_id = ?", (order["id"],))
        else:
            flash("Pesanan dengan kode tersebut tidak ditemukan pada akun Anda.", "warning")
    return render_template("customer/track.html", kode=kode, order=order, items=items,
                           orders=database.query(
                               "SELECT kode, status FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 10",
                               (user["id"],)))


@bp.route("/ringkasan")
def summary():
    user = helpers.current_user()
    rows = database.query(
        "SELECT o.*, (SELECT COUNT(*) FROM order_items i WHERE i.order_id = o.id) AS jumlah_item"
        " FROM orders o WHERE o.user_id = ? ORDER BY o.id DESC", (user["id"],))
    total = sum(r["total"] for r in rows)
    lunas = sum(r["total"] for r in rows if r["status_bayar"] == "Lunas")
    return render_template("customer/summary.html", orders=rows, total=total, lunas=lunas)


@bp.route("/komplain", methods=["GET", "POST"])
def complaints():
    user = helpers.current_user()
    if request.method == "POST":
        subjek = request.form.get("subjek", "").strip()
        isi = request.form.get("isi", "").strip()
        order_id = request.form.get("order_id") or None
        if not subjek or not isi:
            flash("Subjek dan isi keluhan wajib diisi.", "danger")
        else:
            foto = helpers.save_upload(request.files.get("foto"), "complaints")
            video = helpers.save_upload(request.files.get("video"), "complaints")
            kode = database.next_number("nomor_keluhan")
            database.execute(
                "INSERT INTO complaints (kode, user_id, order_id, nama_pelanggan, subjek, isi, foto, video,"
                " status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Baru', ?, ?)",
                (kode, user["id"], order_id, user["nama"], subjek, isi, foto, video,
                 database.now(), database.now()))
            helpers.notify_roles(["staff_admin", "staff_qc", "staff_keuangan", "administrator"],
                                 "Komplain baru %s" % kode, subjek, url_for("staff.complaints"))
            flash("Komplain %s terkirim. Tim kami akan menindaklanjuti." % kode, "success")
            return redirect(url_for("customer.complaints"))
    return render_template(
        "customer/complaints.html",
        rows=database.query("SELECT * FROM complaints WHERE user_id = ? ORDER BY id DESC", (user["id"],)),
        orders=database.query("SELECT id, kode FROM orders WHERE user_id = ? ORDER BY id DESC", (user["id"],)))


@bp.route("/notifikasi")
def notifications():
    user = helpers.current_user()
    rows = database.query(
        "SELECT * FROM notifications WHERE user_id = ? OR role = ? ORDER BY id DESC LIMIT 100",
        (user["id"], user["role"]))
    database.execute("UPDATE notifications SET dibaca = 1 WHERE user_id = ? OR role = ?",
                     (user["id"], user["role"]))
    return render_template("customer/notifications.html", rows=rows)


@bp.route("/invoice/<int:order_id>")
@helpers.feature_required("invoice")
def invoice(order_id):
    order = _my_order(order_id)
    items = database.query("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    return render_template("shared/invoice.html", order=order, items=items, back=url_for("customer.orders"))
