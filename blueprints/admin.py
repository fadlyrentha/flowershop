"""Halaman administrator: CMS beranda, pengaturan situs, staff, hak akses."""
import json
import os
import tempfile
import threading
import time
import uuid
from datetime import datetime

from flask import (Blueprint, abort, current_app, flash, redirect, render_template,
                   request, send_file, session, url_for)
from werkzeug.security import generate_password_hash

import db as database
import helpers
import version
import updater

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
    "pengiriman_metode": "Metode Pengiriman",
    "jam_operasional": "Jam Operasional & Same Day",
    "menu_publik": "Menu Halaman Depan",
    "update": "Pembaruan Aplikasi",
    "sosial": "Kontroler Sosial Media",
}


@bp.before_request
@helpers.role_required("administrator", "staff_kantor")
def guard():
    pass


STAFF_ONLY = ("accounts", "account_delete", "permissions", "settings", "dashboard",
              "nomor_format", "invoice_template", "invoice_template_delete_design",
              "backup", "backup_download", "backup_delete", "backup_upload", "backup_restore",
              "katalog", "rekening", "reset",
              "pengiriman", "jam_operasional", "menu_publik",
              "update", "update_cek", "update_online", "update_upload",
              "sosial", "sosial_akun_simpan", "sosial_akun_hapus", "sosial_sinkron",
              "sosial_sinkron_semua", "sosial_pengaturan", "sosial_item_simpan",
              "sosial_item_hapus", "sosial_item_saklar")


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
        return redirect(url_for("admin.cms"))

    return render_template(
        "admin/cms.html",
        slides=database.query("SELECT * FROM hero_slides ORDER BY urutan, id"),
        testimonials=database.query("SELECT * FROM testimonials ORDER BY urutan, id"),
        products=database.query("SELECT * FROM products ORDER BY nama"))


@bp.route("/cms/<string:jenis>/<int:item_id>/hapus", methods=["POST"])
def cms_delete(jenis, item_id):
    table = {"hero": "hero_slides", "testimoni": "testimonials"}.get(jenis)
    if not table:
        abort(404)
    database.execute("DELETE FROM %s WHERE id = ?" % table, (item_id,))
    flash("Item beranda dihapus.", "info")
    return redirect(url_for("admin.cms"))


# ------------------------------------------------- kontroler sosial media ----
def _sosial_siap():
    """Jalankan sinkronisasi terjadwal di latar belakang bila sudah waktunya.

    Penarikan konten memanggil jaringan, jadi tidak boleh menahan permintaan
    halaman: pekerjaannya dilempar ke thread daemon dan halaman langsung dibuka
    dengan data yang ada.
    """
    import social_sync
    if not database.social_sinkron_jatuh_tempo():
        return
    threading.Thread(
        target=social_sync.sinkron_terjadwal,
        args=(current_app.config["DATABASE"], current_app.config["UPLOAD_FOLDER"]),
        daemon=True, name="sosial-sync-panel").start()


@bp.route("/sosial")
@helpers.feature_required("sosial")
def sosial():
    """Panel kontroler: akun sosial media beserta feed dan story-nya."""
    _sosial_siap()
    account_id = request.args.get("akun", type=int)
    akun = database.social_account(account_id) if account_id else None
    jenis = request.args.get("jenis", "feed")
    if jenis not in database.SOCIAL_JENIS_LABEL:
        jenis = "feed"
    items = database.social_items(
        account_id=akun["id"] if akun else None, jenis=jenis) if akun else []
    return render_template(
        "admin/sosial.html",
        ringkas=database.social_ringkas(),
        akun=akun,
        akun_id=akun["id"] if akun else None,
        jenis=jenis,
        items=items,
        settings=database.all_settings(),
        platform_label=database.SOCIAL_PLATFORM_LABEL,
        platform_ikon=database.SOCIAL_PLATFORM_IKON,
        platform_warna=database.SOCIAL_PLATFORM_WARNA,
        PLATFORM=database.SOCIAL_PLATFORM,
        SUMBER=database.SOCIAL_SUMBER,
        JENIS=database.SOCIAL_JENIS,
        INTERVAL=database.SOCIAL_INTERVAL,
    )


