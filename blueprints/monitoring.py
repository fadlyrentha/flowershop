"""Halaman monitoring bersama untuk semua peran selain pelanggan."""
from flask import Blueprint, render_template, request

import db as database
import helpers

bp = Blueprint("monitoring", __name__, url_prefix="/monitoring")

MONITORING_ROLES = ("staff_admin", "staff_kantor", "staff_gudang", "staff_qc",
                    "staff_keuangan", "administrator")

# Pilihan interval auto refresh Monitoring Harian (detik).
REFRESH_PILIHAN = {0: "Nonaktif", 15: "15 detik", 30: "30 detik", 60: "1 menit",
                   300: "5 menit"}


@bp.before_request
@helpers.role_required(*MONITORING_ROLES)
def guard():
    pass


@bp.route("/")
@helpers.feature_required("monitoring")
def index():
    return render_template(
        "monitoring/dashboard.html",
        stats={
            "orders": database.query("SELECT COUNT(*) AS c FROM orders", one=True)["c"],
            "aktif": database.query(
                "SELECT COUNT(*) AS c FROM orders WHERE status NOT IN ('Selesai','Dibatalkan')",
                one=True)["c"],
            "stok_menipis": database.query(
                "SELECT COUNT(*) AS c FROM products WHERE aktif = 1 AND stok <= stok_minimum",
                one=True)["c"],
            "kirim": database.query(
                "SELECT COUNT(*) AS c FROM orders WHERE status = 'Dikirim'", one=True)["c"],
        },
        orders=database.query(
            "SELECT o.*, (SELECT COUNT(*) FROM order_items i WHERE i.order_id = o.id) AS jumlah_item"
            " FROM orders o ORDER BY o.id DESC LIMIT 10"),
    )


@bp.route("/order")
@helpers.feature_required("monitoring")
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
    order_ids = [r["id"] for r in rows]
    if order_ids:
        placeholders = ",".join("?" * len(order_ids))
        for item in database.query(
                "SELECT * FROM order_items WHERE order_id IN (%s) ORDER BY id" % placeholders,
                order_ids):
            items.setdefault(item["order_id"], []).append(item)
    return render_template("monitoring/orders.html", rows=rows, items=items,
                           status=status, q=q)


@bp.route("/stok")
@helpers.feature_required("monitoring")
def stock():
    q = request.args.get("q", "").strip()
    sql = "SELECT * FROM products WHERE 1=1"
    args = []
    if q:
        sql += " AND (nama LIKE ? OR kategori LIKE ?)"
        args += ["%" + q + "%"] * 2
    sql += " ORDER BY nama"
    return render_template("monitoring/stock.html", rows=database.query(sql, args), q=q)


@bp.route("/status")
@helpers.feature_required("monitoring")
def status():
    counts = {s: 0 for s in database.ORDER_STATUS}
    for row in database.query("SELECT status, COUNT(*) AS c FROM orders GROUP BY status"):
        counts[row["status"]] = row["c"]
    groups = {s: [] for s in database.ORDER_STATUS}
    for row in database.query(
            "SELECT o.*, (SELECT COUNT(*) FROM order_items i WHERE i.order_id = o.id) AS jumlah_item"
            " FROM orders o ORDER BY o.id DESC"):
        groups.setdefault(row["status"], []).append(row)
    return render_template("monitoring/status.html", counts=counts, groups=groups,
                           statuses=database.ORDER_STATUS)


@bp.route("/harian")
@helpers.feature_required("monitoring_harian")
def daily():
    tanggal = request.args.get("tanggal", "").strip()
    if not tanggal:
        tanggal = database.today()
        if not database.query("SELECT 1 FROM orders WHERE date(created_at) = ? LIMIT 1",
                              (tanggal,), one=True):
            latest = database.query(
                "SELECT date(created_at) AS t FROM orders ORDER BY created_at DESC LIMIT 1", one=True)
            if latest and latest["t"]:
                tanggal = latest["t"]
    try:
        refresh = int(request.args.get("refresh", 0))
    except (TypeError, ValueError):
        refresh = 0
    if refresh not in REFRESH_PILIHAN:
        refresh = 0
    orders = database.query(
        "SELECT o.*, (SELECT COUNT(*) FROM order_items i WHERE i.order_id = o.id) AS jumlah_item"
        " FROM orders o WHERE date(o.created_at) = ? ORDER BY o.id DESC", (tanggal,))
    items = {}
    order_ids = [r["id"] for r in orders]
    if order_ids:
        placeholders = ",".join("?" * len(order_ids))
        for item in database.query(
                "SELECT * FROM order_items WHERE order_id IN (%s) ORDER BY id" % placeholders,
                order_ids):
            items.setdefault(item["order_id"], []).append(item)
    counts = {s: 0 for s in database.ORDER_STATUS}
    for row in database.query(
            "SELECT status, COUNT(*) AS c FROM orders WHERE date(created_at) = ? GROUP BY status",
            (tanggal,)):
        counts[row["status"]] = row["c"]
    return render_template(
        "monitoring/daily.html", tanggal=tanggal, orders=orders, items=items,
        counts=counts, refresh=refresh, refresh_pilihan=REFRESH_PILIHAN,
        products=database.query("SELECT * FROM products WHERE aktif = 1 ORDER BY nama"),
        stok_menipis=database.query(
            "SELECT COUNT(*) AS c FROM products WHERE aktif = 1 AND stok <= stok_minimum",
            one=True)["c"])


@bp.route("/lacak")
@helpers.feature_required("monitoring")
def track():
    kode = request.args.get("kode", "").strip()
    order = None
    items = []
    if kode:
        order = database.query("SELECT * FROM orders WHERE kode = ?", (kode,), one=True)
        if order:
            items = database.query("SELECT * FROM order_items WHERE order_id = ?", (order["id"],))
    return render_template(
        "monitoring/track.html", kode=kode, order=order, items=items,
        orders=database.query("SELECT kode, nama_pelanggan, status FROM orders ORDER BY id DESC LIMIT 10"))
