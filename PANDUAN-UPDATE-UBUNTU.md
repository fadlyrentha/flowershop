# Panduan Pembaruan di Ubuntu — Rasty Florist

Panduan memperbarui **kode aplikasi**, **skema database**, dan **data toko** pada
pemasangan Ubuntu yang dibuat oleh `installer/install_ubuntu.sh`.

Ringkasan lokasi penting (jangan tertukar):

| Isi | Lokasi |
|---|---|
| Kode aplikasi | `/opt/rasty-florist` |
| **Database** | `/var/lib/rasty-florist/rasty_florist.db` |
| **Unggahan (foto, bukti bayar)** | `/var/lib/rasty-florist/uploads` |
| Backup | `/var/lib/rasty-florist/backups` |
| Konfigurasi | `/etc/rasty-florist/rasty.env` |
| Log | `/var/log/rasty-florist/` |

Prinsipnya: **kode di `/opt`, data di `/var/lib`**. Karena keduanya terpisah,
memperbarui kode tidak pernah menghapus database atau foto.

---

## 1. Aturan dasar sebelum apa pun

1. **Selalu backup dulu.** Satu perintah, aman walau aplikasi sedang dipakai.
2. Perbarui di luar jam ramai.
3. Jangan menyalin `rasty_florist.db` dari komputer pengembangan ke server —
   itu akan menimpa data toko yang sudah berjalan.

```bash
sudo bash /opt/rasty-florist/installer/backup_ubuntu.sh
```

Backup yang hanya ada di server yang sama tidak menolong bila disknya rusak,
jadi **salin hasilnya ke luar server**:

```bash
# jalankan di komputer Anda
scp -r user@IP-SERVER:/var/lib/rasty-florist/backups ./backup-rasty
```

---

## 2. Pembaruan kode aplikasi (versi baru)

### 2.0 Cara tercepat: menu Pembaruan Aplikasi di panel

Administrator → **Pembaruan Aplikasi** menyediakan tiga hal:

- **Lihat versi** — versi yang terpasang dan versi terbaru di GitHub, lengkap dengan
  waktu pemeriksaan terakhir.
- **Perbarui dari GitHub** — mengunduh cabang terpantau (`version.py` → `CABANG`)
  dan memasangnya. Tidak perlu SSH.
- **Perbarui dari berkas (.zip)** — untuk server tanpa akses internet.

> Catatan: kode di `/opt/rasty-florist` dimiliki **root** dan hanya-baca bagi pengguna
> layanan, jadi tombol pembaruan **tidak dapat menulis** di server hasil
> `install_ubuntu.sh`. Halaman akan menampilkan perintah SSH yang harus dijalankan.
> Ini disengaja: proses web tidak diberi hak menulis ke kode produksi.
> Gunakan **bagian 2.1** di bawah, atau longgarkan hak tulis folder bila Anda
> memang ingin memperbarui dari browser.

### 2.0b Cara resmi di server: satu perintah

```bash
sudo bash /opt/rasty-florist/installer/update_ubuntu.sh --online
```

Yang dilakukan skrip ini, berurutan:

1. **Backup database** lewat `backup_ubuntu.sh` (gagal backup = pembaruan dibatalkan);
2. **Pasang kode baru** — mengunduh dari GitHub, atau memakai `--zip`/`--sumber`;
3. **Rapikan hak akses** folder aplikasi (`root:rasty`, hanya-baca untuk layanan);
4. **Pasang dependensi** dari `requirements.txt` bila ada yang baru;
5. **Migrasi database** lewat `installer/init_db.py`;
6. **Nyalakan ulang** layanan dan laporkan statusnya.

Database, folder unggahan, folder backup, dan `/etc/rasty-florist/rasty.env`
**tidak pernah tersentuh**. Berkas yang tidak ada di sumber juga tidak dihapus.

Pilihan lain:

