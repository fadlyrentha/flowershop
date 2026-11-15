"""Uji penarik konten sosial media: parser feed, penyimpanan item, dan migrasi.

Semua uji di sini berjalan tanpa jaringan - pengunduhan diuji lewat monkeypatch
supaya hasilnya dapat diulang dan tidak bergantung layanan pihak ketiga.
"""
import os
import sqlite3
import sys
import tempfile

import social_sync

errors = []


def check(nama, syarat, info=""):
    if not syarat:
        errors.append((nama, info) if info else (nama,))


# ------------------------------------------------------------------ parser ----
RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>Rasty Florist</title>
    <item>
      <title>Bouquet pagi ini</title>
      <link>https://instagram.com/p/AAA</link>
      <guid>https://instagram.com/p/AAA</guid>
      <description>&lt;p&gt;Bunga segar &lt;b&gt;pagi&lt;/b&gt; ini.&lt;/p&gt;</description>
      <pubDate>Fri, 14 Nov 2026 09:30:00 +0700</pubDate>
      <media:content url="https://cdn.example.com/a.jpg" type="image/jpeg"/>
    </item>
    <item>
      <title>Tanpa gambar</title>
      <link>https://instagram.com/p/BBB</link>
      <description>&lt;img src="https://cdn.example.com/b.png"/&gt;Packing rapi</description>
    </item>
  </channel>
</rss>"""

entri = social_sync.parse_feed(RSS)
check("rss jumlah entri", len(entri) == 2, len(entri))
check("rss judul", entri[0]["judul"] == "Bouquet pagi ini", entri[0]["judul"])
check("rss sumber_id", entri[0]["sumber_id"] == "https://instagram.com/p/AAA",
      entri[0]["sumber_id"])
check("rss media:content", entri[0]["gambar_url"] == "https://cdn.example.com/a.jpg",
      entri[0]["gambar_url"])
check("rss tag html dibuang", "<" not in entri[0]["caption"], entri[0]["caption"])
check("rss caption utuh", "Bunga segar pagi ini." in entri[0]["caption"], entri[0]["caption"])
check("rss gambar dari description", entri[1]["gambar_url"] == "https://cdn.example.com/b.png",
      entri[1]["gambar_url"])
check("rss waktu dirapikan", entri[0]["waktu"].startswith("2026-11-14"),
      entri[0]["waktu"])

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Story</title>
  <entry>
    <title>Story hari ini</title>
    <id>tag:story,1</id>
    <link href="https://instagram.com/stories/1"/>
    <updated>2026-11-15T02:15:00Z</updated>
    <summary>Restock mawar</summary>
  </entry>
</feed>"""

entri = social_sync.parse_feed(ATOM)
check("atom jumlah entri", len(entri) == 1, len(entri))
check("atom tautan dari href", entri[0]["link"] == "https://instagram.com/stories/1",
      entri[0]["link"])
check("atom waktu iso", entri[0]["waktu"].startswith("2026-11-15"), entri[0]["waktu"])

JSONFEED = """{"version":"https://jsonfeed.org/version/1.1","items":[
  {"id":"1","url":"https://tiktok.com/@x/video/1","title":"Tips mawar",
   "content_text":"Rawat mawar dengan air bersih","date_published":"2026-11-15T03:00:00Z",
   "image":"https://cdn.example.com/c.jpg"}]}"""

entri = social_sync.parse_json_feed(JSONFEED)
check("jsonfeed jumlah", len(entri) == 1, len(entri))
check("jsonfeed gambar", entri[0]["gambar_url"] == "https://cdn.example.com/c.jpg",
      entri[0]["gambar_url"])

# Feed rusak harus menghasilkan ValueError yang bisa ditampilkan ke admin.
for nama, fungsi, isi in (("rss rusak", social_sync.parse_feed, "<bukan xml"),
                          ("json rusak", social_sync.parse_json_feed, "{bukan json"),
                          ("json tanpa items", social_sync.parse_json_feed, '{"a":1}')):
    try:
        fungsi(isi)
        errors.append((nama, "seharusnya ValueError"))
    except ValueError:
        pass

