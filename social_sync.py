"""Penarik konten sosial media (feed & story) untuk panel kontroler.

Alur pemakaian:

* panel **Administrator → Kontroler Sosial Media** memanggil :func:`sinkron_akun`
  saat tombol "Sinkronkan" ditekan, dan
* :func:`sinkron_terjadwal` dipanggil dari latar belakang aplikasi untuk menjaga
  feed dan story tetap segar tanpa menunggu admin.

Modul ini sengaja tidak memakai objek ``flask.g``: penjadwal berjalan di thread
terpisah yang tidak punya konteks aplikasi, jadi koneksi SQLite dibuka sendiri
oleh setiap pemanggilan. Keputusan ini juga membuat modul aman dipakai oleh
``installer/init_db.py`` di server.
"""
import html
import json
import os
import re
import sqlite3
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# Batas kewarasan untuk data yang datang dari internet.
TIMEOUT = 20
MAKS_GAMBAR = 8 * 1024 * 1024
MAKS_ITEM = 60
_UA = "RastyFlorist-SocialSync"

# Story hanya tayang 24 jam di platform asalnya, jadi item yang lebih tua
# dari ini ditandai tidak aktif saat sinkronisasi berikutnya.
UMUR_STORY = timedelta(hours=24)

IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
_EXT_DARI_TIPE = {
    "image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
    "image/gif": "gif", "image/webp": "webp",
}
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
}
_TAG_RE = re.compile(r"<[^>]+>")
_IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)

# Satu sinkronisasi pada satu waktu; dua penjadwal yang bertabrakan bisa
# menulis item kembar.
_LOCK = threading.Lock()


# --------------------------------------------------------------- jaringan ----
def _unduh(url, timeout=TIMEOUT, maks=None):
    """Ambil isi URL. Batas ukuran mencegah unduhan tak terduga besar."""
    permintaan = urllib.request.Request(url, headers={
        "User-Agent": _UA,
        "Accept": "application/rss+xml, application/atom+xml, application/json, image/*;q=0.8, */*;q=0.5",
    })
    with urllib.request.urlopen(permintaan, timeout=timeout) as balasan:
        if maks:
            data = balasan.read(maks + 1)
            if len(data) > maks:
                raise ValueError("Ukuran tanggapan melebihi batas.")
            return data, balasan.headers.get("Content-Type", "")
        return balasan.read(), balasan.headers.get("Content-Type", "")


# ------------------------------------------------------------ teks & waktu ----
def _bersih(teks, maks=400):
    """Buang tag HTML dari cuplikan lalu rapikan spasi."""
    teks = html.unescape(_TAG_RE.sub(" ", teks or ""))
    teks = re.sub(r"\s+", " ", teks).strip()
    return teks[:maks]


def _waktu_teks(nilai):
    """Ubah waktu ISO/RFC 822 dari feed menjadi 'YYYY-MM-DD HH:MM:SS'."""
    if not nilai:
        return ""
    teks = nilai.strip()
    # Format ISO 8601 varian yang lazim di Atom/JSON feed.
    iso = teks.replace("Z", "+00:00")
    # Instagram memakai bentuk "+0000" yang tidak diterima fromisoformat
    # sebelum Python 3.11, jadi titik dua pada offset ditambahkan sendiri.
    if re.search(r"[+-]\d{4}$", iso):
        iso = iso[:-2] + ":" + iso[-2:]
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(teks).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return ""


# ------------------------------------------------------------------ parser ----
def _cari(simpul, tag):
    """Cari anak pertama untuk nama seperti ``title`` atau ``media:content``."""
    if ":" in tag:
        prefiks, lokal = tag.split(":", 1)
        uri = _NS.get(prefiks)
        if not uri:
            return None
        return simpul.find("{%s}%s" % (uri, lokal))
    return simpul.find(tag)


def _teks_simpul(simpul, *nama):
    """Ambil teks anak pertama yang cocok, dengan atau tanpa namespace."""
    for tag in nama:
        anak = _cari(simpul, tag)
        if anak is not None and (anak.text or "").strip():
            return anak.text.strip()
    return ""


