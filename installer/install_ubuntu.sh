#!/usr/bin/env bash
#
# Pemasang Rasty Florist untuk Ubuntu 24.04 (LTS) - bagian penyiapan sistem.
#
# Memasang paket pihak ketiga, membuat pengguna sistem, menyalin aplikasi,
# menyiapkan virtualenv, membuat database SQLite, dan menulis berkas
# konfigurasi. Konfigurasi nginx & HTTPS dilakukan oleh langkah berikutnya.
#
# Jalankan sebagai root:  sudo bash installer/install_ubuntu.sh
#
set -euo pipefail

APP_NAME="rasty-florist"
APP_USER="rasty"
APP_GROUP="rasty"
APP_DIR="/opt/${APP_NAME}"
DATA_DIR="/var/lib/${APP_NAME}"
CONF_DIR="/etc/${APP_NAME}"
LOG_DIR="/var/log/${APP_NAME}"
ENV_FILE="${CONF_DIR}/rasty.env"
PYTHON="python3"
VENV_DIR="/opt/${APP_NAME}/.venv"
SERVICE_NAME="rasty-florist"

SUMBER="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Nilai bawaan; bisa diubah lewat variabel lingkungan sebelum menjalankan skrip.
DOMAIN="${DOMAIN:-}"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-3}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@rastyflorist.id}"
ADMIN_NAMA="${ADMIN_NAMA:-Administrator}"
SEED_DEMO="${SEED_DEMO:-0}"
PAKET_WEB="${PAKET_WEB:-nginx}"

# ------------------------------------------------------------------ bantuan --
warna() { printf '\033[1;36m%s\033[0m\n' "$*"; }
langkah() { printf '  -> %s\n' "$*"; }
ingat() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
gagal() { printf '\033[1;31m  x %s\033[0m\n' "$*" >&2; exit 1; }

judul() {
  printf '\n\033[1m%s\033[0m\n' "=============================================================="
  printf '\033[1m  %s\033[0m\n' "$*"
  printf '\033[1m%s\033[0m\n' "=============================================================="
}

# ------------------------------------------------------- pemeriksaan awal --
if [[ "${EUID}" -ne 0 ]]; then
  gagal "Skrip ini harus dijalankan sebagai root: sudo bash installer/install_ubuntu.sh"
fi

if [[ ! -f "${SUMBER}/app.py" ]]; then
  gagal "app.py tidak ditemukan di ${SUMBER} - letakkan folder aplikasi apa adanya."
fi

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  if [[ "${ID:-}" != "ubuntu" ]]; then
    ingat "Sistem ini bukan Ubuntu (${PRETTY_NAME:-tidak dikenal}); skrip diuji untuk Ubuntu 24.04."
  elif [[ "${VERSION_ID:-}" != "24.04" ]]; then
    ingat "Versi Ubuntu ${VERSION_ID:-?} - skrip diuji untuk 24.04."
  fi
fi

judul "Pemasang Rasty Florist untuk Ubuntu"
echo "  Folder sumber   : ${SUMBER}"
echo "  Folder aplikasi : ${APP_DIR}"
echo "  Folder data     : ${DATA_DIR}  (database, unggahan, backup)"
echo "  Domain          : ${DOMAIN:-(belum diisi - nginx disiapkan sebagai default)}"
echo "  Port aplikasi   : ${PORT}"

if [[ "${SEED_DEMO}" == "1" ]]; then
  MODE_DB="data contoh (produk, pesanan, akun demo)"
else
  MODE_DB="toko sungguhan (hanya akun administrator)"
fi
echo "  Isi database    : ${MODE_DB}"

# ------------------------------------------------------ 1. paket sistem ----
judul "Langkah 1/8 - Memasang paket sistem"

export DEBIAN_FRONTEND=noninteractive
langkah "apt-get update"
apt-get update -qq

