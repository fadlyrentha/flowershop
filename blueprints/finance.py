"""Halaman Keuangan."""
import os
from io import BytesIO

from flask import (Blueprint, abort, current_app, flash, redirect, render_template,
                   request, send_file, url_for)

import db as database
import helpers
import invoice_pdf

bp = Blueprint("finance", __name__, url_prefix="/keuangan")


@bp.before_request
@helpers.role_required("staff_keuangan", "administrator")
def guard():
    pass


@bp.route("/")
def dashboard():
    pemasukan = database.query(
        "SELECT COALESCE(SUM(jumlah),0) AS s FROM finance_entries WHERE tipe = 'pemasukan'", one=True)["s"]
    pengeluaran = database.query(
        "SELECT COALESCE(SUM(jumlah),0) AS s FROM finance_entries WHERE tipe = 'pengeluaran'", one=True)["s"]
    stats = {
        "pemasukan": pemasukan,
        "pengeluaran": pengeluaran,
        "laba": pemasukan - pengeluaran,
        "belum_bayar": database.query(
            "SELECT COALESCE(SUM(total),0) AS s FROM invoices WHERE status != 'Lunas'", one=True)["s"],
        "verifikasi": database.query(
            "SELECT COUNT(*) AS c FROM payments WHERE status = 'Menunggu Verifikasi'", one=True)["c"],
        "qc_siap": database.query(
            "SELECT COUNT(*) AS c FROM orders WHERE status = 'Siap Kirim'", one=True)["c"],
    }
    return render_template(
        "finance/dashboard.html", stats=stats,
        payments=database.query("SELECT * FROM payments ORDER BY id DESC LIMIT 6"),
        invoices=database.query("SELECT * FROM invoices ORDER BY id DESC LIMIT 6"))


@bp.route("/qc")
def qc_list():
    orders = database.query(
        "SELECT o.*, (SELECT COUNT(*) FROM order_items i WHERE i.order_id = o.id) AS jumlah_item,"
        " (SELECT COUNT(*) FROM order_items i WHERE i.order_id = o.id AND i.qc_status = 'Lolos QC') AS lolos"
        " FROM orders o WHERE EXISTS (SELECT 1 FROM order_items i WHERE i.order_id = o.id AND i.qc_status != 'Belum Dicek')"
        " ORDER BY o.id DESC")
    return render_template("finance/qc_list.html", rows=orders)


