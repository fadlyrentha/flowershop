# Panduan Pemasangan — Rasty Florist

Panduan ini untuk memasang aplikasi di komputer toko (Windows), lengkap dengan
server produksi dan database. Ikuti bagian **Pemasangan cepat**; bagian lain
dipakai bila perlu penyesuaian.

---

## 1. Yang dibutuhkan

| Kebutuhan | Keterangan |
|---|---|
| Windows 10/11 | Aplikasi diuji di Windows 11 |
| Python 3.10+ | Unduh di <https://www.python.org/downloads/> |
| Koneksi internet | Hanya saat pemasangan, untuk mengunduh Flask & waitress |
| Hak Administrator | Hanya bila ingin membuka port di firewall |

Saat memasang Python, **centang “Add python.exe to PATH”** di layar pertama.
Tanpa itu perintah `python` tidak dikenali.

Tidak perlu memasang database server. Database memakai SQLite dan dibuat
otomatis di dalam folder aplikasi.

---

## 2. Pemasangan cepat

1. Salin folder `rasty-florist` ke komputer toko, misalnya ke
   `C:\rasty-florist`.
2. Klik dua kali **`pasang.bat`**.
3. Jawab pertanyaan yang muncul (tekan **Enter** untuk memakai nilai bawaan).
   **Catat kata sandi yang ditampilkan** — kata sandi itu hanya muncul sekali,
   dan tanpa itu Anda tidak bisa masuk. Bila terlewat, lihat bagian
   **Mengelola akun** di bawah untuk membuat ulang.

   | Pertanyaan | Bawaan | Keterangan |
   |---|---|---|
   | Layani juga komputer lain di jaringan toko? | Ya | Ya = kasir lain bisa membuka aplikasi dari komputernya |
   | Port server | 5000 | Ubah bila port ini sudah dipakai program lain |
   | Isi data contoh? | Tidak | **Pilih Tidak** untuk toko sungguhan |
   | Username administrator | admin | Boleh diganti, misalnya `pemilik` |
   | Kata sandi administrator | (dibuat acak) | Diketik dua kali. **Kosongkan** agar pemasang membuat sandi acak yang kuat — sandi itu ditampilkan sekali di layar |
   | Nama administrator | Administrator | Muncul di halaman akun |
   | Email administrator | admin@rastyflorist.id | Boleh dikosongkan |
   | Pintasan desktop | Ya | Membuat ikon “Rasty Florist” di desktop |
   | Jalankan otomatis saat Windows menyala? | Tidak | Pilih Ya bila komputer ini khusus untuk server |

4. Tunggu sampai muncul tulisan **“Pemasangan selesai”**. Pemasang akan:
   - memasang Flask dan waitress,
   - membuat database `rasty_florist.db`,
   - membuat akun administrator,
   - menulis berkas konfigurasi `rasty.conf`,
   - membuat `jalankan-server.bat` dan pintasan desktop,
   - membuka port di Windows Firewall (bila dijalankan sebagai Administrator).

5. Klik dua kali **`jalankan-server.bat`** (atau ikon desktop) untuk
   menjalankan server. Jendela hitam harus dibiarkan terbuka selama toko buka —
   menutupnya berarti mematikan server.

---

## 3. Cara membuka aplikasi

| Dari mana | Alamat |
|---|---|
| Komputer server itu sendiri | <http://127.0.0.1:5000> |
| Komputer/kasir lain di jaringan toko | `http://<IP-komputer-server>:5000` |

IP komputer server ditampilkan pemasang di akhir proses (contoh
`http://192.168.1.10:5000`). Bila lupa, jalankan di komputer server:

```powershell
ipconfig
```

lalu lihat **IPv4 Address** pada adapter yang aktif.

Masuk dengan akun administrator yang dibuat saat pemasangan, kemudian:

1. Buka **Pengaturan Situs** — isi nama toko, alamat, telepon, dan unggah logo.
   Logo ini otomatis tampil di kop faktur.
