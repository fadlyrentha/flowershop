"""Uji fitur pembaruan aplikasi: versi, perlindungan data, dan pemasangan.

Dijalankan tanpa jaringan: pembaruan "online" tidak diuji di sini. Yang diuji
adalah bagian yang paling berisiko menghapus data — aturan berkas yang
dilindungi dan penyalinan dari folder/arsip.

    python update_test.py
"""
import os
import shutil
import sys
import tempfile
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import updater  # noqa: E402
import version  # noqa: E402

gagal = []


def cek(syarat, pesan):
    if not syarat:
        gagal.append(pesan)


# ------------------------------------------------------------- versi --------
cek(updater.versi_sekarang() == version.VERSION,
    "versi_sekarang() = %r, seharusnya %r" % (updater.versi_sekarang(), version.VERSION))
cek(updater.versi_tuple("1.2.3") == (1, 2, 3), "versi_tuple tidak memecah versi")
cek(updater.lebih_baru("1.10.0", "1.9.9"), "1.10.0 seharusnya lebih baru dari 1.9.9")
cek(not updater.lebih_baru("1.0.0", "1.0.0"), "versi sama bukan lebih baru")
cek(not updater.lebih_baru("0.9.9", "1.0.0"), "versi lebih kecil bukan lebih baru")

# --------------------------------------------------- perlindungan berkas ----
HARUS_DILINDUNGI = [
    "rasty_florist.db",
    "data/rasty_florist.db",
    "rasty_florist.db-wal",
    "rasty_florist.db-shm",
    "rasty.conf",
    "rasty.env",
    ".env",
    "static/uploads/foto.jpg",
    "static/uploads/qc/bukti.png",
    "backups/rasty-manual-20260101-000000.db",
    ".venv/bin/python",
    ".git/config",
    "__pycache__/db.cpython-311.pyc",
    "modul.pyc",
    "logs/app.log",
]
HARUS_DITULIS = [
    "app.py",
    "db.py",
    "updater.py",
    "version.py",
    "blueprints/admin.py",
    "templates/admin/update.html",
    "static/css/tema.css",
    "installer/update_ubuntu.sh",
    "requirements.txt",
    "README.md",
]
for rel in HARUS_DILINDUNGI:
    cek(updater.dilindungi(rel), "berkas data '%s' seharusnya dilindungi" % rel)
for rel in HARUS_DITULIS:
    cek(not updater.dilindungi(rel), "berkas kode '%s' seharusnya boleh ditulis" % rel)

# Perlakuan sama untuk pemisah jalur Windows.
cek(updater.dilindungi("static\\uploads\\foto.jpg"),
    "jalur bergaya Windows tidak dikenali sebagai folder unggahan")
cek(not updater.dilindungi(".\\app.py"), "jalur './app.py' seharusnya boleh ditulis")

