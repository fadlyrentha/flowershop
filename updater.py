"""Pembaruan aplikasi: cek versi, unduh dari GitHub, pasang dari berkas lokal.

Modul ini dipakai dua cara:

* oleh halaman **Administrator → Pembaruan Aplikasi** di panel web, dan
* oleh ``installer/update.py`` yang dijalankan sebagai root di server Linux.

Berkas yang tidak boleh tersentuh pembaruan (database, unggahan, backup,
virtualenv, kunci sesi) dilewati di sini, jadi menjalankan pembaruan tidak
pernah menghapus data toko. Aturan ini berlaku untuk sumber lokal maupun
unduhan GitHub.
"""
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile

import version

ROOT = os.path.dirname(os.path.abspath(__file__))

# Batas kewarasan untuk arsip yang diunggah/diunduh (arsip tidak tepercaya).
MAKS_BERKAS = 5000
MAKS_MENTAH = 200 * 1024 * 1024  # total isi setelah diekstrak

# Nama berkas yang tidak pernah ditimpa pembaruan.
BERKAS_DILINDUNGI = {"rasty.conf", "rasty.env", ".env", ".env.local"}
# Nama folder yang isinya tidak pernah disentuh (dicocokkan per segmen jalur).
FOLDER_DILINDUNGI = {".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache"}
# Awalan jalur (relatif terhadap folder aplikasi) yang tidak boleh diubah.
AWALAN_DILINDUNGI = ("static/uploads/", "backups/")
# Akhiran berkas yang selalu dilewati.
AKHIRAN_DILINDUNGI = (".db", ".db-wal", ".db-shm", ".pyc", ".pyo", ".log")

_USER_AGENT = "RastyFlorist-Updater"


# ------------------------------------------------------------- versi --------
def _baca_version_file(teks):
    """Ambil VERSION="x.y.z" dari isi berkas version.py."""
    cocok = re.search(r'^\s*VERSION\s*=\s*["\']([^"\']+)["\']', teks, re.M)
    return cocok.group(1).strip() if cocok else ""


# Cache versi: dibaca ulang hanya bila berkasnya berubah. Versi dibaca di
# setiap request (untuk footer), jadi pembacaan berkas perlu dihindari.
# Ukuran ikut dijadikan kunci karena penyalinan berkas bisa mempertahankan
# waktu ubah (mtime) berkas sumber.
_VERSI_CACHE = {"kunci": None, "nilai": ""}


def versi_sekarang():
    """Versi aplikasi yang sedang terpasang.

    Dibaca ulang dari berkas (bukan dari modul yang sudah diimpor) supaya
    halaman tetap menampilkan versi baru sesaat setelah pembaruan, tanpa
    menunggu proses server dinyalakan ulang.
    """
    path = os.path.join(ROOT, "version.py")
    try:
        stat = os.stat(path)
        kunci = (stat.st_mtime, stat.st_size)
    except OSError:
        return version.VERSION
    if _VERSI_CACHE["kunci"] != kunci:
        try:
            with open(path, encoding="utf-8") as berkas:
                nilai = _baca_version_file(berkas.read())
        except OSError:
            nilai = ""
        _VERSI_CACHE.update({"kunci": kunci, "nilai": nilai or version.VERSION})
    return _VERSI_CACHE["nilai"]


def versi_tuple(nilai):
    """Ubah "1.2.3" menjadi (1, 2, 3) untuk dibandingkan."""
    bagian = re.findall(r"\d+", nilai or "")
    return tuple(int(b) for b in bagian) if bagian else (0,)


def lebih_baru(kandidat, acuan):
    """True bila versi kandidat lebih tinggi daripada acuan."""
    return versi_tuple(kandidat) > versi_tuple(acuan)


# --------------------------------------------------- perlindungan berkas ----
def _rel_posix(rel):
    rel = rel.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def dilindungi(rel):
    """True bila jalur relatif (``a/b/c.py``) tidak boleh ditimpa pembaruan."""
    rel = _rel_posix(rel)
    if not rel:
        return True
    segmen = rel.split("/")
    if any(s in FOLDER_DILINDUNGI for s in segmen):
        return True
    if segmen[-1] in BERKAS_DILINDUNGI:
        return True
    # Cocokkan juga folder itu sendiri, bukan hanya isinya, agar penelusuran
    # tidak masuk ke folder data.
    for awal in AWALAN_DILINDUNGI:
        if rel == awal.rstrip("/") or rel.startswith(awal):
            return True
    return segmen[-1].endswith(AKHIRAN_DILINDUNGI)


# ------------------------------------------------------------ github --------
def _url_version():
    return "https://raw.githubusercontent.com/%s/%s/version.py" % (version.REPO, version.CABANG)


