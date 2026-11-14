"""Susun faktur menjadi berkas PDF memakai modul pdf.py (tanpa pustaka luar)."""
import os

from pdf import A4, MARGIN, Canvas, load_image, potong, wrap
from helpers import rupiah

ABU = 0.45

# Ukuran kotak logo di kop faktur (pt).
LOGO_TINGGI = 46.0
LOGO_LEBAR_MAKS = 120.0

# Batas bawah area cetak; lewat ini isi dipindah ke halaman baru.
BATAS_BAWAH = 90.0

# Titik acuan kolom tabel sebagai pecahan lebar area cetak.
X_PRODUK = 0.0
X_HARGA = 0.62
X_QTY = 0.78
X_SUBTOTAL = 1.0
LEBAR_PRODUK = 0.44


def _kop(c, x, y, lebar, settings, invoice, logo=None, logo_tinggi=LOGO_TINGGI):
    """Kop surat + identitas faktur. Mengembalikan posisi y berikutnya."""
    teks_x = x
    tinggi_kop = 76
    if logo:
        # Pertahankan rasio asli logo, dibatasi tinggi dan lebar kotak kop.
        skala = min(logo_tinggi / logo["h"], LOGO_LEBAR_MAKS / logo["w"])
        lw, lh = logo["w"] * skala, logo["h"] * skala
        c.gambar(x, y, lw, lh, logo)
        teks_x = x + lw + 14
        tinggi_kop = max(tinggi_kop, lh + 8)

    lebar_teks = max(lebar * 0.62 - (teks_x - x), 90)
    c.text(teks_x, y + 12, potong(settings.get("nama_toko", ""), lebar_teks, 20, True),
           size=20, bold=True)
    c.text(teks_x, y + 30, potong(settings.get("tagline", ""), lebar_teks, 9), size=9, abu=ABU)
    c.text(teks_x, y + 44, potong(settings.get("alamat", ""), lebar_teks, 9), size=9, abu=ABU)
    kontak = " · ".join(v for v in [settings.get("telepon", ""), settings.get("email", "")] if v)
    c.text(teks_x, y + 57, potong(kontak, lebar_teks, 9), size=9, abu=ABU)

    c.text(x + lebar, y + 12, "FAKTUR", size=20, bold=True, align="right")
    c.text(x + lebar, y + 32, invoice["nomor"], size=11, align="right")
    nomor_inv = invoice.get("nomor_invoice") or ""
    if nomor_inv:
        c.text(x + lebar, y + 45, nomor_inv, size=9, align="right", abu=ABU)
    c.text(x + lebar, y + 58, "Jatuh tempo: %s" % (invoice["jatuh_tempo"] or "-"),
           size=9, align="right", abu=ABU)

    y += tinggi_kop
    c.garis(x, y, x + lebar, y)
    return y + 20


def _pihak(c, x, y, lebar, invoice, order):
    """Blok penerima tagihan + ringkasan faktur. Mengembalikan y berikutnya."""
    c.text(x, y, "DITAGIHKAN KEPADA", size=7.5, abu=ABU)
    c.text(x, y + 14, potong(invoice["nama_pelanggan"] or "Pelanggan", lebar * 0.5, 11, True),
           size=11, bold=True)
    baris = y + 28
    if order:
        for teks in (order["alamat"], order["telepon"]):
            for b in wrap(teks or "", lebar * 0.5, 9, maks_baris=2):
                c.text(x, baris, b, size=9, abu=ABU)
                baris += 12

    kx = x + lebar * 0.58
    kw = lebar * 0.42
    info = [("Kode tagihan", invoice["kode_tagihan"]), ("Status", invoice["status"]),
            ("Tanggal", (invoice["created_at"] or "")[:10])]
    if order:
        info.append(("Order", order["kode"]))
        if order["kode_lacak"]:
            info.append(("ID Lacak", order["kode_lacak"]))
    ky = y
    for label, nilai in info:
        c.text(kx, ky, label, size=9, abu=ABU)
        c.text(kx + kw, ky, potong(nilai, kw, 9, True), size=9, bold=True, align="right")
        ky += 14
    return max(baris, ky) + 14