```bash
# dari berkas zip yang sudah diunggah ke server
sudo bash installer/update_ubuntu.sh --zip /tmp/rasty-florist.zip

# dari folder hasil git clone / scp
sudo bash installer/update_ubuntu.sh --sumber /tmp/rasty-florist

# hitung saja tanpa menulis apa pun (aman dicoba)
sudo bash installer/update_ubuntu.sh --online --dry-run

# pasang kode, tetapi jangan nyalakan ulang layanan
sudo bash installer/update_ubuntu.sh --online --tanpa-restart
```

### 2.1 Kirim kode baru ke server

Pilih salah satu sesuai cara Anda memperoleh kode.

**Lewat Git (disarankan):**

```bash
# di server
sudo rm -rf /tmp/rasty-florist
git clone <alamat-repo> /tmp/rasty-florist
```

Bila ingin memakai versi/tag tertentu:

```bash
git clone --branch v1.2.0 --depth 1 <alamat-repo> /tmp/rasty-florist
```

**Lewat SCP dari komputer Anda:**

```bash
# jalankan di komputer Anda
rm -rf /tmp/rasty-florist
scp -r rasty-florist user@IP-SERVER:/tmp/
```

**Lewat tar.gz (paling rapi):**

```bash
# di komputer Anda
tar -czf rasty-florist-baruu.tar.gz rasty-florist
scp rasty-florist-baru.tar.gz user@IP-SERVER:/tmp/

# di server
rm -rf /tmp/rasty-florist
tar -xzf /tmp/rasty-florist-baru.tar.gz -C /tmp
```

### 2.2 Jalankan pemasang

```bash
sudo bash /tmp/rasty-florist/installer/install_ubuntu.sh
```

Pemasang aman dijalankan berulang ("pasang ulang"). Yang terjadi:

1. paket sistem dipastikan ada (tidak mengubah yang sudah benar);
2. kode disalin ke `/opt/rasty-florist` dengan
   `rsync --delete`, **tetapi database (`*.db`), `backups/`, dan
   `static/uploads/` dikecualikan** — data toko tidak tersentuh;
3. virtualenv dipakai ulang, lalu `pip install -r requirements.txt`
   dijalankan lagi (dependensi baru ikut terpasang);
4. `/etc/rasty-florist/rasty.env` dicadangkan ke `.bak-<stempel>` dan
   **kunci sesi lama dipertahankan** — pengguna tidak ter-logout;
5. `installer/init_db.py` dijalankan → memicu `database.init_db()` di `db.py`,
   yang menjalankan **migrasi kolom/tabel baru secara otomatis**
   (`_migrate()`), lalu mengisi pengaturan bawaan yang belum ada;
6. layanan systemd ditulis ulang lalu dinyalakan;
7. uji cepat `curl http://127.0.0.1:8000/` dijalankan.

Penting: karena database sudah ada, pemasang **tidak** membuat ulang akun
administrator dan **tidak** mengubah kata sandi siapa pun.

### 2.3 Perbarui konfigurasi nginx bila perlu

Bila versi baru menambah jenis unggahan, ukuran unggahan, atau rute statis,
jalankan ulang penyiapan nginx:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

`install_ubuntu.sh` tidak menyentuh nginx. Bila Anda mengubah
`installer/setup_nginx.sh` atau `DOMAIN`:

```bash
sudo DOMAIN=toko.example.com EMAIL_SSL=admin@example.com \
     bash /opt/rasty-florist/installer/setup_nginx.sh
```

---

## 3. Pembaruan skema database (migrasi)

Tidak perlu tindakan terpisah. Skema dan migrasi berjalan otomatis saat
aplikasi pertama kali dimuat setelah kode baru:

- Tabel baru: dibuat oleh `CREATE TABLE IF NOT EXISTS` di `db.py`.
- Kolom baru: ditambahkan oleh `_migrate()` dengan
  `ALTER TABLE ... ADD COLUMN` dan penanda di tabel `settings`, sehingga
  migrasi hanya berjalan sekali dan aman diulang.
- Data lama: `NOT NULL DEFAULT 0` / `DEFAULT ''` membuat baris lama langsung
  valid tanpa perlu diisi manual.

### 3.1 Memaksa migrasi tanpa memasang ulang kode