def _gambar_simpul(simpul):
    """Cari URL gambar dari elemen Media RSS, enclosure, atau isi HTML.

    Mendukung bentuk yang paling sering dipakai layanan feed sosial media.
    """
    for tag in ("media:content", "media:thumbnail"):
        for anak in simpul.findall("{%s}%s" % (_NS["media"], tag.split(":")[1])):
            url = anak.get("url")
            tipe = anak.get("type", "")
            if url and (not tipe or tipe.startswith("image")):
                return url
    for anak in simpul.findall("enclosure"):
        if anak.get("url") and anak.get("type", "").startswith("image"):
            return anak.get("url")
    for tag in ("content:encoded", "description", "summary", "content"):
        anak = _cari(simpul, tag)
        if anak is not None and anak.text:
            cocok = _IMG_RE.search(anak.text)
            if cocok:
                return cocok.group(1)
    return ""


def parse_feed(teks):
    """Ubah isi RSS 2.0 atau Atom menjadi daftar entri siap simpan."""
    try:
        akar = ET.fromstring(teks)
    except ET.ParseError as exc:
        raise ValueError("Isi feed bukan XML yang sah: %s" % exc) from exc

    simpul = akar.findall(".//item") or akar.findall(".//atom:entry", _NS)
    entri = []
    for item in simpul[:MAKS_ITEM]:
        judul = _teks_simpul(item, "title", "atom:title")
        isi = _teks_simpul(item, "description", "atom:summary", "atom:content")
        tautan = _teks_simpul(item, "link", "atom:link")
        if not tautan:
            simpul_link = item.find("atom:link", _NS)
            tautan = simpul_link.get("href", "") if simpul_link is not None else ""
        sumber_id = (_teks_simpul(item, "guid", "atom:id") or tautan or judul)
        waktu = _waktu_teks(_teks_simpul(item, "pubDate", "atom:updated", "atom:published",
                                         "dc:date"))
        entri.append({
            "sumber_id": sumber_id.strip()[:200],
            "judul": _bersih(judul, 160),
            "caption": _bersih(isi, 400),
            "link": tautan.strip()[:500],
            "gambar_url": _gambar_simpul(item),
            "waktu": waktu,
        })
    return entri


def parse_json_feed(teks):
    """Ubah JSON Feed (jsonfeed.org) menjadi daftar entri."""
    try:
        data = json.loads(teks)
    except ValueError as exc:
        raise ValueError("Isi feed bukan JSON yang sah: %s" % exc) from exc
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError("JSON tidak memuat daftar 'items'.")
    entri = []
    for item in data["items"][:MAKS_ITEM]:
        if not isinstance(item, dict):
            continue
        gambar = item.get("image") or item.get("banner_image") or ""
        if not gambar:
            cocok = _IMG_RE.search(item.get("content_html") or "")
            gambar = cocok.group(1) if cocok else ""
        entri.append({
            "sumber_id": str(item.get("id") or item.get("url") or item.get("title") or "")[:200],
            "judul": _bersih(item.get("title"), 160),
            "caption": _bersih(item.get("summary") or item.get("content_text")
                               or item.get("content_html"), 400),
            "link": str(item.get("url") or "")[:500],
            "gambar_url": gambar,
            "waktu": _waktu_teks(item.get("date_published") or item.get("date_modified")),
        })
    return entri