2. Buka **Akun Staff** — buat akun untuk Staff Admin, Kantor, Gudang, QC, dan
   Keuangan. Kata sandi bawaan wajib diganti.
3. Buka **Hak Akses** — nyalakan/matikan menu untuk setiap peran.
4. Buka **Data Produk** — hapus atau nonaktifkan produk contoh bila ada, lalu
   masukkan produk toko Anda beserta fotonya.
5. Ganti kata sandi administrator sendiri lewat **Akun → Kata Sandi**.

---

## 4. Berkas yang dibuat saat pemasangan

```
rasty-florist/
├── rasty.conf              # konfigurasi server (port, alamat, kunci sesi)
├── rasty_florist.db        # database toko  <-- ini yang wajib di-backup
├── jalankan-server.bat     # peluncur server produksi (klik dua kali)
├── pasang.bat              # pemasang
├── jalankan_server.py      # peluncur (dipanggil jalankan-server.bat)
├── serve.py                # server waitress
└── backups/                # backup otomatis & manual (berkas .db)
```

`rasty.conf` berisi kunci sesi rahasia; pemasang sudah membatasi hak aksesnya
hanya untuk pengguna Windows yang menjalankan pemasangan. **Jangan dibagikan.**

### Isi `rasty.conf`

```ini
RASTY_SECRET=<kunci acak 64 karakter>
RASTY_HOST=0.0.0.0
RASTY_PORT=5000
RASTY_THREADS=8
RASTY_DEBUG=0
RASTY_DATABASE=C:\rasty-florist\rasty_florist.db
```

| Kunci | Arti |
|---|---|
| `RASTY_SECRET` | Kunci penanda tangan sesi login. Diganti = semua pengguna harus login ulang. |
| `RASTY_HOST` | `0.0.0.0` = dilayani ke jaringan; `127.0.0.1` = hanya komputer ini |
| `RASTY_PORT` | Port server |
| `RASTY_THREADS` | Jumlah koneksi bersamaan waitress (8 cukup untuk toko) |
| `RASTY_DEBUG` | **Harus `0` di toko sungguhan.** `1` hanya untuk pengembangan. |
| `RASTY_DATABASE` | Lokasi berkas database |

Setelah mengubah `rasty.conf`, tutup jendela server lalu jalankan
`jalankan-server.bat` lagi.

---

## 5. Pemasangan tanpa pertanyaan

Untuk memasang ulang dengan cepat atau menyiapkan beberapa komputer:

```powershell
python installer\install.py --yes
```

Mode ini membuat **kata sandi administrator acak** dan menampilkannya sekali di
layar — tanpa `--password`, tidak ada instalasi yang memakai sandi bawaan yang
sudah diketahui umum. Tambahkan `--password` bila ingin menentukan sendiri.

Pilihan lain:

```powershell
# Toko sungguhan, port 8080, hanya komputer ini
python installer\install.py --yes --host 127.0.0.1 --port 8080

# Administrator dengan nama sendiri
python installer\install.py --yes --admin pemilik --password RahasiaToko2026

# Ikut memasang data contoh untuk pelatihan
python installer\install.py --yes --demo

# Lewati pintasan dan firewall
python installer\install.py --yes --tanpa-shortcut --tanpa-firewall
```

---

## 6. Mengelola akun

Lihat semua akun:

```powershell
python installer\set_sandi.py --daftar
```

Ganti kata sandi (tanpa menampilkan sandi di layar):

```powershell
python installer\set_sandi.py --user admin
```

Ganti langsung tanpa ditanya — untuk pemulihan bila administrator terkunci:

```powershell
python installer\set_sandi.py --user admin --password SandiBaru123
```

Ganti `admin` dengan username yang ingin diubah.

---

## 7. Backup dan pemulihan