Berguna bila Anda hanya mengganti satu berkas Python:

```bash
sudo systemctl stop rasty-florist
sudo -u rasty /opt/rasty-florist/.venv/bin/python \
     /opt/rasty-florist/installer/init_db.py
sudo systemctl start rasty-florist
```

`installer/init_db.py` mencetak ringkasan: lokasi database, jumlah akun,
jumlah produk, dan akun administrator. Bila keluar dengan kode ≠ 0, periksa
pesan `!` yang dicetak.

### 3.2 Memeriksa hasil migrasi

```bash
sudo sqlite3 /var/lib/rasty-florist/rasty_florist.db "PRAGMA table_info(products);"
sudo sqlite3 /var/lib/rasty-florist/rasty_florist.db "SELECT key, value FROM settings WHERE key LIKE 'migrasi_%';"
```

Bila kolom baru yang Anda harapkan tidak muncul, berarti langkah 2.2/3.1 belum
menjalankan `db.py` versi terbaru — pastikan berkas tersebut benar-benar
tersalin ke `/opt/rasty-florist`.

---

## 4. Pembaruan data toko

### 4.1 Cara normal — lewat aplikasi (disarankan)

Hampir semua data diubah dari panel, bukan dari baris perintah. Ini menjaga
relasi antar tabel tetap konsisten.

| Yang diubah | Halaman |
|---|---|
| Produk: deskripsi singkat/panjang, rekomendasi, ketentuan, minimum order, harga, stok | **Data Produk** (`/keuangan/produk` atau `/staff/produk`, hanya administrator & staff keuangan) |
| Stok masuk/keluar | **Stok Masuk/Keluar** |
| Faktur: subtotal, ongkir, status, jatuh tempo | **Faktur / Tagihan** (`/keuangan/faktur`) |
| Pengaturan situs, metode pengiriman, jam operasional | **Administrator → Pengaturan / Konfigurasi** |
| Hak akses fitur per peran | **Administrator → Hak Akses** |

### 4.2 Perubahan massal lewat SQL

Untuk kasus seperti "naikkan semua harga 10%" atau "isi minimum order semua
produk". **Backup dulu**, lalu:

```bash
sudo systemctl stop rasty-florist

sudo -u rasty sqlite3 /var/lib/rasty-florist/rasty_florist.db <<'SQL'
.timeout 5000
BEGIN;
UPDATE products SET harga = CAST(harga * 1.1 AS INTEGER) WHERE aktif = 1;
UPDATE products SET min_order = 5 WHERE min_order = 0 AND satuan = 'ikat';
COMMIT;
SQL

sudo systemctl start rasty-florist
```

Aturan aman:

- **Selalu** `BEGIN; ... COMMIT;` agar gagal di tengah tidak meninggalkan data
  separuh jalan.
- **Selalu** `sudo systemctl stop` dulu untuk perubahan besar. WAL sudah
  membuat penulisan bersamaan aman, tetapi berhenti sesaat lebih pasti.
- Jangan pernah `UPDATE`/`DELETE` pada `orders`, `order_items`, atau
  `invoices` secara manual — nomor, subtotal, ongkir, dan total saling
  bergantung. Pakai halaman aplikasi.
- Bila perubahan menyangkut uang (harga, faktur), jalankan uji alur setelahnya
  (bagian 6).

### 4.3 Import data dari pengembangan / server lain

Cara yang benar bukan menimpa database, melainkan menyalin isinya:

```bash
# di komputer pengembangan: buat salinan bersih
sqlite3 rasty_florist.db ".backup 'kirim.db'"
scp kirim.db user@IP-SERVER:/tmp/

# di server: ambil hanya tabel produk sebagai contoh
sudo sqlite3 /var/lib/rasty-florist/rasty_florist.db \
  "ATTACH '/tmp/kirim.db' AS baru;
   INSERT INTO products (nama, deskripsi, deskripsi_panjang, rekomendasi, ketentuan,
                         kategori, harga, stok, stok_minimum, min_order, satuan, aktif, created_at)
   SELECT nama, deskripsi, deskripsi_panjang, rekomendasi, ketentuan,
          kategori, harga, 0, stok_minimum, min_order, satuan, aktif, created_at
     FROM baru.products
    WHERE nama NOT IN (SELECT nama FROM products);
   DETACH DATABASE baru;"
```