def parse_instagram(data, jenis="feed"):
    """Ubah tanggapan Instagram Graph API (media/stories) menjadi entri."""
    if isinstance(data, (bytes, str)):
        try:
            data = json.loads(data)
        except ValueError as exc:
            raise ValueError("Tanggapan Instagram bukan JSON yang sah.") from exc
    if isinstance(data, dict) and "error" in data:
        pesan = (data.get("error") or {}).get("message", "tidak diketahui")
        raise ValueError("Instagram menolak permintaan: %s" % pesan)
    daftar = (data or {}).get("data")
    if not isinstance(daftar, list):
        raise ValueError("Tanggapan Instagram tidak memuat daftar media.")
    entri = []
    for item in daftar[:MAKS_ITEM]:
        if not isinstance(item, dict):
            continue
        # Untuk video, media_url menunjuk berkas video - hanya sampulnya yang dipakai.
        if item.get("media_type") == "VIDEO":
            gambar = item.get("thumbnail_url") or ""
        else:
            gambar = item.get("media_url") or item.get("thumbnail_url") or ""
        entri.append({
            "sumber_id": str(item.get("id") or "")[:200],
            "judul": _bersih(item.get("caption"), 160) or ("Story" if jenis == "story" else "Feed"),
            "caption": _bersih(item.get("caption"), 400),
            "link": str(item.get("permalink") or "")[:500],
            "gambar_url": gambar,
            "waktu": _waktu_teks(item.get("timestamp")),
        })
    return entri


# ------------------------------------------------------------------ gambar ----
def _ext_gambar(url, tipe):
    """Tentukan ekstensi gambar; hanya format yang didukung panel diterima."""
    tipe = (tipe or "").split(";")[0].strip().lower()
    if tipe in _EXT_DARI_TIPE:
        return _EXT_DARI_TIPE[tipe]
    jalur = urllib.parse.urlparse(url).path
    ext = jalur.rsplit(".", 1)[-1].lower() if "." in jalur else ""
    return ext if ext in IMAGE_EXT else ""


def simpan_gambar(url, upload_dir, subdir="social"):
    """Unduh gambar dari internet dan simpan ke folder unggahan.

    Mengembalikan nama berkas relatif (``social/xxxx.jpg``) atau string kosong
    bila gagal - kegagalan gambar tidak boleh menggagalkan sinkronisasi teks.
    """
    if not url or not url.lower().startswith(("http://", "https://")):
        return ""
    try:
        data, tipe = _unduh(url, maks=MAKS_GAMBAR)
    except (urllib.error.URLError, OSError, ValueError):
        return ""
    ext = _ext_gambar(url, tipe)
    if not ext or not data:
        return ""
    folder = os.path.join(upload_dir, subdir)
    try:
        os.makedirs(folder, exist_ok=True)
        nama = uuid.uuid4().hex + "." + ext
        with open(os.path.join(folder, nama), "wb") as berkas:
            berkas.write(data)
    except OSError:
        return ""
    return subdir + "/" + nama


def hapus_gambar(nama, upload_dir):
    """Hapus berkas unggahan lokal; URL jarak jauh diabaikan."""
    if not nama or nama.startswith(("http://", "https://")) or ".." in nama:
        return
    path = os.path.normpath(os.path.join(upload_dir, nama))
    if not path.startswith(os.path.normpath(upload_dir) + os.sep):
        return
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


# -------------------------------------------------------------- pengambilan ----
def _url_instagram(akun, jenis):
    """Endpoint Instagram Graph API untuk feed atau story akun bisnis."""
    dasar = "https://graph.facebook.com/v19.0/%s/%s" % (
        urllib.parse.quote(akun["username"] or ""),
        "media" if jenis == "feed" else "stories")
    if jenis == "feed":
        fields = "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp"
    else:
        fields = "id,media_type,media_url,permalink,timestamp"
    return "%s?fields=%s&limit=%d&access_token=%s" % (
        dasar, fields, min(MAKS_ITEM, max(1, akun["jumlah_" + jenis] or 12)),
        urllib.parse.quote(akun["token"] or ""))


def punya_sumber(akun, jenis):
    """True bila akun ini punya sumber untuk jenis konten tersebut.

    Story tidak pernah memakai URL feed sebagai cadangan: isi feed adalah
    postingan, bukan story, sehingga memakainya akan menggandakan konten yang
    sama di kedua bagian beranda.
    """
    sumber = (akun.get("sumber") or "manual").lower()
    if sumber == "manual":
        return False
    if jenis == "story":
        return bool(akun.get("story_url")) if sumber == "rss" else True
    return bool(akun.get("feed_url") or akun.get("token"))