@bp.route("/qc/<int:order_id>")
def qc_detail(order_id):
    order = database.query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    if order is None:
        abort(404)
    items = database.query("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    checks = {}
    for c in database.query(
            "SELECT q.* FROM qc_checks q JOIN order_items i ON i.id = q.order_item_id"
            " WHERE i.order_id = ? ORDER BY q.id DESC", (order_id,)):
        checks.setdefault(c["order_item_id"], c)
    return render_template("finance/qc_detail.html", order=order, items=items, checks=checks)


@bp.route("/qc/<int:order_id>/cetak")
def qc_print(order_id):
    """Cetak checklist QC dari panel keuangan (tidak lewat blueprint staff)."""
    order = database.query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    if order is None:
        abort(404)
    items = database.query("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    return render_template("shared/qc_list.html", order=order, items=items)


# -------------------------------------------------------------- faktur ----
@bp.route("/faktur", methods=["GET", "POST"])
def invoices():
    if request.method == "POST":
        iid = request.form.get("id")
        data = (
            request.form.get("nomor", "").strip(),
            request.form.get("order_id") or None,
            request.form.get("user_id") or None,
            request.form.get("nama_pelanggan", "").strip(),
            int(request.form.get("total") or 0),
            request.form.get("kode_tagihan", "Reguler"),
            request.form.get("status", "Belum Dibayar"),
            request.form.get("jatuh_tempo", ""),
        )
        if not data[0]:
            flash("Nomor faktur wajib diisi.", "danger")
        elif data[5] not in database.KODE_TAGIHAN:
            flash("Kode tagihan tidak valid.", "danger")
        elif iid:
            database.execute(
                "UPDATE invoices SET nomor=?, order_id=?, user_id=?, nama_pelanggan=?, total=?, kode_tagihan=?,"
                " status=?, jatuh_tempo=? WHERE id=?", data + (iid,))
            flash("Faktur diperbarui.", "success")
        else:
            database.execute(
                "INSERT INTO invoices (nomor, nomor_invoice, order_id, user_id, nama_pelanggan, total,"
                " kode_tagihan, status, jatuh_tempo, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                data[:1] + (database.next_number("nomor_invoice"),) + data[1:] + (database.now(),))
            flash("Faktur baru dibuat.", "success")
        return redirect(url_for("finance.invoices"))
    kode = request.args.get("kode", "")
    sql = "SELECT * FROM invoices WHERE 1=1"
    args = []
    if kode in database.KODE_TAGIHAN:
        sql += " AND kode_tagihan = ?"
        args.append(kode)
    sql += " ORDER BY id DESC"
    counts = {k: 0 for k in database.KODE_TAGIHAN}
    for row in database.query("SELECT kode_tagihan, COUNT(*) AS c FROM invoices GROUP BY kode_tagihan"):
        counts[row["kode_tagihan"]] = row["c"]
    return render_template(
        "finance/invoices.html",
        rows=database.query(sql, args),
        orders=database.query("SELECT id, kode, nama_pelanggan, total FROM orders ORDER BY id DESC"),
        customers=database.query("SELECT id, nama FROM users WHERE role = 'pelanggan' ORDER BY nama"),
        kode_tagihan=database.KODE_TAGIHAN, kode=kode, counts=counts,
        total_semua=database.query("SELECT COUNT(*) AS c FROM invoices", one=True)["c"])


@bp.route("/faktur/<int:iid>/wa")
def invoice_wa(iid):
    invoice = database.query("SELECT * FROM invoices WHERE id = ?", (iid,), one=True)
    if invoice is None:
        abort(404)
    telepon = ""
    if invoice["order_id"]:
        order = database.query("SELECT telepon FROM orders WHERE id = ?", (invoice["order_id"],), one=True)
        telepon = order["telepon"] if order else ""
    if not telepon and invoice["user_id"]:
        user = database.query("SELECT telepon FROM users WHERE id = ?", (invoice["user_id"],), one=True)
        telepon = user["telepon"] if user else ""
    rekening, tampil = _rekening_tampil()
    pesan = (
        "Halo %s, berikut faktur dari %s.\n\n"
        "Nomor faktur : %s\n"
        "Kode tagihan : %s\n"
        "Total tagihan: %s\n"
        "Jatuh tempo  : %s\n"
        "Status       : %s\n"
    ) % (invoice["nama_pelanggan"] or "Pelanggan", database.get_setting("nama_toko"),
         invoice["nomor"], invoice["kode_tagihan"], helpers.rupiah(invoice["total"]),
         invoice["jatuh_tempo"] or "-", invoice["status"])
    if tampil and rekening:
        pesan += "\nPembayaran transfer ke:\n%s\n" % rekening
    pdf_url = url_for("finance.invoice_pdf_download", iid=iid, _external=True)
    pesan += "\nUnduh faktur (PDF):\n%s\n\nTerima kasih." % pdf_url
    return redirect(helpers.wa_link(telepon, pesan))


@bp.route("/faktur/<int:iid>/hapus", methods=["POST"])
def invoice_delete(iid):
    database.execute("DELETE FROM invoices WHERE id = ?", (iid,))
    flash("Faktur dihapus.", "info")
    return redirect(url_for("finance.invoices"))


def _invoice_data(iid):
    """Ambil faktur beserta order dan itemnya; None bila faktur tidak ada."""
    invoice = database.query("SELECT * FROM invoices WHERE id = ?", (iid,), one=True)
    if invoice is None:
        return None, None, []
    order = None
    items = []
    if invoice["order_id"]:
        order = database.query("SELECT * FROM orders WHERE id = ?", (invoice["order_id"],), one=True)
        items = database.query("SELECT * FROM order_items WHERE order_id = ?", (invoice["order_id"],))
    return invoice, order, items


def _rekening_tampil():
    tampil = database.get_setting("tampil_rekening", "1") == "1"
    return database.get_setting("rekening_bank", ""), tampil


def _logo_path():
    """Lokasi berkas logo toko untuk ditempel di PDF faktur."""
    nama = database.get_setting("logo", "")
    if not nama:
        return ""
    return os.path.join(current_app.config["UPLOAD_FOLDER"], nama)


# Template cetak faktur untuk tiap pilihan di menu Ganti Template Invoice.
TEMPLATE_CETAK = {"klasik": "finance/invoice_print.html",
                  "modern": "finance/invoice_modern.html"}


@bp.route("/faktur/<int:iid>/cetak")
def invoice_print(iid):
    invoice, order, items = _invoice_data(iid)
    if invoice is None:
        abort(404)
    rekening, tampil = _rekening_tampil()
    template = database.get_setting("template_invoice", "klasik")
    if template == "desain":
        desain = database.get_setting("template_invoice_file", "")
        if desain:
            return render_template("finance/invoice_desain.html", invoice=invoice, order=order,
                                   items=items, desain=desain, rekening=rekening,
                                   tampil_rekening=tampil)
        template = "klasik"
    return render_template(TEMPLATE_CETAK.get(template, TEMPLATE_CETAK["klasik"]),
                           invoice=invoice, order=order, items=items,
                           rekening=rekening, tampil_rekening=tampil)


@bp.route("/faktur/<int:iid>/pdf")
def invoice_pdf_download(iid):
    invoice, order, items = _invoice_data(iid)
    if invoice is None:
        abort(404)
    rekening, tampil = _rekening_tampil()
    data = invoice_pdf.build(invoice, order, items, database.all_settings(),
                            rekening=rekening, tampil_rekening=tampil,
                            logo_path=_logo_path())
    nama = "faktur-%s.pdf" % "".join(ch if ch.isalnum() or ch in "-_" else "-"
                                     for ch in (invoice["nomor"] or str(iid)))
    return send_file(BytesIO(data), mimetype="application/pdf", as_attachment=True,
                     download_name=nama)


# ------------------------------------------------------------- keluhan ----
@bp.route("/keluhan", methods=["GET", "POST"])
def complaints():
    if request.method == "POST":
        cid = request.form.get("id")
        user_id = request.form.get("user_id") or None
        nama = request.form.get("nama_pelanggan", "").strip()
        if user_id and not nama:
            cust = database.query("SELECT nama FROM users WHERE id = ?", (user_id,), one=True)
            nama = cust["nama"] if cust else ""
        kategori = request.form.get("kategori", "Lainnya")
        kompensasi = request.form.get("kompensasi", "Tidak Ada")
        status = request.form.get("status", "Baru")
        try:
            nominal = int(request.form.get("nominal") or 0)
        except (TypeError, ValueError):
            nominal = 0
        subjek = request.form.get("subjek", "").strip()
        isi = request.form.get("isi", "").strip()
        tanggapan = request.form.get("tanggapan", "").strip()

        if not subjek:
            flash("Subjek keluhan wajib diisi.", "danger")
        elif kategori not in database.KATEGORI_KELUHAN:
            flash("Kategori keluhan tidak valid.", "danger")
        elif kompensasi not in database.KOMPENSASI_KELUHAN:
            flash("Pilihan kompensasi tidak valid.", "danger")
        elif status not in database.STATUS_KELUHAN:
            flash("Status keluhan tidak valid.", "danger")
        elif cid:
            database.execute(
                "UPDATE complaints SET user_id=?, nama_pelanggan=?, kategori=?, kompensasi=?, nominal=?,"
                " subjek=?, isi=?, status=?, tanggapan=?, updated_at=? WHERE id=?",
                (user_id, nama, kategori, kompensasi, nominal, subjek, isi, status, tanggapan,
                 database.now(), cid))
            flash("Keluhan diperbarui.", "success")
        else:
            database.execute(
                "INSERT INTO complaints (kode, user_id, order_id, nama_pelanggan, kategori, kompensasi,"
                " nominal, subjek, isi, status, tanggapan, created_at, updated_at)"
                " VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (database.next_number("nomor_keluhan"), user_id, nama, kategori, kompensasi, nominal,
                 subjek, isi, status, tanggapan, database.now(), database.now()))
            flash("Keluhan ditambahkan.", "success")
        return redirect(url_for("finance.complaints"))
    return render_template(
        "finance/complaints.html",
        rows=database.query("SELECT * FROM complaints ORDER BY id DESC"),
        customers=database.query("SELECT id, nama, username FROM users WHERE role = 'pelanggan' ORDER BY nama"),
        kategori_list=database.KATEGORI_KELUHAN,
        kompensasi_list=database.KOMPENSASI_KELUHAN,
        status_list=database.STATUS_KELUHAN)


@bp.route("/keluhan/<int:cid>/hapus", methods=["POST"])
def complaint_delete(cid):
    database.execute("DELETE FROM complaints WHERE id = ?", (cid,))
    flash("Keluhan dihapus.", "info")
    return redirect(url_for("finance.complaints"))


@bp.route("/keluhan/cetak")
def complaints_print():
    return render_template("finance/complaints_print.html",
                           rows=database.query("SELECT * FROM complaints ORDER BY id DESC"))


# ----------------------------------------------------------------- stok ----
@bp.route("/stok", methods=["GET", "POST"])
def stock():
    if request.method == "POST":
        sid = request.form.get("id")
        pid = request.form.get("product_id")
        tipe = request.form.get("tipe", "masuk")
        qty = int(request.form.get("qty") or 0)
        keterangan = request.form.get("keterangan", "").strip()
        referensi = request.form.get("referensi", "").strip()
        if not pid or qty <= 0:
            flash("Produk dan jumlah wajib diisi dengan benar.", "danger")
        elif sid:
            old = database.query("SELECT * FROM stock_moves WHERE id = ?", (sid,), one=True)
            if old:
                revert = old["qty"] if old["tipe"] == "masuk" else -old["qty"]
                database.execute("UPDATE products SET stok = stok - ? WHERE id = ?", (revert, old["product_id"]))
                delta = qty if tipe == "masuk" else -qty
                database.execute("UPDATE products SET stok = MAX(0, stok + ?) WHERE id = ?", (delta, pid))
                database.execute(
                    "UPDATE stock_moves SET product_id=?, tipe=?, qty=?, keterangan=?, referensi=? WHERE id=?",
                    (pid, tipe, qty, keterangan, referensi, sid))
            flash("Mutasi stok diperbarui.", "success")
        else:
            delta = qty if tipe == "masuk" else -qty
            database.execute("UPDATE products SET stok = MAX(0, stok + ?) WHERE id = ?", (delta, pid))
            database.execute(
                "INSERT INTO stock_moves (product_id, tipe, qty, keterangan, referensi, dibuat_oleh, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (pid, tipe, qty, keterangan, referensi, helpers.current_user()["id"], database.now()))
            flash("Mutasi stok dicatat.", "success")
        return redirect(url_for("finance.stock"))
    return render_template(
        "finance/stock.html",
        products=database.query("SELECT * FROM products ORDER BY nama"),
        rows=database.query(
            "SELECT m.*, p.nama AS produk FROM stock_moves m JOIN products p ON p.id = m.product_id"
            " ORDER BY m.id DESC LIMIT 100"))


@bp.route("/stok/<int:sid>/hapus", methods=["POST"])
def stock_delete(sid):
    move = database.query("SELECT * FROM stock_moves WHERE id = ?", (sid,), one=True)
    if move:
        revert = move["qty"] if move["tipe"] == "masuk" else -move["qty"]
        database.execute("UPDATE products SET stok = MAX(0, stok - ?) WHERE id = ?", (revert, move["product_id"]))
        database.execute("DELETE FROM stock_moves WHERE id = ?", (sid,))
        flash("Mutasi stok dihapus dan saldo stok disesuaikan.", "info")
    return redirect(url_for("finance.stock"))


@bp.route("/stok/cetak")
def stock_print():
    return render_template(
        "finance/stock_print.html",
        products=database.query("SELECT * FROM products ORDER BY nama"),
        rows=database.query(
            "SELECT m.*, p.nama AS produk FROM stock_moves m JOIN products p ON p.id = m.product_id"
            " ORDER BY m.id DESC LIMIT 200"))


# --------------------------------------------------------- pembayaran -----
@bp.route("/pembayaran", methods=["GET", "POST"])
def payments():
    if request.method == "POST":
        pid = request.form.get("id")
        bukti = helpers.save_upload(request.files.get("bukti"), "payments")
        try:
            jumlah = int(request.form.get("jumlah") or 0)
        except (TypeError, ValueError):
            jumlah = 0
        data = (
            request.form.get("invoice_id") or None,
            request.form.get("order_id") or None,
            request.form.get("metode", "Transfer Bank"),
            jumlah,
            request.form.get("status", "Menunggu Verifikasi"),
            request.form.get("catatan", "").strip(),
        )
        if not data[3]:
            flash("Jumlah pembayaran wajib diisi.", "danger")
        elif pid:
            if bukti:
                database.execute(
                    "UPDATE payments SET invoice_id=?, order_id=?, metode=?, jumlah=?, bukti=?, status=?,"
                    " catatan=? WHERE id=?", data[:4] + (bukti,) + data[4:] + (pid,))
            else:
                database.execute(
                    "UPDATE payments SET invoice_id=?, order_id=?, metode=?, jumlah=?, status=?, catatan=?"
                    " WHERE id=?", data[:4] + data[4:] + (pid,))
            flash("Pembayaran diperbarui.", "success")
        else:
            database.execute(
                "INSERT INTO payments (kode, kode_verifikasi, invoice_id, order_id, metode, jumlah, bukti,"
                " status, catatan, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (database.next_number("nomor_transaksi"),
                 database.next_number("nomor_verifikasi"))
                + data[:4] + (bukti,) + data[4:] + (database.now(),))
            flash("Pembayaran dicatat.", "success")
        return redirect(url_for("finance.payments"))
    return render_template(
        "finance/payments.html",
        rows=database.query("SELECT * FROM payments ORDER BY id DESC"),
        invoices=database.query("SELECT id, nomor, nama_pelanggan, total FROM invoices ORDER BY id DESC"),
        orders=database.query("SELECT id, kode, total FROM orders ORDER BY id DESC"))


@bp.route("/pembayaran/<int:pid>/verifikasi", methods=["POST"])
def verify_payment(pid):
    payment = database.query("SELECT * FROM payments WHERE id = ?", (pid,), one=True)
    if payment is None:
        abort(404)
    status = request.form.get("status", "Terverifikasi")
    database.execute("UPDATE payments SET status = ? WHERE id = ?", (status, pid))
    if status == "Terverifikasi":
        if payment["invoice_id"]:
            database.execute("UPDATE invoices SET status = 'Lunas' WHERE id = ?", (payment["invoice_id"],))
        if payment["order_id"]:
            database.execute("UPDATE orders SET status_bayar = 'Lunas', updated_at = ? WHERE id = ?",
                             (database.now(), payment["order_id"]))
            order = database.query("SELECT * FROM orders WHERE id = ?", (payment["order_id"],), one=True)
            if order and order["user_id"]:
                helpers.notify("Pembayaran terverifikasi", "Pesanan %s sudah lunas." % order["kode"],
                               url_for("customer.order_detail", order_id=order["id"]),
                               user_id=order["user_id"])
        database.execute(
            "INSERT INTO finance_entries (tipe, kategori, keterangan, jumlah, tanggal, dibuat_oleh, created_at)"
            " VALUES ('pemasukan', 'Pembayaran Pelanggan', ?, ?, ?, ?, ?)",
            (payment["metode"], payment["jumlah"], database.today(),
             helpers.current_user()["id"], database.now()))
        flash("Pembayaran terverifikasi dan tercatat sebagai pemasukan.", "success")
    else:
        flash("Status pembayaran diperbarui menjadi %s." % status, "info")
    return redirect(url_for("finance.payments"))


@bp.route("/pembayaran/<int:pid>/hapus", methods=["POST"])
def payment_delete(pid):
    database.execute("DELETE FROM payments WHERE id = ?", (pid,))
    flash("Pembayaran dihapus.", "info")
    return redirect(url_for("finance.payments"))


@bp.route("/pembayaran/cetak")
def payments_print():
    return render_template("finance/payments_print.html",
                           rows=database.query("SELECT * FROM payments ORDER BY id DESC"))


# ------------------------------------------------------------- laporan ----
@bp.route("/laporan", methods=["GET", "POST"])
def reports():
    if request.method == "POST":
        eid = request.form.get("id")
        data = (
            request.form.get("tipe", "pemasukan"),
            request.form.get("kategori", "Lainnya"),
            request.form.get("keterangan", "").strip(),
            int(request.form.get("jumlah") or 0),
            request.form.get("tanggal", database.today()),
        )
        if not data[3]:
            flash("Jumlah wajib diisi.", "danger")
        elif eid:
            database.execute(
                "UPDATE finance_entries SET tipe=?, kategori=?, keterangan=?, jumlah=?, tanggal=? WHERE id=?",
                data + (eid,))
            flash("Catatan keuangan diperbarui.", "success")
        else:
            database.execute(
                "INSERT INTO finance_entries (tipe, kategori, keterangan, jumlah, tanggal, dibuat_oleh, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                data + (helpers.current_user()["id"], database.now()))
            flash("Catatan keuangan ditambahkan.", "success")
        return redirect(url_for("finance.reports"))

    periode = request.args.get("periode", "hari")
    today = database.today()
    if periode == "minggu":
        start = (database.datetime.now() - database.timedelta(days=7)).strftime("%Y-%m-%d")
    elif periode == "bulan":
        start = today[:8] + "01"
    elif periode == "tahun":
        start = today[:5] + "01-01"
    else:
        start = today

    rows = database.query(
        "SELECT * FROM finance_entries WHERE tanggal >= ? ORDER BY tanggal DESC, id DESC", (start,))
    pemasukan = sum(r["jumlah"] for r in rows if r["tipe"] == "pemasukan")
    pengeluaran = sum(r["jumlah"] for r in rows if r["tipe"] == "pengeluaran")
    return render_template("finance/reports.html", rows=rows, periode=periode, start=start,
                           pemasukan=pemasukan, pengeluaran=pengeluaran,
                           laba=pemasukan - pengeluaran)


@bp.route("/laporan/<int:eid>/hapus", methods=["POST"])
def report_delete(eid):
    database.execute("DELETE FROM finance_entries WHERE id = ?", (eid,))
    flash("Catatan keuangan dihapus.", "info")
    return redirect(url_for("finance.reports"))


@bp.route("/laporan/cetak")
def reports_print():
    periode = request.args.get("periode", "hari")
    today = database.today()
    if periode == "minggu":
        start = (database.datetime.now() - database.timedelta(days=7)).strftime("%Y-%m-%d")
    elif periode == "bulan":
        start = today[:8] + "01"
    elif periode == "tahun":
        start = today[:5] + "01-01"
    else:
        start = today
    rows = database.query(
        "SELECT * FROM finance_entries WHERE tanggal >= ? ORDER BY tanggal DESC", (start,))
    pemasukan = sum(r["jumlah"] for r in rows if r["tipe"] == "pemasukan")
    pengeluaran = sum(r["jumlah"] for r in rows if r["tipe"] == "pengeluaran")
    return render_template("finance/reports_print.html", rows=rows, periode=periode,
                           pemasukan=pemasukan, pengeluaran=pengeluaran,
                           laba=pemasukan - pengeluaran)


# ------------------------------------------------------- pesanan manual ----
@bp.route("/pesanan-baru", methods=["GET", "POST"])
def new_order():
    """Formulir order manual dari panel keuangan, lengkap dengan kategori tagihan."""
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
        flash("Pesanan %s dibuat dengan kategori %s." % (kode, kode_tagihan), "success")
        return redirect(url_for("finance.invoices"))
    return render_template("staff/new_order.html", products=products,
                           customers_list=customers_list, form={})


# ---------------------------------------------------------------- produk ----
@bp.route("/produk", methods=["GET", "POST"])
@helpers.feature_required("produk")
def products():
    """Kelola produk: tambah, ubah, dan hapus dari panel keuangan."""
    if request.method == "POST":
        pid = request.form.get("id")
        try:
            harga = int(request.form.get("harga") or 0)
            stok = int(request.form.get("stok") or 0)
            stok_minimum = int(request.form.get("stok_minimum") or 5)
        except (TypeError, ValueError):
            flash("Harga dan stok harus berupa angka.", "danger")
            return redirect(url_for("finance.products"))
        data = (
            request.form.get("nama", "").strip(),
            request.form.get("deskripsi", "").strip(),
            request.form.get("kategori", "Bunga Potong").strip(),
            harga, stok, stok_minimum,
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
        return redirect(url_for("finance.products"))
    q = request.args.get("q", "").strip()
    sql = "SELECT * FROM products WHERE 1=1"
    args = []
    if q:
        sql += " AND (nama LIKE ? OR kategori LIKE ?)"
        args += ["%" + q + "%"] * 2
    sql += " ORDER BY nama"
    return render_template("finance/products.html", rows=database.query(sql, args), q=q)


@bp.route("/produk/<int:pid>/hapus", methods=["POST"])
@helpers.feature_required("produk")
def product_delete(pid):
    used = database.query("SELECT COUNT(*) AS c FROM order_items WHERE product_id = ?",
                          (pid,), one=True)["c"]
    if used:
        database.execute("UPDATE products SET aktif = 0 WHERE id = ?", (pid,))
        flash("Produk dinonaktifkan karena memiliki riwayat pesanan.", "warning")
    else:
        produk = database.query("SELECT gambar FROM products WHERE id = ?", (pid,), one=True)
        database.execute("DELETE FROM products WHERE id = ?", (pid,))
        if produk:
            helpers.delete_upload(produk["gambar"])
        flash("Produk dihapus.", "info")
    return redirect(url_for("finance.products"))


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
    return redirect(url_for("finance.products"))


# -------------------------------------------------------------- rekening ----
@bp.route("/rekening", methods=["GET", "POST"])
def rekening():
    """Lihat dan atur rekening bank yang dicetak di faktur."""
    if request.method == "POST":
        database.set_setting("rekening_bank", request.form.get("rekening_bank", "").strip())
        database.set_setting("tampil_rekening", "1" if request.form.get("tampil_rekening") else "0")
        flash("Data rekening bank disimpan.", "success")
        return redirect(url_for("finance.rekening"))
    return render_template(
        "finance/rekening.html",
        rekening=database.get_setting("rekening_bank", ""),
        tampil=database.get_setting("tampil_rekening", "1") == "1")


@bp.route("/notifikasi")
def notifications():
    user = helpers.current_user()
    rows = database.query(
        "SELECT * FROM notifications WHERE user_id = ? OR role = ? ORDER BY id DESC LIMIT 100",
        (user["id"], user["role"]))
    database.execute("UPDATE notifications SET dibaca = 1 WHERE user_id = ? OR role = ?",
                     (user["id"], user["role"]))
    return render_template("staff/notifications.html", rows=rows)
