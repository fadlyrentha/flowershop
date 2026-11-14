#!/usr/bin/env bash
#
# Backup Rasty Florist di Ubuntu: database + berkas unggahan.
#
# Memakai "sqlite3 .backup" (bukan salin berkas) supaya backup tetap utuh
# walaupun ada penulisan yang sedang berjalan. Backup lama dipangkas otomatis.
#
# Jalankan sebagai root:  sudo bash installer/backup_ubuntu.sh
# Atau lewat cron (sudah dipasang otomatis oleh install_ubuntu.sh):
#   /etc/cron.d/rasty-florist
#
set -euo pipefail

APP_NAME="rasty-florist"
APP_USER="rasty"
APP_GROUP="rasty"
DATA_DIR="/var/lib/${APP_NAME}"
BACKUP_DIR="${DATA_DIR}/backups"
DB="${DATA_DIR}/rasty_florist.db"
UPLOADS="${DATA_DIR}/uploads"

# Berapa banyak backup yang disimpan sebelum yang tertua dihapus.
SIMPAN="${SIMPAN:-14}"

langkah() { printf '  -> %s\n' "$*"; }
ingat() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
gagal() { printf '\033[1;31m  x %s\033[0m\n' "$*" >&2; exit 1; }

if [[ "${EUID}" -ne 0 ]]; then
  gagal "Jalankan sebagai root: sudo bash installer/backup_ubuntu.sh"
fi

if [[ ! -f "${DB}" ]]; then
  gagal "Database ${DB} tidak ditemukan."
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
  gagal "sqlite3 belum terpasang: sudo apt-get install -y sqlite3"
fi

STEMPEL="$(date +%Y%m%d-%H%M%S)"
install -d -o "${APP_USER}" -g "${APP_GROUP}" -m 0750 "${BACKUP_DIR}"

# ------------------------------------------------------------- database ----
DB_BACKUP="${BACKUP_DIR}/rasty-db-${STEMPEL}.db"
# .backup membuat salinan yang konsisten walau aplikasi sedang melayani.
sqlite3 "${DB}" ".backup '${DB_BACKUP}'"
chown "${APP_USER}":"${APP_GROUP}" "${DB_BACKUP}"
chmod 0640 "${DB_BACKUP}"

# Periksa hasil backup benar-benar bisa dibaca.
if ! sqlite3 "${DB_BACKUP}" "PRAGMA integrity_check;" | grep -q '^ok$'; then
  gagal "Backup database rusak: ${DB_BACKUP}"
fi
langkah "Database  : $(basename "${DB_BACKUP}") ($(du -h "${DB_BACKUP}" | cut -f1))"

# -------------------------------------------------------------- unggahan ---
if [[ -d "${UPLOADS}" ]] && [[ -n "$(ls -A "${UPLOADS}" 2>/dev/null)" ]]; then
  UP_BACKUP="${BACKUP_DIR}/rasty-uploads-${STEMPEL}.tar.gz"
  tar -czf "${UP_BACKUP}" -C "${UPLOADS}" .
  chown "${APP_USER}":"${APP_GROUP}" "${UP_BACKUP}"
  chmod 0640 "${UP_BACKUP}"
  langkah "Unggahan  : $(basename "${UP_BACKUP}") ($(du -h "${UP_BACKUP}" | cut -f1))"
else
  ingat "Folder unggahan kosong - tidak ada yang diarsipkan."
fi

# ------------------------------------------------------------ pemangkasan --
# Hapus backup database paling lama bila jumlahnya melebihi ${SIMPAN}.
pangkas() {
  # Terima pola nama berkas; simpan hanya ${SIMPAN} berkas terbaru.
  local pola="$1"
  local daftar jumlah hapus
  # mapfile menampung hasil lebih dulu supaya tidak ada proses yang mati
  # karena SIGPIPE saat pipefail aktif.
  mapfile -t daftar < <(find "${BACKUP_DIR}" -maxdepth 1 -name "${pola}" -type f \
    -printf '%T@ %p\n' | sort -n | cut -d' ' -f2-)
  jumlah="${#daftar[@]}"
  if [[ "${jumlah}" -le "${SIMPAN}" ]]; then
    return 0
  fi
  hapus=$((jumlah - SIMPAN))
  langkah "Menghapus ${hapus} berkas backup terlama (${pola})."
  local i
  for ((i = 0; i < hapus; i++)); do
    rm -f "${daftar[i]}"
  done
}

pangkas 'rasty-db-*.db'
pangkas 'rasty-uploads-*.tar.gz'

# --------------------------------------------------------------- ringkasan --
echo
echo "  Folder backup : ${BACKUP_DIR}"
echo "  Isi terbaru   :"
ls -1t "${BACKUP_DIR}" 2>/dev/null | head -n 5 | sed 's/^/    /'
echo
echo "  Memulihkan database:"
echo "    sudo systemctl stop ${APP_NAME}"
echo "    sudo cp ${BACKUP_DIR}/rasty-db-<stempel>.db ${DB}"
echo "    sudo chown ${APP_USER}:${APP_GROUP} ${DB}"
echo "    sudo systemctl start ${APP_NAME}"
echo