def ambil_entri(akun, jenis):
    """Ambil entri feed/story satu akun sesuai mode sumbernya.

    Mengembalikan daftar entri; melempar ``ValueError`` dengan pesan yang bisa
    ditampilkan ke admin bila sumbernya belum siap atau ditolak platform.
    """
    sumber = (akun["sumber"] or "manual").lower()
    if not punya_sumber(akun, jenis):
        return []
    if sumber == "api":
        if (akun["platform"] or "").lower() != "instagram":
            raise ValueError(
                "Mode API baru tersedia untuk Instagram. Platform lain gunakan mode RSS.")
        if not akun["token"] or not akun["username"]:
            raise ValueError("Mode API Instagram butuh ID akun bisnis dan access token.")
        teks, _tipe = _unduh(_url_instagram(akun, jenis))
        return parse_instagram(teks, jenis)

    url = akun["story_url"] if jenis == "story" else akun["feed_url"]
    teks, tipe = _unduh(url)
    isi = teks.decode("utf-8", "replace")
    if "json" in (tipe or "").lower() or isi.lstrip()[:1] in "{[":
        return parse_json_feed(isi)
    return parse_feed(isi)


# ------------------------------------------------------------------ simpan ----
def _simpan_entri(conn, akun, entri, jenis, upload_dir):
    """Tulis hasil penarikan ke tabel; item kembar diperbarui.

    Kolom ``aktif`` sengaja tidak ditimpa supaya item yang disembunyikan admin
    tetap tersembunyi pada sinkronisasi berikutnya.
    """
    baru = diperbarui = 0
    created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for urut, item in enumerate(entri):
        sumber_id = (item.get("sumber_id") or "").strip()
        if not sumber_id:
            continue
        lama = conn.execute(
            "SELECT id, gambar FROM social_items WHERE account_id = ? AND jenis = ? AND sumber_id = ?",
            (akun["id"], jenis, sumber_id)).fetchone()
        gambar = ""
        # Gambar hanya diunduh untuk item yang belum punya gambar lokal, supaya
        # sinkronisasi berkala tidak mengunduh berkas yang sama berulang kali.
        # Gambar bisa hilang bila berkasnya dihapus manual, jadi keberadaannya
        # dicek juga di disk.
        if item.get("gambar_url") and not (lama and lama["gambar"]
                                          and os.path.isfile(
                                              os.path.join(upload_dir, lama["gambar"]))):
            gambar = simpan_gambar(item["gambar_url"], upload_dir)
        if lama:
            # Gambar lama hanya dibuang bila memang diganti berkas baru; kalau
            # tidak ada gambar baru, nama lama dipertahankan apa adanya.
            if gambar and gambar != lama["gambar"]:
                hapus_gambar(lama["gambar"], upload_dir)
            else:
                gambar = lama["gambar"] or gambar
            conn.execute(
                "UPDATE social_items SET judul = ?, caption = ?, gambar = ?, link = ?, waktu = ?"
                " WHERE id = ?",
                (item.get("judul", ""), item.get("caption", ""), gambar,
                 item.get("link", ""), item.get("waktu", ""), lama["id"]))
            diperbarui += 1
        else:
            conn.execute(
                "INSERT INTO social_items (account_id, jenis, sumber_id, judul, caption, gambar,"
                " link, waktu, urutan, aktif, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
                (akun["id"], jenis, sumber_id, item.get("judul", ""), item.get("caption", ""),
                 gambar, item.get("link", ""), item.get("waktu", ""), urut, created))
            baru += 1
    return baru, diperbarui


