# Rasty Florist — Sistem Manajemen Toko Bunga

Web app supplier bunga potong dengan 7 peran pengguna, dibangun dengan
**Python + Flask + SQLite + Bootstrap 5**. Tidak perlu build tool atau database server.

## Pemasangan

Ada dua pemasang: **Windows** (toko, satu komputer) dan **Ubuntu 24.04**
(server, diakses lewat jaringan/internet).

### Ubuntu 24.04 (server)

```bash
scp -r rasty-florist user@IP-SERVER:/tmp/
ssh user@IP-SERVER
cd /tmp/rasty-florist
sudo bash installer/install_ubuntu.sh                        # sistem + database
sudo DOMAIN=toko.example.com bash /opt/rasty-florist/installer/setup_nginx.sh
```

Memasang nginx, gunicorn, SQLite, certbot (HTTPS Let's Encrypt), firewall UFW,
backup harian otomatis, layanan systemd, dan akun administrator. Langkah
lengkap, termasuk backup, pemulihan, pembaruan, dan penanganan masalah, ada di
[PANDUAN-INSTALL-UBUNTU.md](PANDUAN-INSTALL-UBUNTU.md). Khusus pembaruan rutin
(kode, skema database, dan data toko) lihat
[PANDUAN-UPDATE-UBUNTU.md](PANDUAN-UPDATE-UBUNTU.md).

### Windows (toko)

Klik dua kali `pasang.bat`, atau dari terminal:

```powershell
cd C:\Users\FadlyRentha\rasty-florist
python installer\install.py
```

Pemasang memasang Flask + waitress, membuat database dan akun administrator,
menulis `rasty.conf`, membuat `jalankan-server.bat` beserta pintasan desktop,
dan membuka port di Windows Firewall. Kata sandi administrator dibuat acak dan
ditampilkan **sekali** di akhir pemasangan. Sesudahnya jalankan
**`jalankan-server.bat`** (server produksi, waitress) dan buka
<http://127.0.0.1:5000>.

Untuk memasang tanpa pertanyaan: `python installer\install.py --yes`
(tambahkan `--demo` bila ingin data contoh). Langkah lengkap, termasuk backup,
pemulihan, autostart, dan penanganan masalah ada di
[PANDUAN-INSTALL.md](PANDUAN-INSTALL.md).

### Variabel lingkungan

Dipakai oleh kedua pemasang (`rasty.conf` di Windows, `rasty.env` di Ubuntu):

| Variabel | Arti |
|---|---|
| `RASTY_SECRET` | Kunci penanda tangan sesi login |
| `RASTY_DATABASE` | Lokasi berkas database `.db` |
| `RASTY_UPLOAD_FOLDER` | Folder berkas unggahan (di Ubuntu: `/var/lib/rasty-florist/uploads`) |
| `RASTY_BACKUP_FOLDER` | Folder backup (di Ubuntu: `/var/lib/rasty-florist/backups`) |
| `RASTY_HOST` / `RASTY_PORT` | Alamat & port server |
| `RASTY_PROXY` | `1` bila di belakang reverse proxy (nginx), agar URL publik benar |
| `RASTY_DEBUG` | **`0` di server sungguhan** |
| `RASTY_SEED_DEMO` | `1` = isi data contoh, `0` = hanya akun administrator |

## Menjalankan (pengembangan)

```powershell
cd C:\Users\FadlyRentha\rasty-florist
python -m pip install -r requirements.txt
python app.py
```

Buka <http://127.0.0.1:5000>. Atau klik dua kali `jalankan.bat`.

Database `rasty_florist.db` dan data contoh dibuat otomatis saat pertama dijalankan.
Hapus file itu untuk memulai dari nol. Instalasi toko sungguhan (`RASTY_SEED_DEMO=0`)
hanya membuat satu akun administrator, tanpa data contoh.

## Akun demo

| Peran | Username | Password | Halaman awal |
|---|---|---|---|
| Pelanggan | `pelanggan` | `pelanggan123` | `/pelanggan/` |
| Pelanggan (2) | `pelanggan2` | `pelanggan123` | `/pelanggan/` |
| Staff Admin | `staffadmin` | `staff123` | `/staff/` |
| Staff Kantor | `staffkantor` | `staff123` | `/staff/` |
| Staff Gudang | `staffgudang` | `staff123` | `/staff/` |
| Staff Quality Kontrol | `staffqc` | `staff123` | `/qc/` |
| Staff Keuangan | `staffkeuangan` | `staff123` | `/keuangan/` |
| Administrator | `admin` | `admin123` | `/admin/` |

Password disimpan sebagai hash PBKDF2 (Werkzeug). **Ganti password bawaan** sebelum
dipakai di toko sungguhan.

## Matriks peran & menu

### Pelanggan (`/pelanggan/`)
Dashboard · Profil (update data + ubah password) · **Formulir pembelian multi produk** ·
Pesanan saya · Lacak order & status · Ringkasan pembelian · Komplain (upload foto/video) ·
Notifikasi · Konfirmasi WhatsApp · Logout.
Registrasi wajib sebelum checkout — halaman publik menolak pemesanan tanpa akun.
Cetak PO/Invoice pelanggan dinonaktifkan (fitur `invoice` dimatikan di Hak Akses).

### Staff Admin / Staff Kantor / Staff Gudang (`/staff/`)
Menu dibedakan oleh hak akses yang diaktifkan master:
- **Admin** — pelanggan (CRUD), pesanan manual multi produk, **konfirmasi order**,
  data pesanan, produk, stok (hanya lihat), komplain, laporan, notifikasi.
  Di halaman **Konfirmasi Order** setiap produk pesanan bisa **ditambah, diubah, atau
  dihapus** selama pesanan masih *Menunggu Konfirmasi* — dipakai saat stok tidak memenuhi
  jumlah order atau produk kosong. Baris yang bermasalah ditandai *Stok kosong* /
  *Stok kurang*, dan stok, total pesanan, serta faktur dihitung ulang otomatis.
  Item terakhir tidak boleh dihapus (tolak pesanannya bila pelanggan membatalkan).
- **Kantor** — pelanggan, pesanan, produk, stok (termasuk catat mutasi), komplain,
  CMS beranda, laporan.
- **Gudang** — pesanan (hanya detail produk, tanpa total/harga), produk, stok,
  notifikasi, cetak label & checklist QC.

Di menu **Data Produk** (Staff Admin, Staff Kantor, Staff Gudang, dan Staff Keuangan)
setiap produk bisa diberi **foto**: unggah saat menambah produk, ganti lewat tombol ubah,
atau hapus fotonya saja lewat tombol foto tanpa menghapus produknya. Foto lama otomatis
dibuang dari folder unggahan saat diganti atau dihapus, dan foto yang sama tampil di
katalog publik serta panel pelanggan.

Cetak PO/Invoice dan konfirmasi WhatsApp dinonaktifkan untuk Staff Admin dan Staff Gudang.

### Monitoring (semua peran kecuali pelanggan, `/monitoring/`)
**Monitoring Harian** (ringkasan order per tanggal + list stok produk, dengan **auto refresh**
15 detik / 30 detik / 1 menit / 5 menit) · List Order ·
List Stok · Status Pesanan · Lacak Pesanan — halaman baca-saja bersama untuk Staff Admin,
Staff Kantor, Staff Gudang, Staff QC, Staff Keuangan, dan Administrator.

### Monitoring Mandiri (`/pantau`)
Halaman monitoring berdiri sendiri — **di luar situs publik dan panel staf**, tanpa navbar
situs maupun sidebar panel. Menampilkan papan status order (hitung per status), list order
beserta detail produk, dan list stok produk. Bisa difilter per status, punya auto refresh
(15 detik / 30 detik / 1 menit / 5 menit), dan bisa dicetak. Cocok dibuka di layar monitor
gudang.

Aksesnya diatur sebagai fitur hak akses **`monitoring_mandiri`** — administrator bisa
menyalakan atau mematikannya untuk **setiap peran** di menu *Hak Akses*, persis seperti
fitur lain. Bawaannya aktif untuk Staff Admin, Staff Kantor, Staff Gudang, dan
Administrator; nonaktif untuk Pelanggan, Staff QC, dan Staff Keuangan (daftar bawaannya ada
di `db.FEATURE_BAWAAN_OFF`). Peran yang fiturnya mati tidak melihat tautannya dan ditolak
(403) bila membuka URL-nya langsung.

### Akun (semua peran, `/akun/`)
Setiap peran — pelanggan maupun staf — punya halaman **Profil** (`/akun/profil`) dan
**Kata Sandi** (`/akun/kata-sandi`) sendiri, dan bisa membukanya dari **dropdown di nama
sebelah kanan atas** panel (Profil · Kata Sandi · Logout) atau dari grup menu *Akun* di
sidebar. Halaman ini dipakai bersama oleh seluruh peran (`blueprints/account.py`).

### Quality Kontrol (`/qc/`)
Dashboard · List order pembelian dari karyawan · **Verifikasi produk** (upload foto,
upload video, ceklist per produk, keterangan, status) · **Ganti produk** (tukar produk
pesanan yang tidak memenuhi kebutuhan; stok lama dikembalikan, stok pengganti dikurangi,
total pesanan dan faktur dihitung ulang) · **Tambah produk** (menambahkan produk baru ke
pesanan yang sedang ditangani; stok dikurangi dan total pesanan/faktur dihitung ulang) ·
Data komplain (hanya lihat bukti foto/video dan tulisan keluhan) · Status pengiriman/diambil
(tambah, update, hapus, cetak).

Setelah semua item berstatus *Lolos QC*, status pesanan otomatis menjadi **Siap Kirim**
dan notifikasi dikirim ke Keuangan.

### Keuangan (`/keuangan/`)
Ceklist verifikasi order dari QC (termasuk **cetak checklist**) · **Pesanan Manual**
(formulir order multi produk dengan pilihan **kategori tagihan**: Reguler, Abonemen IB,
Abonemen KK, Abonemen KTR) · **Konfirmasi Order** dan **Data Pesanan** — kolom dan fiturnya
sama dengan Staff Admin (produk pesanan bisa ditambah/diubah/dihapus selama masih menunggu
konfirmasi, cetak label, checklist QC, ubah status, hapus pesanan) · Faktur/tagihan
(CRUD + cetak + **unduh PDF** + **kirim ke WhatsApp** lengkap dengan tautan PDF dan rekening
bank) · Keluhan pelanggan (CRUD + cetak,
dengan **kategori keluhan**, **pilihan kompensasi** — Refund / Pengganti Produk / Voucher /
Tidak Ada — **nominal**, **status** Baru/Ditinjau/Proses/Selesai, dan **kolom balasan**;
nama pelanggan terisi otomatis dari daftar pelanggan) · Stok
masuk/keluar (CRUD + cetak) · Verifikasi pembayaran Transfer Bank / QRIS (CRUD + cetak,
otomatis melunasi invoice dan mencatat pemasukan) · Laporan keuangan
harian/mingguan/bulanan/tahunan (CRUD + cetak) · **Data Produk** (tambah, ubah, hapus —
produk yang punya riwayat pesanan hanya dinonaktifkan; **foto produk** bisa ditambah,
diganti, dan dihapus terpisah dari produknya) · **Rekening Bank** (atur rekening
yang dicetak di faktur).

Faktur bisa diekspor ke **PDF** lewat `pdf.py` (penulis PDF mandiri, tanpa pustaka
tambahan) dan dikirim ke WhatsApp pelanggan. Kolom **rekening bank** muncul di dalam
faktur bila diaktifkan administrator di menu *Rekening Bank Faktur*.

**Logo di kop faktur** — logo dari *Pengaturan Situs* otomatis tampil di kop semua
template invoice (klasik, modern, desain unggahan), baik saat dicetak, diekspor PDF,
maupun dibuka dari panel peran mana pun. Administrator bisa menyalakan/mematikannya dan
memilih ukuran **Kecil / Sedang / Besar** di menu *Ganti Template Invoice*. Logo PNG
(dengan/tanpa transparansi) dan JPG ditanam langsung ke berkas PDF tanpa pustaka tambahan.

### Administrator (`/admin/`)
Dashboard · CMS beranda (slider hero, testimoni, sosial media — CRUD) · Pengaturan situs
(logo, nama toko, tagline, alamat, telepon, deskripsi, warna website, jam operasional,
same day delivery) · **Kolom Katalog** (mengaktifkan/menonaktifkan bagian beranda: hero
slider, katalog bunga, ketersediaan stok, jam operasional & same day delivery, testimoni
pelanggan, sosial media) · Data pelanggan · Master produk, stok, pesanan, konfirmasi order,
komplain, faktur, **Ubah Format Nomor** (pola penomoran order, faktur, invoice, keluhan,
transaksi, verifikasi pembayaran, dan ID lacak), **ganti template invoice** (klasik / modern /
desain unggahan PNG-JPG-WEBP), **Rekening Bank Faktur** (kolom rekening di dalam
faktur/invoice), pembayaran,
laporan, checklist QC, pengiriman · Akun staff · **Master hak akses**
(mengaktifkan/menonaktifkan fitur per peran, termasuk menyalakan/mematikan
**Monitoring Mandiri** untuk tiap peran) · **Backup data** (manual + otomatis
harian/mingguan/bulanan/tahunan, unduh & hapus berkas) · **Pembaruan Aplikasi**
(cek versi terpasang vs versi di GitHub, perbarui online dari GitHub atau dari berkas
`.zip`, dengan database/unggahan/backup/konfigurasi yang tidak pernah tersentuh) ·
**Reset Pengaturan** · Notifikasi. Versi aplikasi juga tampil di sidebar panel dan
footer website.

Menu **Reset Pengaturan** mengembalikan aplikasi/website ke pengaturan default per bagian:
Pengaturan Website, Kolom Katalog Beranda, Isi Beranda (CMS), dan Hak Akses Peran.
Backup database otomatis dibuat lebih dulu, dan data pesanan/produk/pelanggan tidak
pernah dihapus.

## Alur status pesanan

```
Menunggu Konfirmasi → Diproses → Quality Kontrol → Siap Kirim → Dikirim → Selesai
                              ↘ Dibatalkan (stok dikembalikan otomatis)
```

## Struktur berkas

```
rasty-florist/
├── pasang.bat          # pemasang Windows (klik dua kali)
├── installer/
│   ├── install.py           # pemasang Windows: dependensi, database, rasty.conf, pintasan, firewall
│   ├── set_sandi.py         # lihat akun & ganti kata sandi (lintas platform)
│   ├── install_ubuntu.sh    # pemasang Ubuntu: paket, pengguna, venv, database, systemd
│   ├── setup_nginx.sh       # vhost nginx + HTTPS Let's Encrypt
│   ├── backup_ubuntu.sh     # backup database + unggahan, dipangkas otomatis
│   ├── update_ubuntu.sh     # perbarui kode di server (backup → pasang → migrasi → restart)
│   ├── set_sandi_ubuntu.sh  # kelola akun di server (daftar/sandi/aktif-nonaktif)
│   ├── uninstall_ubuntu.sh  # cabut pemasangan (data dipertahankan secara bawaan)
│   ├── update.py            # pasang kode baru dari folder/zip/GitHub (lintas platform)
│   └── init_db.py           # inisialisasi database dari variabel lingkungan
├── jalankan-server.bat # peluncur server produksi Windows (dibuat oleh pemasang)
├── jalankan_server.py  # baca rasty.conf lalu jalankan server (waitress)
├── serve.py            # server produksi waitress (Windows)
├── wsgi.py             # entry point gunicorn (Linux)
├── rasty.conf          # konfigurasi server Windows (dibuat oleh pemasang)
├── app.py              # factory aplikasi, context processor, error handler
├── version.py          # nomor versi aplikasi + repositori GitHub sumber pembaruan
├── updater.py          # cek versi, unduh GitHub, pasang kode baru (menjaga data toko)
├── db.py               # skema SQLite, seed data, pengaturan situs, hak akses
├── helpers.py          # auth, dekorator hak akses, upload, notifikasi, transaksi pesanan
├── pdf.py              # penulis berkas PDF mandiri (tanpa pustaka tambahan)
├── invoice_pdf.py      # tata letak faktur untuk ekspor PDF
├── nav.py              # konfigurasi menu sidebar per peran
├── blueprints/
│   ├── auth.py         # login, register, logout
│   ├── account.py      # profil + kata sandi untuk semua peran
│   ├── public.py       # beranda, katalog, detail produk, lacak publik
│   ├── customer.py     # panel pelanggan
│   ├── staff.py        # panel staff (admin/kantor/gudang)
│   ├── qc.py           # panel quality kontrol
│   ├── finance.py      # panel keuangan
│   ├── admin.py        # CMS, pengaturan, akun staff, hak akses, kontroller ID, template invoice
│   └── monitoring.py   # monitoring harian, list order/stok/status/lacak untuk semua peran staf
├── templates/
│   ├── public/         # base + beranda + CSS tema
│   ├── pantau/         # halaman monitoring mandiri (layout sendiri)
│   ├── auth/  account/  customer/  staff/  qc/  finance/  admin/  shared/
│   └── panel_base.html # layout panel (sidebar + topbar)
├── static/uploads/     # berkas unggahan (foto QC, komplain, pembayaran, logo, CMS, desain invoice)
├── backups/            # berkas backup database (.db) dari menu Backup Data
├── smoke_test.py       # uji semua rute GET per peran
├── flow_test.py        # uji alur pesanan → QC → pembayaran → laporan
├── install_test.py     # uji instalasi bersih (tanpa data contoh)
├── update_test.py      # uji pembaruan aplikasi (versi, proteksi data, zip)
└── requirements.txt    # Flask + waitress
```

## Uji

```powershell
python smoke_test.py    # semua rute GET untuk 7 peran (butuh data contoh)
python flow_test.py     # alur transaksi end-to-end (butuh data contoh)
python install_test.py  # instalasi bersih tanpa data contoh
python update_test.py   # pembaruan aplikasi, tanpa jaringan
```

Di server Ubuntu:

```bash
cd /opt/rasty-florist
sudo -u rasty .venv/bin/python installer/init_db.py   # struktur & akun
sudo -u rasty .venv/bin/python smoke_test.py
sudo -u rasty .venv/bin/python flow_test.py
```

## Catatan teknis

- **Keamanan** — password PBKDF2; sesi Flask bertanda tangan; dekorator `role_required`
  dan `feature_required` menjaga setiap halaman; unggahan dibatasi ekstensi
  (gambar/video) dan ukuran 32 MB, nama berkas diacak.
- **Stok** — berkurang otomatis saat pesanan dibuat dan kembali saat pesanan dibatalkan
  atau dihapus; setiap perubahan tercatat di `stock_moves`.
- **Cetak** — semua dokumen cetak memakai `@media print` sehingga sidebar, tombol, dan
  navigasi tidak ikut tercetak.
- **Backup** — berkas `.db` disalin dengan `sqlite3.Connection.backup()` ke folder
  `backups/`. Jadwal otomatis (harian/mingguan/bulanan/tahunan) diperiksa tiap jam
  selama aplikasi berjalan, jadi backup tetap jalan walau server tidak pernah restart.
- **Warna situs** — warna primer/sekunder dari Pengaturan disuntik sebagai CSS variable,
  jadi seluruh tampilan (publik dan panel) ikut berubah tanpa perlu edit CSS.