**Backup otomatis** berjalan dari dalam aplikasi sesuai jadwal di menu
**Backup Data** (harian/mingguan/bulanan/tahunan). Hasilnya berkas `.db` di
folder `backups\`. Backup hanya berjalan saat server hidup.

**Backup manual** yang disarankan setiap tutup toko:

1. Tutup jendela server (supaya database tidak sedang ditulis).
2. Salin folder `rasty-florist` — minimal berkas `rasty_florist.db` **dan**
   folder `static\uploads` (berisi foto produk, logo, bukti pembayaran) — ke
   flashdisk atau Google Drive.

**Memulihkan** dari backup:

1. Tutup server.
2. Ganti `rasty_florist.db` dengan berkas backup.
3. Jalankan `jalankan-server.bat` lagi.

Database berisi seluruh transaksi. Folder `static\uploads` berisi berkas foto;
database hanya menyimpan nama berkasnya, jadi keduanya harus dipulihkan bersama.

---

## 8. Menjalankan otomatis saat komputer menyala

Bila belum dipilih saat pemasangan, buat pintasan ke folder Startup:

1. Tekan `Win + R`, ketik `shell:startup`, tekan Enter.
2. Klik kanan `jalankan-server.bat` → **Copy**.
3. Di jendela Startup yang terbuka, klik kanan → **Paste shortcut**.

Aplikasi akan menyala sendiri setiap kali Windows masuk ke desktop.

---

## 9. Bila ada masalah

| Gejala | Penyebab & solusi |
|---|---|
| `'python' is not recognized` | Python belum masuk PATH. Pasang ulang Python dan centang “Add python.exe to PATH”. |
| Jendela server langsung tertutup | Buka Command Prompt di folder aplikasi, jalankan `python jalankan_server.py` untuk membaca pesan galatnya. |
| `Address already in use` | Port 5000 dipakai program lain. Ubah `RASTY_PORT` di `rasty.conf`, misalnya ke 8080, lalu jalankan ulang. |
| Halaman tidak bisa dibuka dari kasir lain | Jaringan: pastikan `RASTY_HOST=0.0.0.0` dan aturan firewall untuk port tersebut sudah ada. Jalankan Command Prompt **sebagai Administrator**: `netsh advfirewall firewall add rule name="Rasty Florist" dir=in action=allow protocol=TCP localport=5000` |
| Tampilan polos tanpa warna/gambar | Komputer kasir tidak bisa mengakses internet — Bootstrap dan ikon dimuat dari CDN. Sambungkan ke internet atau minta pemasangan aset lokal. |
| Lupa kata sandi administrator | `python installer\set_sandi.py --user admin --password SandiBaru123` |
| Muncul galat halaman 500 | Jalankan `python smoke_test.py` di folder aplikasi untuk melihat rute mana yang bermasalah. |

---

## 10. Uji setelah pemasangan

```powershell
python smoke_test.py    # membuka semua halaman untuk 7 peran
python flow_test.py     # alur pesanan sampai pembayaran
python social_test.py   # penarik feed & story sosial media (tanpa jaringan)
python install_test.py  # memastikan instalasi bersih berhasil
```

`smoke_test.py` dan `flow_test.py` mengandaikan **data contoh** ada (akun
`admin`, `staffadmin`, `pelanggan`, dan seterusnya). Bila dipasang tanpa data
contoh, jalankan `install_test.py` saja, atau pasang ulang dengan
`--demo` di komputer pelatihan.

---

## 11. Catatan teknis

- Server produksi memakai **waitress**, bukan server pengembangan Flask.
  Jangan menjalankan `python app.py` di toko — mode itu menyalakan debugger.
- Aplikasi tidak memakai build tool. Bootstrap 5 dan Bootstrap Icons dimuat
  dari CDN, jadi halaman butuh internet agar tampil penuh.
- Batas unggahan 32 MB per berkas (foto produk, bukti pembayaran, video QC).
- Ekspor PDF faktur ditulis sendiri oleh aplikasi, tanpa pustaka tambahan.
