# Panduan Pemasangan di Ubuntu 24.04 — Rasty Florist

Panduan memasang aplikasi di server Ubuntu 24.04 (LTS) lengkap dengan web
server (nginx), server aplikasi (gunicorn), database (SQLite), HTTPS, firewall,
backup otomatis, dan perangkat pihak ketiga lainnya.

Aplikasi ini **tidak butuh** MySQL/PostgreSQL, Node.js, Docker, atau build tool.
Database memakai SQLite yang sudah menyatu dengan Python.

---

## 1. Yang dibutuhkan

| Kebutuhan | Keterangan |
|---|---|
| Ubuntu Server 24.04 LTS | 64-bit, minimal 1 vCPU / 1 GB RAM / 10 GB disk |
| Akses root atau `sudo` | Seluruh pemasangan dijalankan sebagai root |
| Koneksi internet | Untuk mengunduh paket apt dan dependensi Python |
| Domain + DNS (opsional) | Diperlukan bila ingin HTTPS dari Let's Encrypt |

Ukuran server: untuk satu toko, 1 vCPU / 1 GB RAM sudah cukup. Yang paling
menentukan adalah ukuran disk, karena foto produk dan bukti pembayaran
disimpan di server.

---

## 2. Paket pihak ketiga yang dipasang

Pemasang memasang paket-paket berikut dari repositori resmi Ubuntu:

| Paket | Untuk apa |
|---|---|
| `nginx` | Web server / reverse proxy, melayani HTTPS dan berkas statis |
| `certbot`, `python3-certbot-nginx` | Sertifikat SSL gratis Let's Encrypt + perpanjangan otomatis |
| `python3`, `python3-venv`, `python3-pip` | Menjalankan aplikasi dan memasang dependensi di virtualenv |
| `python3-dev`, `build-essential` | Compiler cadangan bila ada paket Python yang perlu dibangun |
| `sqlite3` | Alat perintah untuk memeriksa dan mem-backup database |
| `ufw` | Firewall sederhana (aturan dibuat, pengaktifan manual) |
| `rsync` | Menyalin kode aplikasi ke `/opt` |
| `curl`, `ca-certificates` | Uji layanan & sertifikat |

Dependensi Python (`Flask`, `gunicorn`) dipasang di dalam virtualenv
`/opt/rasty-florist/.venv`, terpisah dari paket sistem.

Arsitektur yang dihasilkan:

```
Internet
   |
   v
[ nginx :80/:443 ]  <-- HTTPS (Let's Encrypt), berkas /static/uploads
   |  proxy_pass
   v
[ gunicorn 127.0.0.1:8000 ]  3 worker, dijalankan systemd
   |
   v
[ Flask + SQLite ]  /var/lib/rasty-florist/rasty_florist.db
```

---

## 3. Pemasangan

### 3.1 Salin aplikasi ke server

Dari komputer Anda, kirim folder aplikasi ke server:

```bash
# jalankan di komputer Anda
scp -r rasty-florist user@IP-SERVER:/tmp/
```

Atau lewat Git bila kode ada di repositori:

```bash
git clone <alamat-repo> /tmp/rasty-florist
```

### 3.2 Jalankan pemasang

```bash
ssh user@IP-SERVER
cd /tmp/rasty-florist
sudo bash installer/install_ubuntu.sh
```

Sekitar 1–3 menit. Pemasang akan:

1. memasang paket sistem di atas;
2. membuat pengguna sistem `rasty` (tanpa login) dan folder data;
3. menyalin aplikasi ke `/opt/rasty-florist` (hanya-baca untuk pengguna layanan);
4. membuat virtualenv dan memasang Flask + gunicorn;
5. menulis `/etc/rasty-florist/rasty.env` berisi kunci sesi acak;
6. membuat database SQLite dan akun administrator;
7. memasang layanan systemd `rasty-florist` (langsung dinyalakan);
8. memasang backup harian otomatis dan aturan sudo pemeliharaan;
9. menguji aplikasi lewat `http://127.0.0.1:8000`.

**Catat username dan kata sandi administrator yang ditampilkan di akhir.**
Kata sandi dibuat acak dan hanya muncul sekali.

### 3.3 Pasang nginx & HTTPS