INSTAGRAM = {"data": [
    {"id": "1", "caption": "Feed foto", "media_type": "IMAGE",
     "media_url": "https://cdn.example.com/i1.jpg", "permalink": "https://instagram.com/p/1",
     "timestamp": "2026-11-15T01:00:00+0000"},
    {"id": "2", "caption": "Video", "media_type": "VIDEO",
     "media_url": "https://cdn.example.com/v2.mp4",
     "thumbnail_url": "https://cdn.example.com/v2.jpg",
     "permalink": "https://instagram.com/p/2", "timestamp": "2026-11-15T02:00:00+0000"},
]}
entri = social_sync.parse_instagram(INSTAGRAM)
check("instagram jumlah", len(entri) == 2, len(entri))
check("instagram gambar foto", entri[0]["gambar_url"] == "https://cdn.example.com/i1.jpg",
      entri[0]["gambar_url"])
# Video memakai sampul, bukan berkas .mp4-nya.
check("instagram video pakai thumbnail",
      entri[1]["gambar_url"] == "https://cdn.example.com/v2.jpg", entri[1]["gambar_url"])

try:
    social_sync.parse_instagram({"error": {"message": "Invalid token"}})
    errors.append(("instagram error", "seharusnya ValueError"))
except ValueError as exc:
    check("instagram pesan error disampaikan", "Invalid token" in str(exc), str(exc))


# --------------------------------------------------------------- ekstensi ----
check("ekstensi dari tipe", social_sync._ext_gambar("https://x/y", "image/jpeg") == "jpg")
check("ekstensi dari path", social_sync._ext_gambar("https://x/y.PNG", "") == "png")
# Tipe yang tidak didukung tidak disimpan agar folder unggahan tetap bersih.
check("ekstensi asing ditolak", social_sync._ext_gambar("https://x/y.svg", "image/svg+xml") == "")
check("ekstensi tanpa gambar", social_sync._ext_gambar("https://x/halaman", "text/html") == "")


# ---------------------------------------------------- sinkronisasi + simpan ----
SCHEMA_UJI = """
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE social_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT NOT NULL DEFAULT 'instagram',
    nama TEXT DEFAULT '', username TEXT DEFAULT '', url TEXT DEFAULT '', avatar TEXT DEFAULT '',
    sumber TEXT NOT NULL DEFAULT 'manual', feed_url TEXT DEFAULT '', story_url TEXT DEFAULT '',
    token TEXT DEFAULT '', sinkron_otomatis INTEGER NOT NULL DEFAULT 1,
    jumlah_feed INTEGER NOT NULL DEFAULT 12, jumlah_story INTEGER NOT NULL DEFAULT 10,
    aktif INTEGER NOT NULL DEFAULT 1, urutan INTEGER DEFAULT 0,
    terakhir_sinkron TEXT DEFAULT '', status_sinkron TEXT DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE social_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER NOT NULL,
    jenis TEXT NOT NULL DEFAULT 'feed', sumber_id TEXT DEFAULT '', judul TEXT DEFAULT '',
    caption TEXT DEFAULT '', gambar TEXT DEFAULT '', link TEXT DEFAULT '#',
    waktu TEXT DEFAULT '', urutan INTEGER DEFAULT 0, aktif INTEGER DEFAULT 1,
    created_at TEXT NOT NULL);
CREATE UNIQUE INDEX idx_uji_sumber ON social_items(account_id, jenis, sumber_id)
    WHERE sumber_id != '';
"""

tmp = tempfile.mkdtemp(prefix="rasty-social-test-")
db_path = os.path.join(tmp, "uji.db")
upload_dir = os.path.join(tmp, "uploads")
os.makedirs(upload_dir, exist_ok=True)

conn = sqlite3.connect(db_path)
conn.executescript(SCHEMA_UJI)
conn.execute("INSERT INTO settings (key, value) VALUES ('sosial_aktif', '1'),"
             " ('sosial_interval', '30'), ('sosial_terakhir_sinkron', '')")
