"""Halaman administrator: CMS beranda, pengaturan situs, staff, hak akses."""
import os

from flask import (Blueprint, abort, current_app, flash, redirect, render_template,
                   request, send_file, url_for)
from werkzeug.security import generate_password_hash

import db as database
import helpers

bp = Blueprint("admin", __name__, url_prefix="/admin")

ROLE_ORDER = ["pelanggan", "staff_admin", "staff_kantor", "staff_gudang",
              "staff_qc", "staff_keuangan", "administrator"]

TEMPLATE_INVOICE = {
    "klasik": "Klasik — kop surat sederhana, tabel rapi",
    "modern": "Modern — header berwarna, kartu total",
    "desain": "Desain Unggahan — memakai berkas desain yang Anda unggah",
}

DESAIN_EXT = {"png", "jpg", "jpeg", "webp"}

FEATURE_LABELS = {
    "dashboard": "Dashboard",
    "profil": "Profil & Kata Sandi Akun",
    "pesanan_baru": "Formulir Pesanan Baru",
    "pesanan": "Data Pesanan",
    "lacak": "Lacak Pesanan",
    "komplain": "Komplain",
    "notifikasi": "Notifikasi",
    "invoice": "Invoice Pelanggan",
    "pelanggan": "Data Pelanggan",
    "produk": "Data Produk",
    "stok": "Stok Masuk/Keluar",
    "stok_mutasi": "Catat Mutasi Stok",
    "label": "Cetak Label",
    "qc_list": "List QC / Checklist",
    "laporan": "Laporan",
    "cms": "Manajemen Beranda (CMS)",
    "pengaturan": "Pengaturan Situs",
    "faktur": "Faktur",
    "pembayaran": "Verifikasi Pembayaran",
    "qc_verifikasi": "Verifikasi Quality Kontrol",
    "pengiriman": "Status Pengiriman",
    "keluhan": "Keluhan Pelanggan",
    "akun_staff": "Akun Staff",
    "hak_akses": "Hak Akses",
    "konfirmasi_order": "Konfirmasi Order",
    "format_nomor": "Ubah Format Nomor",
    "template_invoice": "Ganti Template Invoice",
    "monitoring": "Monitoring (List Order/Stok/Status/Lacak)",
    "monitoring_harian": "Monitoring Harian",
    "monitoring_mandiri": "Monitoring Mandiri (Halaman /pantau)",
    "ganti_produk": "Ganti Produk (QC)",
    "backup": "Backup Data",
    "katalog_seksi": "Kolom Katalog Beranda",
    "rekening": "Rekening Bank Faktur",
    "reset": "Reset Pengaturan",
}


@bp.before_request
@helpers.role_required("administrator", "staff_kantor")
def guard():
    pass


STAFF_ONLY = ("accounts", "account_delete", "permissions", "settings", "dashboard",
              "nomor_format", "invoice_template", "invoice_template_delete_design",
              "backup", "backup_download", "backup_delete", "katalog", "rekening", "reset")


@bp.before_request
def restrict_to_admin():
    from flask import request as _rq
    if _rq.endpoint and _rq.endpoint.split(".")[-1] in STAFF_ONLY:
        if helpers.current_user().role != "administrator":
            abort(403)


@bp.route("/")
def dashboard():
    stats = {
        "pelanggan": database.query("SELECT COUNT(*) AS c FROM users WHERE role='pelanggan'", one=True)["c"],
        "staff": database.query("SELECT COUNT(*) AS c FROM users WHERE role!='pelanggan'", one=True)["c"],
        "produk": database.query("SELECT COUNT(*) AS c FROM products", one=True)["c"],
        "pesanan": database.query("SELECT COUNT(*) AS c FROM orders", one=True)["c"],
        "omzet": database.query("SELECT COALESCE(SUM(total),0) AS s FROM orders WHERE status='Selesai'", one=True)["s"],
        "komplain": database.query("SELECT COUNT(*) AS c FROM complaints", one=True)["c"],
    }
    return render_template(
        "admin/dashboard.html", stats=stats,
        orders=database.query("SELECT * FROM orders ORDER BY id DESC LIMIT 8"),
        role_stats=database.query(
            "SELECT role, COUNT(*) AS c FROM users GROUP BY role"))


