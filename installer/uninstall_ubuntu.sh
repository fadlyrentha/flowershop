#!/usr/bin/env bash
#
# Menghapus Rasty Florist dari server Ubuntu.
#
# Bawaannya hanya menghentikan layanan dan memindahkan aplikasi ke tempat
# sampah — database dan berkas unggahan TIDAK dihapus, supaya data toko tidak
# hilang karena salah jalankan. Penghapusan total harus diminta eksplisit.
#
# Jalankan sebagai root:
#   sudo bash installer/uninstall_ubuntu.sh
#   sudo bash installer/uninstall_ubuntu.sh --hapus-data
#
set -euo pipefail

APP_NAME="rasty-florist"
APP_USER="rasty"
APP_GROUP="rasty"
APP_DIR="/opt/${APP_NAME}"
DATA_DIR="/var/lib/${APP_NAME}"
CONF_DIR="/etc/${APP_NAME}"
LOG_DIR="/var/log/${APP_NAME}"
SERVICE_NAME="rasty-florist"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

HAPUS_DATA="0"
HAPUS_PAKET="0"

petunjuk() {
  cat <<'EOF'
Pemakaian: sudo bash installer/uninstall_ubuntu.sh [pilihan]

  (tanpa pilihan)   hentikan layanan, hapus konfigurasi nginx & systemd.
                    Database dan berkas unggahan DIPERTAHANKAN.
  --hapus-data      hapus juga database, unggahan, dan backup (tidak bisa dibatalkan)
  --hapus-paket     hapus juga nginx, certbot, dan sqlite3
  -h, --help        tampilkan bantuan ini
EOF
}

for arg in "$@"; do
  case "${arg}" in
    --hapus-data) HAPUS_DATA="1" ;;
    --hapus-paket) HAPUS_PAKET="1" ;;
    -h|--help) petunjuk; exit 0 ;;
    *) printf 'Pilihan tidak dikenal: %s\n\n' "${arg}" >&2; petunjuk; exit 1 ;;
  esac
done

if [[ "${EUID}" -ne 0 ]]; then
  printf '\033[1;31m  x Harus dijalankan sebagai root: sudo bash %s\033[0m\n' "$0" >&2
  exit 1
fi

langkah() { printf '  -> %s\n' "$*"; }
ingat() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }

printf '\n\033[1mPenghapusan Rasty Florist\033[0m\n\n'

if [[ "${HAPUS_DATA}" == "1" ]]; then
  ingat "MODE --hapus-data: database, unggahan, dan backup akan dihapus permanen."
  printf '    Ketik HAPUS untuk melanjutkan: '
  read -r KONFIRMASI
  if [[ "${KONFIRMASI}" != "HAPUS" ]]; then
    echo "    Dibatalkan."
    exit 1
  fi
fi

# ------------------------------------------------------- 1. layanan --------
langkah "Menghentikan dan menonaktifkan layanan"
systemctl disable --now "${SERVICE_NAME}" >/dev/null 2>&1 || true
rm -f "${SERVICE_FILE}"
systemctl daemon-reload
langkah "Layanan dihapus."

# ---------------------------------------------------------- 2. nginx -------
if [[ -e "/etc/nginx/sites-enabled/${APP_NAME}" || -e "/etc/nginx/sites-available/${APP_NAME}" ]]; then
  rm -f "/etc/nginx/sites-enabled/${APP_NAME}"
  rm -f "/etc/nginx/sites-available/${APP_NAME}"
  # Kembalikan situs bawaan bila tidak ada vhost lain yang aktif.
  if [[ -z "$(ls -A /etc/nginx/sites-enabled 2>/dev/null)" && -e /etc/nginx/sites-available/default ]]; then
    ln -sfn /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default
    langkah "Situs bawaan nginx diaktifkan kembali."
  fi
  nginx -t >/dev/null 2>&1 && systemctl reload nginx || true
  langkah "Virtual host nginx dihapus."
fi

# ------------------------------------------------- 3. cron & sudoers ------
rm -f "/etc/cron.d/${APP_NAME}"
rm -f "/etc/sudoers.d/${APP_NAME}"
langkah "Cron dan aturan sudo dihapus."

# --------------------------------------------------------- 4. kode ---------
if [[ -d "${APP_DIR}" ]]; then
  if [[ "${HAPUS_DATA}" == "1" ]]; then
    rm -rf "${APP_DIR}"
    langkah "Folder aplikasi ${APP_DIR} dihapus."
  else
    # Dipindahkan, bukan dihapus, supaya bisa diperiksa atau dipasang ulang.
    SARINGAN="${APP_DIR}.dihapus-$(date +%Y%m%d-%H%M%S)"
    mv "${APP_DIR}" "${SARINGAN}"
    langkah "Folder aplikasi dipindahkan ke ${SARINGAN}."
  fi
fi

rm -f "${CONF_DIR}/rasty.env"
rmdir "${CONF_DIR}" 2>/dev/null || true
langkah "Konfigurasi ${CONF_DIR} dihapus."

# --------------------------------------------------------- 5. data ---------
if [[ "${HAPUS_DATA}" == "1" ]]; then
  rm -rf "${DATA_DIR}"
  rm -rf "${LOG_DIR}"
  langkah "Database, unggahan, dan backup dihapus."
else
  echo
  ingat "DATA MASIH ADA di ${DATA_DIR}:"
  ls -1 "${DATA_DIR}" 2>/dev/null | sed 's/^/      /' || true
  echo "      Database  : ${DATA_DIR}/rasty_florist.db"
  echo "      Unggahan  : ${DATA_DIR}/uploads"
  echo "      Backup    : ${DATA_DIR}/backups"
  echo
  echo "      Data ini tidak dihapus. Untuk menghapus semuanya:"
  echo "        sudo bash installer/uninstall_ubuntu.sh --hapus-data"
  echo "      Sebelum itu, salin dulu bila masih diperlukan:"
  echo "        sudo tar -czf ~/rasty-backup.tar.gz ${DATA_DIR}"
fi

# -------------------------------------------------------- 6. paket ---------
if [[ "${HAPUS_PAKET}" == "1" ]]; then
  ingat "Menghapus paket nginx, certbot, dan sqlite3."
  DEBIAN_FRONTEND=noninteractive apt-get remove -y -qq nginx nginx-common certbot python3-certbot-nginx >/dev/null 2>&1 || true
  DEBIAN_FRONTEND=noninteractive apt-get autoremove -y -qq >/dev/null 2>&1 || true
  langkah "Paket dihapus."
else
  echo
  echo "      Paket nginx/certbot/sqlite3 dibiarkan terpasang."
  echo "      Hapus dengan: sudo bash installer/uninstall_ubuntu.sh --hapus-paket"
fi

printf '\n\033[1mSelesai.\033[0m\n\n'