def _header_tabel(c, x, y, lebar):
    c.kotak(x, y - 4, lebar, 20, isi=(0.96, 0.96, 0.97))
    c.text(x + 8, y + 9, "Produk", size=9, bold=True)
    c.text(x + lebar * X_HARGA, y + 9, "Harga", size=9, bold=True, align="right")
    c.text(x + lebar * X_QTY, y + 9, "Qty", size=9, bold=True, align="center")
    c.text(x + lebar - 8, y + 9, "Subtotal", size=9, bold=True, align="right")
    return y + 24


def build(invoice, order, items, settings, rekening="", tampil_rekening=False, logo_path=""):
    c = Canvas(A4)
    lebar = c.w - 2 * MARGIN
    x = MARGIN

    logo = None
    if settings.get("invoice_logo_tampil", "1") == "1" and logo_path and os.path.isfile(logo_path):
        logo = load_image(logo_path)
    # Ukuran logo di PDF mengikuti pilihan kecil/sedang/besar (px -> pt).
    tinggi_px = {"kecil": 40, "sedang": 64, "besar": 96}.get(
        settings.get("invoice_logo_ukuran", "sedang"), 64)
    y = _kop(c, x, MARGIN, lebar, settings, invoice, logo=logo,
             logo_tinggi=tinggi_px * 0.75)
    y = _pihak(c, x, y, lebar, invoice, order)
    y = _header_tabel(c, x, y, lebar)

    for it in items:
        baris_produk = wrap(it["nama_produk"], lebar * LEBAR_PRODUK - 12, 9.5, maks_baris=2)
        if y + len(baris_produk) * 12 > c.h - BATAS_BAWAH:
            c.new_page()
            y = _header_tabel(c, x, MARGIN, lebar)
        tinggi = 0
        for b in baris_produk:
            c.text(x + 8, y + tinggi, b, size=9.5)
            tinggi += 12
        c.text(x + lebar * X_HARGA, y, rupiah(it["harga"]), size=9.5, align="right")
        c.text(x + lebar * X_QTY, y, str(it["qty"]), size=9.5, align="center")
        c.text(x + lebar - 8, y, rupiah(it["subtotal"]), size=9.5, align="right")
        y += max(tinggi, 12) + 8
        c.garis(x, y - 5, x + lebar, y - 5, lebar=0.4, abu=0.85)

    # --------------------------------------------------------------- total ----
    y += 8
    if y + 120 > c.h - BATAS_BAWAH:
        c.new_page()
        y = MARGIN

    baris_total = []
    if order:
        baris_total.append(("Subtotal", rupiah(order["subtotal"])))
        baris_total.append(("Ongkir", rupiah(order["ongkir"])))
    baris_total.append(("Total Tagihan", rupiah(invoice["total"])))

    tx = x + lebar * 0.55
    akhir_idx = len(baris_total) - 1
    for i, (label, nilai) in enumerate(baris_total):
        if i == akhir_idx:
            c.kotak(tx - 10, y - 6, lebar * 0.45 + 10, 26, isi=(0.97, 0.94, 0.95))
            c.text(tx + 2, y + 10, label, size=11, bold=True)
            c.text(x + lebar - 12, y + 10, nilai, size=13, bold=True, align="right")
            y += 34
        else:
            c.text(tx, y, label, size=9, abu=ABU)
            c.text(x + lebar - 8, y, nilai, size=9, align="right")
            y += 15

    # ------------------------------------------------------------ rekening ----
    if tampil_rekening and rekening:
        y += 6
        blok = wrap(rekening, lebar - 28, 9.5, maks_baris=4)
        tinggi = 20 + len(blok) * 12
        if y + tinggi > c.h - BATAS_BAWAH:
            c.new_page()
            y = MARGIN
        c.kotak(x, y - 4, lebar, tinggi, isi=(0.97, 0.97, 0.98), garis=(0.85, 0.85, 0.87))
        c.text(x + 12, y + 12, "PEMBAYARAN TRANSFER", size=8, bold=True, abu=ABU)
        ty = y + 26
        for b in blok:
            c.text(x + 12, ty, b, size=9.5)
            ty += 12
        y += tinggi + 10
        c.text(x, y, "Mohon cantumkan nomor faktur pada berita transfer.", size=9, abu=ABU)
        y += 18
    else:
        c.text(x, y, "Pembayaran melalui transfer bank atau QRIS. Mohon cantumkan nomor faktur"
                     " pada berita transfer.", size=9, abu=ABU)
        y += 20

    c.text(c.w / 2, y + 8, settings.get("footer_text", ""), size=8, align="center", abu=ABU)
    return c.output()