def _buang_story_lama(conn, account_id, upload_dir):
    """Hapus story tarikan yang sudah lewat 24 jam.

    Story di platform asalnya hanya tayang 24 jam, jadi item yang lebih tua
    tidak akan muncul lagi. Story tarikan dihapus (bukan sekadar dinonaktifkan)
    agar gambar lokalnya tidak menumpuk di folder unggahan; story yang diisi
    manual admin tidak disentuh.
    """
    batas = (datetime.now() - UMUR_STORY).strftime("%Y-%m-%d %H:%M:%S")
    baris = conn.execute(
        "SELECT id, gambar FROM social_items WHERE account_id = ? AND jenis = 'story'"
        " AND sumber_id != '' AND waktu != '' AND waktu < ?", (account_id, batas)).fetchall()
    for item in baris:
        hapus_gambar(item["gambar"], upload_dir)
        conn.execute("DELETE FROM social_items WHERE id = ?", (item["id"],))
    return len(baris)


def sinkron_akun(account_id, db_path, upload_dir):
    """Sinkronkan feed dan story satu akun. Mengembalikan ringkasan dict."""
    ringkas = {"akun": account_id, "feed": 0, "story": 0, "pesan": [], "berhasil": True}
    if not _LOCK.acquire(blocking=False):
        ringkas.update({"berhasil": False, "pesan": ["Sinkronisasi lain sedang berjalan."]})
        return ringkas
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        baris = conn.execute("SELECT * FROM social_accounts WHERE id = ?", (account_id,)).fetchone()
        if baris is None:
            ringkas.update({"berhasil": False, "pesan": ["Akun tidak ditemukan."]})
            return ringkas
        akun = dict(baris)
        # Story kedaluwarsa dibersihkan lebih dulu dan tanpa syarat: akun yang
        # sumbernya dikosongkan atau diubah ke manual pun tetap harus berhenti
        # menyimpan story lama beserta gambarnya.
        _buang_story_lama(conn, account_id, upload_dir)
        if (akun["sumber"] or "manual") == "manual":
            ringkas["pesan"].append("Mode manual: tidak ada yang ditarik.")
            conn.commit()
            return ringkas

        for jenis in ("feed", "story"):
            if not punya_sumber(akun, jenis):
                ringkas["pesan"].append("%s: sumber belum diisi." % jenis.capitalize())
                continue
            try:
                entri = ambil_entri(akun, jenis)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                ringkas["berhasil"] = False
                ringkas["pesan"].append("%s: %s" % (jenis.capitalize(), exc))
                continue
            if not entri:
                ringkas["pesan"].append("%s: tidak ada konten baru." % jenis.capitalize())
                continue
            try:
                baru, diperbarui = _simpan_entri(conn, akun, entri, jenis, upload_dir)
            except sqlite3.Error as exc:
                # Dua proses bisa menarik akun yang sama; indeks unik pada
                # sumber_id menjaga data tetap rapi, dan kegagalannya cukup
                # dilaporkan sebagai pesan, bukan menjatuhkan halaman panel.
                conn.rollback()
                ringkas["berhasil"] = False
                ringkas["pesan"].append("%s: gagal menyimpan (%s)" % (jenis.capitalize(), exc))
                continue
            ringkas[jenis] = baru + diperbarui
            ringkas["pesan"].append(
                "%s: %d baru, %d diperbarui." % (jenis.capitalize(), baru, diperbarui))
            _pangkas(conn, akun["id"], jenis, upload_dir, akun["jumlah_" + jenis] or 12)

        sekarang = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE social_accounts SET terakhir_sinkron = ?, status_sinkron = ? WHERE id = ?",
            (sekarang, " | ".join(ringkas["pesan"])[:300], account_id))
        conn.commit()
    finally:
        if conn is not None:
            conn.close()
        _LOCK.release()
    return ringkas


def _pangkas(conn, account_id, jenis, upload_dir, simpan):
    """Buang item hasil tarikan yang melebihi kuota tampil, agar tidak menumpuk."""
    batas = max(1, int(simpan)) * 3
    baris = conn.execute(
        "SELECT id, gambar FROM social_items WHERE account_id = ? AND jenis = ?"
        " AND sumber_id != '' AND aktif = 1"
        " ORDER BY (waktu = ''), waktu DESC, id DESC LIMIT -1 OFFSET ?",
        (account_id, jenis, batas)).fetchall()
    for item in baris:
        hapus_gambar(item["gambar"], upload_dir)
        conn.execute("DELETE FROM social_items WHERE id = ?", (item["id"],))