def _url_zip():
    return "https://codeload.github.com/%s/zip/refs/heads/%s" % (version.REPO, version.CABANG)


def _unduh(url, timeout=20):
    permintaan = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(permintaan, timeout=timeout) as balasan:
        return balasan.read()


def cek_github(timeout=20):
    """Periksa versi terbaru di GitHub. Mengembalikan dict hasil."""
    hasil = {
        "sumber": "github",
        "sekarang": versi_sekarang(),
        "terbaru": "",
        "ada_baru": False,
        "pesan": "",
        "url": "https://github.com/%s" % version.REPO,
    }
    try:
        teks = _unduh(_url_version(), timeout=timeout).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        hasil["pesan"] = ("Repositori atau cabang tidak ditemukan (HTTP %s). "
                          "Periksa REPO dan CABANG di version.py." % exc.code)
        return hasil
    except (urllib.error.URLError, OSError) as exc:
        hasil["pesan"] = "Tidak dapat menghubungi GitHub: %s" % exc
        return hasil
    terbaru = _baca_version_file(teks)
    if not terbaru:
        hasil["pesan"] = "Berkas version.py di GitHub tidak memuat nilai VERSION."
        return hasil
    hasil["terbaru"] = terbaru
    hasil["ada_baru"] = lebih_baru(terbaru, hasil["sekarang"])
    if hasil["ada_baru"]:
        hasil["pesan"] = "Versi %s tersedia (terpasang %s)." % (terbaru, hasil["sekarang"])
    else:
        hasil["pesan"] = "Aplikasi sudah memakai versi terbaru (%s)." % hasil["sekarang"]
    return hasil


# ------------------------------------------------------------ arsip ---------
def _periksa_arsip(zf):
    """Tolak arsip yang jumlah/isinya di luar batas kewarasan."""
    anggota = zf.infolist()
    if len(anggota) > MAKS_BERKAS:
        return "Arsip berisi terlalu banyak berkas (%d)." % len(anggota)
    total = sum(a.file_size for a in anggota)
    if total > MAKS_MENTAH:
        return "Isi arsip terlalu besar (%.0f MB)." % (total / 1024 / 1024)
    return ""


def ekstrak_zip(zip_path, tujuan):
    """Ekstrak arsip dengan penjagaan zip-slip. Mengembalikan (folder_akar, pesan).

    ``folder_akar`` adalah folder di dalam hasil ekstraksi yang memuat ``app.py``.
    """
    try:
        with zipfile.ZipFile(zip_path) as zf:
            pesan = _periksa_arsip(zf)
            if pesan:
                return None, pesan
            tujuan_abs = os.path.abspath(tujuan)
            for anggota in zf.infolist():
                nama = anggota.filename
                if not nama or nama.endswith("/"):
                    continue
                target = os.path.abspath(os.path.join(tujuan_abs, nama))
                # Zip-slip: jalur yang keluar dari folder tujuan ditolak.
                if target != tujuan_abs and not target.startswith(tujuan_abs + os.sep):
                    return None, "Arsip memuat jalur tidak aman: %s" % nama
            zf.extractall(tujuan_abs)
    except zipfile.BadZipFile:
        return None, "Berkas bukan arsip .zip yang sah."
    except OSError as exc:
        return None, "Gagal membuka arsip: %s" % exc
    akar = akar_aplikasi(tujuan)
    if akar is None:
        return None, "Arsip tidak memuat app.py - bukan paket aplikasi Rasty Florist."
    return akar, ""


def akar_aplikasi(folder):
    """Cari folder yang memuat app.py di dalam hasil ekstraksi."""
    if os.path.isfile(os.path.join(folder, "app.py")):
        return folder
    try:
        isi = sorted(os.listdir(folder))
    except OSError:
        return None
    for nama in isi:
        sub = os.path.join(folder, nama)
        if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, "app.py")):
            return sub
    return None


