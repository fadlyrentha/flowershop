"""Halaman publik: beranda, katalog, detail produk, cek status pesanan."""
from flask import Blueprint, render_template, request

import db as database
import helpers

bp = Blueprint("public", __name__)


@bp.route("/")
def index():
    q = request.args.get("q", "").strip()
    kategori = request.args.get("kategori", "").strip()

    sql = "SELECT * FROM products WHERE aktif = 1"
    args = []
    if q:
        sql += " AND (nama LIKE ? OR deskripsi LIKE ? OR kategori LIKE ?)"
        args += ["%" + q + "%"] * 3
    if kategori:
        sql += " AND kategori = ?"
        args.append(kategori)
    sql += " ORDER BY nama"
    products = database.query(sql, args)

    kategori_list = [r["kategori"] for r in database.query(
        "SELECT DISTINCT kategori FROM products WHERE aktif = 1 ORDER BY kategori")]

    settings = database.all_settings()

    return render_template(
        "public/index.html",
        slides=database.query("SELECT * FROM hero_slides WHERE aktif = 1 ORDER BY urutan, id"),
        products=products,
        kategori_list=kategori_list,
        q=q,
        kategori=kategori,
        testimonials=database.query("SELECT * FROM testimonials WHERE aktif = 1 ORDER BY urutan, id"),
        # Feed & story ditarik dari setiap akun sosial media yang dikelola panel
        # kontroler, jadi kolom beranda selalu mengikuti data akun terkini.
        akun_sosial=database.social_accounts(aktif_saja=True),
        feed_sosial=database.social_gabungan("feed", settings),
        story_sosial=database.social_gabungan("story", settings),
        platform_sosial_ikon=database.SOCIAL_PLATFORM_IKON,
        platform_sosial_label=database.SOCIAL_PLATFORM_LABEL,
        platform_sosial_warna=database.SOCIAL_PLATFORM_WARNA,
        stok_list=database.query(
            "SELECT * FROM products WHERE aktif = 1 ORDER BY stok DESC LIMIT 8"),
        katalog=database.katalog_dari(settings),
    )


@bp.route("/produk/<int:product_id>")
def product_detail(product_id):
    product = database.query("SELECT * FROM products WHERE id = ? AND aktif = 1", (product_id,), one=True)
    if product is None:
        from flask import abort
        abort(404)
    related = database.query(
        "SELECT * FROM products WHERE aktif = 1 AND kategori = ? AND id != ? LIMIT 4",
        (product["kategori"], product_id))
    return render_template("public/product.html", product=product, related=related)


@bp.route("/lacak")
def track():
    kode = request.args.get("kode", "").strip()
    order = None
    items = []
    if kode:
        order = database.query("SELECT * FROM orders WHERE kode = ?", (kode,), one=True)
        if order:
            items = database.query("SELECT * FROM order_items WHERE order_id = ?", (order["id"],))
    return render_template("public/track.html", kode=kode, order=order, items=items)


# ------------------------------------------------------- monitoring publik ----
PANTAU_REFRESH = {0: "Nonaktif", 15: "15 detik", 30: "30 detik", 60: "1 menit",
                  300: "5 menit"}


@bp.route("/pantau")
@helpers.feature_required("monitoring_mandiri")
def pantau():
    """Halaman monitoring mandiri: di luar situs publik dan panel staf."""
    try:
        refresh = int(request.args.get("refresh", 0))
    except (TypeError, ValueError):
        refresh = 0
    if refresh not in PANTAU_REFRESH:
        refresh = 0

    status = request.args.get("status", "").strip()
    if status not in database.ORDER_STATUS:
        status = ""

    sql = ("SELECT o.*, (SELECT COUNT(*) FROM order_items i WHERE i.order_id = o.id) AS jumlah_item"
           " FROM orders o WHERE 1=1")
    args = []
    if status:
        sql += " AND o.status = ?"
        args.append(status)
    sql += " ORDER BY o.id DESC LIMIT 100"
    orders = database.query(sql, args)

    items = {}
    order_ids = [r["id"] for r in orders]
    if order_ids:
        placeholders = ",".join("?" * len(order_ids))
        for item in database.query(
                "SELECT * FROM order_items WHERE order_id IN (%s) ORDER BY id" % placeholders,
                order_ids):
            items.setdefault(item["order_id"], []).append(item)

    counts = {s: 0 for s in database.ORDER_STATUS}
    for row in database.query("SELECT status, COUNT(*) AS c FROM orders GROUP BY status"):
        counts[row["status"]] = row["c"]

    return render_template(
        "pantau/index.html", orders=orders, items=items, counts=counts,
        status=status, statuses=database.ORDER_STATUS,
        refresh=refresh, refresh_pilihan=PANTAU_REFRESH,
        products=database.query("SELECT * FROM products WHERE aktif = 1 ORDER BY nama"),
        stok_menipis=database.query(
            "SELECT COUNT(*) AS c FROM products WHERE aktif = 1 AND stok <= stok_minimum",
            one=True)["c"],
        total_order=database.query("SELECT COUNT(*) AS c FROM orders", one=True)["c"])
