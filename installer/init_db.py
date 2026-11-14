"""Inisialisasi database Rasty Florist dari variabel lingkungan.

Dipakai pemasang (installer) di Linux: membuat skema, mengisi pengaturan
bawaan, menyiapkan hak akses peran, lalu membuat akun administrator pertama.

Variabel lingkungan:
    RASTY_DATABASE        lokasi berkas .db
    RASTY_SEED_DEMO       1 = isi data contoh, 0 = hanya akun administrator
    RASTY_ADMIN_USER      username administrator pertama
    RASTY_ADMIN_PASSWORD  kata sandinya
    RASTY_ADMIN_NAMA      nama tampilan
    RASTY_ADMIN_EMAIL     email

Keluar dengan kode 0 bila berhasil, 1 bila gagal.
"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.chdir(BASE)

# Impor app menjalankan create_app(), yang di dalamnya sudah memanggil
# init_db(), seed, dan auto_backup di dalam app context.
import app as application  # noqa: E402
import db as database  # noqa: E402


def main():
    app = application.app
    seed_demo = os.environ.get("RASTY_SEED_DEMO", "0") == "1"
    with app.app_context():
        jumlah_user = database.query("SELECT COUNT(*) AS c FROM users", one=True)["c"]
        jumlah_produk = database.query("SELECT COUNT(*) AS c FROM products", one=True)["c"]
        admin = database.query(
            "SELECT username, role, aktif FROM users WHERE role = 'administrator'"
            " ORDER BY id LIMIT 1", one=True)

    print("Database      : %s" % app.config["DATABASE"])
    print("Folder unggah : %s" % app.config["UPLOAD_FOLDER"])
    print("Akun          : %d" % jumlah_user)
    print("Produk        : %d" % jumlah_produk)
    print("Mode          : %s" % ("data contoh" if seed_demo else "toko sungguhan"))

    if jumlah_user == 0:
        print("! Tidak ada akun sama sekali - administrator gagal dibuat.")
        return 1
    if admin is None:
        print("! Tidak ada akun administrator.")
        return 1
    if not admin["aktif"]:
        print("! Akun administrator '%s' nonaktif." % admin["username"])
        return 1
    print("Administrator : %s" % admin["username"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