```bash
# tanpa domain (bisa dibuka lewat IP server)
sudo bash /opt/rasty-florist/installer/setup_nginx.sh

# dengan domain + HTTPS otomatis
sudo DOMAIN=toko.example.com EMAIL_SSL=admin@example.com \
     bash /opt/rasty-florist/installer/setup_nginx.sh
```

Sebelum memakai domain, arahkan **A record** domain ke IP server ini dan
tunggu propagasi DNS. Skrip memeriksa hal ini sendiri: bila DNS belum tepat,
sertifikat dilewati dan aplikasi tetap jalan lewat HTTP.

Aplikasi kini bisa dibuka di `https://toko.example.com`.

---

## 4. Pilihan pemasang

Semua lewat variabel lingkungan di depan perintah:

```bash
# Toko sungguhan (bawaan) - hanya akun administrator
sudo bash installer/install_ubuntu.sh

# Ikut data contoh untuk pelatihan (produk, pesanan, akun demo)
sudo SEED_DEMO=1 bash installer/install_ubuntu.sh

# Port aplikasi lain & jumlah worker berbeda
sudo PORT=9000 WORKERS=5 bash installer/install_ubuntu.sh

# Administrator dengan nama sendiri (sandi tetap dibuat acak)
sudo ADMIN_USER=pemilik ADMIN_NAMA="Pemilik Toko" ADMIN_EMAIL=owner@example.com \
     bash installer/install_ubuntu.sh
```

| Variabel | Bawaan | Arti |
|---|---|---|
| `DOMAIN` | (kosong) | Nama domain untuk vhost nginx |
| `PORT` | `8000` | Port internal gunicorn (nginx yang menghadap internet) |
| `WORKERS` | `3` | Jumlah proses gunicorn. Rumus umum: 2 × CPU + 1 |
| `ADMIN_USER` | `admin` | Username administrator pertama |
| `ADMIN_EMAIL` | `admin@rastyflorist.id` | Email administrator |
| `ADMIN_NAMA` | `Administrator` | Nama tampilan administrator |
| `SEED_DEMO` | `0` | `1` = isi data contoh |

Memasang ulang aman: database lama dipertahankan, kunci sesi tidak berubah
(pengguna tidak ter-logout), dan konfigurasi lama dicadangkan.

---

## 5. Lokasi berkas penting

| Isi | Lokasi |
|---|---|
| Kode aplikasi | `/opt/rasty-florist` (milik `root`, hanya-baca untuk layanan) |
| Virtualenv | `/opt/rasty-florist/.venv` |
| **Database** | `/var/lib/rasty-florist/rasty_florist.db` |
| **Berkas unggahan** | `/var/lib/rasty-florist/uploads` |
| Backup | `/var/lib/rasty-florist/backups` |
| Konfigurasi | `/etc/rasty-florist/rasty.env` (hak akses `0640`) |
| Log aplikasi | `/var/log/rasty-florist/` |
| Log nginx | `/var/log/nginx/rasty-florist-{access,error}.log` |
| Layanan systemd | `/etc/systemd/system/rasty-florist.service` |
| Vhost nginx | `/etc/nginx/sites-available/rasty-florist` |
| Cron backup | `/etc/cron.d/rasty-florist` |
| Aturan sudo | `/etc/sudoers.d/rasty-florist` |

**Database dan unggahan sengaja diletakkan di `/var/lib`**, bukan di dalam
folder kode. Dengan begitu folder kode bisa hanya-baca (lebih aman) dan data
toko tidak ikut terhapus saat aplikasi diperbarui.

---

## 6. Perintah harian

```bash
# Status & log aplikasi
sudo systemctl status rasty-florist
sudo journalctl -u rasty-florist -n 50 --no-pager
sudo journalctl -u rasty-florist -f          # pantau langsung

# Nyalakan / hentikan / muat ulang
sudo systemctl restart rasty-florist
sudo systemctl stop rasty-florist
sudo systemctl start rasty-florist

# Backup manual (database + unggahan)
sudo bash /opt/rasty-florist/installer/backup_ubuntu.sh

# Daftar akun & ganti kata sandi tanpa membuka browser
sudo bash /opt/rasty-florist/installer/set_sandi_ubuntu.sh --daftar
sudo bash /opt/rasty-florist/installer/set_sandi_ubuntu.sh --user admin

# Nonaktifkan akun karyawan yang berhenti
sudo bash /opt/rasty-florist/installer/set_sandi_ubuntu.sh --user staffgudang --nonaktif

# nginx
sudo nginx -t && sudo systemctl reload nginx
```

