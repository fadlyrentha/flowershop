"""Pemasang (installer) Rasty Florist untuk Windows.

Menyalin konfigurasi, memasang dependensi Python, membuat database SQLite,
lalu menulis berkas peluncur server. Hanya memakai pustaka standar Python
supaya bisa dijalankan sebelum Flask terpasang.

Pemakaian:
    python installer\\install.py            # pemasangan interaktif
    python installer\\install.py --yes      # pakai semua nilai bawaan
"""
import argparse
import ctypes
import os
import secrets
import sqlite3
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF_NAME = "rasty.conf"
SERVER_BAT = "jalankan-server.bat"
DB_NAME = "rasty_florist.db"


def rapikan_konsol():
    """Pastikan karakter non-ASCII tidak mematikan skrip di konsol Windows lama."""
    for aliran in (sys.stdout, sys.stderr):
        try:
            aliran.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


DEFAULTS = {
    "host": "0.0.0.0",
    "port": "5000",
    "threads": "8",
    "admin_user": "admin",
    "admin_nama": "Administrator",
    "admin_email": "admin@rastyflorist.id",
    "seed_demo": False,
}


# ------------------------------------------------------------------ helpers --
def tanya(pertanyaan, bawaan=""):
    """Tanya satu nilai; kosong berarti pakai bawaan."""
    tanda = " [%s]" % bawaan if bawaan else ""
    try:
        jawaban = input("%s%s: " % (pertanyaan, tanda)).strip()
    except EOFError:
        return bawaan
    return jawaban or bawaan


def tanya_saklar(pertanyaan, bawaan=False):
    bawaan_teks = "Y/n" if bawaan else "y/N"
    jawaban = tanya("%s (%s)" % (pertanyaan, bawaan_teks), "").strip().lower()
    if not jawaban:
        return bawaan
    return jawaban in ("y", "ya", "yes", "1", "true")


def tanya_port(bawaan):
    while True:
        nilai = tanya("Port server", bawaan)
        try:
            port = int(nilai)
        except ValueError:
            print("  ! Port harus berupa angka.")
            continue
        if not 1 <= port <= 65535:
            print("  ! Port harus antara 1 dan 65535.")
            continue
        return str(port)


def tanya_sandi():
    """Minta kata sandi administrator dua kali.

    Kosong (atau tidak cocok) berarti sandi acak dibuatkan installer, supaya
    tidak ada instalasi yang terpasang dengan sandi bawaan yang diketahui umum.
    """
    try:
        import getpass
        sandi = getpass.getpass(
            "Kata sandi administrator (kosong = dibuat acak): ").strip()
    except (ImportError, EOFError):
        sandi = ""
    if not sandi:
        return ""
    if len(sandi) < 6:
        print("  ! Kata sandi minimal 6 karakter, dibuatkan sandi acak.")
        return ""
    try:
        ulang = getpass.getpass("Ulangi kata sandi: ").strip()
    except (ImportError, EOFError):
        return ""
    if sandi != ulang:
        print("  ! Kata sandi tidak sama, dibuatkan sandi acak.")
        return ""
    return sandi


def sandi_acak(panjang=12):
    """Kata sandi acak yang mudah dibacakan lewat telepon (tanpa karakter mirip)."""
    abjad = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(abjad) for _ in range(panjang))


def judul(teks):
    print()
    print("=" * 62)
    print("  " + teks)
    print("=" * 62)


def langkah(teks):
    print("  -> %s" % teks)


def peringatan(teks):
    print("  ! %s" % teks)


# --------------------------------------------------------------- langkah ----
def pasang_dependensi():
    """Pasang Flask + waitress dari requirements.txt."""
    req = os.path.join(APP_DIR, "requirements.txt")
    if not os.path.isfile(req):
        peringatan("requirements.txt tidak ditemukan, melewati pemasangan dependensi.")
        return False
    perintah = [sys.executable, "-m", "pip", "install", "-r", req]
    hasil = subprocess.run(perintah, cwd=APP_DIR)
    if hasil.returncode != 0:
        peringatan("Pemasangan dependensi gagal (kode %d)." % hasil.returncode)
        return False
    return True


def cek_flask():
    try:
        import flask  # noqa: F401
    except ImportError:
        return False
    return True