# ------------------------------------------------------------------ CMS ----
@bp.route("/cms", methods=["GET", "POST"])
def cms():
    if request.method == "POST":
        aksi = request.form.get("aksi")
        if aksi == "hero":
            hid = request.form.get("id")
            data = (
                request.form.get("judul", "").strip(),
                request.form.get("subjudul", "").strip(),
                request.form.get("teks_tombol", "Belanja Sekarang").strip(),
                request.form.get("link_tombol", "/#katalog").strip(),
                int(request.form.get("urutan") or 0),
                1 if request.form.get("aktif") else 0,
            )
            gambar = helpers.save_upload(request.files.get("gambar"), "hero")
            if not data[0]:
                flash("Judul slide wajib diisi.", "danger")
            elif hid:
                if gambar:
                    database.execute(
                        "UPDATE hero_slides SET judul=?, subjudul=?, teks_tombol=?, link_tombol=?, urutan=?,"
                        " aktif=?, gambar=? WHERE id=?", data + (gambar, hid))
                else:
                    database.execute(
                        "UPDATE hero_slides SET judul=?, subjudul=?, teks_tombol=?, link_tombol=?, urutan=?,"
                        " aktif=? WHERE id=?", data + (hid,))
                flash("Slide diperbarui.", "success")
            else:
                database.execute(
                    "INSERT INTO hero_slides (judul, subjudul, teks_tombol, link_tombol, urutan, aktif, gambar)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)", data + (gambar,))
                flash("Slide ditambahkan.", "success")
        elif aksi == "testimoni":
            tid = request.form.get("id")
            data = (
                request.form.get("nama", "").strip(),
                request.form.get("isi", "").strip(),
                int(request.form.get("rating") or 5),
                int(request.form.get("urutan") or 0),
                1 if request.form.get("aktif") else 0,
            )
            foto = helpers.save_upload(request.files.get("foto"), "testimonials")
            if not data[0] or not data[1]:
                flash("Nama dan isi testimoni wajib diisi.", "danger")
            elif tid:
                if foto:
                    database.execute(
                        "UPDATE testimonials SET nama=?, isi=?, rating=?, urutan=?, aktif=?, foto=? WHERE id=?",
                        data + (foto, tid))
                else:
                    database.execute(
                        "UPDATE testimonials SET nama=?, isi=?, rating=?, urutan=?, aktif=? WHERE id=?",
                        data + (tid,))
                flash("Testimoni diperbarui.", "success")
            else:
                database.execute(
                    "INSERT INTO testimonials (nama, isi, rating, urutan, aktif, foto) VALUES (?, ?, ?, ?, ?, ?)",
                    data + (foto,))
                flash("Testimoni ditambahkan.", "success")
        elif aksi == "sosial":
            sid = request.form.get("id")
            data = (
                request.form.get("platform", "instagram"),
                request.form.get("judul", "").strip(),
                request.form.get("link", "#").strip(),
                int(request.form.get("urutan") or 0),
                1 if request.form.get("aktif") else 0,
            )
            gambar = helpers.save_upload(request.files.get("gambar"), "social")
            if sid:
                if gambar:
                    database.execute(
                        "UPDATE social_posts SET platform=?, judul=?, link=?, urutan=?, aktif=?, gambar=?"
                        " WHERE id=?", data + (gambar, sid))
                else:
                    database.execute(
                        "UPDATE social_posts SET platform=?, judul=?, link=?, urutan=?, aktif=? WHERE id=?",
                        data + (sid,))
                flash("Postingan sosial diperbarui.", "success")
            else:
                database.execute(
                    "INSERT INTO social_posts (platform, judul, link, urutan, aktif, gambar)"
                    " VALUES (?, ?, ?, ?, ?, ?)", data + (gambar,))
                flash("Postingan sosial ditambahkan.", "success")
        return redirect(url_for("admin.cms"))

    return render_template(
        "admin/cms.html",
        slides=database.query("SELECT * FROM hero_slides ORDER BY urutan, id"),
        testimonials=database.query("SELECT * FROM testimonials ORDER BY urutan, id"),
        socials=database.query("SELECT * FROM social_posts ORDER BY urutan, id"),
        products=database.query("SELECT * FROM products ORDER BY nama"))