Berkat aturan sudo yang dipasang, perintah-perintah itu bisa dijalankan
tanpa mengetik sandi (hanya untuk pengguna di grup `sudo`).

---

## 7. Backup dan pemulihan

**Otomatis:** `/etc/cron.d/rasty-florist` menjalankan backup setiap hari pukul
02.00 — database memakai `sqlite3 .backup` (aman walau aplikasi sedang
melayani) dan berkas unggahan diarsipkan ke `.tar.gz`. 14 backup terakhir
disimpan, sisanya dihapus otomatis.

**Manual** sebelum perubahan besar:

```bash
sudo bash /opt/rasty-florist/installer/backup_ubuntu.sh
```

**Salin ke luar server** (wajib — backup di server yang sama tidak menolong
bila disknya rusak):

```bash
# dari komputer Anda
scp -r user@IP-SERVER:/var/lib/rasty-florist/backups ./backup-rasty
```

**Memulihkan** dari backup:

```bash
sudo systemctl stop rasty-florist
sudo cp /var/lib/rasty-florist/backups/rasty-db-<stempel>.db \
        /var/lib/rasty-florist/rasty_florist.db
sudo chown rasty:rasty /var/lib/rasty-florist/rasty_florist.db
sudo systemctl start rasty-florist

# pulihkan unggahan (ganti <stempel> sesuai nama berkas)
sudo tar -xzf /var/lib/rasty-florist/backups/rasty-uploads-<stempel>.tar.gz \
     -C /var/lib/rasty-florist/uploads
sudo chown -R rasty:www-data /var/lib/rasty-florist/uploads
```

Database menyimpan nama berkas foto, bukan isinya — jadi **database dan
unggahan harus dipulihkan bersama**.

Administrator juga bisa memulihkan tanpa SSH lewat **Administrator → Backup
Data**: tombol pulihkan pada riwayat backup, atau unggah berkas `.db` hasil
unduhan. Keduanya mencadangkan keadaan saat ini lebih dulu sebagai
`sebelum-restore`, sehingga salah pilih masih bisa dibatalkan.

---

## 8. Memperbarui aplikasi

```bash
# 1. backup dulu
sudo bash /opt/rasty-florist/installer/backup_ubuntu.sh

# 2. kirim kode baru ke /tmp/rasty-florist (scp/git), lalu:
sudo bash /tmp/rasty-florist/installer/install_ubuntu.sh
```

Pemasang menyalin ulang kode, memperbarui dependensi, menjalankan migrasi
database otomatis, dan menyalakan ulang layanan. Database, unggahan, dan
konfigurasi lama tetap dipakai. Perubahan skema database (kolom/tabel baru)
ditangani otomatis oleh mekanisme migrasi di `db.py`.

Untuk pembaruan rutin, pembaruan data lewat SQL, pemulihan saat gagal, dan
kesalahan yang sering terjadi, lihat **`PANDUAN-UPDATE-UBUNTU.md`**.

---

## 9. Firewall

Pemasang menambahkan aturan UFW untuk SSH dan Nginx, tetapi **tidak**
mengaktifkan UFW. Setelah Anda yakin SSH tetap bisa diakses:

```bash
sudo ufw enable
sudo ufw status verbose
```

Yang dibuka: `22/tcp` (SSH) dan Nginx Full (`80`, `443`). Port `8000` hanya
didengarkan di `127.0.0.1`, jadi tidak bisa diakses dari luar.

---

## 10. Keamanan yang sudah diterapkan

- Aplikasi berjalan sebagai pengguna sistem `rasty` tanpa shell dan tanpa home.
- Folder kode di `/opt` hanya-baca untuk pengguna layanan (`ProtectSystem=strict`).
- `RASTY_DEBUG=0` — debugger Flask mati di server.
- Kunci sesi acak 64 karakter, berkas env `0640` milik `root:rasty`.
- Berkas baru dibuat dengan umask `0027` (grup boleh baca, publik tidak).
- Database `0640` bergrup `rasty`, sehingga nginx tidak bisa membacanya.
- HTTPS dengan pengalihan otomatis dari HTTP ke HTTPS, perpanjangan otomatis.
- systemd hardening: `NoNewPrivileges`, `ProtectHome`, `PrivateTmp`, dan lain-lain.
- Batas unggahan 32 MB di aplikasi, 40 MB di nginx.
- Berkas tersembunyi (`.env`, `.git`) ditolak nginx.