@bp.route("/sosial/akun", methods=["POST"])
@helpers.feature_required("sosial")
def sosial_akun_simpan():
    """Tambah atau ubah satu akun sosial media."""
    account_id = request.form.get("id")
    platform = request.form.get("platform", "instagram")
    if platform not in database.SOCIAL_PLATFORM_LABEL:
        abort(400)
    sumber = request.form.get("sumber", "manual")
    if sumber not in {k for k, _label, _ket in database.SOCIAL_SUMBER}:
        abort(400)
    username = request.form.get("username", "").strip().lstrip("@")
    nama = request.form.get("nama", "").strip()
    url = request.form.get("url", "").strip()
    feed_url = request.form.get("feed_url", "").strip()
    story_url = request.form.get("story_url", "").strip()
    token = request.form.get("token", "").strip()
    for tautan in (url, feed_url, story_url):
        if tautan and not tautan.startswith(("http://", "https://")):
            flash("Tautan harus dimulai dengan http:// atau https://", "danger")
            return redirect(url_for("admin.sosial"))
    lama = database.social_account(account_id) if account_id else None
    if account_id and lama is None:
        abort(404)
    # Field token selalu kosong di formulir demi keamanan, jadi kosong berarti
    # "jangan ubah", bukan "hapus".
    if not token and lama is not None:
        token = lama["token"] or ""
    if sumber != "manual" and not (feed_url or story_url or token):
        flash("Mode %s butuh URL feed atau access token." % sumber.upper(), "danger")
        return redirect(url_for("admin.sosial"))
    if not url and username:
        url = "https://" + database.SOCIAL_PLATFORM_AKHIRAN.get(platform, "") + username

    def _batas(nama_field, bawaan, minimum, maksimum):
        try:
            nilai = int(request.form.get(nama_field) or bawaan)
        except (TypeError, ValueError):
            nilai = bawaan
        return max(minimum, min(maksimum, nilai))

    data = (
        platform, nama or username or database.SOCIAL_PLATFORM_LABEL[platform],
        username, url, sumber, feed_url, story_url, token,
        1 if request.form.get("sinkron_otomatis") else 0,
        _batas("jumlah_feed", 12, 1, 50), _batas("jumlah_story", 10, 1, 50),
        1 if request.form.get("aktif") else 0,
        _batas("urutan", 0, -999, 999),
    )
    avatar = helpers.save_image(request.files.get("avatar"), "social")
    if account_id:
        if avatar:
            if lama["avatar"]:
                helpers.delete_upload(lama["avatar"])
            database.execute(
                "UPDATE social_accounts SET platform=?, nama=?, username=?, url=?, sumber=?,"
                " feed_url=?, story_url=?, token=?, sinkron_otomatis=?, jumlah_feed=?,"
                " jumlah_story=?, aktif=?, urutan=?, avatar=? WHERE id=?", data + (avatar, account_id))
        else:
            database.execute(
                "UPDATE social_accounts SET platform=?, nama=?, username=?, url=?, sumber=?,"
                " feed_url=?, story_url=?, token=?, sinkron_otomatis=?, jumlah_feed=?,"
                " jumlah_story=?, aktif=?, urutan=? WHERE id=?", data + (account_id,))
        flash("Akun sosial media diperbarui.", "success")
    else:
        database.execute(
            "INSERT INTO social_accounts (platform, nama, username, url, sumber, feed_url,"
            " story_url, token, sinkron_otomatis, jumlah_feed, jumlah_story, aktif, urutan,"
            " avatar, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            data + (avatar, database.now()))
        flash("Akun sosial media ditambahkan.", "success")
    return redirect(url_for("admin.sosial"))


@bp.route("/sosial/akun/<int:account_id>/hapus", methods=["POST"])
@helpers.feature_required("sosial")
def sosial_akun_hapus(account_id):
    """Hapus akun beserta seluruh feed & story serta gambar lokalnya."""
    akun = database.social_account(account_id)
    if akun is None:
        abort(404)
    for item in database.social_items(account_id=account_id):
        if item["gambar"] and not item["gambar"].startswith(("http://", "https://")):
            helpers.delete_upload(item["gambar"])
    if akun["avatar"]:
        helpers.delete_upload(akun["avatar"])
    database.execute("DELETE FROM social_items WHERE account_id = ?", (account_id,))
    database.execute("DELETE FROM social_accounts WHERE id = ?", (account_id,))
    flash("Akun %s beserta kontennya dihapus." % (akun["nama"] or akun["username"]), "info")
    return redirect(url_for("admin.sosial"))


@bp.route("/sosial/akun/<int:account_id>/sinkron", methods=["POST"])
@helpers.feature_required("sosial")
def sosial_sinkron(account_id):
    """Tarik feed dan story terbaru dari satu akun."""
    import social_sync
    if database.social_account(account_id) is None:
        abort(404)
    ringkas = social_sync.sinkron_akun(account_id, current_app.config["DATABASE"],
                                       current_app.config["UPLOAD_FOLDER"])
    pesan = " ".join(ringkas["pesan"]) or "Tidak ada yang ditarik."
    flash(pesan, "success" if ringkas["berhasil"] else "warning")
    return redirect(url_for("admin.sosial", akun=account_id))


@bp.route("/sosial/sinkron-semua", methods=["POST"])
@helpers.feature_required("sosial")
def sosial_sinkron_semua():
    """Tarik feed dan story dari seluruh akun aktif."""
    import social_sync
    ringkas = social_sync.sinkron_semua(current_app.config["DATABASE"],
                                        current_app.config["UPLOAD_FOLDER"])
    pesan = " ".join(ringkas["pesan"]) or "Tidak ada akun aktif yang perlu ditarik."
    flash("%d akun diperiksa, %d konten diperbarui. %s"
          % (ringkas["akun"], ringkas["item"], pesan),
          "success" if ringkas["berhasil"] else "warning")
    return redirect(url_for("admin.sosial"))


@bp.route("/sosial/pengaturan", methods=["POST"])
@helpers.feature_required("sosial")
def sosial_pengaturan():
    """Atur sinkronisasi otomatis dan jumlah konten yang tampil di beranda."""
    database.set_setting("sosial_aktif", "1" if request.form.get("sosial_aktif") else "0")
    try:
        interval = int(request.form.get("sosial_interval") or 0)
    except (TypeError, ValueError):
        interval = 0
    if interval not in dict(database.SOCIAL_INTERVAL):
        interval = 0
    database.set_setting("sosial_interval", str(interval))
    for key, bawaan in (("sosial_feed_tampil", 8), ("sosial_story_tampil", 8)):
        try:
            nilai = int(request.form.get(key) or bawaan)
        except (TypeError, ValueError):
            nilai = bawaan
        database.set_setting(key, str(max(1, min(24, nilai))))
    flash("Pengaturan kontroler sosial media disimpan.", "success")
    return redirect(url_for("admin.sosial"))


@bp.route("/sosial/item", methods=["POST"])
@helpers.feature_required("sosial")
def sosial_item_simpan():
    """Tambah atau ubah satu konten feed/story secara manual."""
    item_id = request.form.get("id")
    account_id = request.form.get("account_id", type=int)
    if database.social_account(account_id) is None:
        abort(404)
    jenis = request.form.get("jenis", "feed")
    if jenis not in database.SOCIAL_JENIS_LABEL:
        abort(400)
    link = request.form.get("link", "#").strip() or "#"
    if link != "#" and not link.startswith(("http://", "https://")):
        flash("Tautan konten harus dimulai dengan http:// atau https://", "danger")
        return redirect(url_for("admin.sosial", akun=account_id, jenis=jenis))
    data = (
        jenis,
        request.form.get("judul", "").strip(),
        request.form.get("caption", "").strip(),
        link,
        request.form.get("waktu", "").strip(),
        int(request.form.get("urutan") or 0),
        1 if request.form.get("aktif") else 0,
    )
    gambar = helpers.save_image(request.files.get("gambar"), "social")
    if item_id:
        lama = database.query("SELECT * FROM social_items WHERE id = ?", (item_id,), one=True)
        if lama is None:
            abort(404)
        if gambar:
            if lama["gambar"] and not lama["gambar"].startswith(("http://", "https://")):
                helpers.delete_upload(lama["gambar"])
            database.execute(
                "UPDATE social_items SET jenis=?, judul=?, caption=?, link=?, waktu=?, urutan=?,"
                " aktif=?, gambar=? WHERE id=?", data + (gambar, item_id))
        else:
            database.execute(
                "UPDATE social_items SET jenis=?, judul=?, caption=?, link=?, waktu=?, urutan=?,"
                " aktif=? WHERE id=?", data + (item_id,))
        flash("Konten %s diperbarui." % database.SOCIAL_JENIS_LABEL[jenis].lower(), "success")
    else:
        jenis_konten, judul, caption, link_konten, waktu, urutan, aktif = data
        database.execute(
            "INSERT INTO social_items (account_id, jenis, sumber_id, judul, caption, gambar,"
            " link, waktu, urutan, aktif, created_at)"
            " VALUES (?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?)",
            (account_id, jenis_konten, judul, caption, gambar, link_konten, waktu, urutan,
             aktif, database.now()))
        flash("Konten %s ditambahkan." % database.SOCIAL_JENIS_LABEL[jenis].lower(), "success")
    return redirect(url_for("admin.sosial", akun=account_id, jenis=jenis))


@bp.route("/sosial/item/<int:item_id>/hapus", methods=["POST"])
@helpers.feature_required("sosial")
def sosial_item_hapus(item_id):
    item = database.query("SELECT * FROM social_items WHERE id = ?", (item_id,), one=True)
    if item is None:
        abort(404)
    if item["gambar"] and not item["gambar"].startswith(("http://", "https://")):
        helpers.delete_upload(item["gambar"])
    database.execute("DELETE FROM social_items WHERE id = ?", (item_id,))
    flash("Konten sosial media dihapus.", "info")
    return redirect(url_for("admin.sosial", akun=item["account_id"], jenis=item["jenis"]))


@bp.route("/sosial/item/<int:item_id>/saklar", methods=["POST"])
@helpers.feature_required("sosial")
def sosial_item_saklar(item_id):
    """Sembunyikan atau tampilkan satu konten di beranda."""
    item = database.query("SELECT * FROM social_items WHERE id = ?", (item_id,), one=True)
    if item is None:
        abort(404)
    database.execute("UPDATE social_items SET aktif = ? WHERE id = ?",
                     (0 if item["aktif"] else 1, item_id))
    return redirect(url_for("admin.sosial", akun=item["account_id"], jenis=item["jenis"]))


# ------------------------------------------------------------ pengaturan ----
@bp.route("/pengaturan", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        keys = ["nama_toko", "tagline", "deskripsi", "alamat", "telepon", "email", "instagram",
                "tiktok", "whatsapp", "warna_primer", "warna_sekunder", "footer_text"]
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


# --------------------------------------------------- metode pengiriman -----
@bp.route("/pengiriman", methods=["GET", "POST"])
@helpers.feature_required("pengiriman_metode")
def pengiriman():
    """Aktifkan / nonaktifkan metode penyerahan barang di seluruh panel."""
    if request.method == "POST":
        dipilih = [label for key, label, _ket in database.PENGIRIMAN_METODE
                   if request.form.get(key)]
        if not dipilih:
            flash("Minimal satu metode pengiriman harus tetap aktif.", "danger")
            return redirect(url_for("admin.pengiriman"))
        for key, _label, _ket in database.PENGIRIMAN_METODE:
            database.set_setting(key, "1" if request.form.get(key) else "0")
        flash("Metode pengiriman diperbarui: %s." % ", ".join(dipilih), "success")
        return redirect(url_for("admin.pengiriman"))
    return render_template("admin/pengiriman.html", metode=database.PENGIRIMAN_METODE,
                           aktif=database.pengiriman_aktif())


# ---------------------------------------------------- jam operasional ------
@bp.route("/jam-operasional", methods=["GET", "POST"])
@helpers.feature_required("jam_operasional")
def jam_operasional():
    """Panel jam layanan harian dan pengaturan same day delivery."""
    if request.method == "POST":
        jadwal = {}
        for key, label in database.HARI:
            if "jam_buka_" + key not in request.form and "jam_tutup_" + key not in request.form:
                continue
            buka = request.form.get("jam_buka_" + key, "").strip()
            tutup = request.form.get("jam_tutup_" + key, "").strip()
            if not _jam_valid(buka) or not _jam_valid(tutup):
                flash("Format jam hari %s tidak valid (contoh 07:00)." % label, "danger")
                return redirect(url_for("admin.jam_operasional"))
            jadwal[key] = (buka, tutup)
        batas = request.form.get("sameday_batas_jam", "14:00").strip()
        if not _jam_valid(batas):
            flash("Batas jam same day delivery tidak valid.", "danger")
            return redirect(url_for("admin.jam_operasional"))
        for key, (buka, tutup) in jadwal.items():
            database.set_setting("jam_buka_" + key, buka)
            database.set_setting("jam_tutup_" + key, tutup)
        database.set_setting("sameday_aktif", "1" if request.form.get("sameday_aktif") else "0")
        database.set_setting("sameday_batas_jam", batas)
        hari = [key for key, _label in database.HARI
                if key in request.form.getlist("sameday_hari")]
        database.set_setting("sameday_hari", json.dumps(hari))
        database.set_setting("sameday_info", request.form.get("sameday_info", "").strip())
        flash("Jam operasional dan same day delivery disimpan.", "success")
        return redirect(url_for("admin.jam_operasional"))
    return render_template(
        "admin/jam_operasional.html",
        hari=database.HARI,
        jam=database.jam_dari(database.all_settings()),
        sameday_aktif=database.get_setting("sameday_aktif", "1") == "1",
        sameday_batas=database.get_setting("sameday_batas_jam", "14:00"),
        sameday_hari=database.sameday_hari(),
        sameday_info=database.get_setting("sameday_info", ""))


def _jam_valid(nilai):
    try:
        datetime.strptime(nilai, "%H:%M")
    except ValueError:
        return False
    return True


# ------------------------------------------------------- menu publik ------
@bp.route("/menu-publik", methods=["GET", "POST"])
@helpers.feature_required("menu_publik")
def menu_publik():
    """Tampilkan / sembunyikan menu di halaman depan website."""
    if request.method == "POST":
        for key, _label, _ket in database.MENU_PUBLIK:
            database.set_setting(key, "1" if request.form.get(key) else "0")
        flash("Menu halaman depan diperbarui.", "success")
        return redirect(url_for("admin.menu_publik"))
    return render_template("admin/menu_publik.html", daftar_menu=database.MENU_PUBLIK,
                           aktif=database.menu_publik())


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
        terakhir=database.get_setting("backup_terakhir", ""),
        restore_terakhir=database.get_setting("restore_terakhir", ""))


def _unggah_backup_sementara():
    """Simpan berkas backup yang diunggah ke folder sementara. Mengembalikan (path, pesan)."""
    berkas = request.files.get("berkas")
    if not berkas or not berkas.filename:
        return None, "Pilih berkas backup (.db) yang ingin dipulihkan."
    if not berkas.filename.lower().endswith(".db"):
        return None, "Berkas harus berekstensi .db hasil fitur backup aplikasi ini."
    # Disimpan di folder backup, bukan folder unggahan: isi folder unggahan
    # disajikan lewat URL, sedangkan berkas database tidak boleh bisa diunduh
    # siapa pun. Nama acak dipakai agar tidak menimpa berkas lain.
    # Akhiran sengaja bukan .db agar berkas sementara tidak muncul di riwayat.
    folder = database.backup_dir()
    # Sisa unggahan yang gagal di tengah jalan (misalnya koneksi putus) dibuang
    # agar folder backup tidak menumpuk berkas yatim. Hanya berkas berumur > 1
    # jam yang dihapus supaya unggahan lain yang sedang berjalan tidak tersentuh.
    batas = time.time() - 3600
    for lama in os.listdir(folder):
        if not lama.startswith("unggahan-"):
            continue
        jalur_lama = os.path.join(folder, lama)
        try:
            if os.path.getmtime(jalur_lama) < batas:
                os.remove(jalur_lama)
        except OSError:
            pass
    path = os.path.join(folder, "unggahan-" + uuid.uuid4().hex + ".db.unggah")
    berkas.save(path)
    return path, ""


@bp.route("/backup/unggah", methods=["POST"])
@helpers.feature_required("backup")
def backup_upload():
    """Pulihkan database dari berkas backup .db yang diunggah."""
    path, pesan = _unggah_backup_sementara()
    if path is None:
        flash(pesan, "danger")
        return redirect(url_for("admin.backup"))
    try:
        berhasil, pesan = database.pulihkan_backup(path)
    finally:
        if os.path.isfile(path):
            os.remove(path)
    # Sesi milik akun yang tidak ada lagi di database pulihan harus dibuang.
    if berhasil and helpers.current_user() is None:
        session.clear()
        return redirect(url_for("auth.login"))
    flash(pesan, "success" if berhasil else "danger")
    return redirect(url_for("admin.backup"))


@bp.route("/backup/<string:nama>/pulihkan", methods=["POST"])
@helpers.feature_required("backup")
def backup_restore(nama):
    """Pulihkan database dari berkas backup yang sudah ada di server."""
    path = database.backup_path(nama)
    if path is None:
        flash("Berkas backup tidak ditemukan.", "warning")
        return redirect(url_for("admin.backup"))
    berhasil, pesan = database.pulihkan_backup(path)
    if berhasil and helpers.current_user() is None:
        session.clear()
        return redirect(url_for("auth.login"))
    flash(pesan, "success" if berhasil else "danger")
    return redirect(url_for("admin.backup"))


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


# --------------------------------------------------------------- update ----
def _catat_hasil_update(ringkas):
    """Simpan jejak waktu pembaruan terakhir."""
    if not ringkas.get("berhasil"):
        return
    # Migrasi skema baru berjalan sendiri saat proses dimulai ulang
    # (create_app memanggil init_db), jadi tidak perlu dijalankan di sini.
    database.set_setting("update_terakhir", database.now())


@bp.route("/update")
@helpers.feature_required("update")
def update():
    return render_template(
        "admin/update.html",
        sekarang=updater.versi_sekarang(),
        repo=version.REPO,
        cabang=version.CABANG,
        repo_url="https://github.com/%s" % version.REPO,
        versi_github=database.get_setting("update_versi_github", ""),
        cek_terakhir=database.get_setting("update_cek_terakhir", ""),
        update_terakhir=database.get_setting("update_terakhir", ""),
        bisa_tulis=updater.bisa_menulis(),
        perintah_server=updater.perintah_server(),
        app_dir=updater.ROOT)


@bp.route("/update/cek", methods=["POST"])
@helpers.feature_required("update")
def update_cek():
    """Bandingkan versi terpasang dengan versi terbaru di GitHub."""
    hasil = updater.cek_github()
    database.set_setting("update_cek_terakhir", database.now())
    if hasil["terbaru"]:
        database.set_setting("update_versi_github", hasil["terbaru"])
        if hasil["ada_baru"]:
            flash(hasil["pesan"], "warning")
        else:
            flash(hasil["pesan"], "success")
    else:
        flash(hasil["pesan"] or "Versi GitHub tidak dapat dibaca.", "danger")
    return redirect(url_for("admin.update"))


@bp.route("/update/online", methods=["POST"])
@helpers.feature_required("update")
def update_online():
    """Unduh rilis terbaru dari GitHub lalu pasang di atas kode saat ini."""
    if not updater.bisa_menulis():
        flash("Folder aplikasi tidak dapat ditulis proses web. Di server, "
              "jalankan: %s" % updater.perintah_server(), "danger")
        return redirect(url_for("admin.update"))
    ringkas = updater.pasang_online()
    _catat_hasil_update(ringkas)
    if ringkas["berhasil"]:
        flash("Pembaruan online selesai: %s Nyalakan ulang aplikasi/layanan agar "
              "kode baru dipakai sepenuhnya." % ringkas["pesan"], "success")
    else:
        flash("Pembaruan online gagal: %s" % ringkas["pesan"], "danger")
    return redirect(url_for("admin.update"))


@bp.route("/update/unggah", methods=["POST"])
@helpers.feature_required("update")
def update_upload():
    """Pasang pembaruan dari berkas .zip yang diunggah administrator."""
    if not updater.bisa_menulis():
        flash("Folder aplikasi tidak dapat ditulis proses web. Di server, "
              "jalankan: %s" % updater.perintah_server(), "danger")
        return redirect(url_for("admin.update"))
    berkas = request.files.get("berkas")
    if not berkas or not berkas.filename:
        flash("Pilih berkas pembaruan (.zip) terlebih dahulu.", "danger")
        return redirect(url_for("admin.update"))
    if not berkas.filename.lower().endswith(".zip"):
        flash("Berkas pembaruan harus berupa arsip .zip berisi folder aplikasi.", "danger")
        return redirect(url_for("admin.update"))
    # Arsip disimpan di folder sementara di luar folder aplikasi.
    fd, path = tempfile.mkstemp(prefix="rasty-update-", suffix=".zip")
    os.close(fd)
    try:
        berkas.save(path)
        ringkas = updater.pasang_dari_zip(path)
    finally:
        if os.path.isfile(path):
            os.remove(path)
    _catat_hasil_update(ringkas)
    if ringkas["berhasil"]:
        flash("Pembaruan dari berkas selesai: %s Nyalakan ulang aplikasi/layanan agar "
              "kode baru dipakai sepenuhnya." % ringkas["pesan"], "success")
    else:
        flash("Pembaruan dari berkas gagal: %s" % ringkas["pesan"], "danger")
    return redirect(url_for("admin.update"))


@bp.route("/notifikasi")
def notifications():
    user = helpers.current_user()
    rows = database.query(
        "SELECT * FROM notifications WHERE user_id = ? OR role = ? ORDER BY id DESC LIMIT 100",
        (user["id"], user["role"]))
    database.execute("UPDATE notifications SET dibaca = 1 WHERE user_id = ? OR role = ?",
                     (user["id"], user["role"]))
    return render_template("staff/notifications.html", rows=rows)