# Paket pihak ketiga yang dipakai:
#   python3-venv         - virtualenv untuk dependensi aplikasi
#   python3-pip          - pemasang paket Python
#   nginx                - web server / reverse proxy + HTTPS
#   certbot, python3-certbot-nginx - sertifikat SSL Let's Encrypt
#   sqlite3              - alat periksa & backup database
#   ufw                  - firewall sederhana
#   rsync, curl, ca-certificates - utilitas pemasangan
PAKET=(
  python3
  python3-venv
  python3-pip
  python3-dev
  build-essential
  "${PAKET_WEB}"
  certbot
  python3-certbot-nginx
  sqlite3
  ufw
  rsync
  curl
  ca-certificates
)
langkah "Memasang: ${PAKET[*]}"
apt-get install -y -qq "${PAKET[@]}"

# --------------------------------------------------- 2. pengguna & folder --
judul "Langkah 2/8 - Membuat pengguna sistem & folder"

if id "${APP_USER}" >/dev/null 2>&1; then
  langkah "Pengguna sistem '${APP_USER}' sudah ada."
else
  # Tanpa shell login dan tanpa home: akun ini hanya untuk menjalankan layanan.
  useradd --system --no-create-home --shell /usr/sbin/nologin "${APP_USER}"
  langkah "Pengguna sistem '${APP_USER}' dibuat (tanpa login)."
fi

# Grup www-data dipakai agar nginx bisa menembus folder ini untuk membaca
# berkas unggahan. Database tetap bergrup "${APP_GROUP}" sehingga nginx
# tidak bisa membacanya.
install -d -o "${APP_USER}" -g www-data -m 0750 "${DATA_DIR}"
# Unggahan dibaca langsung oleh nginx (pengguna www-data), jadi folder dan
# isinya diberi grup www-data dengan hak baca-jalur. Aplikasi tetap pemiliknya,
# sehingga masih bisa menulis.
install -d -o "${APP_USER}" -g www-data -m 2750 "${DATA_DIR}/uploads"
install -d -o "${APP_USER}" -g "${APP_GROUP}" -m 0750 "${DATA_DIR}/backups"
install -d -o root -g "${APP_GROUP}" -m 0750 "${CONF_DIR}"
# Log aplikasi (gunicorn) ditulis oleh pengguna layanan.
install -d -o "${APP_USER}" -g "${APP_GROUP}" -m 0750 "${LOG_DIR}"
langkah "Folder data, unggahan, backup, konfigurasi, dan log siap."

# ------------------------------------------------------- 3. salin aplikasi --
judul "Langkah 3/8 - Menyalin aplikasi ke ${APP_DIR}"

install -d -o root -g "${APP_GROUP}" -m 0755 "${APP_DIR}"
# Kode disalin tanpa berkas lokal Windows, database, atau unggahan lama.
rsync -a --delete \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '*.db' \
  --exclude '*.db-wal' \
  --exclude '*.db-shm' \
  --exclude 'rasty.conf' \
  --exclude 'jalankan-server.bat' \
  --exclude 'installer/_sementara.ps1' \
  --exclude 'backups/' \
  --exclude 'static/uploads/' \
  "${SUMBER}/" "${APP_DIR}/"

# static/uploads hanya berisi berkas contoh dari pengembangan; unggahan
# sungguhan disimpan di DATA_DIR lewat RASTY_UPLOAD_FOLDER.
install -d -o root -g "${APP_GROUP}" -m 0755 "${APP_DIR}/static/uploads"
chown -R root:"${APP_GROUP}" "${APP_DIR}"
# Pemilik (root) boleh menulis, grup layanan hanya membaca. Mode ditulis ulang
# eksplisit supaya hasilnya sama apa pun mode berkas di komputer sumber.
chmod -R u=rwX,g=rX,o= "${APP_DIR}"
langkah "Kode aplikasi tersalin (hanya-baca untuk pengguna layanan)."

# --------------------------------------------------- 4. virtualenv & paket --
judul "Langkah 4/8 - Menyiapkan virtualenv & dependensi Python"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  "${PYTHON}" -m venv "${VENV_DIR}"
  langkah "Virtualenv dibuat di ${VENV_DIR}."
else
  langkah "Virtualenv sudah ada - dipakai ulang."
fi

