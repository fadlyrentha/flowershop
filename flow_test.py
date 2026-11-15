"""Uji alur transaksi end-to-end: pesanan -> QC -> pembayaran -> laporan."""
import io
import sys

import app as application

app = application.app
app.config["TESTING"] = True


def login(client, username, password):
    r = client.post("/login", data={"username": username, "password": password},
                    follow_redirects=True)
    assert r.status_code == 200, (username, r.status_code)


def png_bytes():
    # PNG 1x1 transparan
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )


errors = []

# 1. Pelanggan buat pesanan multi produk
cust = app.test_client()
login(cust, "pelanggan", "pelanggan123")
with app.app_context():
    import db as database
    prods = database.query("SELECT id, nama, stok FROM products WHERE aktif = 1 LIMIT 2")
    pid1, pid2 = prods[0]["id"], prods[1]["id"]
    stok_awal = {p["id"]: p["stok"] for p in prods}

res = cust.post("/pelanggan/pesanan/baru", data={
    "product_id[]": [str(pid1), str(pid2)],
    "qty[]": ["2", "3"],
    "nama_pelanggan": "Toko Bunga Melodi",
    "telepon": "0813-2222-3333",
    "alamat": "Jl. Kenanga No. 8",
    "catatan": "uji otomatis",
    "metode_bayar": "Transfer Bank",
    "pengiriman": "Kurir",
}, follow_redirects=True)
if res.status_code != 200:
    errors.append(("buat pesanan", res.status_code))

with app.app_context():
    import db as database
    order = database.query("SELECT * FROM orders ORDER BY id DESC LIMIT 1", one=True)
    items = database.query("SELECT * FROM order_items WHERE order_id = ?", (order["id"],))
    if len(items) != 2:
        errors.append(("jumlah item", len(items)))
    if order["subtotal"] != sum(i["subtotal"] for i in items):
        errors.append(("subtotal tidak konsisten", order["subtotal"]))
    if order["total"] != order["subtotal"] + order["ongkir"]:
        errors.append(("total tidak konsisten", order["total"]))
    for p in prods:
        now_stok = database.query("SELECT stok FROM products WHERE id = ?", (p["id"],), one=True)["stok"]
        if now_stok != stok_awal[p["id"]] - (2 if p["id"] == pid1 else 3):
            errors.append(("stok tidak berkurang", p["nama"], now_stok))
    order_id = order["id"]
    order_kode = order["kode"]

# 2. Detail & lacak (cetak invoice pelanggan sudah dinonaktifkan)
for url in ["/pelanggan/pesanan/%d" % order_id,
            "/pelanggan/lacak?kode=" + order_kode]:
    r = cust.get(url)
    if r.status_code != 200:
        errors.append((url, r.status_code))
r = cust.get("/pelanggan/invoice/%d" % order_id)
if r.status_code != 403:
    errors.append(("invoice pelanggan harus nonaktif", r.status_code))

# 3. Staff proses pesanan
staff = app.test_client()
login(staff, "staffadmin", "staff123")

# 3a. Konfirmasi order: tambah / ubah / hapus produk sebelum order dikonfirmasi
r = staff.get("/staff/konfirmasi-order")
if r.status_code != 200:
    errors.append(("halaman konfirmasi order", r.status_code))

with app.app_context():
    import db as database
    item_kurangi = database.query(
        "SELECT * FROM order_items WHERE order_id = ? ORDER BY id LIMIT 1", (order_id,), one=True)
    produk_kurangi = database.query(
        "SELECT * FROM products WHERE aktif = 1 AND id != ? ORDER BY id LIMIT 1",
        (item_kurangi["product_id"],), one=True)
    stok_produk_kurangi = produk_kurangi["stok"]
    jumlah_item_awal = database.query(
        "SELECT COUNT(*) AS c FROM order_items WHERE order_id = ?", (order_id,), one=True)["c"]