def sinkron_semua(db_path, upload_dir, account_id=None, otomatis=False):
    """Sinkronkan satu atau seluruh akun. Mengembalikan ringkasan gabungan.

    ``otomatis`` menyaring akun yang tidak dicentang "Ikut sinkron otomatis";
    tombol "Sinkronkan Semua" di panel sengaja tidak menyaring agar admin tetap
    bisa menarik akun mana pun saat itu juga.
    """
    hasil = []
    if account_id:
        hasil.append(sinkron_akun(account_id, db_path, upload_dir))
    else:
        sql = ("SELECT id FROM social_accounts WHERE aktif = 1 AND sumber != 'manual'"
               + (" AND sinkron_otomatis = 1" if otomatis else "")
               + " ORDER BY urutan, id")
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            ids = [r["id"] for r in conn.execute(sql)]
        finally:
            conn.close()
        for aid in ids:
            hasil.append(sinkron_akun(aid, db_path, upload_dir))
    return {
        "akun": len(hasil),
        "item": sum(h["feed"] + h["story"] for h in hasil),
        "berhasil": all(h["berhasil"] for h in hasil) if hasil else True,
        "pesan": [p for h in hasil for p in h["pesan"]],
    }


def _catat_jadwal(db_path, pesan):
    """Simpan waktu & status sinkronisasi terakhir di tabel pengaturan."""
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout = 30000")
        for key, value in (("sosial_terakhir_sinkron",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                           ("sosial_status_sinkron", pesan[:300])):
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)"
                         " ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        conn.close()


def _klaim_jadwal(db_path):
    """Ambil giliran sinkron otomatis secara atomik; True bila giliran didapat.

    Beberapa proses (mis. gunicorn dengan beberapa worker) bisa memeriksa
    jadwal ini bersamaan. Transaksi IMMEDIATE memastikan hanya satu proses yang
    benar-benar menarik data, dan waktunya langsung dicatat sehingga proses lain
    melihat jadwal sudah terpakai.
    """
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("BEGIN IMMEDIATE")
        pengaturan = {r["key"]: r["value"] for r in conn.execute(
            "SELECT key, value FROM settings WHERE key IN"
            " ('sosial_aktif','sosial_interval','sosial_terakhir_sinkron')")}
        if pengaturan.get("sosial_aktif", "1") != "1":
            conn.rollback()
            return False
        try:
            selang = max(0, int(pengaturan.get("sosial_interval", "30") or 0)) * 60
        except (TypeError, ValueError):
            selang = 0
        if not selang:
            conn.rollback()
            return False
        terakhir = pengaturan.get("sosial_terakhir_sinkron", "")
        if terakhir:
            try:
                if (datetime.now() - datetime.strptime(terakhir, "%Y-%m-%d %H:%M:%S")
                        ).total_seconds() < selang:
                    conn.rollback()
                    return False
            except ValueError:
                pass
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('sosial_terakhir_sinkron', ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
        conn.commit()
        return True
    except sqlite3.Error:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        return False
    finally:
        conn.close()


def sinkron_terjadwal(db_path, upload_dir):
    """Sinkronkan seluruh akun bila selang waktunya sudah lewat.

    Dipanggil dari latar belakang aplikasi, jadi kegagalan apa pun ditelan:
    masalah jaringan tidak boleh sampai memunculkan galat ke pengunjung.
    """
    if not _klaim_jadwal(db_path):
        return None
    try:
        ringkas = sinkron_semua(db_path, upload_dir, otomatis=True)
    except Exception:  # noqa: BLE001 - penjadwal latar belakang tidak boleh menjatuhkan app
        return None
    _catat_jadwal(db_path, " | ".join(ringkas["pesan"]))
    return ringkas