def siapkan_database(seed_demo, admin, sandi, nama, email):
    """Buat skema + akun administrator lewat factory aplikasi."""
    os.environ["RASTY_DATABASE"] = os.path.join(APP_DIR, DB_NAME)
    os.environ["RASTY_SEED_DEMO"] = "1" if seed_demo else "0"
    os.environ["RASTY_ADMIN_USER"] = admin
    os.environ["RASTY_ADMIN_PASSWORD"] = sandi
    os.environ["RASTY_ADMIN_NAMA"] = nama
    os.environ["RASTY_ADMIN_EMAIL"] = email
    sys.path.insert(0, APP_DIR)
    os.chdir(APP_DIR)
    import app as application  # noqa: F401  - impor memicu init_db + seed
    return os.path.join(APP_DIR, DB_NAME)


def jumlah_baris(path, tabel):
    if not os.path.isfile(path):
        return 0
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT COUNT(*) FROM %s" % tabel).fetchone()[0]
    except sqlite3.Error:
        return 0
    finally:
        con.close()


def cadangkan_database(path):
    """Cadangkan database sebelum dipasang ulang.

    Memakai API backup sqlite3, bukan salin berkas: dengan mode WAL, salinan
    berkas biasa bisa kehilangan transaksi yang belum dipindahkan ke berkas
    utama.
    """
    from datetime import datetime
    stempel = datetime.now().strftime("%Y%m%d-%H%M%S")
    tujuan = "%s.sebelum-pasang-%s.bak" % (path, stempel)
    sumber = sqlite3.connect(path)
    sasaran = sqlite3.connect(tujuan)
    try:
        sumber.backup(sasaran)
    finally:
        sasaran.close()
        sumber.close()
    return tujuan


def tulis_conf(conf):
    baris = [
        "# Konfigurasi Rasty Florist - dibuat oleh installer.",
        "# Ubah nilai di bawah lalu jalankan ulang jalankan-server.bat.",
    ]
    for kunci, nilai in conf.items():
        baris.append("%s=%s" % (kunci, nilai))
    path = os.path.join(APP_DIR, CONF_NAME)
    with open(path, "w", encoding="utf-8") as berkas:
        berkas.write("\n".join(baris) + "\n")
    return path


def sid_pengguna():
    """SID pengguna Windows saat ini (mis. S-1-5-21-...). Kosong bila gagal."""
    try:
        hasil = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
                               capture_output=True, text=True)
    except OSError:
        return ""
    for potong in hasil.stdout.replace('"', "").strip().split(","):
        potong = potong.strip()
        if potong.startswith("S-1-5-21"):
            return potong
    return ""