# tambah produk
r = staff.post("/staff/konfirmasi-order/%d/produk" % order_id, data={
    "aksi": "tambah", "product_id": str(produk_kurangi["id"]), "qty": "2",
}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("konfirmasi tambah produk", r.status_code))
with app.app_context():
    import db as database
    jumlah_item_baru = database.query(
        "SELECT COUNT(*) AS c FROM order_items WHERE order_id = ?", (order_id,), one=True)["c"]
    if jumlah_item_baru != jumlah_item_awal + 1:
        errors.append(("konfirmasi item tidak bertambah", jumlah_item_baru))
    sisa = database.query("SELECT stok FROM products WHERE id = ?",
                          (produk_kurangi["id"],), one=True)["stok"]
    if sisa != stok_produk_kurangi - 2:
        errors.append(("stok tidak berkurang setelah tambah", sisa))
    order_now = database.query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    items_now = database.query("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    if order_now["subtotal"] != sum(i["subtotal"] for i in items_now):
        errors.append(("subtotal setelah konfirmasi tambah", order_now["subtotal"]))
    inv_now = database.query("SELECT total FROM invoices WHERE order_id = ?", (order_id,), one=True)
    if inv_now and inv_now["total"] != order_now["total"]:
        errors.append(("faktur tidak dihitung ulang setelah konfirmasi tambah", inv_now["total"]))
    item_kurangi_id = item_kurangi["id"]
    qty_kurangi = item_kurangi["qty"]

# ubah produk (ganti produk + qty)
with app.app_context():
    import db as database
    stok_kurangi = database.query("SELECT stok FROM products WHERE id = ?",
                                  (item_kurangi["product_id"],), one=True)["stok"]
r = staff.post("/staff/konfirmasi-order/%d/produk" % order_id, data={
    "aksi": "ubah", "item_id": str(item_kurangi_id),
    "product_id": str(produk_kurangi["id"]), "qty": "1",
}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("konfirmasi ubah produk", r.status_code))
with app.app_context():
    import db as database
    diubah = database.query("SELECT * FROM order_items WHERE id = ?", (item_kurangi_id,), one=True)
    if diubah["product_id"] != produk_kurangi["id"] or diubah["qty"] != 1:
        errors.append(("item tidak terubah", diubah["product_id"], diubah["qty"]))
    if diubah["qc_status"] != "Belum Dicek":
        errors.append(("qc_status tidak direset setelah ubah",))
    kembali = database.query("SELECT stok FROM products WHERE id = ?",
                             (item_kurangi["product_id"],), one=True)["stok"]
    if kembali != stok_kurangi + qty_kurangi:
        errors.append(("stok produk lama tidak kembali setelah ubah", kembali))

# hapus produk
r = staff.post("/staff/konfirmasi-order/%d/produk" % order_id, data={
    "aksi": "hapus", "item_id": str(item_kurangi_id),
}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("konfirmasi hapus produk", r.status_code))
with app.app_context():
    import db as database
    if database.query("SELECT 1 FROM order_items WHERE id = ?", (item_kurangi_id,), one=True):
        errors.append(("item tidak terhapus",))
    order_now = database.query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    items_now = database.query("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    if order_now["subtotal"] != sum(i["subtotal"] for i in items_now):
        errors.append(("subtotal setelah hapus produk", order_now["subtotal"]))
    if len(items_now) < 1:
        errors.append(("pesanan kehilangan semua item",))

# hapus item terakhir harus ditolak
with app.app_context():
    import db as database
    terakhir = database.query("SELECT id FROM order_items WHERE order_id = ? ORDER BY id",
                              (order_id,), one=True)
    database.execute("DELETE FROM order_items WHERE order_id = ? AND id != ?",
                     (order_id, terakhir["id"]))
r = staff.post("/staff/konfirmasi-order/%d/produk" % order_id,
               data={"aksi": "hapus", "item_id": str(terakhir["id"])}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("tolak hapus item terakhir", r.status_code))
with app.app_context():
    import db as database
    if not database.query("SELECT 1 FROM order_items WHERE id = ?", (terakhir["id"],), one=True):
        errors.append(("item terakhir tidak boleh terhapus",))

r = staff.post("/staff/pesanan/%d/status" % order_id,
               data={"status": "Quality Kontrol"}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("update status", r.status_code))
r = staff.get("/staff/pesanan/%d/label" % order_id)
if r.status_code != 200:
    errors.append(("label", r.status_code))
r = staff.get("/staff/pesanan/%d/qc-list" % order_id)
if r.status_code != 200:
    errors.append(("qc list", r.status_code))

# 4. QC ganti produk (produk tidak memenuhi kebutuhan)
qc = app.test_client()
login(qc, "staffqc", "staff123")
r = qc.get("/qc/ganti-produk?order_id=%d" % order_id)
if r.status_code != 200:
    errors.append(("qc ganti produk page", r.status_code))

# 4a. QC tambah produk ke pesanan
with app.app_context():
    import db as database
    tambahan = database.query(
        "SELECT * FROM products WHERE aktif = 1 ORDER BY id DESC LIMIT 1", one=True)
    stok_tambahan = tambahan["stok"]
    jumlah_item_awal = database.query(
        "SELECT COUNT(*) AS c FROM order_items WHERE order_id = ?", (order_id,), one=True)["c"]

r = qc.post("/qc/ganti-produk", data={
    "aksi": "tambah", "order_id": str(order_id), "product_id": str(tambahan["id"]),
    "qty": "2", "catatan": "Tambahan permintaan pelanggan",
}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("qc tambah produk", r.status_code))

with app.app_context():
    import db as database
    jumlah_item_baru = database.query(
        "SELECT COUNT(*) AS c FROM order_items WHERE order_id = ?", (order_id,), one=True)["c"]
    if jumlah_item_baru != jumlah_item_awal + 1:
        errors.append(("item tidak bertambah", jumlah_item_baru))
    sisa = database.query("SELECT stok FROM products WHERE id = ?",
                          (tambahan["id"],), one=True)["stok"]
    if sisa != stok_tambahan - 2:
        errors.append(("stok tambahan tidak berkurang", sisa))
    order_now = database.query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    items_now = database.query("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    if order_now["subtotal"] != sum(i["subtotal"] for i in items_now):
        errors.append(("subtotal setelah tambah produk", order_now["subtotal"]))
    inv_now = database.query("SELECT total FROM invoices WHERE order_id = ?", (order_id,), one=True)
    if inv_now and inv_now["total"] != order_now["total"]:
        errors.append(("faktur tidak ikut dihitung ulang setelah tambah", inv_now["total"]))

with app.app_context():
    import db as database
    item0 = database.query("SELECT * FROM order_items WHERE order_id = ? ORDER BY id LIMIT 1",
                           (order_id,), one=True)
    pengganti = database.query(
        "SELECT * FROM products WHERE aktif = 1 AND id != ? ORDER BY id LIMIT 1",
        (item0["product_id"],), one=True)
    stok_lama = database.query("SELECT stok FROM products WHERE id = ?",
                               (item0["product_id"],), one=True)["stok"]
    stok_baru = pengganti["stok"]

r = qc.post("/qc/ganti-produk", data={
    "item_id": str(item0["id"]), "product_id": str(pengganti["id"]),
    "qty": str(item0["qty"]), "alasan": "Bunga tidak segar",
}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("qc ganti produk", r.status_code))

with app.app_context():
    import db as database
    baru = database.query("SELECT * FROM order_items WHERE id = ?", (item0["id"],), one=True)
    if baru["product_id"] != pengganti["id"]:
        errors.append(("produk tidak terganti", baru["product_id"]))
    if baru["qc_status"] != "Belum Dicek":
        errors.append(("qc_status tidak direset", baru["qc_status"]))
    s_lama = database.query("SELECT stok FROM products WHERE id = ?",
                            (item0["product_id"],), one=True)["stok"]
    s_baru = database.query("SELECT stok FROM products WHERE id = ?",
                            (pengganti["id"],), one=True)["stok"]
    if s_lama != stok_lama + item0["qty"]:
        errors.append(("stok produk lama tidak kembali", s_lama))
    if s_baru != stok_baru - item0["qty"]:
        errors.append(("stok produk pengganti tidak berkurang", s_baru))
    items = database.query("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    order_now = database.query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    if order_now["subtotal"] != sum(i["subtotal"] for i in items):
        errors.append(("subtotal setelah ganti produk", order_now["subtotal"]))
    inv_now = database.query("SELECT total FROM invoices WHERE order_id = ?", (order_id,), one=True)
    if inv_now and inv_now["total"] != order_now["total"]:
        errors.append(("faktur tidak ikut dihitung ulang", inv_now["total"]))

# 5. QC verifikasi semua item lolos
r = qc.get("/qc/pesanan/%d" % order_id)
if r.status_code != 200:
    errors.append(("qc verify page", r.status_code))
data = {"status_%d" % i["id"]: "Lolos QC" for i in items}
data["catatan_%d" % items[0]["id"]] = "Bunga segar, batang tebal"
data["foto_%d" % items[0]["id"]] = (io.BytesIO(png_bytes()), "bukti.png")
r = qc.post("/qc/pesanan/%d" % order_id, data=data, content_type="multipart/form-data",
            follow_redirects=True)
if r.status_code != 200:
    errors.append(("qc submit", r.status_code))

with app.app_context():
    import db as database
    st = database.query("SELECT status FROM orders WHERE id = ?", (order_id,), one=True)["status"]
    if st != "Siap Kirim":
        errors.append(("status setelah QC", st))
    checks = database.query(
        "SELECT q.* FROM qc_checks q JOIN order_items i ON i.id = q.order_item_id"
        " WHERE i.order_id = ?", (order_id,))
    if not checks:
        errors.append(("qc_checks kosong",))

# 5. Komplain dengan upload foto + video
r = cust.post("/pelanggan/komplain", data={
    "subjek": "Uji komplain",
    "isi": "Isi keluhan uji otomatis",
    "order_id": str(order_id),
    "foto": (io.BytesIO(png_bytes()), "foto.png"),
}, content_type="multipart/form-data", follow_redirects=True)
if r.status_code != 200:
    errors.append(("komplain", r.status_code))

# 6. Keuangan: faktur, pembayaran, verifikasi, laporan
fin = app.test_client()
login(fin, "staffkeuangan", "staff123")
r = fin.get("/keuangan/qc/%d" % order_id)
if r.status_code != 200:
    errors.append(("fin qc detail", r.status_code))

with app.app_context():
    import db as database
    inv = database.query("SELECT * FROM invoices WHERE order_id = ?", (order_id,), one=True)

r = fin.post("/keuangan/pembayaran", data={
    "invoice_id": str(inv["id"]), "order_id": str(order_id), "metode": "Transfer Bank",
    "jumlah": str(inv["total"]), "status": "Menunggu Verifikasi", "catatan": "uji",
    "bukti": (io.BytesIO(png_bytes()), "tf.png"),
}, content_type="multipart/form-data", follow_redirects=True)
if r.status_code != 200:
    errors.append(("pembayaran", r.status_code))

with app.app_context():
    import db as database
    pay = database.query("SELECT * FROM payments ORDER BY id DESC LIMIT 1", one=True)
    if not pay["bukti"]:
        errors.append(("bukti pembayaran tidak tersimpan",))

r = fin.post("/keuangan/pembayaran/%d/verifikasi" % pay["id"],
             data={"status": "Terverifikasi"}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("verifikasi bayar", r.status_code))

with app.app_context():
    import db as database
    inv2 = database.query("SELECT status FROM invoices WHERE id = ?", (inv["id"],), one=True)
    o2 = database.query("SELECT status_bayar FROM orders WHERE id = ?", (order_id,), one=True)
    if inv2["status"] != "Lunas":
        errors.append(("invoice belum lunas", inv2["status"]))
    if o2["status_bayar"] != "Lunas":
        errors.append(("order belum lunas", o2["status_bayar"]))

for url in ["/keuangan/qc", "/keuangan/faktur", "/keuangan/pembayaran", "/keuangan/laporan?periode=bulan",
            "/keuangan/stok", "/keuangan/keluhan", "/keuangan/laporan/cetak?periode=tahun",
            "/keuangan/pesanan-baru", "/keuangan/produk", "/keuangan/rekening"]:
    r = fin.get(url)
    if r.status_code != 200:
        errors.append((url, r.status_code))

# 6a. Cetak checklist QC dari panel keuangan (dulu 403 karena memakai rute staff)
r = fin.get("/keuangan/qc/%d/cetak" % order_id)
if r.status_code != 200:
    errors.append(("cetak checklist keuangan", r.status_code))
elif b"Checklist Produk Quality Kontrol" not in r.data:
    errors.append(("isi checklist keuangan kosong",))

# 6b. Catat pembayaran tanpa faktur/order (dulu error karena next_number)
r = fin.post("/keuangan/pembayaran", data={
    "metode": "Tunai", "jumlah": "150000", "status": "Menunggu Verifikasi",
    "catatan": "uji tanpa faktur",
}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("pembayaran tanpa faktur", r.status_code))
with app.app_context():
    import db as database
    pay2 = database.query("SELECT * FROM payments ORDER BY id DESC LIMIT 1", one=True)
    if not pay2["kode"] or not pay2["kode_verifikasi"]:
        errors.append(("kode pembayaran kosong", pay2["kode"], pay2["kode_verifikasi"]))

# 6c. Keluhan: kategori, kompensasi, nominal, status, balasan
r = fin.post("/keuangan/keluhan", data={
    "nama_pelanggan": "Toko Uji", "kategori": "Produk Rusak", "kompensasi": "Refund",
    "nominal": "75000", "status": "Ditinjau", "subjek": "Bunga rusak",
    "isi": "Sebagian bunga layu.", "tanggapan": "Kami proses refund.",
}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("tambah keluhan", r.status_code))
with app.app_context():
    import db as database
    kel = database.query("SELECT * FROM complaints ORDER BY id DESC LIMIT 1", one=True)
    if kel["kategori"] != "Produk Rusak" or kel["kompensasi"] != "Refund":
        errors.append(("kategori/kompensasi keluhan", kel["kategori"], kel["kompensasi"]))
    if kel["nominal"] != 75000 or kel["status"] != "Ditinjau":
        errors.append(("nominal/status keluhan", kel["nominal"], kel["status"]))
    if kel["tanggapan"] != "Kami proses refund.":
        errors.append(("balasan keluhan", kel["tanggapan"]))
r = fin.get("/keuangan/keluhan")
if b"Produk Rusak" not in r.data or b"Refund" not in r.data:
    errors.append(("keluhan tidak tampil di daftar",))

# 6d. Pesanan manual dari keuangan dengan kategori tagihan
with app.app_context():
    import db as database
    prod = database.query("SELECT * FROM products WHERE aktif = 1 AND stok > 2 ORDER BY id LIMIT 1", one=True)
r = fin.post("/keuangan/pesanan-baru", data={
    "nama_pelanggan": "Pelanggan Abonemen", "telepon": "0812", "alamat": "Jl. Uji",
    "metode_bayar": "Transfer Bank", "pengiriman": "Kurir", "kode_tagihan": "Abonemen IB",
    "product_id[]": [str(prod["id"])], "qty[]": ["1"],
}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("pesanan manual keuangan", r.status_code))
with app.app_context():
    import db as database
    ord2 = database.query("SELECT * FROM orders ORDER BY id DESC LIMIT 1", one=True)
    inv3 = database.query("SELECT * FROM invoices WHERE order_id = ?", (ord2["id"],), one=True)
    if inv3 is None or inv3["kode_tagihan"] != "Abonemen IB":
        errors.append(("kategori tagihan pesanan manual", inv3["kode_tagihan"] if inv3 else None))

# 6e. Data produk dari keuangan: tambah, ubah, hapus
r = fin.post("/keuangan/produk", data={
    "nama": "Produk Uji Keuangan", "kategori": "Lainnya", "deskripsi": "Uji CRUD",
    "harga": "50000", "stok": "7", "stok_minimum": "2", "satuan": "ikat", "aktif": "on",
}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("tambah produk keuangan", r.status_code))
with app.app_context():
    import db as database
    pbaru = database.query("SELECT * FROM products WHERE nama = 'Produk Uji Keuangan'", one=True)
    if pbaru is None:
        errors.append(("produk keuangan tidak tersimpan",))
    pid_baru = pbaru["id"] if pbaru else 0
r = fin.post("/keuangan/produk", data={
    "id": str(pid_baru), "nama": "Produk Uji Keuangan", "kategori": "Lainnya",
    "harga": "65000", "stok": "9", "stok_minimum": "2", "satuan": "ikat", "aktif": "on",
}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("ubah produk keuangan", r.status_code))
with app.app_context():
    import db as database
    pbaru = database.query("SELECT * FROM products WHERE id = ?", (pid_baru,), one=True)
    if pbaru["harga"] != 65000 or pbaru["stok"] != 9:
        errors.append(("produk keuangan tidak berubah", pbaru["harga"], pbaru["stok"]))
r = fin.post("/keuangan/produk/%d/hapus" % pid_baru, follow_redirects=True)
if r.status_code != 200:
    errors.append(("hapus produk keuangan", r.status_code))
with app.app_context():
    import db as database
    if database.query("SELECT id FROM products WHERE id = ?", (pid_baru,), one=True):
        errors.append(("produk keuangan tidak terhapus",))

# 6e1. Foto produk: tambah, ganti, hapus dari panel keuangan
r = fin.post("/keuangan/produk", data={
    "nama": "Produk Foto Uji", "kategori": "Lainnya", "harga": "40000", "stok": "3",
    "stok_minimum": "1", "satuan": "ikat", "aktif": "on",
    "gambar": (io.BytesIO(png_bytes()), "foto.png"),
}, content_type="multipart/form-data", follow_redirects=True)
if r.status_code != 200:
    errors.append(("tambah produk berfoto", r.status_code))
with app.app_context():
    import db as database
    pf = database.query("SELECT * FROM products WHERE nama = 'Produk Foto Uji'", one=True)
    if pf is None or not pf["gambar"]:
        errors.append(("foto produk tidak tersimpan",))
    pid_foto = pf["id"] if pf else 0
    foto_lama = pf["gambar"] if pf else ""
r = fin.get("/keuangan/produk")
if b"uploads/" not in r.data:
    errors.append(("foto produk tidak tampil di daftar",))
# Ganti foto: berkas lama harus terhapus
r = fin.post("/keuangan/produk", data={
    "id": str(pid_foto), "nama": "Produk Foto Uji", "kategori": "Lainnya", "harga": "40000",
    "stok": "3", "stok_minimum": "1", "satuan": "ikat", "aktif": "on",
    "gambar": (io.BytesIO(png_bytes()), "foto2.png"),
}, content_type="multipart/form-data", follow_redirects=True)
if r.status_code != 200:
    errors.append(("ganti foto produk", r.status_code))
with app.app_context():
    import db as database
    import os
    from flask import current_app
    pf = database.query("SELECT * FROM products WHERE id = ?", (pid_foto,), one=True)
    if not pf["gambar"] or pf["gambar"] == foto_lama:
        errors.append(("foto produk tidak terganti", pf["gambar"]))
    if os.path.isfile(os.path.join(current_app.config["UPLOAD_FOLDER"], foto_lama)):
        errors.append(("foto lama masih ada di disk",))
# Hapus foto saja (produk tetap ada)
r = fin.post("/keuangan/produk/%d/foto/hapus" % pid_foto, follow_redirects=True)
if r.status_code != 200:
    errors.append(("hapus foto produk", r.status_code))
with app.app_context():
    import db as database
    pf = database.query("SELECT * FROM products WHERE id = ?", (pid_foto,), one=True)
    if pf is None:
        errors.append(("produk ikut terhapus saat hapus foto",))
    elif pf["gambar"]:
        errors.append(("foto produk tidak terhapus", pf["gambar"]))
r = fin.post("/keuangan/produk/%d/hapus" % pid_foto, follow_redirects=True)

# 6f. Konfirmasi order + data pesanan untuk staff keuangan (kolom & fitur sama staff admin)
for url in ["/staff/konfirmasi-order", "/staff/pesanan", "/staff/pesanan/%d" % ord2["id"]]:
    r = fin.get(url)
    if r.status_code != 200:
        errors.append(("keuangan %s" % url, r.status_code))
r = fin.get("/staff/pesanan")
if b"Data Pesanan" not in r.data:
    errors.append(("halaman data pesanan keuangan kosong",))
r = fin.post("/staff/konfirmasi-order/%d" % ord2["id"], data={"aksi": "terima"},
             follow_redirects=True)
if r.status_code != 200:
    errors.append(("konfirmasi order keuangan", r.status_code))
with app.app_context():
    import db as database
    o3 = database.query("SELECT status FROM orders WHERE id = ?", (ord2["id"],), one=True)
    if o3["status"] != "Diproses":
        errors.append(("order tidak terkonfirmasi dari keuangan", o3["status"]))

# 7. Admin: CMS, pengaturan, hak akses
admin = app.test_client()
login(admin, "admin", "admin123")
gud = app.test_client()
login(gud, "staffgudang", "staff123")
kantor = app.test_client()
login(kantor, "staffkantor", "staff123")
r = admin.post("/admin/cms", data={
    "aksi": "hero", "judul": "Slide Uji", "subjudul": "Sub uji",
    "teks_tombol": "Lihat", "link_tombol": "/#katalog", "urutan": "1", "aktif": "on",
}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("cms hero", r.status_code))
r = admin.post("/admin/pengaturan", data={"nama_toko": "Rasty Florist",
                                          "warna_primer": "#b3204f",
                                          "warna_sekunder": "#f7e4ea"},
               follow_redirects=True)
if r.status_code != 200:
    errors.append(("pengaturan", r.status_code))
r = admin.post("/admin/hak-akses", data={"role": "staff_gudang", "feature": ["dashboard", "stok"]},
               follow_redirects=True)
if r.status_code != 200:
    errors.append(("hak akses", r.status_code))

# 7a2. Kontroler sosial media: akun, konten manual, saklar tampil, dan beranda
r = admin.post("/admin/sosial/akun", data={
    "platform": "instagram", "nama": "Uji Florist", "username": "ujiflorist",
    "sumber": "manual", "jumlah_feed": "12", "jumlah_story": "10",
    "urutan": "0", "aktif": "on", "sinkron_otomatis": "on",
}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("tambah akun sosial", r.status_code))
with app.app_context():
    import db as database
    akun = database.query("SELECT * FROM social_accounts WHERE username = 'ujiflorist'", one=True)
    if not akun:
        errors.append(("akun sosial tidak tersimpan",))
    elif akun["url"] != "https://instagram.com/ujiflorist":
        errors.append(("url akun tidak disusun dari username", akun["url"]))
    akun_id = akun["id"] if akun else None

if akun_id:
    r = admin.post("/admin/sosial/item", data={
        "account_id": str(akun_id), "jenis": "story", "judul": "Story uji",
        "caption": "coba", "link": "https://instagram.com/ujiflorist",
        "urutan": "0", "aktif": "on",
    }, follow_redirects=True)
    if r.status_code != 200:
        errors.append(("tambah konten sosial", r.status_code))
    with app.app_context():
        import db as database
        item = database.query("SELECT * FROM social_items WHERE account_id = ? AND jenis = 'story'",
                              (akun_id,), one=True)
        if not item:
            errors.append(("konten sosial tidak tersimpan",))
        item_id = item["id"] if item else None
    # Konten yang dimatikan tidak boleh muncul di beranda, lalu muncul lagi saat dinyalakan.
    if item_id:
        r = admin.post("/admin/sosial/item/%d/saklar" % item_id, follow_redirects=True)
        if r.status_code != 200:
            errors.append(("saklar konten sosial", r.status_code))
        with app.app_context():
            import db as database
            if database.query("SELECT aktif FROM social_items WHERE id = ?",
                              (item_id,), one=True)["aktif"]:
                errors.append(("saklar konten tidak mematikan",))
        # Beranda dikunjungi sebagai pengunjung biasa (belum masuk).
        beranda = app.test_client().get("/")
        if beranda.status_code != 200:
            errors.append(("beranda dengan kontroler sosial", beranda.status_code))

    # Mode non-manual tanpa URL feed harus ditolak, bukan membuat akun setengah jadi.
    r = admin.post("/admin/sosial/akun", data={
        "platform": "instagram", "username": "tanpafeed", "sumber": "rss",
    }, follow_redirects=True)
    with app.app_context():
        import db as database
        if database.query("SELECT 1 FROM social_accounts WHERE username = 'tanpafeed'", one=True):
            errors.append(("akun RSS tanpa feed_url seharusnya ditolak",))

    # Sinkronisasi akun manual tidak menarik apa pun tetapi tetap membalas wajar.
    r = admin.post("/admin/sosial/akun/%d/sinkron" % akun_id, follow_redirects=True)
    if r.status_code != 200:
        errors.append(("sinkron akun manual", r.status_code))

    # Panel kontroler mengatur jadwal sinkronisasi.
    r = admin.post("/admin/sosial/pengaturan", data={
        "sosial_aktif": "on", "sosial_interval": "60",
        "sosial_feed_tampil": "8", "sosial_story_tampil": "8",
    }, follow_redirects=True)
    if r.status_code != 200:
        errors.append(("pengaturan sosial", r.status_code))
    with app.app_context():
        import db as database
        if database.get_setting("sosial_interval") != "60":
            errors.append(("interval sosial tidak tersimpan",))

    r = admin.post("/admin/sosial/akun/%d/hapus" % akun_id, follow_redirects=True)
    if r.status_code != 200:
        errors.append(("hapus akun sosial", r.status_code))
    with app.app_context():
        import db as database
        if database.query("SELECT 1 FROM social_accounts WHERE id = ?", (akun_id,), one=True):
            errors.append(("akun sosial tidak terhapus",))
        if database.query("SELECT 1 FROM social_items WHERE account_id = ?", (akun_id,), one=True):
            errors.append(("konten akun tidak ikut terhapus",))
        if database.query("SELECT 1 FROM social_accounts WHERE username = 'tanpafeed'", one=True):
            errors.append(("akun tak valid tersimpan",))

# 7a3. Staff kantor tidak boleh membuka kontroler sosial media milik administrator.
r = kantor.get("/admin/sosial")
if r.status_code != 403:
    errors.append(("proteksi kontroler sosial", r.status_code))

# 7b. Admin: ganti template invoice + kontroller ID
r = admin.post("/admin/template-invoice", data={"template_invoice": "modern"},
               follow_redirects=True)
if r.status_code != 200:
    errors.append(("template invoice", r.status_code))
with app.app_context():
    import db as database
    if database.get_setting("template_invoice") != "modern":
        errors.append(("template invoice tidak tersimpan",))
r = admin.get("/keuangan/faktur/%d/cetak" % inv["id"])
if r.status_code != 200:
    errors.append(("cetak invoice modern", r.status_code))
r = admin.post("/admin/template-invoice", data={"template_invoice": "klasik"},
               follow_redirects=True)

# 7b1. Template invoice dari berkas desain unggahan
r = admin.post("/admin/template-invoice",
               data={"template_invoice": "desain",
                     "desain": (io.BytesIO(png_bytes()), "desain.png")},
               content_type="multipart/form-data", follow_redirects=True)
if r.status_code != 200:
    errors.append(("unggah desain invoice", r.status_code))
with app.app_context():
    import db as database
    if not database.get_setting("template_invoice_file"):
        errors.append(("berkas desain tidak tersimpan",))
    if database.get_setting("template_invoice") != "desain":
        errors.append(("template desain tidak aktif",))
r = admin.get("/keuangan/faktur/%d/cetak" % inv["id"])
if r.status_code != 200:
    errors.append(("cetak invoice desain", r.status_code))
r = admin.post("/admin/template-invoice/hapus-desain", follow_redirects=True)
if r.status_code != 200:
    errors.append(("hapus desain invoice", r.status_code))
with app.app_context():
    import db as database
    if database.get_setting("template_invoice_file"):
        errors.append(("berkas desain masih ada",))
    if database.get_setting("template_invoice") != "klasik":
        errors.append(("template tidak kembali ke klasik",))

r = admin.get("/admin/format-nomor")
if r.status_code != 200:
    errors.append(("format nomor", r.status_code))

# 7b2. Format nomor: ubah format lalu buat dokumen baru
r = admin.post("/admin/format-nomor", data={
    "format_nomor_order": "ORD{YYYY}{MM}-{SEQ:5}",
    "format_nomor_keluhan": "KEL{YY}{MM}{DD}-{SEQ:3}",
}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("simpan format nomor", r.status_code))
with app.app_context():
    import db as database
    if database.get_setting("format_nomor_order") != "ORD{YYYY}{MM}-{SEQ:5}":
        errors.append(("format order tidak tersimpan",))
    nomor = database.next_number("nomor_order")
    if not nomor.startswith("ORD"):
        errors.append(("nomor order tidak mengikuti format", nomor))
    if not database.valid_nomor_format("TANPA-TOKEN"):
        pass
    else:
        errors.append(("format tanpa token dianggap valid",))
    if database.valid_nomor_format("ORD{YYYY}-{SEQ:3}"):
        pass
    else:
        errors.append(("format dengan SEQ dianggap tidak valid",))
    database.set_setting("format_nomor_order", database.DEFAULT_SETTINGS["format_nomor_order"])
    database.set_setting("format_nomor_keluhan", database.DEFAULT_SETTINGS["format_nomor_keluhan"])

# 7b3. Backup manual + unduh + hapus
r = admin.post("/admin/backup", data={"aksi": "buat"}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("backup buat", r.status_code))
with app.app_context():
    import db as database
    backups = database.list_backups()
    if not backups:
        errors.append(("backup tidak dibuat",))
    nama_backup = backups[0]["nama"] if backups else ""
if nama_backup:
    r = admin.get("/admin/backup/%s/unduh" % nama_backup)
    if r.status_code != 200:
        errors.append(("backup unduh", r.status_code))
    r = admin.post("/admin/backup/%s/hapus" % nama_backup, follow_redirects=True)
    if r.status_code != 200:
        errors.append(("backup hapus", r.status_code))

# 7b4. Pulihkan database dari berkas backup (riwayat & unggahan)
r = admin.post("/admin/backup", data={"aksi": "buat"}, follow_redirects=True)
nama_pulih = ""
jalur_pulih = None
with app.app_context():
    import db as database
    daftar = database.list_backups()
    if daftar:
        nama_pulih = daftar[0]["nama"]
    else:
        errors.append(("backup untuk pemulihan tidak dibuat",))
# Data yang ditambahkan setelah backup harus hilang setelah pemulihan.
with app.app_context():
    import db as database
    database.execute(
        "INSERT INTO products (nama, kategori, harga, stok, stok_minimum, satuan, aktif, created_at)"
        " VALUES ('Produk Sebelum Pulih', 'Lainnya', 1000, 1, 1, 'ikat', 1, ?)", (database.now(),))
if nama_pulih:
    r = admin.post("/admin/backup/%s/pulihkan" % nama_pulih, follow_redirects=True)
    if r.status_code != 200:
        errors.append(("pulihkan backup riwayat", r.status_code))
    with app.app_context():
        import db as database
        if database.query("SELECT id FROM products WHERE nama = 'Produk Sebelum Pulih'", one=True):
            errors.append(("pulihkan backup tidak mengembalikan data",))
        if not database.get_setting("restore_terakhir"):
            errors.append(("waktu pemulihan tidak dicatat",))
        # Keadaan sebelum pemulihan harus tercadangkan otomatis.
        if not any(b["nama"].startswith("rasty-sebelum-restore-")
                   for b in database.list_backups()):
            errors.append(("cadangan sebelum-restore tidak dibuat",))
        jalur_pulih = database.backup_path(nama_pulih)

# Unggah berkas backup lalu pulihkan dari unggahan itu.
with app.app_context():
    import db as database
    database.execute(
        "INSERT INTO products (nama, kategori, harga, stok, stok_minimum, satuan, aktif, created_at)"
        " VALUES ('Produk Setelah Pulih', 'Lainnya', 1000, 1, 1, 'ikat', 1, ?)", (database.now(),))
if jalur_pulih:
    with open(jalur_pulih, "rb") as fh:
        r = admin.post("/admin/backup/unggah", data={"berkas": (io.BytesIO(fh.read()), "pulih.db")},
                       content_type="multipart/form-data", follow_redirects=True)
    if r.status_code != 200:
        errors.append(("unggah backup", r.status_code))
    with app.app_context():
        import db as database
        if database.query("SELECT id FROM products WHERE nama = 'Produk Setelah Pulih'", one=True):
            errors.append(("pulihkan dari unggahan tidak berjalan",))
# Berkas asing harus ditolak, bukan menimpa database.
r = admin.post("/admin/backup/unggah",
               data={"berkas": (io.BytesIO(b"bukan database"), "asing.db")},
               content_type="multipart/form-data", follow_redirects=True)
if r.status_code != 200 or not (b"tidak bisa dibaca" in r.data or b"bukan backup" in r.data):
    errors.append(("berkas backup asing tidak ditolak", r.status_code))
with app.app_context():
    import db as database
    if database.query("SELECT id FROM products WHERE nama = 'Produk Setelah Pulih'", one=True):
        errors.append(("database berubah setelah unggahan ditolak",))
    # Berkas sementara tidak boleh tertinggal di folder backup.
    import os
    if any(n.startswith("unggahan-") for n in os.listdir(database.backup_dir())):
        errors.append(("berkas unggahan sementara tertinggal",))

r = admin.post("/admin/backup", data={"aksi": "jadwal", "backup_jadwal": "harian"},
               follow_redirects=True)
if r.status_code != 200:
    errors.append(("backup jadwal", r.status_code))
with app.app_context():
    import db as database
    if database.get_setting("backup_jadwal") != "harian":
        errors.append(("jadwal backup tidak tersimpan",))
    database.set_setting("backup_jadwal", "off")

# 7c. Monitoring harian + auto refresh
r = admin.get("/monitoring/harian")
if r.status_code != 200:
    errors.append(("monitoring harian", r.status_code))
r = admin.get("/monitoring/harian?refresh=30")
if r.status_code != 200:
    errors.append(("monitoring harian auto refresh", r.status_code))

# 7d. Halaman monitoring mandiri (fitur hak akses, di luar situs publik & panel)
for url in ["/pantau", "/pantau?refresh=30", "/pantau?status=Selesai"]:
    r = admin.get(url)
    if r.status_code != 200:
        errors.append((url, r.status_code))
# Bawaan: staff_admin & staff_kantor terbuka; pelanggan, QC, dan Keuangan ditolak.
# (staff_gudang diuji di 7d1/7d2 karena hak aksesnya sudah diubah di langkah 7.)
for peran, klien in (("staff_admin", staff), ("staff_kantor", kantor)):
    r = klien.get("/pantau")
    if r.status_code != 200:
        errors.append(("pantau harus terbuka untuk %s" % peran, r.status_code))
for peran, klien in (("pelanggan", cust), ("staff_qc", qc), ("staff_keuangan", fin)):
    r = klien.get("/pantau")
    if r.status_code != 403:
        errors.append(("pantau harus menolak %s" % peran, r.status_code))

# 7d1. Menyalakan monitoring mandiri lewat panel hak akses membuka aksesnya
with app.app_context():
    import db as database
    gud_asal = sorted(f for f, on in database.role_features("staff_gudang").items() if on)
r = admin.post("/admin/hak-akses",
               data={"role": "staff_gudang", "feature": gud_asal + ["monitoring_mandiri"]},
               follow_redirects=True)
if r.status_code != 200:
    errors.append(("nyalakan monitoring mandiri", r.status_code))
with app.app_context():
    import db as database
    if not database.feature_enabled("staff_gudang", "monitoring_mandiri"):
        errors.append(("monitoring_mandiri tidak tersimpan",))
r = gud.get("/pantau")
if r.status_code != 200:
    errors.append(("pantau aktif untuk staff_gudang", r.status_code))
r = gud.get("/staff/")
if b"Monitoring Mandiri" not in r.data:
    errors.append(("tautan monitoring mandiri tidak tampil di sidebar",))

# 7d2. Mematikannya kembali menutup akses dan menyembunyikan tautan
r = admin.post("/admin/hak-akses", data={"role": "staff_gudang", "feature": gud_asal},
               follow_redirects=True)
if r.status_code != 200:
    errors.append(("matikan monitoring mandiri", r.status_code))
r = gud.get("/pantau")
if r.status_code != 403:
    errors.append(("pantau harus tertutup lagi", r.status_code))
r = gud.get("/staff/")
if b"Monitoring Mandiri" in r.data:
    errors.append(("tautan monitoring mandiri masih tampil",))

# 7d3. Profil + kata sandi tersedia untuk semua peran
for peran, klien in (("pelanggan", cust), ("staff_admin", staff), ("staff_kantor", kantor),
                     ("staff_gudang", gud), ("staff_qc", qc), ("staff_keuangan", fin),
                     ("administrator", admin)):
    for url in ("/akun/profil", "/akun/kata-sandi"):
        r = klien.get(url)
        if r.status_code != 200:
            errors.append(("akun %s %s" % (peran, url), r.status_code))
r = cust.get("/pelanggan/profil")
if r.status_code not in (301, 302):
    errors.append(("profil pelanggan harus dialihkan", r.status_code))
elif "/akun/profil" not in r.headers.get("Location", ""):
    errors.append(("arah alih profil pelanggan salah", r.headers.get("Location")))

# 7d4. Ganti kata sandi lewat halaman akun bersama
r = cust.post("/akun/kata-sandi",
              data={"lama": "pelanggan123", "baru": "rahasia123", "ulang": "rahasia123"},
              follow_redirects=True)
if r.status_code != 200:
    errors.append(("ubah kata sandi pelanggan", r.status_code))
with app.app_context():
    import db as database
    from werkzeug.security import check_password_hash
    u = database.query("SELECT * FROM users WHERE username = 'pelanggan'", one=True)
    if not check_password_hash(u["password_hash"], "rahasia123"):
        errors.append(("kata sandi pelanggan tidak berubah",))
r = cust.post("/akun/kata-sandi",
              data={"lama": "rahasia123", "baru": "pelanggan123", "ulang": "pelanggan123"},
              follow_redirects=True)
r = cust.post("/akun/kata-sandi",
              data={"lama": "salah", "baru": "baru12345", "ulang": "baru12345"},
              follow_redirects=True)
if r.status_code != 200:
    errors.append(("kata sandi lama salah ditolak", r.status_code))

# 7e. Ekspor PDF faktur + kolom rekening bank
r = fin.get("/keuangan/faktur/%d/pdf" % inv["id"])
if r.status_code != 200:
    errors.append(("ekspor pdf faktur", r.status_code))
elif r.data[:4] != b"%PDF":
    errors.append(("berkas pdf tidak valid", r.data[:8]))
with app.app_context():
    import db as database
    database.set_setting("rekening_bank", "Bank BCA · 1234567890 · a.n. Rasty Florist")
    database.set_setting("tampil_rekening", "1")
r = fin.get("/keuangan/faktur/%d/cetak" % inv["id"])
if r.status_code != 200:
    errors.append(("cetak faktur dengan rekening", r.status_code))
elif b"1234567890" not in r.data:
    errors.append(("rekening tidak tampil di faktur",))
r = fin.get("/keuangan/faktur/%d/wa" % inv["id"])
if r.status_code not in (301, 302):
    errors.append(("kirim faktur ke whatsapp", r.status_code))
elif b"1234567890" not in r.headers.get("Location", "").encode():
    errors.append(("rekening tidak ada di pesan whatsapp",))

# 7e1. Logo di kop faktur: unggah logo, atur ukuran, cek cetak + PDF
r = admin.post("/admin/pengaturan", data={
    "nama_toko": "Rasty Florist", "warna_primer": "#b3204f", "warna_sekunder": "#f7e4ea",
    "logo": (io.BytesIO(png_bytes()), "logo.png"),
}, content_type="multipart/form-data", follow_redirects=True)
if r.status_code != 200:
    errors.append(("unggah logo", r.status_code))
with app.app_context():
    import db as database
    if not database.get_setting("logo"):
        errors.append(("logo tidak tersimpan",))
r = admin.post("/admin/template-invoice", data={
    "template_invoice": "klasik", "invoice_logo_tampil": "on", "invoice_logo_ukuran": "besar",
}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("simpan logo faktur", r.status_code))
with app.app_context():
    import db as database
    if database.get_setting("invoice_logo_ukuran") != "besar":
        errors.append(("ukuran logo tidak tersimpan",))
    if database.get_setting("invoice_logo_tampil") != "1":
        errors.append(("tampil logo tidak tersimpan",))
r = fin.get("/keuangan/faktur/%d/cetak" % inv["id"])
if r.status_code != 200:
    errors.append(("cetak faktur dengan logo", r.status_code))
elif b"uploads/" not in r.data:
    errors.append(("logo tidak tampil di faktur cetak",))
r = fin.get("/keuangan/faktur/%d/pdf" % inv["id"])
if r.status_code != 200:
    errors.append(("pdf faktur dengan logo", r.status_code))
elif b"/XObject" not in r.data or b"/Image" not in r.data:
    errors.append(("logo tidak tertanam di pdf",))
# Mematikan logo menghilangkan gambar dari PDF
r = admin.post("/admin/template-invoice", data={
    "template_invoice": "klasik", "invoice_logo_ukuran": "sedang",
}, follow_redirects=True)
r = fin.get("/keuangan/faktur/%d/pdf" % inv["id"])
if r.status_code != 200:
    errors.append(("pdf faktur tanpa logo", r.status_code))
elif b"/Image" in r.data:
    errors.append(("logo masih tertanam walau dimatikan",))
r = admin.post("/admin/template-invoice", data={
    "template_invoice": "klasik", "invoice_logo_tampil": "on", "invoice_logo_ukuran": "sedang",
}, follow_redirects=True)

# 7f. Administrator: kolom katalog beranda + reset pengaturan
r = admin.post("/admin/katalog", data={"katalog_hero": "on", "katalog_testimoni": "on"},
               follow_redirects=True)
if r.status_code != 200:
    errors.append(("simpan kolom katalog", r.status_code))
with app.app_context():
    import db as database
    if database.get_setting("katalog_produk") != "0":
        errors.append(("katalog produk seharusnya nonaktif",))
r = admin.get("/")
if r.status_code != 200:
    errors.append(("beranda tanpa kolom dinonaktifkan", r.status_code))
elif b'id="katalog"' in r.data:
    errors.append(("kolom katalog masih tampil walau dinonaktifkan",))

r = admin.post("/admin/rekening", data={
    "rekening_bank": "Bank Mandiri · 9876543210 · a.n. Rasty Florist",
    "tampil_rekening": "on",
}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("simpan rekening", r.status_code))
with app.app_context():
    import db as database
    if "Mandiri" not in database.get_setting("rekening_bank"):
        errors.append(("rekening tidak tersimpan",))

# 7f1. Administrator: metode pengiriman, jam operasional, menu publik
r = admin.post("/admin/pengiriman", data={"kirim_kurir": "on", "kirim_cod": "on"},
               follow_redirects=True)
if r.status_code != 200:
    errors.append(("simpan metode pengiriman", r.status_code))
with app.app_context():
    import db as database
    if database.pengiriman_metode() != ["COD", "Kurir"]:
        errors.append(("metode pengiriman tidak tersimpan", database.pengiriman_metode()))
    if database.get_setting("kirim_cargo") != "0":
        errors.append(("cargo seharusnya nonaktif",))
r = admin.post("/admin/pengiriman", data={}, follow_redirects=True)
with app.app_context():
    import db as database
    if not database.pengiriman_metode():
        errors.append(("metode pengiriman kosong",))

r = admin.post("/admin/jam-operasional", data={
    "jam_buka_senin": "08:00", "jam_tutup_senin": "17:00",
    "jam_buka_minggu": "08:00", "jam_tutup_minggu": "08:00",
    "sameday_batas_jam": "15:30", "sameday_info": "Info uji same day",
    "sameday_hari": ["senin", "selasa"],
}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("simpan jam operasional", r.status_code))
with app.app_context():
    import db as database
    if database.jam_dari(database.all_settings())["senin"] != ("08:00", "17:00"):
        errors.append(("jam senin tidak tersimpan",))
    if database.sameday_hari() != ["senin", "selasa"]:
        errors.append(("hari same day tidak tersimpan", database.sameday_hari()))
r = admin.post("/admin/jam-operasional", data={
    "jam_buka_senin": "bukan-jam", "jam_tutup_senin": "17:00",
    "sameday_batas_jam": "14:00",
}, follow_redirects=True)
with app.app_context():
    import db as database
    if database.get_setting("jam_buka_senin") != "08:00":
        errors.append(("jam tidak valid tetap tersimpan",))

r = admin.post("/admin/menu-publik", data={"nav_katalog": "on"}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("simpan menu publik", r.status_code))
with app.app_context():
    import db as database
    if database.get_setting("nav_lacak") != "0":
        errors.append(("menu lacak seharusnya nonaktif",))
r = admin.get("/")
if r.status_code != 200:
    errors.append(("beranda menu publik", r.status_code))
elif b'Lacak</a>' in r.data:
    errors.append(("menu lacak masih tampil walau dinonaktifkan",))

r = admin.post("/admin/reset", data={"aksi": "menu_publik"}, follow_redirects=True)
with app.app_context():
    import db as database
    if database.get_setting("nav_lacak") != "1":
        errors.append(("reset menu publik tidak mengaktifkan kembali",))
r = admin.post("/admin/reset", data={"aksi": "jam_operasional"}, follow_redirects=True)
with app.app_context():
    import db as database
    if database.get_setting("sameday_batas_jam") != database.DEFAULT_SETTINGS["sameday_batas_jam"]:
        errors.append(("reset jam operasional tidak kembali bawaan",))
r = admin.post("/admin/reset", data={"aksi": "pengiriman"}, follow_redirects=True)
with app.app_context():
    import db as database
    if len(database.pengiriman_metode()) != len(database.PENGIRIMAN_METODE):
        errors.append(("reset metode pengiriman tidak lengkap",))

r = admin.post("/admin/reset", data={"aksi": "katalog"}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("reset katalog", r.status_code))
with app.app_context():
    import db as database
    if database.get_setting("katalog_produk") != "1":
        errors.append(("reset katalog tidak mengaktifkan kembali",))
r = admin.post("/admin/reset", data={"aksi": "pengaturan"}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("reset pengaturan", r.status_code))
with app.app_context():
    import db as database
    if database.get_setting("nama_toko") != database.DEFAULT_SETTINGS["nama_toko"]:
        errors.append(("reset pengaturan tidak kembali ke bawaan",))

with app.app_context():
    import db as database
    on = database.feature_enabled("staff_gudang", "stok")
    off = database.feature_enabled("staff_gudang", "produk")
    if not on or off:
        errors.append(("hak akses tidak berlaku", on, off))

# 7g. Reset hak akses mengembalikan susunan bawaan
r = admin.post("/admin/reset", data={"aksi": "hak_akses"}, follow_redirects=True)
if r.status_code != 200:
    errors.append(("reset hak akses", r.status_code))
with app.app_context():
    import db as database
    if not database.feature_enabled("staff_gudang", "produk"):
        errors.append(("reset hak akses tidak mengaktifkan kembali",))

# 8. Pelanggan tidak boleh akses panel staff
r = cust.get("/staff/")
if r.status_code != 403:
    errors.append(("proteksi staff", r.status_code))
r = cust.get("/qc/")
if r.status_code != 403:
    errors.append(("proteksi qc", r.status_code))

if errors:
    for e in errors:
        print("ERROR", e)
    sys.exit(1)
print("ALUR END-TO-END OK")