# ------------------------------------------------- pemasangan dari folder ---
akar = tempfile.mkdtemp(prefix="rasty-uji-")
sumber = os.path.join(akar, "sumber")
tujuan = os.path.join(akar, "tujuan")
try:
    # Folder sumber meniru paket aplikasi.
    os.makedirs(os.path.join(sumber, "blueprints"))
    os.makedirs(os.path.join(sumber, "static", "uploads"))
    os.makedirs(os.path.join(sumber, "backups"))
    os.makedirs(os.path.join(sumber, ".git"))
    with open(os.path.join(sumber, "app.py"), "w", encoding="utf-8") as f:
        f.write("# app versi baru\n")
    with open(os.path.join(sumber, "blueprints", "admin.py"), "w", encoding="utf-8") as f:
        f.write("# admin versi baru\n")
    with open(os.path.join(sumber, "rasty_florist.db"), "w", encoding="utf-8") as f:
        f.write("database-dari-sumber")
    with open(os.path.join(sumber, "rasty.conf"), "w", encoding="utf-8") as f:
        f.write("konfigurasi-dari-sumber")
    with open(os.path.join(sumber, "static", "uploads", "foto.jpg"), "w", encoding="utf-8") as f:
        f.write("foto-dari-sumber")
    with open(os.path.join(sumber, ".git", "config"), "w", encoding="utf-8") as f:
        f.write("git-dari-sumber")

    # Folder tujuan meniru pemasangan yang sedang berjalan.
    os.makedirs(os.path.join(tujuan, "blueprints"))
    os.makedirs(os.path.join(tujuan, "static", "uploads"))
    with open(os.path.join(tujuan, "app.py"), "w", encoding="utf-8") as f:
        f.write("# app versi lama\n")
    with open(os.path.join(tujuan, "rasty_florist.db"), "w", encoding="utf-8") as f:
        f.write("database-toko-asli")
    with open(os.path.join(tujuan, "rasty.conf"), "w", encoding="utf-8") as f:
        f.write("konfigurasi-toko-asli")
    with open(os.path.join(tujuan, "static", "uploads", "foto.jpg"), "w", encoding="utf-8") as f:
        f.write("foto-toko-asli")
    with open(os.path.join(tujuan, "berkas_lama.py"), "w", encoding="utf-8") as f:
        f.write("# berkas yang tidak ada di sumber\n")

    ringkas = updater.pasang_dari_folder(sumber, app_dir=tujuan)
    cek(ringkas["berhasil"], "pemasangan dari folder gagal: %s" % ringkas["pesan"])

    def baca(rel):
        with open(os.path.join(tujuan, rel), encoding="utf-8") as f:
            return f.read()

    cek(baca("app.py") == "# app versi baru\n", "app.py tidak diperbarui")
    cek(baca("blueprints/admin.py") == "# admin versi baru\n", "berkas di subfolder tidak diperbarui")
    cek(baca("rasty_florist.db") == "database-toko-asli", "database toko tertimpa!")
    cek(baca("rasty.conf") == "konfigurasi-toko-asli", "konfigurasi toko tertimpa!")
    cek(baca(os.path.join("static", "uploads", "foto.jpg")) == "foto-toko-asli",
        "berkas unggahan tertimpa!")
    cek(not os.path.exists(os.path.join(tujuan, ".git", "config")),
        "folder .git dari sumber ikut tersalin")
    cek(os.path.exists(os.path.join(tujuan, "berkas_lama.py")),
        "berkas lama yang tidak ada di sumber ikut terhapus")

    # dry-run tidak boleh menulis apa pun.
    with open(os.path.join(tujuan, "app.py"), "w", encoding="utf-8") as f:
        f.write("# app versi lama\n")
    ringkas = updater.pasang_dari_folder(sumber, app_dir=tujuan, dry_run=True)
    cek(ringkas["berhasil"] and ringkas["ditulis"] > 0,
        "dry-run tidak melaporkan berkas: %s" % ringkas["pesan"])
    cek(baca("app.py") == "# app versi lama\n", "dry-run menulis berkas!")

    # -------------------------------------------------- pemasangan dari zip --
    zip_path = os.path.join(akar, "paket.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("rasty-florist-main/app.py", "# app dari zip\n")
        zf.writestr("rasty-florist-main/version.py", 'VERSION = "9.9.9"\n')
        zf.writestr("rasty-florist-main/rasty_florist.db", "database-dari-zip")
        zf.writestr("rasty-florist-main/static/uploads/foto.jpg", "foto-dari-zip")
    ringkas = updater.pasang_dari_zip(zip_path, app_dir=tujuan)
    cek(ringkas["berhasil"], "pemasangan dari zip gagal: %s" % ringkas["pesan"])
    cek(baca("app.py") == "# app dari zip\n", "app.py tidak diperbarui dari zip")
    cek(baca("version.py") == 'VERSION = "9.9.9"\n', "version.py tidak diperbarui dari zip")
    cek(baca("rasty_florist.db") == "database-toko-asli", "database tertimpa oleh zip!")
    cek(baca(os.path.join("static", "uploads", "foto.jpg")) == "foto-toko-asli",
        "unggahan tertimpa oleh zip!")

    # Zip tanpa app.py harus ditolak.
    zip_buruk = os.path.join(akar, "buruk.zip")
    with zipfile.ZipFile(zip_buruk, "w") as zf:
        zf.writestr("apa-saja/berkas.txt", "bukan aplikasi")
    ringkas = updater.pasang_dari_zip(zip_buruk, app_dir=tujuan)
    cek(not ringkas["berhasil"], "zip tanpa app.py seharusnya ditolak")

    # Zip yang mencoba keluar folder (zip-slip) harus ditolak.
    zip_slip = os.path.join(akar, "slip.zip")
    with zipfile.ZipFile(zip_slip, "w") as zf:
        zf.writestr("rasty/app.py", "# app\n")
        zf.writestr("../../jahat.py", "# keluar folder\n")
    ringkas = updater.pasang_dari_zip(zip_slip, app_dir=tujuan)
    cek(not ringkas["berhasil"], "arsip zip-slip seharusnya ditolak")
    cek(not os.path.exists(os.path.join(akar, "jahat.py")),
        "berkas dari zip-slip berhasil keluar folder")

    # Folder sumber tanpa app.py juga ditolak.
    kosong = os.path.join(akar, "kosong")
    os.makedirs(kosong)
    ringkas = updater.pasang_dari_folder(kosong, app_dir=tujuan)
    cek(not ringkas["berhasil"], "folder tanpa app.py seharusnya ditolak")
finally:
    shutil.rmtree(akar, ignore_errors=True)

if gagal:
    for item in gagal:
        print("FAIL", item)
    sys.exit(1)
print("UJI PEMBARUAN OK")