def batasi_akses(path):
    """Batasi berkas konfigurasi hanya untuk pengguna saat ini (berisi SECRET_KEY).

    Memakai SID, bukan nama grup, karena nama grup Windows diterjemahkan
    (mis. "Administrators" menjadi "Administrator" di Windows berbahasa Indonesia).
    """
    if os.name != "nt":
        return
    sid = sid_pengguna()
    perintah = ["icacls", path, "/inheritance:r"]
    # S-1-5-18 = SYSTEM, S-1-5-32-544 = Administrators.
    for akun in (sid, "*S-1-5-18", "*S-1-5-32-544"):
        if akun:
            perintah += ["/grant:r", "%s:F" % akun]
    if len(perintah) == 3:
        return
    subprocess.run(perintah, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def tulis_bat():
    """Tulis peluncur server. Memakai 'python', jatuh ke 'py -3' bila tak ada."""
    path = os.path.join(APP_DIR, SERVER_BAT)
    isi = (
        "@echo off\r\n"
        "cd /d \"%~dp0\"\r\n"
        "title Rasty Florist - Server\r\n"
        "python --version >nul 2>nul\r\n"
        "if not errorlevel 1 (\r\n"
        "    python jalankan_server.py\r\n"
        "    goto berhenti\r\n"
        ")\r\n"
        "py -3 --version >nul 2>nul\r\n"
        "if not errorlevel 1 (\r\n"
        "    py -3 jalankan_server.py\r\n"
        "    goto berhenti\r\n"
        ")\r\n"
        "echo Python tidak ditemukan. Pasang Python lalu jalankan pasang.bat.\r\n"
        ":berhenti\r\n"
        "echo.\r\n"
        "echo Server berhenti. Tekan tombol apa saja untuk menutup.\r\n"
        "pause >nul\r\n"
    )
    with open(path, "w", encoding="ascii", newline="") as berkas:
        berkas.write(isi)
    return path


def perintah_powershell(script):
    """Jalankan skrip PowerShell dari berkas sementara."""
    sementara = os.path.join(APP_DIR, "installer", "_sementara.ps1")
    with open(sementara, "w", encoding="utf-8") as berkas:
        berkas.write(script)
    try:
        return subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", sementara],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0
    finally:
        try:
            os.remove(sementara)
        except OSError:
            pass


def buat_pintasan(nama, target, folder, argumen="", ikon=""):
    tujuan = os.path.join(folder, nama + ".lnk")
    ikon_baris = "IconLocation = '%s'" % ikon if ikon else ""
    script = (
        "$ws = New-Object -ComObject WScript.Shell\n"
        "$s = $ws.CreateShortcut('%s')\n"
        "$s.TargetPath = '%s'\n"
        "$s.Arguments = '%s'\n"
        "$s.WorkingDirectory = '%s'\n"
        "%s\n"
        "$s.Save()\n"
    ) % (tujuan, target, argumen, APP_DIR, ikon_baris)
    if perintah_powershell(script):
        return tujuan
    return ""


def buka_firewall(port):
    """Buka port di Windows Firewall (butuh hak administrator)."""
    hasil = subprocess.run(
        ["netsh", "advfirewall", "firewall", "add", "rule",
         "name=Rasty Florist (TCP %s)" % port, "dir=in", "action=allow",
         "protocol=TCP", "localport=%s" % port],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return hasil.returncode == 0


def sedang_admin():
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def alamat_lokal():
    import socket
    try:
        nama = socket.gethostname()
        return socket.gethostbyname(nama)
    except OSError:
        return "127.0.0.1"


def folder_desktop():
    """Folder Desktop sebenarnya — OneDrive suka memindahkannya."""
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as kunci:
            nilai, _tipe = winreg.QueryValueEx(kunci, "Desktop")
            if nilai and os.path.isdir(nilai):
                return nilai
    except (ImportError, OSError):
        pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


# -------------------------------------------------------------------- main ---
def main():
    parser = argparse.ArgumentParser(description="Pemasang Rasty Florist")
    parser.add_argument("--yes", action="store_true", help="pakai semua nilai bawaan")
    parser.add_argument("--port", default="", help="port server")
    parser.add_argument("--host", default="", help="alamat bind")
    parser.add_argument("--admin", default="", help="username administrator")
    parser.add_argument("--password", default="", help="kata sandi administrator")
    parser.add_argument("--demo", action="store_true", help="isi data contoh")
    parser.add_argument("--tanpa-shortcut", action="store_true", help="jangan buat pintasan")
    parser.add_argument("--tanpa-firewall", action="store_true", help="jangan ubah firewall")
    opsi = parser.parse_args()

    os.chdir(APP_DIR)
    judul("Pemasang Rasty Florist")
    print("  Folder aplikasi : %s" % APP_DIR)
    print("  Python          : %s" % sys.version.split()[0])
    print("  Pemasangan akan memasang dependensi, membuat database, dan")
    print("  menyiapkan berkas peluncur server.")

    # --- 1. konfigurasi ---
    judul("Langkah 1/5 - Konfigurasi server")
    if opsi.yes:
        host = opsi.host or DEFAULTS["host"]
        port = opsi.port or DEFAULTS["port"]
        admin_user = opsi.admin or DEFAULTS["admin_user"]
        # Tanpa --password, buat sandi acak: jangan pernah pasang sandi bawaan
        # yang sudah diketahui umum, apalagi bila server dilayani ke jaringan.
        sandi = opsi.password or sandi_acak()
        admin_nama = DEFAULTS["admin_nama"]
        admin_email = DEFAULTS["admin_email"]
        seed_demo = opsi.demo
        print("  Mode otomatis: host=%s port=%s admin=%s" % (host, port, admin_user))
        print("  Kata sandi: %s" % sandi)
        if not opsi.password:
            print("  (sandi dibuat acak - catat sekarang, bisa diganti dengan")
            print("   python installer\\set_sandi.py --user %s)" % admin_user)
    else:
        lanjut = tanya_saklar(
            "Layani juga komputer lain di jaringan toko (bukan hanya komputer ini)?", True)
        host = "0.0.0.0" if lanjut else "127.0.0.1"
        port = tanya_port(DEFAULTS["port"])
        seed_demo = tanya_saklar(
            "Isi data contoh (produk, pesanan, akun demo)?", False)
        admin_user = tanya("Username administrator", DEFAULTS["admin_user"])
        sandi = tanya_sandi()
        if not sandi:
            sandi = sandi_acak()
            print("  -> Kata sandi administrator dibuat acak: %s" % sandi)
            print("     Catat sekarang - hanya ditampilkan sekali di sini.")
        admin_nama = tanya("Nama administrator", DEFAULTS["admin_nama"])
        admin_email = tanya("Email administrator", DEFAULTS["admin_email"])

    # --- 2. dependensi ---
    judul("Langkah 2/5 - Memasang dependensi")
    if cek_flask():
        langkah("Flask sudah terpasang, melanjutkan pemasangan dari requirements.txt.")
    if pasang_dependensi():
        langkah("Dependensi siap.")
    elif not cek_flask():
        peringatan("Flask belum tersedia. Jalankan: python -m pip install -r requirements.txt")
        return 1

    # --- 3. database ---
    judul("Langkah 3/5 - Menyiapkan database")
    db_path = os.path.join(APP_DIR, DB_NAME)
    if os.path.isfile(db_path):
        if opsi.yes:
            langkah("Database sudah ada - dipakai ulang tanpa menghapus data.")
        elif tanya_saklar("Database sudah ada. Buat ulang dari nol?", False):
            cadangan = cadangkan_database(db_path)
            langkah("Cadangan lama disimpan: %s" % os.path.basename(cadangan))
            os.remove(db_path)
        else:
            langkah("Database lama dipertahankan.")
    try:
        siapkan_database(seed_demo, admin_user, sandi, admin_nama, admin_email)
    except Exception as exc:  # noqa: BLE001 - tampilkan penyebab apa adanya
        peringatan("Gagal menyiapkan database: %s" % exc)
        return 1
    langkah("Database: %s" % db_path)
    langkah("Akun pengguna: %d, produk: %d"
            % (jumlah_baris(db_path, "users"), jumlah_baris(db_path, "products")))

    # --- 4. berkas peluncur ---
    judul("Langkah 4/5 - Menulis konfigurasi & peluncur")
    conf = {
        "RASTY_SECRET": secrets.token_hex(32),
        "RASTY_HOST": host,
        "RASTY_PORT": port,
        "RASTY_THREADS": DEFAULTS["threads"],
        "RASTY_DEBUG": "0",
        "RASTY_DATABASE": db_path,
    }
    conf_path = tulis_conf(conf)
    batasi_akses(conf_path)
    langkah("Konfigurasi : %s (kunci sesi dibuat acak)" % CONF_NAME)
    langkah("Peluncur    : %s" % os.path.basename(tulis_bat()))

    # --- 5. pintasan & firewall ---
    judul("Langkah 5/5 - Pintasan & firewall")
    bat_path = os.path.join(APP_DIR, SERVER_BAT)
    if not opsi.tanpa_shortcut and os.name == "nt":
        desktop = folder_desktop()
        if buat_pintasan("Rasty Florist", bat_path, desktop):
            langkah("Pintasan desktop dibuat.")
        else:
            peringatan("Pintasan desktop gagal dibuat (bisa dijalankan lewat %s)." % SERVER_BAT)
        if tanya_saklar("Jalankan server otomatis saat Windows menyala?", False):
            startup = os.path.join(os.environ.get("APPDATA", ""),
                                   "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
            if os.path.isdir(startup) and buat_pintasan("Rasty Florist", bat_path, startup):
                langkah("Autostart ditambahkan ke folder Startup.")
            else:
                peringatan("Folder Startup tidak ditemukan, autostart dilewati.")
    if host == "0.0.0.0" and not opsi.tanpa_firewall and os.name == "nt":
        if sedang_admin():
            if buka_firewall(port):
                langkah("Aturan firewall untuk port %s dibuat." % port)
            else:
                peringatan("Gagal membuat aturan firewall.")
        else:
            peringatan("Firewall tidak diubah (perlu jalankan sebagai Administrator).")
            print("      Jalankan manual: netsh advfirewall firewall add rule "
                  "name=\"Rasty Florist\" dir=in action=allow protocol=TCP localport=%s" % port)

    judul("Pemasangan selesai")
    print("  Mulai server : klik dua kali %s" % SERVER_BAT)
    print("  Alamat lokal : http://127.0.0.1:%s" % port)
    if host == "0.0.0.0":
        print("  Alamat jaringan : http://%s:%s" % (alamat_lokal(), port))
    print()
    print("  Masuk sebagai  : %s" % admin_user)
    print("  Kata sandi     : %s" % sandi)
    print("  ! Kata sandi ini hanya ditampilkan sekali. Catat, lalu ganti lewat")
    print("    menu Akun > Kata Sandi setelah masuk.")
    if seed_demo:
        print("  Data contoh terpasang - akun demo ada di README.md.")
    print()
    print("  Pengaturan server (port, alamat, kunci sesi) ada di %s" % CONF_NAME)
    return 0


if __name__ == "__main__":
    rapikan_konsol()
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nPemasangan dibatalkan.")
        sys.exit(130)
