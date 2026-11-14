"""Uji instalasi bersih: database baru tanpa data contoh.

Memakai berkas .db sementara supaya database toko yang asli tidak tersentuh.
"""
import os
import shutil
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
os.chdir(BASE)

tmp = os.path.join(tempfile.gettempdir(), "rasty_install_test.db")
for sisa in (tmp, tmp + "-wal", tmp + "-shm"):
    if os.path.isfile(sisa):
        os.remove(sisa)

# Folder unggahan sementara, meniru pemasangan Linux yang memindahkan folder
# unggahan ke luar folder aplikasi (mis. /var/lib/rasty-florist/uploads).
tmp_uploads = os.path.join(tempfile.gettempdir(), "rasty_install_test_uploads")
tmp_backups = os.path.join(tempfile.gettempdir(), "rasty_install_test_backups")
for folder in (tmp_uploads, tmp_backups):
    if os.path.isdir(folder):
        shutil.rmtree(folder)

os.environ["RASTY_DATABASE"] = tmp
os.environ["RASTY_UPLOAD_FOLDER"] = tmp_uploads
os.environ["RASTY_BACKUP_FOLDER"] = tmp_backups
os.environ["RASTY_SEED_DEMO"] = "0"
os.environ["RASTY_ADMIN_USER"] = "pemilik"
os.environ["RASTY_ADMIN_PASSWORD"] = "rahasia123"
os.environ["RASTY_ADMIN_NAMA"] = "Pemilik Toko"
os.environ["RASTY_ADMIN_EMAIL"] = "pemilik@example.com"

import app as application  # noqa: E402
import db as database  # noqa: E402

app = application.app
app.config["TESTING"] = True
gagal = []

with app.app_context():
    jumlah_user = database.query("SELECT COUNT(*) AS c FROM users", one=True)["c"]
    if jumlah_user != 1:
        gagal.append("jumlah pengguna = %d, seharusnya 1" % jumlah_user)

    admin = database.query("SELECT * FROM users WHERE username = 'pemilik'", one=True)
    if admin is None:
        gagal.append("akun 'pemilik' tidak dibuat")
    else:
        if admin["role"] != "administrator":
            gagal.append("peran akun = %s, seharusnya administrator" % admin["role"])
        if admin["nama"] != "Pemilik Toko":
            gagal.append("nama akun = %s" % admin["nama"])
        if not admin["aktif"]:
            gagal.append("akun tidak aktif")

    jumlah_produk = database.query("SELECT COUNT(*) AS c FROM products", one=True)["c"]
    if jumlah_produk != 0:
        gagal.append("produk ikut terisi (%d) padahal tanpa data contoh" % jumlah_produk)

    # Hak akses administrator harus lengkap supaya semua menu bisa dibuka.
    fitur = database.role_features("administrator")
    for wajib in ("dashboard", "hak_akses", "produk", "faktur", "backup", "pengaturan"):
        if not fitur.get(wajib):
            gagal.append("fitur administrator '%s' tidak aktif" % wajib)

    # Pengaturan bawaan harus tersedia.
    for kunci in ("nama_toko", "invoice_logo_tampil", "invoice_logo_ukuran"):
        if kunci not in database.all_settings():
            gagal.append("pengaturan '%s' tidak ada" % kunci)

# Impor kedua tidak boleh menambah akun (idempoten).
os.environ["RASTY_SEED_DEMO"] = "0"
with app.app_context():
    if database.query("SELECT COUNT(*) AS c FROM users", one=True)["c"] != 1:
        gagal.append("impor ulang menambah pengguna")

# Login lewat HTTP harus berhasil.
client = app.test_client()
r = client.post("/login", data={"username": "pemilik", "password": "rahasia123"},
                follow_redirects=True)
if r.status_code != 200:
    gagal.append("login gagal: HTTP %d" % r.status_code)
elif b"/admin/" not in r.request.path.encode():
    gagal.append("login tidak diarahkan ke panel admin (path %s)" % r.request.path)

r = client.get("/admin/")
if r.status_code != 200:
    gagal.append("panel admin HTTP %d" % r.status_code)

r = client.get("/")
if r.status_code != 200:
    gagal.append("beranda publik HTTP %d" % r.status_code)

# Unggahan harus disajikan dari UPLOAD_FOLDER walau foldernya di luar folder
# aplikasi (kondisi pemasangan di Linux).
nama_uji = "uji-install.txt"
with open(os.path.join(tmp_uploads, nama_uji), "w", encoding="utf-8") as berkas:
    berkas.write("isi uji")
r = client.get("/static/uploads/" + nama_uji)
if r.status_code != 200:
    gagal.append("rute unggahan HTTP %d (folder unggahan di luar aplikasi)" % r.status_code)
elif r.get_data(as_text=True) != "isi uji":
    gagal.append("isi berkas unggahan tidak sesuai")

# Berkas di luar folder unggahan tidak boleh bisa diambil.
r = client.get("/static/uploads/../../../../etc/passwd")
if r.status_code == 200:
    gagal.append("rute unggahan bisa keluar dari folder unggahan")

if not os.path.isdir(tmp_uploads):
    gagal.append("folder unggahan tidak dibuat otomatis")

if os.path.isfile(tmp):
    os.remove(tmp)
for folder in (tmp_uploads, tmp_backups):
    if os.path.isdir(folder):
        shutil.rmtree(folder)

if gagal:
    for item in gagal:
        print("FAIL", item)
    sys.exit(1)
print("INSTALASI BERSIH OK")