"${VENV_DIR}/bin/python" -m pip install --quiet --upgrade pip wheel setuptools
langkah "Memasang dependensi dari requirements.txt"
"${VENV_DIR}/bin/python" -m pip install --quiet -r "${APP_DIR}/requirements.txt"
chown -R root:"${APP_GROUP}" "${VENV_DIR}"
chmod -R u=rwX,g=rX,o= "${VENV_DIR}"
langkah "Dependensi terpasang: $("${VENV_DIR}/bin/python" -c 'import flask; print("Flask " + flask.__version__)')"

# ------------------------------------------------------------ 5. berkas env --
judul "Langkah 5/8 - Menulis konfigurasi ${ENV_FILE}"

SECRET="$(openssl rand -hex 32 2>/dev/null || "${VENV_DIR}/bin/python" -c 'import secrets; print(secrets.token_hex(32))')"

if [[ -f "${ENV_FILE}" ]]; then
  # Kunci sesi lama dipertahankan supaya pengguna tidak ter-logout saat pasang ulang.
  SECRET_LAMA="$(grep -E '^RASTY_SECRET=' "${ENV_FILE}" | head -n1 | cut -d= -f2- || true)"
  if [[ -n "${SECRET_LAMA}" ]]; then
    SECRET="${SECRET_LAMA}"
    langkah "Kunci sesi lama dipertahankan."
  fi
  cp "${ENV_FILE}" "${ENV_FILE}.bak-$(date +%Y%m%d-%H%M%S)"
  langkah "Konfigurasi lama dicadangkan."
fi

cat > "${ENV_FILE}" <<EOF
# Konfigurasi Rasty Florist - dibuat otomatis oleh installer.
# Ubah nilai di bawah lalu jalankan: sudo systemctl restart ${SERVICE_NAME}
#
# Kunci penanda tangan sesi login. Jangan dibagikan.
RASTY_SECRET=${SECRET}

# Port aplikasi. Dibaca oleh unit systemd (--bind) dan oleh setup_nginx.sh
# saat menyusun konfigurasi reverse proxy. Gunicorn hanya mendengarkan di
# localhost; nginx yang menghadap internet.
RASTY_PORT=${PORT}

# Wajib 0 di server sungguhan (1 menyalakan debugger).
RASTY_DEBUG=0

# Aplikasi berjalan di belakang nginx, jadi header X-Forwarded-* dipercaya.
RASTY_PROXY=1

# Lokasi data. Ketiganya di luar folder kode agar kode bisa hanya-baca.
RASTY_DATABASE=${DATA_DIR}/rasty_florist.db
RASTY_UPLOAD_FOLDER=${DATA_DIR}/uploads
RASTY_BACKUP_FOLDER=${DATA_DIR}/backups
EOF
chown root:"${APP_GROUP}" "${ENV_FILE}"
chmod 0640 "${ENV_FILE}"
langkah "Konfigurasi ditulis dengan kunci sesi acak (hak akses 0640)."

# -------------------------------------------------------- 6. basis data ----
judul "Langkah 6/8 - Membuat database & akun administrator"

# Kata sandi acak tanpa karakter yang mudah tertukar (0/O, 1/l/I).
SANDI="$("${VENV_DIR}/bin/python" -c 'import secrets; a="abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"; print("".join(secrets.choice(a) for _ in range(12)))')"

if [[ -f "${DATA_DIR}/rasty_florist.db" ]]; then
  ADA_DB=1
  ingat "Database sudah ada di ${DATA_DIR} - data lama dipertahankan."
  ingat "Akun administrator tidak dibuat ulang; sandi lama tetap berlaku."
else
  ADA_DB=0
fi

run_as_app() {
  # Jalankan perintah dengan lingkungan dari berkas env, sebagai pengguna layanan.
  sudo -u "${APP_USER}" env \
    RASTY_SECRET="${SECRET}" \
    RASTY_DATABASE="${DATA_DIR}/rasty_florist.db" \
    RASTY_UPLOAD_FOLDER="${DATA_DIR}/uploads" \
    RASTY_BACKUP_FOLDER="${DATA_DIR}/backups" \
    RASTY_SEED_DEMO="${SEED_DEMO}" \
    RASTY_ADMIN_USER="${ADMIN_USER}" \
    RASTY_ADMIN_PASSWORD="${SANDI}" \
    RASTY_ADMIN_NAMA="${ADMIN_NAMA}" \
    RASTY_ADMIN_EMAIL="${ADMIN_EMAIL}" \
    "${VENV_DIR}/bin/python" "${APP_DIR}/installer/init_db.py"
}