**Yang perlu Anda lakukan:** ganti kata sandi bawaan setiap akun karyawan,
buat akun terpisah per karyawan (jangan berbagi akun), dan nonaktifkan akun
yang tidak lagi bekerja.

---

## 11. Bila ada masalah

| Gejala | Penyebab & solusi |
|---|---|
| `502 Bad Gateway` | gunicorn mati. `sudo systemctl status rasty-florist`, lalu `sudo journalctl -u rasty-florist -n 50` |
| `504 Gateway Timeout` saat ekspor PDF | Proses lama. Sudah dinaikkan ke 120 detik; periksa log aplikasi bila masih terjadi |
| Halaman terbuka tapi tanpa warna | Server tidak bisa akses internet (Bootstrap dimuat dari CDN). Lihat bagian 12 |
| Ganti pengaturan tampilan, warna/gambar tidak muncul | Cache nginx. `sudo systemctl reload nginx` atau tekan `Ctrl+F5` di browser |
| Foto produk muncul sebagai ikon rusak | Hak akses folder unggahan. Jalankan: `sudo chown -R rasty:www-data /var/lib/rasty-florist/uploads && sudo chmod -R 2750 /var/lib/rasty-florist/uploads` |
| `database is locked` | Seharusnya tidak terjadi (WAL + busy_timeout aktif). Periksa apakah ada proses lain membuka `.db`: `sudo lsof /var/lib/rasty-florist/rasty_florist.db` |
| `413 Request Entity Too Large` | Berkas > 40 MB. Naikkan `client_max_body_size` di vhost dan `MAX_CONTENT_LENGTH` di aplikasi |
| Port 8000 sudah dipakai | Pasang ulang dengan `sudo PORT=9000 bash installer/install_ubuntu.sh` |
| Sertifikat SSL gagal | DNS belum mengarah ke server. `dig +short toko.example.com`, bandingkan dengan `curl -s ifconfig.me` |
| Lupa kata sandi administrator | `sudo bash /opt/rasty-florist/installer/set_sandi_ubuntu.sh --user admin` |
| Perlu lihat galat detail | `sudo journalctl -u rasty-florist -n 100 --no-pager` |

---

## 12. Bila server tanpa internet

Bootstrap 5 dan Bootstrap Icons dimuat dari CDN, jadi tampilan akan polos
tanpa internet. Untuk server yang terisolasi:

1. Unduh asset Bootstrap dari <https://getbootstrap.com> ke
   `/opt/rasty-florist/static/vendor/`.
2. Ganti URL CDN di `templates/public/base.html` dan `templates/panel_base.html`
   dengan `{{ url_for('static', filename='vendor/...') }}`.

Seluruh fitur aplikasi tetap berjalan tanpa internet — hanya tampilannya yang
bergantung pada CDN.

---

## 13. Uji setelah pemasangan

```bash
cd /opt/rasty-florist
sudo -u rasty .venv/bin/python installer/init_db.py    # struktur & akun
sudo -u rasty .venv/bin/python smoke_test.py           # semua halaman per peran
sudo -u rasty .venv/bin/python flow_test.py            # alur pesanan sampai bayar
```

`smoke_test.py` dan `flow_test.py` mengandaikan **data contoh** sudah terpasang
(akun `admin`, `staffadmin`, `pelanggan`, dan seterusnya). Untuk server toko
sungguhan, lewati keduanya atau pasang data contoh di server uji terpisah.

---

## 14. Menghapus pemasangan

```bash
# Hentikan layanan & hapus konfigurasi. Database DAN unggahan dipertahankan.
sudo bash /opt/rasty-florist/installer/uninstall_ubuntu.sh

# Hapus semuanya termasuk data (minta konfirmasi ketik HAPUS)
sudo bash /opt/rasty-florist/installer/uninstall_ubuntu.sh --hapus-data

# Sekaligus hapus paket nginx/certbot/sqlite3
sudo bash /opt/rasty-florist/installer/uninstall_ubuntu.sh --hapus-data --hapus-paket
```

Tanpa `--hapus-data`, folder aplikasi dipindahkan ke
`/opt/rasty-florist.dihapus-<stempel>` dan data toko tetap utuh di `/var/lib`.
