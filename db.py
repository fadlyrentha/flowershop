"""Skema basis data + seed data untuk Rasty Florist."""
import json
import os
import random
import re
import sqlite3
from datetime import datetime, timedelta

from flask import current_app, g
from werkzeug.security import generate_password_hash

ROLES = [
    ("pelanggan", "Pelanggan"),
    ("staff_admin", "Staff Admin"),
    ("staff_kantor", "Staff Kantor"),
    ("staff_gudang", "Staff Gudang"),
    ("staff_qc", "Staff Quality Kontrol"),
    ("staff_keuangan", "Staff Keuangan"),
    ("administrator", "Administrator"),
]
ROLE_LABEL = dict(ROLES)

ORDER_STATUS = [
    "Menunggu Konfirmasi",
    "Diproses",
    "Quality Kontrol",
    "Siap Kirim",
    "Dikirim",
    "Selesai",
    "Dibatalkan",
]
QC_STATUS = ["Belum Dicek", "Lolos QC", "Tidak Lolos"]

# Hari kerja untuk panel jam operasional.
HARI = [
    ("senin", "Senin"),
    ("selasa", "Selasa"),
    ("rabu", "Rabu"),
    ("kamis", "Kamis"),
    ("jumat", "Jumat"),
    ("sabtu", "Sabtu"),
    ("minggu", "Minggu"),
]

# Jam layanan bawaan per hari: (buka, tutup).
JAM_BAWAAN = {
    "senin": ("07:00", "19:00"),
    "selasa": ("07:00", "19:00"),
    "rabu": ("07:00", "19:00"),
    "kamis": ("07:00", "19:00"),
    "jumat": ("07:00", "19:00"),
    "sabtu": ("07:00", "19:00"),
    "minggu": ("08:00", "14:00"),
}

# Metode penyerahan barang ke pelanggan yang bisa diaktifkan administrator.
# (kunci pengaturan, label, keterangan)
PENGIRIMAN_METODE = [
    ("kirim_cod", "COD", "Bayar tunai saat produk diterima penerima."),
    ("kirim_kurir", "Kurir", "Diantar kurir internal toko ke alamat penerima."),
    ("kirim_cargo", "Cargo", "Dikirim lewat ekspedisi cargo untuk luar kota."),
    ("kirim_kib", "KIB", "Dikirim lewat kereta api (KIB) untuk pengiriman cepat."),
    ("kirim_travel", "Travel", "Dititipkan lewat jasa travel antar kota."),
]

# Menu navigasi halaman depan yang bisa disembunyikan administrator.
# (kunci pengaturan, label, keterangan)
MENU_PUBLIK = [
    ("nav_katalog", "Katalog", "Tautan menuju bagian katalog produk."),
    ("nav_stok", "Stok", "Tautan menuju tabel ketersediaan stok."),
    ("nav_testimoni", "Testimoni", "Tautan menuju karusel testimoni pelanggan."),
    ("nav_jam", "Jam Operasional", "Tautan menuju blok jam layanan."),
    ("nav_lacak", "Lacak Pesanan", "Tautan menuju halaman pelacakan pesanan."),
    ("nav_monitoring", "Monitoring", "Tautan menuju halaman monitoring mandiri."),
]

KODE_TAGIHAN = ["Reguler", "Abonemen IB", "Abonemen KK", "Abonemen KTR"]

# Kategori & kompensasi keluhan yang dikelola bagian keuangan.
KATEGORI_KELUHAN = ["Produk Rusak", "Produk Tidak Sesuai", "Keterlambatan Kirim",
                    "Salah Kirim", "Kualitas Bunga", "Lainnya"]
KOMPENSASI_KELUHAN = ["Tidak Ada", "Refund", "Pengganti Produk", "Voucher"]
STATUS_KELUHAN = ["Baru", "Ditinjau", "Proses", "Selesai"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    nama TEXT NOT NULL,
    role TEXT NOT NULL,
    telepon TEXT DEFAULT '',
    email TEXT DEFAULT '',
    alamat TEXT DEFAULT '',
    aktif INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS hero_slides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    judul TEXT NOT NULL,
    subjudul TEXT DEFAULT '',
    gambar TEXT DEFAULT '',
    teks_tombol TEXT DEFAULT 'Belanja Sekarang',
    link_tombol TEXT DEFAULT '/#katalog',
    urutan INTEGER DEFAULT 0,
    aktif INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT NOT NULL,
    deskripsi TEXT DEFAULT '',
    deskripsi_panjang TEXT DEFAULT '',
    rekomendasi TEXT DEFAULT '',
    ketentuan TEXT DEFAULT '',
    kategori TEXT DEFAULT 'Bunga Potong',
    harga INTEGER NOT NULL DEFAULT 0,
    stok INTEGER NOT NULL DEFAULT 0,
    stok_minimum INTEGER DEFAULT 5,
    min_order INTEGER NOT NULL DEFAULT 0,
    satuan TEXT DEFAULT 'ikat',
    gambar TEXT DEFAULT '',
    aktif INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS testimonials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT NOT NULL,
    isi TEXT NOT NULL,
    rating INTEGER DEFAULT 5,
    foto TEXT DEFAULT '',
    aktif INTEGER DEFAULT 1,
    urutan INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS social_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL DEFAULT 'instagram',
    judul TEXT DEFAULT '',
    gambar TEXT DEFAULT '',
    link TEXT DEFAULT '#',
    aktif INTEGER DEFAULT 1,
    urutan INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kode TEXT UNIQUE NOT NULL,
    user_id INTEGER,
    nama_pelanggan TEXT NOT NULL,
    telepon TEXT DEFAULT '',
    alamat TEXT DEFAULT '',
    catatan TEXT DEFAULT '',
    subtotal INTEGER NOT NULL DEFAULT 0,
    ongkir INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    metode_bayar TEXT DEFAULT 'Transfer Bank',
    status TEXT NOT NULL DEFAULT 'Menunggu Konfirmasi',
    status_bayar TEXT NOT NULL DEFAULT 'Belum Bayar',
    pengiriman TEXT DEFAULT 'Kurir',
    dibuat_oleh INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER,
    nama_produk TEXT NOT NULL,
    harga INTEGER NOT NULL DEFAULT 0,
    qty INTEGER NOT NULL DEFAULT 1,
    subtotal INTEGER NOT NULL DEFAULT 0,
    qc_status TEXT NOT NULL DEFAULT 'Belum Dicek',
    qc_catatan TEXT DEFAULT '',
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qc_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_item_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'Lolos QC',
    catatan TEXT DEFAULT '',
    foto TEXT DEFAULT '',
    video TEXT DEFAULT '',
    dicek_oleh INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (order_item_id) REFERENCES order_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kode TEXT UNIQUE NOT NULL,
    user_id INTEGER,
    order_id INTEGER,
    nama_pelanggan TEXT DEFAULT '',
    subjek TEXT NOT NULL,
    isi TEXT NOT NULL,
    foto TEXT DEFAULT '',
    video TEXT DEFAULT '',
    kategori TEXT DEFAULT 'Lainnya',
    kompensasi TEXT DEFAULT 'Tidak Ada',
    nominal INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'Baru',
    tanggapan TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    tipe TEXT NOT NULL,
    qty INTEGER NOT NULL,
    keterangan TEXT DEFAULT '',
    referensi TEXT DEFAULT '',
    dibuat_oleh INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomor TEXT UNIQUE NOT NULL,
    order_id INTEGER,
    user_id INTEGER,
    nama_pelanggan TEXT DEFAULT '',
    subtotal INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    ongkir INTEGER NOT NULL DEFAULT 0,
    kode_tagihan TEXT NOT NULL DEFAULT 'Reguler',
    status TEXT NOT NULL DEFAULT 'Belum Dibayar',
    jatuh_tempo TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER,
    order_id INTEGER,
    metode TEXT NOT NULL DEFAULT 'Transfer Bank',
    jumlah INTEGER NOT NULL DEFAULT 0,
    bukti TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Menunggu Verifikasi',
    catatan TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS finance_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipe TEXT NOT NULL,
    kategori TEXT NOT NULL,
    keterangan TEXT DEFAULT '',
    jumlah INTEGER NOT NULL DEFAULT 0,
    tanggal TEXT NOT NULL,
    dibuat_oleh INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shipments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    nama_penerima TEXT DEFAULT '',
    alamat TEXT DEFAULT '',
    kurir TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Menunggu Diambil',
    keterangan TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT DEFAULT '',
    user_id INTEGER,
    judul TEXT NOT NULL,
    pesan TEXT DEFAULT '',
    link TEXT DEFAULT '',
    dibaca INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS role_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    feature TEXT NOT NULL,
    aktif INTEGER NOT NULL DEFAULT 1,
    UNIQUE (role, feature)
);

CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_moves_product ON stock_moves(product_id);
"""

DEFAULT_SETTINGS = {
    "nama_toko": "Rasty Florist",
    "tagline": "Supplier Bunga Potong Segar",
    "deskripsi": (
        "Rasty Florist adalah supplier bunga potong segar untuk florist, dekorasi "
        "acara, hotel, dan kebutuhan harian. Bunga dipilih langsung dari kebun "
        "setiap pagi sehingga kesegaran terjaga hingga sampai di tangan Anda."
    ),
    "alamat": "Jl. Melati Indah No. 27, Bandung, Jawa Barat",
    "telepon": "0812-3456-7890",
    "email": "halo@rastyflorist.id",
    "instagram": "https://instagram.com/rastyflorist",
    "tiktok": "https://tiktok.com/@rastyflorist",
    "whatsapp": "6281234567890",
    "jam_buka_senin": "07:00",
    "jam_tutup_senin": "19:00",
    "jam_buka_selasa": "07:00",
    "jam_tutup_selasa": "19:00",
    "jam_buka_rabu": "07:00",
    "jam_tutup_rabu": "19:00",
    "jam_buka_kamis": "07:00",
    "jam_tutup_kamis": "19:00",
    "jam_buka_jumat": "07:00",
    "jam_tutup_jumat": "19:00",
    "jam_buka_sabtu": "07:00",
    "jam_tutup_sabtu": "19:00",
    "jam_buka_minggu": "08:00",
    "jam_tutup_minggu": "14:00",
    "sameday_aktif": "1",
    "sameday_batas_jam": "14:00",
    "sameday_hari": json.dumps(["senin", "selasa", "rabu", "kamis", "jumat", "sabtu"]),
    "sameday_info": (
        "Pesanan sebelum pukul 14.00 WIB dikirim di hari yang sama untuk area "
        "Bandung dan sekitarnya. Gratis ongkir untuk pembelian minimal Rp 500.000."
    ),
    "kirim_cod": "1",
    "kirim_kurir": "1",
    "kirim_cargo": "1",
    "kirim_kib": "1",
    "kirim_travel": "1",
    "nav_katalog": "1",
    "nav_stok": "1",
    "nav_testimoni": "1",
    "nav_jam": "1",
    "nav_lacak": "1",
    "nav_monitoring": "1",
    "warna_primer": "#b3204f",
    "warna_sekunder": "#f7e4ea",
    "logo": "",
    "footer_text": "Rasty Florist - Bunga segar setiap hari.",
    "template_invoice": "klasik",
    "template_invoice_file": "",
    "invoice_logo_tampil": "1",
    "invoice_logo_ukuran": "sedang",
    "backup_jadwal": "off",
    "backup_terakhir": "",
    "restore_terakhir": "",
    "update_terakhir": "",
    "update_cek_terakhir": "",
    "update_versi_github": "",
    "format_nomor_order": "INV{YYYY}{MM}{DD}-{SEQ:4}",
    "format_nomor_faktur": "FK{YYYY}{MM}{DD}-{SEQ:4}",
    "format_nomor_invoice": "INV{YYYY}{MM}{DD}-{SEQ:4}",
    "format_nomor_keluhan": "CMP{YYYY}{MM}{DD}-{SEQ:4}",
    "format_nomor_transaksi": "TRX{YYYY}{MM}{DD}-{SEQ:4}",
    "format_nomor_verifikasi": "VRF{YYYY}{MM}{DD}-{SEQ:4}",
    "format_nomor_lacak": "LACAK{YYYY}{MM}{DD}-{SEQ:4}",
    "rekening_bank": "Bank BCA · 1234567890 · a.n. Rasty Florist",
    "tampil_rekening": "1",
    "katalog_hero": "1",
    "katalog_produk": "1",
    "katalog_stok": "1",
    "katalog_jam": "1",
    "katalog_testimoni": "1",
    "katalog_sosial": "1",
}

# Ukuran logo di kop faktur/invoice. (kunci, label, tinggi px)
INVOICE_LOGO_UKURAN = [
    ("kecil", "Kecil", 40),
    ("sedang", "Sedang", 64),
    ("besar", "Besar", 96),
]


def invoice_logo_px(settings=None):
    """Tinggi logo faktur dalam piksel sesuai pengaturan ukuran."""
    ukuran = (settings or all_settings()).get("invoice_logo_ukuran", "sedang")
    for kunci, _label, px in INVOICE_LOGO_UKURAN:
        if kunci == ukuran:
            return px
    return 64


# Kolom katalog beranda yang bisa diaktifkan/dinonaktifkan administrator.
# (kunci pengaturan, label, penjelasan)
KATALOG_SEKSI = [
    ("katalog_hero", "Hero Slider", "Banner bergambar besar di bagian paling atas beranda."),
    ("katalog_produk", "Katalog Bunga", "Grid produk bunga potong beserta pencarian dan filter."),
    ("katalog_stok", "Ketersediaan Stok", "Tabel katalog stok produk yang diperbarui harian."),
    ("katalog_jam", "Jam Operasional & Same Day Delivery",
     "Blok jam layanan, tombol telepon, dan info kirim hari yang sama."),
    ("katalog_testimoni", "Testimoni Pelanggan", "Karusel ulasan dari florist, hotel, dan pelanggan."),
    ("katalog_sosial", "Sosial Media", "Karusel konten Instagram dan TikTok."),
]


def katalog_tampil(key):
    """True bila kolom katalog beranda sedang diaktifkan administrator."""
    return get_setting(key, DEFAULT_SETTINGS.get(key, "1")) == "1"


def katalog_aktif():
    return {key: katalog_tampil(key) for key, _label, _ket in KATALOG_SEKSI}


def katalog_dari(settings):
    """Sama seperti katalog_aktif() tetapi memakai dict pengaturan yang sudah dibaca."""
    return {key: settings.get(key, "1") == "1" for key, _label, _ket in KATALOG_SEKSI}


# ------------------------------------------------------------- pengiriman ----
def pengiriman_metode(settings=None):
    """Daftar metode pengiriman aktif. Selalu menyisakan minimal satu metode."""
    data = settings or all_settings()
    aktif = [label for key, label, _ket in PENGIRIMAN_METODE
             if data.get(key, "1") == "1"]
    return aktif or [PENGIRIMAN_METODE[1][1]]


def pengiriman_aktif(settings=None):
    data = settings or all_settings()
    return {key: data.get(key, "1") == "1" for key, _label, _ket in PENGIRIMAN_METODE}


def pengiriman_valid(nilai, settings=None):
    """Cara pengiriman harus termasuk metode yang diaktifkan administrator."""
    return nilai == "Diambil" or nilai in pengiriman_metode(settings)


def pengiriman_pilihan(nilai, settings=None):
    """Pakai nilai kiriman bila masih aktif, jika tidak jatuh ke Kurir lalu metode pertama."""
    if pengiriman_valid(nilai, settings):
        return nilai
    aktif = pengiriman_metode(settings)
    return "Kurir" if "Kurir" in aktif else aktif[0]


def ongkir_untuk(cara, subtotal):
    """COD dan pengambilan di toko tidak dikenakan ongkir kurir."""
    if subtotal >= 500000 or cara in ("Diambil", "COD"):
        return 0
    return 25000


# ------------------------------------------------------- jam operasional ----
def jam_harian(settings=None):
    """Dict hari -> (buka, tutup) sesuai panel jam operasional."""
    data = settings or all_settings()
    hasil = {}
    for key, _label in HARI:
        buka, tutup = JAM_BAWAAN[key]
        hasil[key] = (data.get("jam_buka_" + key, buka), data.get("jam_tutup_" + key, tutup))
    return hasil


def jam_dari(settings):
    return {key: (settings.get("jam_buka_" + key, JAM_BAWAAN[key][0]),
                  settings.get("jam_tutup_" + key, JAM_BAWAAN[key][1]))
            for key, _label in HARI}


def _jam_teks(nilai):
    """'07:00' -> '07.00'."""
    return nilai.replace(":", ".")


def jam_daftar(settings=None):
    """Baris jam layanan siap tampil: hari, label, dan rentang jam."""
    data = settings or all_settings()
    jam = jam_dari(data)
    rows = []
    for key, label in HARI:
        buka, tutup = jam[key]
        rows.append({
            "key": key,
            "label": label,
            "buka": buka,
            "tutup": tutup,
            "tutup_hari": buka == tutup or not buka or not tutup,
            "teks": "%s – %s WIB" % (_jam_teks(buka), _jam_teks(tutup)),
        })
    return rows


def jam_ringkas(settings=None):
    """Kelompokkan hari berurutan yang jamnya sama: [(label, teks jam), ...]."""
    rows = jam_daftar(settings)
    grup = []
    for row in rows:
        nilai = "Tutup" if row["tutup_hari"] else row["teks"]
        if grup and grup[-1][1] == nilai:
            grup[-1][2] = row["label"]
        else:
            grup.append([row["label"], nilai, row["label"]])
    hasil = []
    for awal, nilai, akhir in grup:
        label = awal if awal == akhir else "%s – %s" % (awal, akhir)
        hasil.append((label, nilai))
    return hasil


def toko_buka(settings=None, saat=None):
    """True bila jam sekarang berada di rentang layanan hari ini."""
    saat = saat or datetime.now()
    key = HARI[saat.weekday()][0]
    buka, tutup = jam_harian(settings)[key]
    try:
        jam_buka = datetime.strptime(buka, "%H:%M").time()
        jam_tutup = datetime.strptime(tutup, "%H:%M").time()
    except ValueError:
        return False
    return jam_buka <= saat.time() <= jam_tutup


def sameday_hari(settings=None):
    """Daftar kunci hari yang dilayani same day delivery."""
    data = settings or all_settings()
    try:
        daftar = json.loads(data.get("sameday_hari", "[]"))
    except (TypeError, ValueError):
        daftar = []
    kunci = [key for key, _label in HARI]
    return [k for k in daftar if k in kunci]


def sameday_tersedia(settings=None, saat=None):
    """Same day bisa dipakai bila fitur aktif dan sekarang sebelum batas jam."""
    saat = saat or datetime.now()
    data = settings or all_settings()
    if data.get("sameday_aktif", "1") != "1":
        return False
    key = HARI[saat.weekday()][0]
    if key not in sameday_hari(data):
        return False
    try:
        batas = datetime.strptime(data.get("sameday_batas_jam", "14:00"), "%H:%M").time()
    except ValueError:
        return False
    return saat.time() <= batas


# ------------------------------------------------------------ menu publik ----
def menu_publik(settings=None):
    data = settings or all_settings()
    return {key: data.get(key, "1") == "1" for key, _label, _ket in MENU_PUBLIK}

# Format nomor dokumen: (kunci pengaturan, tabel, kolom, label, contoh)
NOMOR_FORMAT = {
    "nomor_order": ("format_nomor_order", "orders", "kode", "Nomor Order"),
    "nomor_faktur": ("format_nomor_faktur", "invoices", "nomor", "Nomor Faktur"),
    "nomor_invoice": ("format_nomor_invoice", "invoices", "nomor_invoice", "Nomor Invoice"),
    "nomor_keluhan": ("format_nomor_keluhan", "complaints", "kode", "Nomor Keluhan"),
    "nomor_transaksi": ("format_nomor_transaksi", "payments", "kode", "Nomor Transaksi"),
    "nomor_verifikasi": ("format_nomor_verifikasi", "payments", "kode_verifikasi",
                         "Nomor Verifikasi Pembayaran"),
    "nomor_lacak": ("format_nomor_lacak", "orders", "kode_lacak", "Nomor ID Lacak"),
}

# Token yang boleh dipakai di format nomor.
TOKEN_RE = re.compile(r"\{(YYYY|YY|MM|DD|SEQ(?::\d+)?|RAND(?::\d+)?)\}")


def _token_value(token, seq=None, rand=None):
    now = datetime.now()
    if token == "YYYY":
        return now.strftime("%Y")
    if token == "YY":
        return now.strftime("%y")
    if token == "MM":
        return now.strftime("%m")
    if token == "DD":
        return now.strftime("%d")
    if token.startswith("SEQ"):
        width = int(token.split(":")[1]) if ":" in token else 4
        return str(seq or 0).zfill(width)
    if token.startswith("RAND"):
        width = int(token.split(":")[1]) if ":" in token else 4
        return str(rand if rand is not None else random.randint(0, 10 ** width - 1)).zfill(width)
    return ""


def render_nomor(template, seq=None, rand=None):
    parts = TOKEN_RE.split(template)
    out = []
    for i, part in enumerate(parts):
        out.append(_token_value(part, seq, rand) if i % 2 else part)
    return "".join(out)


def _nomor_regex(template):
    parts = TOKEN_RE.split(template)
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            out.append(re.escape(part))
        elif part.startswith("SEQ"):
            out.append(r"(\d+)")
        elif part.startswith("RAND"):
            out.append(r"\d+")
        elif part == "YYYY":
            out.append(r"\d{4}")
        else:
            out.append(r"\d{2}")
    return re.compile("^" + "".join(out) + "$")


def valid_nomor_format(template):
    """Format wajib memakai token {SEQ} atau {RAND} agar nomor unik."""
    if not template:
        return False
    tokens = TOKEN_RE.findall(template)
    return any(t.startswith("SEQ") or t.startswith("RAND") for t in tokens)


def next_number(key):
    """Buat nomor berikutnya sesuai format yang disimpan administrator."""
    setting, table, column = NOMOR_FORMAT[key][:3]
    template = get_setting(setting, DEFAULT_SETTINGS[setting])
    if not valid_nomor_format(template):
        template = DEFAULT_SETTINGS[setting]
    rx = _nomor_regex(template)
    maxseq = 0
    for row in query("SELECT %s AS v FROM %s" % (column, table)):
        match = rx.match(row["v"] or "")
        if match and match.groups():
            try:
                maxseq = max(maxseq, int(match.group(1)))
            except ValueError:
                continue
    for _ in range(50):
        nomor = render_nomor(template, seq=maxseq + 1)
        if not query("SELECT 1 FROM %s WHERE %s = ? LIMIT 1" % (table, column),
                     (nomor,), one=True):
            return nomor
        maxseq += 1
    return render_nomor(template, rand=random.randint(0, 9999))


# Jumlah hari antar backup otomatis untuk tiap pilihan jadwal.
BACKUP_JADWAL = {
    "harian": 1,
    "mingguan": 7,
    "bulanan": 30,
    "tahunan": 365,
}


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today():
    return datetime.now().strftime("%Y-%m-%d")


class Row(dict):
    """Baris hasil query: bisa diakses sebagai dict maupun atribut."""

    __slots__ = ()

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=30)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        # busy_timeout bersifat per-koneksi dan wajib: saat aplikasi dilayani
        # beberapa proses (gunicorn), penulisan bersamaan tanpa ini langsung
        # gagal dengan "database is locked".
        g.db.execute("PRAGMA busy_timeout = 30000")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = [Row(r) for r in cur.fetchall()]
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    last = cur.lastrowid
    cur.close()
    return last


def get_setting(key, default=""):
    row = query("SELECT value FROM settings WHERE key = ?", (key,), one=True)
    return row["value"] if row and row["value"] is not None else default


def all_settings():
    data = dict(DEFAULT_SETTINGS)
    for row in query("SELECT key, value FROM settings"):
        data[row["key"]] = row["value"]
    return data


def set_setting(key, value):
    execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def init_db():
    db = get_db()
    # WAL bersifat menetap di berkas database, jadi cukup diatur sekali di sini.
    # Membuat pembaca tidak memblokir penulis - penting saat nginx/gunicorn
    # melayani beberapa permintaan sekaligus.
    db.execute("PRAGMA journal_mode = WAL")
    db.executescript(SCHEMA)
    db.commit()
    _migrate(db)
    for key, value in DEFAULT_SETTINGS.items():
        execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    seed_features()


# ---------------------------------------------------------------- backup ----
def backup_dir():
    folder = os.environ.get("RASTY_BACKUP_FOLDER") or os.path.join(current_app.root_path, "backups")
    os.makedirs(folder, exist_ok=True)
    return folder


def create_backup(label="manual"):
    """Salin database ke berkas .db di folder backups. Mengembalikan nama berkas."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = "rasty-%s-%s.db" % (label, stamp)
    target = os.path.join(backup_dir(), name)
    source = sqlite3.connect(current_app.config["DATABASE"])
    dest = sqlite3.connect(target)
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()
    set_setting("backup_terakhir", now())
    return name


