"""Uji cepat: login setiap peran lalu akses semua halaman GET."""
import re
import sys

import app as application

app = application.app
app.config["TESTING"] = True

ROUTES = {
    "pelanggan": ["/pelanggan/", "/pelanggan/profil", "/pelanggan/pesanan/baru",
                  "/pelanggan/pesanan", "/pelanggan/lacak", "/pelanggan/ringkasan",
                  "/pelanggan/komplain", "/pelanggan/notifikasi",
                  "/akun/profil", "/akun/kata-sandi"],
    "staffadmin": ["/staff/", "/staff/pelanggan", "/staff/pesanan", "/staff/pesanan/baru",
                   "/staff/konfirmasi-order", "/staff/produk", "/staff/produk?q=Mawar",
                   "/staff/stok", "/staff/komplain",
                   "/staff/notifikasi", "/staff/laporan", "/monitoring/", "/monitoring/harian",
                   "/monitoring/order", "/monitoring/stok", "/monitoring/status", "/monitoring/lacak",
                   "/akun/profil", "/akun/kata-sandi",
                   "/pantau", "/pantau?refresh=30", "/pantau?status=Selesai"],
    "staffkantor": ["/staff/", "/staff/pelanggan", "/staff/pesanan", "/staff/produk",
                    "/staff/stok", "/staff/komplain", "/admin/cms", "/staff/notifikasi",
                    "/monitoring/", "/monitoring/harian", "/monitoring/order", "/monitoring/stok",
                    "/monitoring/status", "/monitoring/lacak",
                    "/akun/profil", "/akun/kata-sandi"],
    "staffgudang": ["/staff/", "/staff/pesanan", "/staff/produk", "/staff/stok",
                    "/staff/notifikasi", "/monitoring/", "/monitoring/harian",
                    "/monitoring/order", "/monitoring/stok", "/monitoring/status",
                    "/monitoring/lacak", "/akun/profil", "/akun/kata-sandi"],
    "staffqc": ["/qc/", "/qc/pesanan", "/qc/ganti-produk", "/qc/komplain", "/qc/pengiriman",
                "/qc/pengiriman/cetak", "/qc/notifikasi", "/monitoring/", "/monitoring/harian",
                "/monitoring/order", "/monitoring/stok", "/monitoring/status",
                "/monitoring/lacak", "/akun/profil", "/akun/kata-sandi"],
    "staffkeuangan": ["/keuangan/", "/keuangan/qc", "/keuangan/faktur", "/keuangan/keluhan",
                      "/keuangan/stok", "/keuangan/pembayaran", "/keuangan/laporan",
                      "/keuangan/laporan/cetak", "/keuangan/notifikasi", "/keuangan/stok/cetak",
                      "/keuangan/pembayaran/cetak", "/keuangan/keluhan/cetak",
                      "/keuangan/pesanan-baru", "/keuangan/produk", "/keuangan/rekening",
                      "/staff/konfirmasi-order", "/staff/pesanan",
                      "/monitoring/", "/monitoring/harian", "/monitoring/order",
                      "/monitoring/stok", "/monitoring/status", "/monitoring/lacak",
                      "/akun/profil", "/akun/kata-sandi"],
    "admin": ["/admin/", "/admin/cms", "/admin/sosial", "/admin/pengaturan", "/admin/akun",
              "/admin/hak-akses",
              "/admin/format-nomor", "/admin/template-invoice", "/admin/backup",
              "/admin/update",
              "/admin/katalog", "/admin/rekening", "/admin/reset",
              "/admin/pengiriman", "/admin/jam-operasional", "/admin/menu-publik",
              "/admin/notifikasi", "/staff/",
              "/staff/pesanan", "/staff/pelanggan", "/staff/konfirmasi-order", "/staff/produk",
              "/staff/stok", "/staff/komplain", "/staff/laporan", "/qc/", "/qc/pesanan",
              "/qc/ganti-produk", "/qc/pengiriman", "/keuangan/", "/keuangan/qc",
              "/keuangan/faktur", "/keuangan/keluhan", "/keuangan/stok", "/keuangan/pembayaran",
              "/keuangan/laporan", "/monitoring/", "/monitoring/harian", "/monitoring/order",
              "/monitoring/stok", "/monitoring/status", "/monitoring/lacak",
              "/akun/profil", "/akun/kata-sandi"],
}
PASSWORDS = {
    "pelanggan": "pelanggan123", "staffadmin": "staff123", "staffkantor": "staff123",
    "staffgudang": "staff123", "staffqc": "staff123", "staffkeuangan": "staff123",
    "admin": "admin123",
}

failures = []
for username, urls in ROUTES.items():
    client = app.test_client()
    r = client.post("/login", data={"username": username, "password": PASSWORDS[username]},
                    follow_redirects=True)
    if r.status_code != 200:
        failures.append((username, "/login", r.status_code, ""))
        continue
    for url in urls:
        try:
            res = client.get(url)
        except Exception as exc:  # noqa: BLE001
            failures.append((username, url, "EXC", repr(exc)[:300]))
            continue
        if res.status_code >= 400:
            body = res.get_data(as_text=True)
            m = re.search(r"<title>(.*?)</title>", body, re.S)
            failures.append((username, url, res.status_code, m.group(1).strip() if m else ""))

if failures:
    for f in failures:
        print("FAIL", f)
    sys.exit(1)
print("SEMUA RUTE OK")