@bp.route("/cms/<string:jenis>/<int:item_id>/hapus", methods=["POST"])
def cms_delete(jenis, item_id):
    table = {"hero": "hero_slides", "testimoni": "testimonials", "sosial": "social_posts"}.get(jenis)
    if not table:
        abort(404)
    database.execute("DELETE FROM %s WHERE id = ?" % table, (item_id,))
    flash("Item beranda dihapus.", "info")
    return redirect(url_for("admin.cms"))


# ------------------------------------------------------------ pengaturan ----
@bp.route("/pengaturan", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        keys = ["nama_toko", "tagline", "deskripsi", "alamat", "telepon", "email", "instagram",
                "tiktok", "whatsapp", "jam_operasional", "jam_minggu", "sameday_info",
                "warna_primer", "warna_sekunder", "footer_text"]
        for key in keys:
            if key in request.form:
                database.set_setting(key, request.form.get(key, "").strip())
        logo = helpers.save_upload(request.files.get("logo"), "brand")
        if logo:
            database.set_setting("logo", logo)
        flash("Pengaturan situs disimpan.", "success")
        return redirect(url_for("admin.settings"))
    return render_template("admin/settings.html")


# ---------------------------------------------------------------- staff ----
@bp.route("/akun", methods=["GET", "POST"])
def accounts():
    if request.method == "POST":
        uid = request.form.get("id")
        username = request.form.get("username", "").strip()
        nama = request.form.get("nama", "").strip()
        role = request.form.get("role", "staff_admin")
        telepon = request.form.get("telepon", "").strip()
        email = request.form.get("email", "").strip()
        aktif = 1 if request.form.get("aktif") else 0
        password = request.form.get("password", "")
        if role not in database.ROLE_LABEL:
            abort(400)
        if not username or not nama:
            flash("Nama dan username wajib diisi.", "danger")
        elif uid:
            database.execute(
                "UPDATE users SET username=?, nama=?, role=?, telepon=?, email=?, aktif=? WHERE id=?",
                (username, nama, role, telepon, email, aktif, uid))
            if password:
                database.execute("UPDATE users SET password_hash=? WHERE id=?",
                                 (generate_password_hash(password), uid))
            flash("Akun diperbarui.", "success")
        else:
            if database.query("SELECT id FROM users WHERE username=?", (username,), one=True):
                flash("Username sudah digunakan.", "danger")
                return redirect(url_for("admin.accounts"))
            database.execute(
                "INSERT INTO users (username, password_hash, nama, role, telepon, email, alamat, aktif, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, '', ?, ?)",
                (username, generate_password_hash(password or "staff123"), nama, role, telepon, email,
                 aktif, database.now()))
            flash("Akun baru dibuat.", "success")
        return redirect(url_for("admin.accounts"))
    return render_template(
        "admin/accounts.html",
        rows=database.query("SELECT * FROM users WHERE role != 'pelanggan' ORDER BY role, nama"))


@bp.route("/akun/<int:uid>/hapus", methods=["POST"])
def account_delete(uid):
    user = helpers.current_user()
    if uid == user["id"]:
        flash("Anda tidak dapat menghapus akun sendiri.", "warning")
    else:
        database.execute("DELETE FROM users WHERE id = ? AND role != 'pelanggan'", (uid,))
        flash("Akun staff dihapus.", "info")
    return redirect(url_for("admin.accounts"))


# ------------------------------------------------------------ hak akses ----
@bp.route("/hak-akses", methods=["GET", "POST"])
def permissions():
    if request.method == "POST":
        role = request.form.get("role")
        if role not in database.ROLE_LABEL:
            abort(400)
        selected = set(request.form.getlist("feature"))
        for feature in FEATURE_LABELS:
            database.execute(
                "INSERT INTO role_features (role, feature, aktif) VALUES (?, ?, ?)"
                " ON CONFLICT(role, feature) DO UPDATE SET aktif = excluded.aktif",
                (role, feature, 1 if feature in selected else 0))
        flash("Hak akses peran %s diperbarui." % database.ROLE_LABEL[role], "success")
        return redirect(url_for("admin.permissions", role=role))

    role = request.args.get("role", "staff_admin")
    if role not in database.ROLE_LABEL:
        role = "staff_admin"
    active = database.role_features(role)
    rows = database.query(
        "SELECT role, SUM(aktif) AS aktif, COUNT(*) AS total FROM role_features GROUP BY role")
    summary = {r["role"]: r for r in rows}
    return render_template("admin/permissions.html", role=role, active=active,
                           FEATURE_LABELS=FEATURE_LABELS, ROLE_LABEL=database.ROLE_LABEL,
                           ROLE_ORDER=ROLE_ORDER, summary=summary)


@bp.route("/format-nomor", methods=["GET", "POST"])
@helpers.feature_required("format_nomor")
def nomor_format():
    """Ubah format nomor order, faktur, invoice, keluhan, transaksi, verifikasi, lacak."""
    if request.method == "POST":
        berubah = 0
        for key, (setting, _table, _column, label) in database.NOMOR_FORMAT.items():
            nilai = request.form.get(setting, "").strip()
            if not nilai:
                continue
            if not database.valid_nomor_format(nilai):
                flash("Format %s harus memakai {SEQ} atau {RAND} agar nomor unik." % label,
                      "danger")
                continue
            database.set_setting(setting, nilai)
            berubah += 1
        if berubah:
            flash("%d format nomor disimpan. Nomor baru berlaku untuk dokumen berikutnya."
                  % berubah, "success")
        return redirect(url_for("admin.nomor_format"))

    rows = []
    for key, (setting, _table, _column, label) in database.NOMOR_FORMAT.items():
        template = database.get_setting(setting, database.DEFAULT_SETTINGS[setting])
        rows.append({
            "key": key,
            "setting": setting,
            "label": label,
            "format": template,
            "contoh": database.render_nomor(template, seq=1),
        })
    return render_template("admin/nomor_format.html", rows=rows)


@bp.route("/template-invoice", methods=["GET", "POST"])
@helpers.feature_required("template_invoice")
def invoice_template():
    if request.method == "POST":
        pilihan = request.form.get("template_invoice", "klasik")
        if pilihan not in TEMPLATE_INVOICE:
            flash("Template invoice tidak valid.", "danger")
            return redirect(url_for("admin.invoice_template"))
        berkas = request.files.get("desain")
        if berkas and berkas.filename:
            ext = berkas.filename.rsplit(".", 1)[-1].lower() if "." in berkas.filename else ""
            if ext not in DESAIN_EXT:
                flash("Berkas desain harus berupa gambar (PNG/JPG/WEBP).", "danger")
                return redirect(url_for("admin.invoice_template"))
            nama = helpers.save_upload(berkas, "invoice")
            if not nama:
                return redirect(url_for("admin.invoice_template"))
            lama = database.get_setting("template_invoice_file", "")
            if lama:
                path = os.path.join(current_app.config["UPLOAD_FOLDER"], lama)
                if os.path.isfile(path):
                    os.remove(path)
            database.set_setting("template_invoice_file", nama)
            pilihan = "desain"
        elif pilihan == "desain" and not database.get_setting("template_invoice_file", ""):
            flash("Unggah berkas desain terlebih dahulu.", "danger")
            return redirect(url_for("admin.invoice_template"))
        database.set_setting("template_invoice", pilihan)
        database.set_setting("invoice_logo_tampil", "1" if request.form.get("invoice_logo_tampil") else "0")
        ukuran = request.form.get("invoice_logo_ukuran", "sedang")
        if ukuran not in {k for k, _l, _p in database.INVOICE_LOGO_UKURAN}:
            ukuran = "sedang"
        database.set_setting("invoice_logo_ukuran", ukuran)
        flash("Template invoice diperbarui.", "success")
        return redirect(url_for("admin.invoice_template"))
    return render_template("admin/invoice_template.html",
                           aktif=database.get_setting("template_invoice", "klasik"),
                           templates=TEMPLATE_INVOICE,
                           desain=database.get_setting("template_invoice_file", ""),
                           logo=database.get_setting("logo", ""),
                           logo_tampil=database.get_setting("invoice_logo_tampil", "1") == "1",
                           logo_ukuran=database.get_setting("invoice_logo_ukuran", "sedang"))


@bp.route("/template-invoice/hapus-desain", methods=["POST"])
@helpers.feature_required("template_invoice")
def invoice_template_delete_design():
    lama = database.get_setting("template_invoice_file", "")
    if lama:
        path = os.path.join(current_app.config["UPLOAD_FOLDER"], lama)
        if os.path.isfile(path):
            os.remove(path)
        database.set_setting("template_invoice_file", "")
    if database.get_setting("template_invoice", "klasik") == "desain":
        database.set_setting("template_invoice", "klasik")
    flash("Berkas desain invoice dihapus.", "info")
    return redirect(url_for("admin.invoice_template"))


# ---------------------------------------------------- kolom katalog --------
@bp.route("/katalog", methods=["GET", "POST"])
@helpers.feature_required("katalog_seksi")
def katalog():
    """Aktifkan / nonaktifkan kolom katalog yang tampil di beranda."""
    if request.method == "POST":
        for key, _label, _ket in database.KATALOG_SEKSI:
            database.set_setting(key, "1" if request.form.get(key) else "0")
        flash("Kolom katalog beranda diperbarui.", "success")
        return redirect(url_for("admin.katalog"))
    return render_template("admin/katalog.html", seksi=database.KATALOG_SEKSI,
                           aktif=database.katalog_aktif())


@bp.route("/rekening", methods=["GET", "POST"])
@helpers.feature_required("rekening")
def rekening():
    """Atur rekening bank yang dicetak di dalam faktur / invoice."""
    if request.method == "POST":
        database.set_setting("rekening_bank", request.form.get("rekening_bank", "").strip())
        database.set_setting("tampil_rekening", "1" if request.form.get("tampil_rekening") else "0")
        flash("Data rekening bank disimpan.", "success")
        return redirect(url_for("admin.rekening"))
    return render_template(
        "admin/rekening.html",
        rekening=database.get_setting("rekening_bank", ""),
        tampil=database.get_setting("tampil_rekening", "1") == "1")


# -------------------------------------------------------------- reset -----
@bp.route("/reset", methods=["GET", "POST"])
@helpers.feature_required("reset")
def reset():
    """Kembalikan pengaturan aplikasi ke nilai bawaan."""
    if request.method == "POST":
        aksi = request.form.get("aksi", "")
        if aksi not in database.RESET_AKSI:
            flash("Pilihan reset tidak dikenal.", "danger")
        else:
            database.create_backup("sebelum-reset")
            jumlah = database.RESET_AKSI[aksi]()
            label = dict((k, v) for k, v, _ in database.RESET_BAGIAN)[aksi]
            flash("%s dikembalikan ke pengaturan default (%d data)." % (label, jumlah), "success")
        return redirect(url_for("admin.reset"))
    return render_template("admin/reset.html", bagian=database.RESET_BAGIAN)


# --------------------------------------------------------------- backup ----
@bp.route("/backup", methods=["GET", "POST"])
@helpers.feature_required("backup")
def backup():
    if request.method == "POST":
        aksi = request.form.get("aksi", "buat")
        if aksi == "jadwal":
            jadwal = request.form.get("backup_jadwal", "off")
            if jadwal != "off" and jadwal not in database.BACKUP_JADWAL:
                flash("Jadwal backup tidak valid.", "danger")
            else:
                database.set_setting("backup_jadwal", jadwal)
                flash("Jadwal backup disimpan.", "success")
        elif aksi == "buat":
            nama = database.create_backup("manual")
            flash("Backup dibuat: %s" % nama, "success")
        return redirect(url_for("admin.backup"))
    return render_template(
        "admin/backup.html",
        rows=database.list_backups(),
        jadwal=database.get_setting("backup_jadwal", "off"),
        jadwal_pilihan=database.BACKUP_JADWAL,
        terakhir=database.get_setting("backup_terakhir", ""))


@bp.route("/backup/<string:nama>/unduh")
@helpers.feature_required("backup")
def backup_download(nama):
    path = database.backup_path(nama)
    if path is None:
        abort(404)
    return send_file(path, as_attachment=True, download_name=nama)


@bp.route("/backup/<string:nama>/hapus", methods=["POST"])
@helpers.feature_required("backup")
def backup_delete(nama):
    if database.delete_backup(nama):
        flash("Backup %s dihapus." % nama, "info")
    else:
        flash("Berkas backup tidak ditemukan.", "warning")
    return redirect(url_for("admin.backup"))


@bp.route("/notifikasi")
def notifications():
    user = helpers.current_user()
    rows = database.query(
        "SELECT * FROM notifications WHERE user_id = ? OR role = ? ORDER BY id DESC LIMIT 100",
        (user["id"], user["role"]))
    database.execute("UPDATE notifications SET dibaca = 1 WHERE user_id = ? OR role = ?",
                     (user["id"], user["role"]))
    return render_template("staff/notifications.html", rows=rows)