langkah "Menjalankan inisialisasi database"
run_as_app || gagal "Inisialisasi database gagal."

chown "${APP_USER}":"${APP_GROUP}" "${DATA_DIR}/rasty_florist.db"
chmod 0640 "${DATA_DIR}/rasty_florist.db"

# ---------------------------------------------------------- 7. systemd -----
judul "Langkah 7/8 - Membuat layanan systemd"

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Rasty Florist - Sistem Manajemen Toko Bunga
Documentation=file://${APP_DIR}/PANDUAN-INSTALL-UBUNTU.md
After=network-online.target
Wants=network-online.target

[Service]
# Type=simple, bukan notify: dukungan sd_notify gunicorn butuh paket tambahan
# (systemd-python). Tanpa itu, Type=notify membuat systemd menunggu sinyal
# yang tidak pernah datang sampai batas waktu habis dan layanan dianggap gagal.
Type=simple
User=${APP_USER}
Group=${APP_GROUP}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${ENV_FILE}
# Satu baris, tanpa lanjutan baris: lebih mudah diperiksa bila ada masalah.
ExecStart=${VENV_DIR}/bin/gunicorn --workers ${WORKERS} --bind 127.0.0.1:${PORT} --timeout 120 --access-logfile ${LOG_DIR}/access.log --error-logfile ${LOG_DIR}/error.log --capture-output wsgi:app

Restart=always
RestartSec=3

# Berkas baru (unggahan, database) dibuat 0640: grup tetap bisa membaca
# (nginx memakai grup www-data lewat setgid di folder unggahan), pengguna
# lain tidak.
UMask=0027

# --- Pengerasan keamanan ---
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictRealtime=true
LockPersonality=true
# ProtectSystem=strict membuat seluruh sistem berkas hanya-baca. Hanya dua
# folder ini yang boleh ditulis: data toko dan folder log aplikasi.
ReadWritePaths=${DATA_DIR} ${LOG_DIR}

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
langkah "Layanan ${SERVICE_NAME}.service ditulis."

# Firewall: hanya SSH dan web yang dibuka.
if command -v ufw >/dev/null 2>&1; then
  ufw allow OpenSSH >/dev/null 2>&1 || true
  ufw allow 'Nginx Full' >/dev/null 2>&1 || true
  langkah "Aturan firewall UFW untuk OpenSSH dan Nginx ditambahkan."
  ingat "UFW belum diaktifkan otomatis. Aktifkan dengan: sudo ufw enable"
fi

# Backup otomatis tiap hari pukul 02.00. Aplikasi juga punya backup internal
# (menu Backup Data), tetapi cron ini bekerja walau server tidak dibuka siapa pun
# dan menyertakan berkas unggahan.
cat > "/etc/cron.d/${APP_NAME}" <<EOF
# Backup harian Rasty Florist - database + berkas unggahan.
# Hasilnya di /var/lib/${APP_NAME}/backups. Untuk memeriksa manual:
#   sudo bash /opt/${APP_NAME}/installer/backup_ubuntu.sh
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
0 2 * * * root bash ${APP_DIR}/installer/backup_ubuntu.sh >/dev/null 2>&1
EOF
chmod 0644 "/etc/cron.d/${APP_NAME}"
langkah "Backup harian otomatis dipasang (/etc/cron.d/${APP_NAME}, pukul 02.00)."