# ------------------------------------------------------------ pemasangan ----
def pasang_dari_folder(sumber, app_dir=None, dry_run=False):
    """Salin berkas dari folder sumber ke folder aplikasi.

    Berkas yang dilindungi (database, unggahan, backup, konfigurasi) dilewati,
    dan berkas yang tidak ada di sumber tidak dihapus. Mengembalikan dict
    ringkasan: ``ditulis``, ``dilewati``, ``pesan``, ``berhasil``.
    """
    app_dir = os.path.abspath(app_dir or ROOT)
    sumber = os.path.abspath(sumber)
    ringkas = {"ditulis": 0, "dilewati": 0, "pesan": "", "berhasil": False}
    if not os.path.isdir(sumber):
        ringkas["pesan"] = "Folder sumber tidak ditemukan: %s" % sumber
        return ringkas
    if akar_aplikasi(sumber) is None:
        ringkas["pesan"] = "Folder sumber tidak memuat app.py."
        return ringkas
    sumber_norm = os.path.normcase(sumber)
    app_norm = os.path.normcase(app_dir)
    if sumber_norm == app_norm:
        ringkas["pesan"] = "Folder sumber sama dengan folder aplikasi - tidak ada yang disalin."
        return ringkas
    # Sumber yang berada di dalam folder aplikasi akan menyalin ke tengah
    # penelusurannya sendiri (berpotensi berulang tanpa henti), jadi ditolak.
    if sumber_norm.startswith(app_norm + os.sep):
        ringkas["pesan"] = "Folder sumber berada di dalam folder aplikasi - pindahkan dulu."
        return ringkas
    if app_norm.startswith(sumber_norm + os.sep):
        ringkas["pesan"] = "Folder aplikasi berada di dalam folder sumber - salin sumbernya ke luar."
        return ringkas
    # Uji coba tidak menulis apa pun, jadi tidak perlu izin tulis.
    if not dry_run and not os.access(app_dir, os.W_OK):
        ringkas["pesan"] = ("Folder aplikasi %s tidak dapat ditulis oleh proses ini. "
                            "Jalankan pembaruan lewat server: "
                            "sudo bash installer/update_ubuntu.sh" % app_dir)
        return ringkas

    for dirpath, dirnames, filenames in os.walk(sumber):
        rel_dir = os.path.relpath(dirpath, sumber)
        rel_dir = "" if rel_dir == "." else rel_dir
        # Folder yang dilindungi tidak ditelusuri sama sekali.
        dirnames[:] = [d for d in dirnames
                       if not dilindungi((rel_dir + "/" + d) if rel_dir else d)]
        for nama in filenames:
            rel = (rel_dir + "/" + nama) if rel_dir else nama
            if dilindungi(rel):
                ringkas["dilewati"] += 1
                continue
            tujuan = os.path.join(app_dir, rel)
            if dry_run:
                ringkas["ditulis"] += 1
                continue
            try:
                os.makedirs(os.path.dirname(tujuan), exist_ok=True)
                shutil.copy2(os.path.join(dirpath, nama), tujuan)
            except OSError as exc:
                ringkas["pesan"] = "Gagal menulis %s: %s" % (rel, exc)
                return ringkas
            ringkas["ditulis"] += 1

    ringkas["berhasil"] = True
    ringkas["pesan"] = "%d berkas diperbarui, %d berkas data dilewati." % (
        ringkas["ditulis"], ringkas["dilewati"])
    return ringkas


def pasang_dari_zip(zip_path, app_dir=None, dry_run=False):
    """Ekstrak arsip ke folder sementara lalu pasang isinya. Mengembalikan dict."""
    with tempfile.TemporaryDirectory(prefix="rasty-update-") as tmp:
        akar, pesan = ekstrak_zip(zip_path, tmp)
        if akar is None:
            return {"ditulis": 0, "dilewati": 0, "berhasil": False, "pesan": pesan}
        return pasang_dari_folder(akar, app_dir=app_dir, dry_run=dry_run)


def pasang_online(app_dir=None, timeout=60, dry_run=False):
    """Unduh cabang terbaru dari GitHub lalu pasang. Mengembalikan dict."""
    try:
        data = _unduh(_url_zip(), timeout=timeout)
    except urllib.error.HTTPError as exc:
        return {"ditulis": 0, "dilewati": 0, "berhasil": False,
                "pesan": "GitHub menolak permintaan (HTTP %s)." % exc.code}
    except (urllib.error.URLError, OSError) as exc:
        return {"ditulis": 0, "dilewati": 0, "berhasil": False,
                "pesan": "Gagal mengunduh dari GitHub: %s" % exc}
    with tempfile.TemporaryDirectory(prefix="rasty-update-") as tmp:
        path = os.path.join(tmp, "rasty.zip")
        try:
            with open(path, "wb") as berkas:
                berkas.write(data)
        except OSError as exc:
            return {"ditulis": 0, "dilewati": 0, "berhasil": False,
                    "pesan": "Gagal menyimpan unduhan: %s" % exc}
        return pasang_dari_zip(path, app_dir=app_dir, dry_run=dry_run)


def bisa_menulis(app_dir=None):
    """True bila proses ini boleh menulis ke folder aplikasi."""
    return os.access(os.path.abspath(app_dir or ROOT), os.W_OK)


def perintah_server():
    """Perintah yang disarankan di server Linux untuk memperbarui lewat SSH."""
    return "sudo bash installer/update_ubuntu.sh"