Perhatikan `stok` sengaja diisi `0`: stok harus masuk lewat halaman
**Stok Masuk/Keluar** agar tercatat di riwayat mutasi.

### 4.4 Unggahan (foto produk, bukti pembayaran)

Berkas unggahan disimpan di `/var/lib/rasty-florist/uploads`, sedangkan
database hanya menyimpan **nama berkasnya**. Jadi:

- Menambah foto: lewat form produk (otomatis tersimpan di folder itu).
- Menyalin foto antar server: salin **berkasnya** ke folder unggahan, bukan
  hanya baris database.
- Hak akses setelah menyalin manual:

```bash
sudo chown -R rasty:www-data /var/lib/rasty-florist/uploads
sudo chmod -R 2750 /var/lib/rasty-florist/uploads
```

---

## 5. Memeriksa setelah pembaruan

```bash
# 1. Layanan hidup?
sudo systemctl status rasty-florist --no-pager
sudo journalctl -u rasty-florist -n 50 --no-pager

# 2. Aplikasi merespons?
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/

# 3. Lewat nginx/HTTPS
curl -s -o /dev/null -w '%{http_code}\n' https://toko.example.com/

# 4. Database utuh?
sudo sqlite3 /var/lib/rasty-florist/rasty_florist.db "PRAGMA integrity_check;"
```

Harapan: layanan `active (running)`, HTTP `200`, dan integrity check `ok`.

Setelah itu buka browser dan lakukan uji manual cepat: login sebagai
administrator, buka **Data Produk**, ubah satu produk, dan lihat hasilnya di
halaman publik.

---

## 6. Uji otomatis (opsional, hanya di server uji)

```bash
cd /opt/rasty-florist
sudo -u rasty .venv/bin/python smoke_test.py   # semua halaman tiap peran
sudo -u rasty .venv/bin/python flow_test.py    # alur pesanan → faktur → bayar
```

Keduanya memerlukan **data contoh** (`SEED_DEMO=1`). Jangan dijalankan di
server toko sungguhan — tes membuat dan menghapus data.

---

## 7. Mengembalikan bila pembaruan bermasalah

### 7.1 Kembalikan kode saja (data tetap)

```bash
sudo rm -rf /tmp/rasty-florist
git clone --branch <tag-sebelumnya> <alamat-repo> /tmp/rasty-florist
sudo bash /tmp/rasty-florist/installer/install_ubuntu.sh
```

Catatan: migrasi database **tidak** dibatalkan oleh langkah ini. Kolom baru
tetap ada (tidak mengganggu kode lama, karena hanya menambah). Bila kode lama
benar-benar tidak tahan terhadap kolom tambahan, lakukan 7.2.

### 7.2 Kembalikan database dari backup

```bash
sudo systemctl stop rasty-florist
sudo cp /var/lib/rasty-florist/rasty_florist.db \
        /var/lib/rasty-florist/backups/sebelum-update.db   # simpan kondisi sekarang

sudo cp /var/lib/rasty-florist/backups/rasty-db-<stempel>.db \
        /var/lib/rasty-florist/rasty_florist.db
# Berkas WAL/SHM lama harus ikut dibuang agar tidak menimpa hasil restore.
sudo rm -f /var/lib/rasty-florist/rasty_florist.db-wal \
           /var/lib/rasty-florist/rasty_florist.db-shm
sudo chown rasty:rasty /var/lib/rasty-florist/rasty_florist.db
sudo chmod 0640 /var/lib/rasty-florist/rasty_florist.db
sudo systemctl start rasty-florist
```

Langkah `rm -f ...-wal` dan `...-shm` penting: tanpa itu SQLite dapat
memakai kembali isi WAL lama dan perubahan yang seharusnya dibatalkan tetap
muncul.