conn.execute("INSERT INTO social_accounts (platform, nama, username, sumber, feed_url,"
             " sinkron_otomatis, aktif, urutan, created_at)"
             " VALUES ('instagram', 'Uji', 'uji', 'rss', 'https://contoh/feed.xml', 1, 1, 0,"
             " '2026-11-15 00:00:00')")
conn.commit()
conn.close()

# Gambar tidak benar-benar diunduh; fungsinya diganti agar uji tidak butuh
# jaringan, tetapi berkasnya tetap dibuat di disk supaya pemeriksaan "gambar
# sudah ada" ikut teruji.
_gambar_asli = social_sync.simpan_gambar
_unduhan_gambar = {"jumlah": 0}


def _gambar_palsu(url, folder, subdir="social"):
    if not url:
        return ""
    _unduhan_gambar["jumlah"] += 1
    os.makedirs(os.path.join(folder, subdir), exist_ok=True)
    nama = "%s/uji-%d.jpg" % (subdir, _unduhan_gambar["jumlah"])
    with open(os.path.join(folder, nama), "wb") as berkas:
        berkas.write(b"x")
    return nama


social_sync.simpan_gambar = _gambar_palsu

_unduh_asli = social_sync._unduh
social_sync._unduh = lambda url, timeout=20, maks=None: (RSS.encode(), "application/rss+xml")
ringkas = social_sync.sinkron_akun(1, db_path, upload_dir)
check("sinkron berhasil", ringkas["berhasil"], ringkas["pesan"])
check("sinkron mengisi feed", ringkas["feed"] == 2, ringkas["feed"])
# Feed tidak boleh dipakai sebagai cadangan story - isinya postingan, bukan story.
check("feed tidak disalin ke story", ringkas["story"] == 0, ringkas["story"])

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
baris = conn.execute("SELECT * FROM social_items ORDER BY id").fetchall()
check("item tersimpan", len(baris) == 2, len(baris))
check("gambar item tersimpan", baris[0]["gambar"].startswith("social/uji-"),
      baris[0]["gambar"])
akun = conn.execute("SELECT * FROM social_accounts WHERE id = 1").fetchone()
check("status sinkron dicatat", bool(akun["terakhir_sinkron"]), akun["terakhir_sinkron"])
gambar_awal = baris[0]["gambar"]
unduhan_awal = _unduhan_gambar["jumlah"]

# Sinkronisasi ulang harus memperbarui item yang sama, bukan menggandakannya,
# dan tidak mengunduh ulang gambar yang sudah tersimpan.
ringkas = social_sync.sinkron_akun(1, db_path, upload_dir)
jumlah = conn.execute("SELECT COUNT(*) AS c FROM social_items").fetchone()["c"]
check("sinkron ulang tidak menggandakan", jumlah == 2, jumlah)
check("gambar tidak diunduh ulang", _unduhan_gambar["jumlah"] == unduhan_awal,
      (_unduhan_gambar["jumlah"], unduhan_awal))
check("gambar lama dipertahankan",
      conn.execute("SELECT gambar FROM social_items WHERE id = ?",
                   (baris[0]["id"],)).fetchone()["gambar"] == gambar_awal)

# Item yang dimatikan admin tetap tersembunyi setelah sinkronisasi berikutnya.
conn.execute("UPDATE social_items SET aktif = 0 WHERE id = 1")
conn.commit()
social_sync.sinkron_akun(1, db_path, upload_dir)
aktif = conn.execute("SELECT aktif FROM social_items WHERE id = 1").fetchone()["aktif"]
check("item yang dimatikan tetap mati", aktif == 0, aktif)

# Story tarikan yang lewat 24 jam dibuang; story manual admin tidak disentuh.
conn.execute("INSERT INTO social_items (account_id, jenis, sumber_id, judul, gambar, link,"
             " waktu, urutan, aktif, created_at) VALUES"
             " (1, 'story', 'lama', 'Story lama', '', '#', '2020-01-01 00:00:00', 0, 1,"
             " '2020-01-01 00:00:00'),"
             " (1, 'story', '', 'Story manual', '', '#', '2020-01-01 00:00:00', 1, 1,"
             " '2020-01-01 00:00:00')")