# Perintah pemeliharaan dibungkus aturan sudo supaya administrator toko tidak
# perlu mengetik perintah panjang, dan tidak diberi akses root penuh.
BASH_BIN="$(command -v bash)"
SYSTEMCTL_BIN="$(command -v systemctl)"
cat > "/etc/sudoers.d/${APP_NAME}" <<EOF
# Izinkan grup sudo mengelola layanan, backup, dan akun Rasty Florist.
%sudo ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} restart ${SERVICE_NAME}
%sudo ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} stop ${SERVICE_NAME}
%sudo ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} start ${SERVICE_NAME}
%sudo ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} status ${SERVICE_NAME}
%sudo ALL=(root) NOPASSWD: ${SYSTEMCTL_BIN} reload ${SERVICE_NAME}
%sudo ALL=(root) NOPASSWD: ${BASH_BIN} ${APP_DIR}/installer/backup_ubuntu.sh
%sudo ALL=(root) NOPASSWD: ${BASH_BIN} ${APP_DIR}/installer/set_sandi_ubuntu.sh *
%sudo ALL=(root) NOPASSWD: ${BASH_BIN} ${APP_DIR}/installer/setup_nginx.sh *
EOF
chmod 0440 "/etc/sudoers.d/${APP_NAME}"
if visudo -c -f "/etc/sudoers.d/${APP_NAME}" >/dev/null 2>&1; then
  langkah "Aturan sudo dipasang (/etc/sudoers.d/${APP_NAME})."
else
  rm -f "/etc/sudoers.d/${APP_NAME}"
  ingat "Aturan sudo tidak valid dan dibatalkan."
fi

# ------------------------------------------------- 8. mulai & uji layanan --
judul "Langkah 8/8 - Menjalankan layanan & uji cepat"

systemctl enable --now "${SERVICE_NAME}" >/dev/null 2>&1 || true
sleep 3

LAYANAN_OK=0
if systemctl is-active --quiet "${SERVICE_NAME}"; then
  LAYANAN_OK=1
  langkah "Layanan aktif."
else
  ingat "Layanan tidak aktif. Periksa: journalctl -u ${SERVICE_NAME} -n 50"
fi

if command -v curl >/dev/null 2>&1; then
  KODE="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/" || echo 000)"
  if [[ "${KODE}" == "200" ]]; then
    langkah "Uji halaman beranda: HTTP 200 (server merespons)."
  else
    ingat "Uji halaman beranda: HTTP ${KODE} (periksa ${LOG_DIR}/error.log)"
  fi
fi

# ------------------------------------------------------------- ringkasan --
judul "Penyiapan sistem selesai"

echo "  Aplikasi     : ${APP_DIR}"
echo "  Database     : ${DATA_DIR}/rasty_florist.db"
echo "  Unggahan     : ${DATA_DIR}/uploads"
echo "  Backup       : ${DATA_DIR}/backups"
echo "  Konfigurasi  : ${ENV_FILE}"
echo "  Log          : ${LOG_DIR}/"
echo "  Layanan      : systemctl status ${SERVICE_NAME}"
echo
echo "  Port lokal   : http://127.0.0.1:${PORT}"
echo

if [[ "${ADA_DB}" == "0" ]]; then
  echo "  Akun administrator"
  echo "    Username : ${ADMIN_USER}"
  echo "    Sandi    : ${SANDI}"
  echo "    (hanya ditampilkan sekali - catat sekarang)"
  echo
else
  echo "  Database sudah ada sebelumnya; akun administrator tidak diubah."
  echo "  Lupa sandi? Jalankan:"
  echo "    sudo -u ${APP_USER} ${VENV_DIR}/bin/python ${APP_DIR}/installer/set_sandi.py --daftar"
  echo
fi

echo "  Langkah berikutnya - web server & HTTPS:"
if [[ -n "${DOMAIN}" ]]; then
  echo "    sudo DOMAIN=${DOMAIN} bash ${APP_DIR}/installer/setup_nginx.sh"
else
  echo "    sudo bash ${APP_DIR}/installer/setup_nginx.sh"
  echo "    (tambahkan DOMAIN=nama-domain-anda bila sudah punya domain & DNS)"
fi
echo
echo "  Untuk sementara aplikasi sudah bisa dibuka dari server ini:"
echo "    curl -I http://127.0.0.1:${PORT}/"
echo
echo "  Panduan lengkap: ${APP_DIR}/PANDUAN-INSTALL-UBUNTU.md"
echo

if [[ "${LAYANAN_OK}" == "1" ]]; then
  exit 0
fi
exit 1