def list_backups():
    rows = []
    for name in os.listdir(backup_dir()):
        if not name.endswith(".db"):
            continue
        path = os.path.join(backup_dir(), name)
        stat = os.stat(path)
        rows.append({
            "nama": name,
            "ukuran": stat.st_size,
            "dibuat": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "_mtime": stat.st_mtime,
        })
    rows.sort(key=lambda r: r["_mtime"], reverse=True)
    for row in rows:
        row.pop("_mtime")
    return rows


def delete_backup(name):
    if os.path.basename(name) != name or not name.endswith(".db"):
        return False
    path = os.path.join(backup_dir(), name)
    if not os.path.isfile(path):
        return False
    os.remove(path)
    return True


def backup_path(name):
    if os.path.basename(name) != name or not name.endswith(".db"):
        return None
    path = os.path.join(backup_dir(), name)
    return path if os.path.isfile(path) else None


def auto_backup():
    """Buat backup bila jadwal otomatis sudah jatuh tempo."""
    jadwal = get_setting("backup_jadwal", "off")
    if jadwal not in BACKUP_JADWAL:
        return None
    terakhir = get_setting("backup_terakhir", "")
    if terakhir:
        try:
            last = datetime.strptime(terakhir, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            last = None
        if last and (datetime.now() - last).days < BACKUP_JADWAL[jadwal]:
            return None
    return create_backup(jadwal)


# Tabel yang harus ada agar sebuah berkas .db dianggap backup aplikasi ini.
TABEL_WAJIB_BACKUP = ("users", "products", "orders", "order_items", "invoices",
                      "settings", "role_features")


def periksa_backup(path):
    """Periksa berkas backup sebelum dipulihkan. Mengembalikan (valid, pesan).

    Selain integritas SQLite, tabel inti diperiksa supaya berkas asing tidak
    bisa menimpa database toko.
    """
    try:
        conn = sqlite3.connect(path)
        try:
            hasil = conn.execute("PRAGMA integrity_check").fetchone()
            if not hasil or hasil[0] != "ok":
                return False, "Berkas rusak: pemeriksaan integritas database gagal."
            tabel = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
            hilang = [t for t in TABEL_WAJIB_BACKUP if t not in tabel]
            if hilang:
                return False, ("Berkas ini bukan backup Rasty Florist "
                               "(tabel %s tidak ditemukan)." % ", ".join(hilang))
            akun = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            produk = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as exc:
        return False, "Berkas tidak bisa dibaca sebagai database: %s" % exc
    return True, "%d akun dan %d produk" % (akun, produk)


def pulihkan_backup(path):
    """Ganti database aktif dengan isi berkas backup.

    Keadaan sekarang dicadangkan lebih dulu dengan label 'sebelum-restore',
    sehingga pemulihan yang salah pilih masih bisa dibatalkan. Mengembalikan
    (berhasil, pesan).
    """
    valid, pesan = periksa_backup(path)
    if not valid:
        return False, pesan
    # Cadangan dibuat SEBELUM database ditimpa, jadi berkasnya berisi keadaan
    # sekarang. Penanda backup_terakhir yang ditulis create_backup() ikut
    # hilang bersama database lama; nilai yang berlaku setelah pemulihan
    # adalah nilai milik database backup itu sendiri.
    cadangan = create_backup("sebelum-restore")
    # Tutup koneksi request ini dulu agar berkas database tidak sedang dipegang
    # saat isinya ditimpa.
    aktif = g.pop("db", None)
    if aktif is not None:
        aktif.close()
    sumber = sqlite3.connect(path)
    tujuan = sqlite3.connect(current_app.config["DATABASE"], timeout=30)
    try:
        sumber.backup(tujuan)
    finally:
        tujuan.close()
        sumber.close()
    # Akun yang sedang login bisa saja tidak ada di database pulihan, jadi
    # cache pengguna di request ini harus dibuang.
    g.pop("user", None)
    # Jalankan migrasi agar struktur database pulihan sesuai versi aplikasi ini.
    init_db()
    set_setting("restore_terakhir", now())
    return True, ("Database dipulihkan (%s). Cadangan keadaan sebelumnya: %s"
                  % (pesan, cadangan))


# ------------------------------------------------------------------ reset ----
# Bagian yang bisa dikembalikan ke pengaturan bawaan lewat menu Reset.
RESET_BAGIAN = [
    ("pengaturan", "Pengaturan Website",
     "Nama toko, tagline, kontak, warna, jam operasional, format nomor, dan rekening bank "
     "kembali ke nilai bawaan."),
    ("katalog", "Kolom Katalog Beranda",
     "Semua kolom katalog (hero, produk, stok, jam, testimoni, sosial) diaktifkan kembali."),
    ("pengiriman", "Metode Pengiriman",
     "COD, Kurir, Cargo, KIB, dan Travel diaktifkan kembali."),
    ("jam_operasional", "Jam Operasional & Same Day Delivery",
     "Jam layanan tiap hari dan pengaturan same day delivery kembali ke nilai bawaan."),
    ("menu_publik", "Menu Halaman Depan",
     "Seluruh menu navigasi di halaman depan ditampilkan kembali."),
    ("cms", "Isi Beranda (CMS)",
     "Slider hero, testimoni, dan konten sosial media diganti dengan data contoh bawaan."),
    ("hak_akses", "Hak Akses Peran",
     "Hak akses seluruh peran kembali ke susunan bawaan aplikasi."),
]


def reset_pengaturan():
    """Kembalikan seluruh pengaturan situs ke nilai bawaan."""
    berkas = get_setting("template_invoice_file", "")
    if berkas:
        path = os.path.join(current_app.config["UPLOAD_FOLDER"], berkas)
        if os.path.isfile(path):
            os.remove(path)
    for key, value in DEFAULT_SETTINGS.items():
        set_setting(key, value)
    return len(DEFAULT_SETTINGS)


def reset_katalog():
    """Aktifkan kembali semua kolom katalog beranda."""
    for key, _label, _ket in KATALOG_SEKSI:
        set_setting(key, "1")
    return len(KATALOG_SEKSI)


def reset_pengiriman():
    """Aktifkan kembali semua metode pengiriman."""
    for key, _label, _ket in PENGIRIMAN_METODE:
        set_setting(key, "1")
    return len(PENGIRIMAN_METODE)


def reset_jam_operasional():
    """Kembalikan jam layanan harian dan pengaturan same day ke nilai bawaan."""
    kunci = ["sameday_aktif", "sameday_batas_jam", "sameday_hari"]
    for key, _label in HARI:
        kunci += ["jam_buka_" + key, "jam_tutup_" + key]
    for key in kunci:
        set_setting(key, DEFAULT_SETTINGS[key])
    return len(kunci)


def reset_menu_publik():
    """Tampilkan kembali seluruh menu navigasi halaman depan."""
    for key, _label, _ket in MENU_PUBLIK:
        set_setting(key, "1")
    return len(MENU_PUBLIK)


def reset_cms():
    """Ganti isi beranda dengan data contoh bawaan."""
    for table in ("hero_slides", "testimonials", "social_posts"):
        execute("DELETE FROM %s" % table)
    for judul, subjudul, teks, link in HERO_SEED:
        execute(
            "INSERT INTO hero_slides (judul, subjudul, teks_tombol, link_tombol, urutan, aktif)"
            " VALUES (?, ?, ?, ?, 0, 1)", (judul, subjudul, teks, link))
    for i, (nama, isi, rating) in enumerate(TESTIMONIAL_SEED):
        execute("INSERT INTO testimonials (nama, isi, rating, aktif, urutan) VALUES (?, ?, ?, 1, ?)",
                (nama, isi, rating, i))
    for i, (platform, judul, link) in enumerate(SOCIAL_SEED):
        execute("INSERT INTO social_posts (platform, judul, link, aktif, urutan) VALUES (?, ?, ?, 1, ?)",
                (platform, judul, link, i))
    return len(HERO_SEED) + len(TESTIMONIAL_SEED) + len(SOCIAL_SEED)


def reset_hak_akses():
    """Kembalikan hak akses seluruh peran ke susunan bawaan."""
    execute("DELETE FROM role_features")
    seed_features()
    return sum(len(f) for f in BASE_FEATURES.values())


RESET_AKSI = {
    "pengaturan": reset_pengaturan,
    "katalog": reset_katalog,
    "pengiriman": reset_pengiriman,
    "jam_operasional": reset_jam_operasional,
    "menu_publik": reset_menu_publik,
    "cms": reset_cms,
    "hak_akses": reset_hak_akses,
}


def _migrate(db):
    cols = {r["name"] for r in db.execute("PRAGMA table_info(invoices)")}
    if "kode_tagihan" not in cols:
        db.execute("ALTER TABLE invoices ADD COLUMN kode_tagihan TEXT NOT NULL DEFAULT 'Reguler'")
        db.commit()
    if "nomor_invoice" not in cols:
        db.execute("ALTER TABLE invoices ADD COLUMN nomor_invoice TEXT DEFAULT ''")
        db.commit()
    cols = {r["name"] for r in db.execute("PRAGMA table_info(payments)")}
    if "kode" not in cols:
        db.execute("ALTER TABLE payments ADD COLUMN kode TEXT DEFAULT ''")
        db.commit()
    if "kode_verifikasi" not in cols:
        db.execute("ALTER TABLE payments ADD COLUMN kode_verifikasi TEXT DEFAULT ''")
        db.commit()
    cols = {r["name"] for r in db.execute("PRAGMA table_info(orders)")}
    if "kode_lacak" not in cols:
        db.execute("ALTER TABLE orders ADD COLUMN kode_lacak TEXT DEFAULT ''")
        db.commit()
    cols = {r["name"] for r in db.execute("PRAGMA table_info(complaints)")}
    if "kategori" not in cols:
        db.execute("ALTER TABLE complaints ADD COLUMN kategori TEXT DEFAULT 'Lainnya'")
        db.commit()
    if "kompensasi" not in cols:
        db.execute("ALTER TABLE complaints ADD COLUMN kompensasi TEXT DEFAULT 'Tidak Ada'")
        db.commit()
    if "nominal" not in cols:
        db.execute("ALTER TABLE complaints ADD COLUMN nominal INTEGER NOT NULL DEFAULT 0")
        db.commit()
    # Staff Keuangan mendapat menu konfirmasi order, data pesanan, dan cetak label.
    done = db.execute("SELECT value FROM settings WHERE key = 'migrasi_keuangan_pesanan'").fetchone()
    if not done:
        for feature in ("pesanan", "konfirmasi_order", "label"):
            db.execute(
                "INSERT OR IGNORE INTO role_features (role, feature, aktif) VALUES ('staff_keuangan', ?, 1)",
                (feature,))
        db.execute("INSERT OR REPLACE INTO settings (key, value)"
                   " VALUES ('migrasi_keuangan_pesanan', '1')")
        db.commit()
    # Cetak PO/Invoice pelanggan dinonaktifkan sekali saja (bisa diubah lewat Hak Akses).
    done = db.execute("SELECT value FROM settings WHERE key = 'migrasi_invoice_pelanggan'").fetchone()
    if not done:
        db.execute("UPDATE role_features SET aktif = 0 WHERE role = 'pelanggan' AND feature = 'invoice'")
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('migrasi_invoice_pelanggan', '1')")
        db.commit()
    # Cara pengiriman lama "Dikirim" diganti nama metode yang kini bisa dikonfigurasi.
    done = db.execute("SELECT value FROM settings WHERE key = 'migrasi_metode_pengiriman'").fetchone()
    if not done:
        db.execute("UPDATE orders SET pengiriman = 'Kurir' WHERE pengiriman IN ('Dikirim', '')")
        db.execute("INSERT OR REPLACE INTO settings (key, value)"
                   " VALUES ('migrasi_metode_pengiriman', '1')")
        db.commit()
    cols = {r["name"] for r in db.execute("PRAGMA table_info(products)")}
    if "min_order" not in cols:
        db.execute("ALTER TABLE products ADD COLUMN min_order INTEGER NOT NULL DEFAULT 0")
        db.commit()
    for kolom in ("deskripsi_panjang", "rekomendasi", "ketentuan"):
        if kolom not in cols:
            db.execute("ALTER TABLE products ADD COLUMN %s TEXT DEFAULT ''" % kolom)
            db.commit()
    cols = {r["name"] for r in db.execute("PRAGMA table_info(invoices)")}
    if "subtotal" not in cols:
        db.execute("ALTER TABLE invoices ADD COLUMN subtotal INTEGER NOT NULL DEFAULT 0")
        db.commit()
    if "ongkir" not in cols:
        db.execute("ALTER TABLE invoices ADD COLUMN ongkir INTEGER NOT NULL DEFAULT 0")
        db.commit()
    # Faktur lama: isi rincian dari order terkait agar kolom faktur tidak kosong.
    if "migrasi_faktur_ongkir" not in {r["key"] for r in db.execute("SELECT key FROM settings")}:
        db.execute("UPDATE invoices SET"
                   " ongkir = COALESCE((SELECT o.ongkir FROM orders o WHERE o.id = invoices.order_id),"
                   "                   invoices.ongkir),"
                   " subtotal = COALESCE((SELECT o.subtotal FROM orders o WHERE o.id = invoices.order_id),"
                   "                     MAX(0, invoices.total - invoices.ongkir))")
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('migrasi_faktur_ongkir', '1')")
        db.commit()
    # Panel konfigurasi baru: sediakan baris hak akses agar menunya langsung tampil.
    done = db.execute("SELECT value FROM settings WHERE key = 'migrasi_konfigurasi_panel'").fetchone()
    if not done:
        for feature in ("pengiriman_metode", "jam_operasional", "menu_publik"):
            db.execute(
                "INSERT OR IGNORE INTO role_features (role, feature, aktif)"
                " VALUES ('administrator', ?, 1)", (feature,))
        db.execute("INSERT OR REPLACE INTO settings (key, value)"
                   " VALUES ('migrasi_konfigurasi_panel', '1')")
        db.commit()


# ---------------------------------------------------------------- features ----
BASE_FEATURES = {
    "pelanggan": [
        "dashboard", "profil", "pesanan_baru", "pesanan", "lacak",
        "komplain", "notifikasi", "monitoring_mandiri",
    ],
    "staff_admin": [
        "dashboard", "profil", "pelanggan", "pesanan_baru", "pesanan", "produk", "stok",
        "komplain", "notifikasi", "label", "qc_list", "laporan",
        "konfirmasi_order", "monitoring", "monitoring_harian", "monitoring_mandiri",
    ],
    "staff_kantor": [
        "dashboard", "profil", "pelanggan", "pesanan", "produk", "stok", "stok_mutasi",
        "komplain", "cms", "laporan", "notifikasi", "label", "monitoring",
        "monitoring_harian", "monitoring_mandiri",
    ],
    "staff_gudang": [
        "dashboard", "profil", "pesanan", "stok", "stok_mutasi", "produk", "qc_list",
        "notifikasi", "label", "monitoring", "monitoring_harian", "monitoring_mandiri",
    ],
    "staff_qc": [
        "dashboard", "profil", "qc_verifikasi", "komplain", "pengiriman", "notifikasi",
        "monitoring", "monitoring_harian", "ganti_produk", "monitoring_mandiri",
    ],
    "staff_keuangan": [
        "dashboard", "profil", "qc_list", "label", "pesanan_baru", "pesanan",
        "konfirmasi_order", "faktur", "pembayaran", "keluhan", "stok", "laporan", "produk",
        "rekening", "notifikasi", "monitoring", "monitoring_harian", "monitoring_mandiri",
    ],
    "administrator": [
        "dashboard", "profil", "pelanggan", "pesanan", "produk", "stok", "stok_mutasi",
        "komplain", "cms", "pengaturan", "laporan", "faktur", "pembayaran",
        "qc_verifikasi", "qc_list", "pengiriman", "akun_staff", "hak_akses",
        "notifikasi", "label", "konfirmasi_order", "format_nomor", "monitoring",
        "monitoring_harian", "monitoring_mandiri", "ganti_produk", "template_invoice",
        "backup", "katalog_seksi", "rekening", "reset",
        "pengiriman_metode", "jam_operasional", "menu_publik", "update",
    ],
}

# Fitur yang bawaannya nonaktif walau terdaftar di BASE_FEATURES peran tersebut.
FEATURE_BAWAAN_OFF = {
    ("pelanggan", "monitoring_mandiri"),
    ("staff_qc", "monitoring_mandiri"),
    ("staff_keuangan", "monitoring_mandiri"),
}


def seed_features():
    for role, features in BASE_FEATURES.items():
        for feature in features:
            execute(
                "INSERT OR IGNORE INTO role_features (role, feature, aktif) VALUES (?, ?, ?)",
                (role, feature, 0 if (role, feature) in FEATURE_BAWAAN_OFF else 1),
            )


def feature_enabled(role, feature):
    row = query(
        "SELECT aktif FROM role_features WHERE role = ? AND feature = ?",
        (role, feature),
        one=True,
    )
    return bool(row and row["aktif"])


def role_features(role):
    return {r["feature"]: bool(r["aktif"]) for r in query(
        "SELECT feature, aktif FROM role_features WHERE role = ?", (role,))}


# ------------------------------------------------------------------- seed ----
PRODUCT_SEED = [
    ("Mawar Merah Super", "Mawar merah premium grade A, tangkai panjang 50-60 cm, per ikat 20 tangkai.", "Mawar", 185000, 42, "ikat"),
    ("Mawar Putih Avalanche", "Mawar putih segar dengan kelopak tebal, cocok untuk dekorasi pernikahan.", "Mawar", 195000, 28, "ikat"),
    ("Mawar Pink Sweetness", "Mawar pink lembut dengan aroma khas, favorit untuk bouquet hadiah.", "Mawar", 175000, 35, "ikat"),
    ("Lily Casablanca", "Lily putih wangi dengan 3-4 kuntum per tangkai, mekar tahan lama.", "Lily", 210000, 18, "ikat"),
    ("Anggrek Bulan Putih", "Anggrek bulan potong, kesegaran hingga 7 hari, kemasan khusus.", "Anggrek", 320000, 12, "ikat"),
    ("Tulip Belanda Mix", "Tulip import warna campuran, dikirim dengan cold chain.", "Tulip", 385000, 8, "ikat"),
    ("Carnation Pink", "Carnation pink tahan lama, ideal untuk filler bouquet.", "Carnation", 145000, 26, "ikat"),
    ("Baby Breath", "Gypsophila filler halus, per ikat besar.", "Filler", 95000, 50, "ikat"),
    ("Sunflower Lokal", "Bunga matahari segar diameter 10-12 cm.", "Lainnya", 120000, 22, "ikat"),
    ("Eustoma Ungu", "Eustoma/lisianthus ungu, kelopak lembut, aroma ringan.", "Lainnya", 240000, 15, "ikat"),
    ("Gerbera Mix", "Gerbera warna cerah campuran, cocok untuk hampers.", "Lainnya", 135000, 30, "ikat"),
    ("Daun Ruscus", "Daun ruscus hijau segar untuk rangkaian dan dekorasi.", "Filler", 75000, 60, "ikat"),
]

TESTIMONIAL_SEED = [
    ("Dewi Anggraeni", "Bunga selalu datang dalam kondisi segar, batangnya tebal dan tidak ada yang layu. Sudah langganan 2 tahun untuk toko florist saya.", 5),
    ("Rizky Pratama", "Pesan pagi, sore sudah sampai. Packing rapi dan dingin, cocok untuk kebutuhan acara kantor.", 5),
    ("Sari Florist", "Harga supplier-nya bersaing, kualitas grade A konsisten. Adminnya juga cepat balas WhatsApp.", 4),
    ("Hotel Larasati", "Kami order rutin setiap minggu untuk dekorasi lobi. Tim Rasty selalu on time dan komunikatif.", 5),
]

SOCIAL_SEED = [
    ("instagram", "Bouquet pagi ini", "https://instagram.com/rastyflorist"),
    ("instagram", "Behind the scene packing", "https://instagram.com/rastyflorist"),
    ("tiktok", "Tips merawat mawar potong", "https://tiktok.com/@rastyflorist"),
    ("tiktok", "Restock bunga hari ini", "https://tiktok.com/@rastyflorist"),
]

HERO_SEED = [
    ("Bunga Potong Segar Langsung dari Kebun", "Panen setiap pagi, dikirim dengan rantai dingin agar kesegaran terjaga sampai di tangan Anda.", "Lihat Katalog", "/#katalog"),
    ("Supplier Terpercaya untuk Florist & Acara", "Harga grosir, stok stabil, dan kualitas grade A untuk kebutuhan harian maupun dekorasi acara.", "Pesan Sekarang", "/#katalog"),
    ("Same Day Delivery Sebelum Jam 14.00", "Pesanan Anda kami siapkan dan antar di hari yang sama untuk area Bandung dan sekitarnya.", "Cara Pemesanan", "/#jam"),
]

USER_SEED = [
    ("admin", "admin123", "Rasty Administrator", "administrator", "0812-3456-7890", "admin@rastyflorist.id", "Jl. Melati Indah No. 27, Bandung"),
    ("staffadmin", "staff123", "Nadia Putri", "staff_admin", "0812-1111-2222", "nadia@rastyflorist.id", "Bandung"),
    ("staffkantor", "staff123", "Fajar Nugroho", "staff_kantor", "0812-3333-4444", "fajar@rastyflorist.id", "Bandung"),
    ("staffgudang", "staff123", "Bayu Setiawan", "staff_gudang", "0812-5555-6666", "bayu@rastyflorist.id", "Bandung"),
    ("staffqc", "staff123", "Intan Permata", "staff_qc", "0812-7777-8888", "intan@rastyflorist.id", "Bandung"),
    ("staffkeuangan", "staff123", "Ayu Lestari", "staff_keuangan", "0812-9999-0000", "ayu@rastyflorist.id", "Bandung"),
    ("pelanggan", "pelanggan123", "Toko Bunga Melodi", "pelanggan", "0813-2222-3333", "melodi@example.com", "Jl. Kenanga No. 8, Bandung"),
    ("pelanggan2", "pelanggan123", "Sari Florist", "pelanggan", "0813-4444-5555", "sari@example.com", "Jl. Anggrek No. 12, Cimahi"),
]


def seed_admin(username="admin", password="admin123", nama="Administrator", email="", telepon=""):
    """Buat satu akun administrator saja — dipakai instalasi toko sungguhan.

    Mengembalikan True bila akun dibuat, False bila sudah ada pengguna lain.
    """
    if query("SELECT COUNT(*) AS c FROM users", one=True)["c"]:
        return False
    execute(
        "INSERT INTO users (username, password_hash, nama, role, telepon, email, alamat, aktif, created_at)"
        " VALUES (?, ?, ?, 'administrator', ?, ?, '', 1, ?)",
        (username, generate_password_hash(password), nama, telepon, email, now()),
    )
    return True


def seed_demo():
    if query("SELECT COUNT(*) AS c FROM users", one=True)["c"]:
        return False

    created = now()
    for username, password, nama, role, telepon, email, alamat in USER_SEED:
        execute(
            "INSERT INTO users (username, password_hash, nama, role, telepon, email, alamat, aktif, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (username, generate_password_hash(password), nama, role, telepon, email, alamat, created),
        )

    for judul, subjudul, teks, link in HERO_SEED:
        execute(
            "INSERT INTO hero_slides (judul, subjudul, teks_tombol, link_tombol, urutan, aktif)"
            " VALUES (?, ?, ?, ?, 0, 1)", (judul, subjudul, teks, link),
        )
    for nama, deskripsi, kategori, harga, stok, satuan in PRODUCT_SEED:
        execute(
            "INSERT INTO products (nama, deskripsi, kategori, harga, stok, stok_minimum, satuan, aktif, created_at)"
            " VALUES (?, ?, ?, ?, ?, 5, ?, 1, ?)",
            (nama, deskripsi, kategori, harga, stok, satuan, created),
        )

    for i, (nama, isi, rating) in enumerate(TESTIMONIAL_SEED):
        execute(
            "INSERT INTO testimonials (nama, isi, rating, aktif, urutan) VALUES (?, ?, ?, 1, ?)",
            (nama, isi, rating, i),
        )

    for i, (platform, judul, link) in enumerate(SOCIAL_SEED):
        execute(
            "INSERT INTO social_posts (platform, judul, link, aktif, urutan) VALUES (?, ?, ?, 1, ?)",
            (platform, judul, link, i),
        )

    products = query("SELECT * FROM products ORDER BY id")
    customers = query("SELECT * FROM users WHERE role = 'pelanggan' ORDER BY id")
    staff_admin_id = query("SELECT id FROM users WHERE username = 'staffadmin'", one=True)["id"]

    statuses = ["Menunggu Konfirmasi", "Diproses", "Quality Kontrol", "Siap Kirim", "Selesai"]
    for idx in range(6):
        cust = customers[idx % len(customers)]
        status = statuses[idx % len(statuses)]
        days = 14 - idx * 2
        created_at = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        kode = "INV%s-%04d" % (created_at[:10].replace("-", ""), idx + 1)
        kode_lacak = "LACAK%s-%04d" % (created_at[:10].replace("-", ""), idx + 1)
        picked = random.sample(list(products), 2)
        subtotal = 0
        oid = execute(
            "INSERT INTO orders (kode, kode_lacak, user_id, nama_pelanggan, telepon, alamat, catatan,"
            " subtotal, ongkir, total, metode_bayar, status, status_bayar, pengiriman, dibuat_oleh,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, '', 0, 0, 0, ?, ?, ?, 'Kurir', ?, ?, ?)",
            (kode, kode_lacak, cust["id"], cust["nama"], cust["telepon"], cust["alamat"],
             "Transfer Bank" if idx % 2 == 0 else "QRIS",
             status, "Lunas" if status == "Selesai" else "Belum Bayar",
             staff_admin_id, created_at, created_at),
        )
        for p in picked:
            qty = random.randint(2, 6)
            line = p["harga"] * qty
            subtotal += line
            execute(
                "INSERT INTO order_items (order_id, product_id, nama_produk, harga, qty, subtotal, qc_status)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (oid, p["id"], p["nama"], p["harga"], qty, line,
                 "Lolos QC" if status in ("Siap Kirim", "Selesai") else "Belum Dicek"),
            )
        ongkir = 0 if subtotal >= 500000 else 25000
        execute("UPDATE orders SET subtotal = ?, ongkir = ?, total = ? WHERE id = ?",
                (subtotal, ongkir, subtotal + ongkir, oid))

    execute(
        "INSERT INTO complaints (kode, user_id, order_id, nama_pelanggan, subjek, isi, status, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, 'Baru', ?, ?)",
        ("CMP-0001", customers[0]["id"], None, customers[0]["nama"],
         "Beberapa tangkai mawar layu saat diterima",
         "Pesanan tiba dengan 3 tangkai mawar yang kelopaknya sudah lemas. Mohon pengecekan kualitas pengiriman.",
         created, created),
    )

    execute(
        "INSERT INTO invoices (nomor, nomor_invoice, order_id, user_id, nama_pelanggan, subtotal, total,"
        " ongkir, status, jatuh_tempo, created_at)"
        " SELECT kode, 'INV-' || id, id, user_id, nama_pelanggan, subtotal, total, ongkir,"
        " CASE WHEN status_bayar = 'Lunas' THEN 'Lunas' ELSE 'Belum Dibayar' END,"
        " date(created_at, '+7 day'), created_at FROM orders",
    )

    for row in query("SELECT * FROM products"):
        execute(
            "INSERT INTO stock_moves (product_id, tipe, qty, keterangan, referensi, dibuat_oleh, created_at)"
            " VALUES (?, 'masuk', ?, 'Stok awal gudang', 'SEED', ?, ?)",
            (row["id"], row["stok"], staff_admin_id, created),
        )

    for i in range(10):
        day = (datetime.now() - timedelta(days=i * 3)).strftime("%Y-%m-%d")
        execute(
            "INSERT INTO finance_entries (tipe, kategori, keterangan, jumlah, tanggal, dibuat_oleh, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("pemasukan", "Penjualan", "Penjualan harian", random.randint(1500000, 4500000), day,
             staff_admin_id, created),
        )
        if i % 2 == 0:
            execute(
                "INSERT INTO finance_entries (tipe, kategori, keterangan, jumlah, tanggal, dibuat_oleh, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("pengeluaran", "Pembelian Stok", "Belanja bunga dari kebun", random.randint(800000, 2000000),
                 day, staff_admin_id, created),
            )
    return True