conn.commit()
social_sync.sinkron_akun(1, db_path, upload_dir)
check("story kedaluwarsa dibuang",
      conn.execute("SELECT 1 FROM social_items WHERE sumber_id = 'lama'").fetchone() is None)
check("story manual dipertahankan",
      conn.execute("SELECT 1 FROM social_items WHERE judul = 'Story manual'").fetchone() is not None)

# Akun manual tidak menarik apa pun dan tidak menandai dirinya gagal.
conn.execute("UPDATE social_accounts SET sumber = 'manual', feed_url = '' WHERE id = 1")
conn.commit()
ringkas = social_sync.sinkron_akun(1, db_path, upload_dir)
check("akun manual berhasil tanpa tarikan", ringkas["berhasil"], ringkas["pesan"])
check("akun manual tidak menambah item", ringkas["feed"] == 0, ringkas["feed"])
conn.close()


# Feed yang gagal diunduh ditandai gagal, bukan melempar keluar.
def _gagal(url, timeout=20, maks=None):
    raise OSError("jaringan mati")


conn = sqlite3.connect(db_path)
conn.execute("UPDATE social_accounts SET sumber = 'rss', feed_url = 'https://contoh/feed.xml'"
             " WHERE id = 1")
conn.commit()
conn.close()
social_sync._unduh = _gagal
ringkas = social_sync.sinkron_akun(1, db_path, upload_dir)
check("kegagalan jaringan dilaporkan", not ringkas["berhasil"], ringkas)
check("kegagalan jaringan tidak melempar", isinstance(ringkas["pesan"], list))

# Jadwal: sinkronisasi terjadwal hanya berjalan sekali per selang waktu.
# Pengunduhan tetap memakai data contoh agar uji tidak menyentuh jaringan.
social_sync._unduh = lambda url, timeout=20, maks=None: (RSS.encode(), "application/rss+xml")
conn = sqlite3.connect(db_path)
conn.execute("UPDATE settings SET value = '' WHERE key = 'sosial_terakhir_sinkron'")
conn.commit()
conn.close()
pertama = social_sync.sinkron_terjadwal(db_path, upload_dir)
kedua = social_sync.sinkron_terjadwal(db_path, upload_dir)
check("sinkron terjadwal berjalan sekali", pertama is not None and kedua is None,
      (pertama is not None, kedua is not None))

# Akun yang tidak dicentang "Ikut sinkron otomatis" dilewati penjadwal, tetapi
# tombol "Sinkronkan Semua" di panel tetap menariknya saat diminta admin.
conn = sqlite3.connect(db_path)
conn.execute("UPDATE settings SET value = '' WHERE key = 'sosial_terakhir_sinkron'")
conn.execute("UPDATE social_accounts SET sinkron_otomatis = 0 WHERE id = 1")
conn.commit()
conn.close()
ringkas = social_sync.sinkron_terjadwal(db_path, upload_dir)
check("akun non-otomatis dilewati penjadwal",
      ringkas is not None and ringkas["akun"] == 0, ringkas)
check("sinkron semua tetap menarik akun non-otomatis",
      social_sync.sinkron_semua(db_path, upload_dir)["akun"] == 1)

# Menonaktifkan kontroler menghentikan sinkronisasi otomatis.
conn = sqlite3.connect(db_path)
conn.execute("UPDATE settings SET value = '' WHERE key = 'sosial_terakhir_sinkron'")
conn.execute("UPDATE settings SET value = '0' WHERE key = 'sosial_aktif'")
conn.commit()
conn.close()
check("kontroler nonaktif tidak sinkron",
      social_sync.sinkron_terjadwal(db_path, upload_dir) is None)

social_sync.simpan_gambar = _gambar_asli
social_sync._unduh = _unduh_asli

if errors:
    for e in errors:
        print("ERROR", e)
    sys.exit(1)
print("KONTROLER SOSIAL MEDIA OK")