### 7.3 Kembalikan unggahan

```bash
sudo tar -xzf /var/lib/rasty-florist/backups/rasty-uploads-<stempel>.tar.gz \
     -C /var/lib/rasty-florist/uploads
sudo chown -R rasty:www-data /var/lib/rasty-florist/uploads
```

Database dan unggahan **harus dipulihkan bersama**: nama berkas foto ada di
database, isinya ada di folder unggahan.

### 7.4 Memulihkan lewat panel (tanpa SSH)

Administrator bisa memulihkan langsung dari menu **Administrator → Backup Data**:

- **Pulihkan** (ikon ↺) pada baris riwayat backup — memakai berkas yang sudah ada
  di server.
- **Pulihkan dari Berkas Backup** — unggah berkas `.db` hasil unduhan backup
  (maksimal 32 MB).

Keduanya memeriksa integritas berkas dan memastikan berkas itu memang backup
aplikasi ini (tabel `users`, `products`, `orders`, dan lainnya harus ada)
sebelum menimpa database. Keadaan sebelum pemulihan dicadangkan otomatis
sebagai `rasty-sebelum-restore-<stempel>.db`, jadi salah pilih masih bisa
dibatalkan dengan memulihkan berkas tersebut.

Yang **tidak** ikut berubah: folder unggahan dan `/etc/rasty-florist/rasty.env`.
Bila memulihkan ke server lain, salin folder unggahan secara terpisah
(bagian 7.3).

Bila server melayani banyak pengguna (gunicorn beberapa worker), lakukan
pemulihan saat toko sedang sepi. Untuk memastikan semua proses membaca
database hasil pemulihan, nyalakan ulang layanan setelahnya:

```bash
sudo systemctl restart rasty-florist
```

Pemulihan mengubah seluruh data akun, jadi pengguna yang sedang login bisa
ter-logout sendiri — itu normal.

---

## 8. Ringkasan perintah

```bash
# backup + salin keluar server
sudo bash /opt/rasty-florist/installer/backup_ubuntu.sh
scp -r user@IP-SERVER:/var/lib/rasty-florist/backups ./backup-rasty

# perbarui kode (git)
sudo rm -rf /tmp/rasty-florist && git clone <alamat-repo> /tmp/rasty-florist
sudo bash /tmp/rasty-florist/installer/install_ubuntu.sh

# periksa
sudo systemctl status rasty-florist --no-pager
sudo journalctl -u rasty-florist -n 50 --no-pager
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/

# reload nginx bila konfigurasi berubah
sudo nginx -t && sudo systemctl reload nginx
```

---

## 9. Hal yang sering salah

| Kesalahan | Akibat | Yang benar |
|---|---|---|
| Menimpa `rasty_florist.db` dengan database pengembangan | Seluruh data toko hilang | Ubah data lewat panel atau `INSERT ... SELECT` (bagian 4.3) |
| Menyalin `.db` saat aplikasi berjalan dengan `cp` | Berkas bisa tidak konsisten | Pakai `backup_ubuntu.sh` (memakai `sqlite3 .backup`) |
| Restore tanpa menghapus `-wal`/`-shm` | Perubahan lama muncul kembali | Hapus keduanya sebelum start (bagian 7.2) |
| Menjalankan `smoke_test.py` di server produksi | Data contoh dibuat & dihapus | Hanya di server uji |
| Mengedit berkas di `/opt/rasty-florist` langsung | Hilang saat pasang ulang; folder hanya-baca | Edit di sumber, lalu jalankan pemasang |
| Lupa salin backup ke luar server | Backup ikut hilang saat disk rusak | `scp` rutin (bagian 1) |
| Memulihkan backup lama lalu heran foto hilang | Database dan unggahan dipulihkan terpisah | Pulihkan keduanya (bagian 7.2 & 7.3) |
| Mengunggah berkas `.db` dari aplikasi lain | Ditolak dengan pesan "bukan backup Rasty Florist" | Hanya unggah berkas hasil fitur backup ini |
