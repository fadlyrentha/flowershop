#!/usr/bin/env bash
#
# Pembaruan aplikasi Rasty Florist di Ubuntu (dijalankan sebagai root).
#
# Alur: backup database -> pasang kode baru -> migrasi skema -> nyalakan ulang
# layanan. Kode di /opt diperbarui, sedangkan database dan unggahan di
# /var/lib tidak pernah tersentuh.
#
# Contoh:
#   sudo bash installer/update_ubuntu.sh --online
#   sudo bash installer/update_ubuntu.sh --zip /tmp/rasty-florist.zip
#   sudo bash installer/update_ubuntu.sh --sumber /tmp/rasty-florist
#   sudo bash installer/update_ubuntu.sh --online --tanpa-restart
#   sudo bash installer/update_ubuntu.sh --online --dry-run
#
set -euo pipefail

APP_NAME="rasty-florist"
APP_USER="rasty"
APP_GROUP="rasty"
APP_DIR="/opt/${APP_NAME}"
DATA_DIR="/var/lib/${APP_NAME}"
ENV_FILE="/etc/${APP_NAME}/rasty.env"
VENV_PY="${APP_DIR}/.venv/bin/python"
SERVICE_NAME="rasty-florist"

# Skrip ini bisa menimpa dirinya sendiri saat kode baru disalin (folder /opt
# diperbarui di tengah eksekusi). Bash membaca skrip sedikit demi sedikit,
# jadi berkas yang berubah di tengah jalan membuat baris berikutnya kacau.
# Karena itu, salinan sementara dibuat lebih dulu lalu skrip itu yang berjalan.
if [[ -z "${RASTY_UPDATE_STAGED:-}" ]]; then
  # --suffix dipakai karena mktemp GNU menuntut pola X di akhir template.
  STAGED="$(mktemp --suffix=.sh /tmp/rasty-update-XXXXXX)"
  cp "${BASH_SOURCE[0]}" "${STAGED}"
  chmod +x "${STAGED}"
  export STAGED RASTY_UPDATE_STAGED=1
  exec bash "${STAGED}" "$@"
fi
trap 'rm -f "${STAGED}"' EXIT

SUMBER=""
ZIP=""
ONLINE=0
DRY_RUN=0
RESTART=1
BACKUP=1

langkah() { printf '  -> %s\n' "$*"; }
ingat() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
gagal() { printf '\033[1;31m  x %s\033[0m\n' "$*" >&2; exit 1; }

judul() {
  printf '\n\033[1m%s\033[0m\n' "=============================================================="
  printf '\033[1m  %s\033[0m\n' "$*"
  printf '\033[1m%s\033[0m\n' "=============================================================="
}

petunjuk() {
  cat <<'EOF'
Pemakaian: sudo bash installer/update_ubuntu.sh [sumber] [pilihan]

Sumber pembaruan (pilih satu):
  --online                 unduh cabang terbaru dari GitHub
  --zip BERKAS             pasang dari arsip .zip
  --sumber FOLDER          pasang dari folder kode (memuat app.py)

Pilihan lain:
  --app-dir FOLDER         folder aplikasi tujuan (bawaan /opt/rasty-florist)
  --tanpa-restart          jangan nyalakan ulang layanan setelah selesai
  --tanpa-backup           lewati backup otomatis sebelum memperbarui
  --dry-run                hitung berkas saja, tidak menulis apa pun
  -h, --help               tampilkan bantuan ini

Contoh:
  sudo bash installer/update_ubuntu.sh --online
  sudo bash installer/update_ubuntu.sh --zip /tmp/rasty-florist.zip
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --online) ONLINE=1 ;;
    --zip) ZIP="${2:-}"; shift ;;
    --sumber) SUMBER="${2:-}"; shift ;;
    --app-dir) APP_DIR="${2:-}"; shift ;;
    --tanpa-restart) RESTART=0 ;;
    --tanpa-backup) BACKUP=0 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help) petunjuk; exit 0 ;;
    *) printf 'Pilihan tidak dikenal: %s\n\n' "$1" >&2; petunjuk; exit 1 ;;
  esac
  shift
done

if [[ "${EUID}" -ne 0 ]]; then
  gagal "Jalankan sebagai root: sudo bash installer/update_ubuntu.sh"
fi

JUMLAH_SUMBER="${ONLINE}"
if [[ -n "${ZIP}" ]]; then JUMLAH_SUMBER=$((JUMLAH_SUMBER + 1)); fi
if [[ -n "${SUMBER}" ]]; then JUMLAH_SUMBER=$((JUMLAH_SUMBER + 1)); fi
if [[ "${JUMLAH_SUMBER}" -ne 1 ]]; then
  gagal "Pilih tepat satu sumber pembaruan (--online, --zip, atau --sumber)."
fi

# --app-dir bisa mengubah lokasi aplikasi, jadi venv dihitung ulang dari sini.
VENV_PY="${APP_DIR}/.venv/bin/python"
if [[ ! -x "${VENV_PY}" ]]; then
  gagal "${VENV_PY} tidak ditemukan. Jalankan install_ubuntu.sh lebih dulu."
fi

# Salin nilai konfigurasi (RASTY_DATABASE, RASTY_SECRET, dst) ke lingkungan.
if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a; . "${ENV_FILE}"; set +a
fi
RASTY_DATABASE="${RASTY_DATABASE:-${DATA_DIR}/rasty_florist.db}"
RASTY_UPLOAD_FOLDER="${RASTY_UPLOAD_FOLDER:-${DATA_DIR}/uploads}"
RASTY_BACKUP_FOLDER="${RASTY_BACKUP_FOLDER:-${DATA_DIR}/backups}"

judul "Pembaruan Rasty Florist"
echo "  Folder aplikasi : ${APP_DIR}"
echo "  Database        : ${RASTY_DATABASE}"
echo

# ------------------------------------------------------ 1. backup dahulu ---
if [[ "${BACKUP}" -eq 1 && "${DRY_RUN}" -eq 0 ]]; then
  judul "Langkah 1/4 - Backup sebelum pembaruan"
  if [[ -f "${APP_DIR}/installer/backup_ubuntu.sh" ]]; then
    # Backup gagal berarti pembaruan dibatalkan: lebih baik tidak jadi
    # memperbarui daripada kehilangan kemampuan memulihkan data.
    bash "${APP_DIR}/installer/backup_ubuntu.sh" \
      || gagal "Backup gagal - pembaruan dibatalkan."
  else
    ingat "backup_ubuntu.sh tidak ditemukan - backup dilewati."
  fi
fi

# --------------------------------------------------------- 2. pasang kode --
judul "Langkah 2/4 - Memasang kode baru"
# Kode /opt dimiliki root; installer/update.py dilindungi dari penimpaan
# sehingga skrip yang sedang berjalan tidak tertimpa di tengah jalan.
PERINTAH=("${VENV_PY}" "${APP_DIR}/installer/update.py" "--app-dir" "${APP_DIR}")
if [[ "${ONLINE}" -eq 1 ]]; then
  PERINTAH+=("--online")
elif [[ -n "${ZIP}" ]]; then
  PERINTAH+=("--zip" "${ZIP}")
else
  PERINTAH+=("--sumber" "${SUMBER}")
fi
if [[ "${DRY_RUN}" -eq 1 ]]; then PERINTAH+=("--dry-run"); fi

"${PERINTAH[@]}" || gagal "Pemasangan kode gagal."

if [[ "${DRY_RUN}" -eq 1 ]]; then
  ingat "Mode uji coba - tidak ada perubahan yang ditulis."
  exit 0
fi

# Hak akses dikembalikan seperti hasil pemasang: root menulis, grup membaca.
chown -R root:"${APP_GROUP}" "${APP_DIR}"
chmod -R u=rwX,g=rX,o= "${APP_DIR}"
langkah "Hak akses folder aplikasi dirapikan."

# -------------------------------------------------------- 3. dependensi ----
judul "Langkah 3/4 - Memeriksa dependensi Python"
"${VENV_PY}" -m pip install --quiet -r "${APP_DIR}/requirements.txt" \
  && langkah "Dependensi sesuai requirements.txt." \
  || ingat "Pemasangan dependensi gagal - periksa koneksi atau requirements.txt."
chown -R root:"${APP_GROUP}" "${APP_DIR}/.venv" 2>/dev/null || true

# --------------------------------------------------- 4. migrasi & layanan --
judul "Langkah 4/4 - Migrasi database & menyalakan ulang layanan"
# Migrasi kolom/tabel baru dijalankan sebagai pengguna layanan agar berkas
# database tetap dimiliki pengguna itu.
sudo -u "${APP_USER}" env \
  RASTY_SECRET="${RASTY_SECRET:-}" \
  RASTY_DATABASE="${RASTY_DATABASE}" \
  RASTY_UPLOAD_FOLDER="${RASTY_UPLOAD_FOLDER}" \
  RASTY_BACKUP_FOLDER="${RASTY_BACKUP_FOLDER}" \
  RASTY_SEED_DEMO=0 \
  "${VENV_PY}" "${APP_DIR}/installer/init_db.py" \
  || ingat "Migrasi melaporkan masalah - periksa pesan di atas."

if [[ "${RESTART}" -eq 1 ]]; then
  systemctl restart "${SERVICE_NAME}" || gagal "Gagal menyalakan ulang ${SERVICE_NAME}."
  sleep 3
  if systemctl is-active --quiet "${SERVICE_NAME}"; then
    langkah "Layanan aktif kembali."
  else
    ingat "Layanan tidak aktif. Periksa: journalctl -u ${SERVICE_NAME} -n 50"
  fi
else
  ingat "Layanan tidak dinyalakan ulang (--tanpa-restart). Jalankan:"
  ingat "  sudo systemctl restart ${SERVICE_NAME}"
fi

judul "Pembaruan selesai"
echo "  Periksa layanan : systemctl status ${SERVICE_NAME} --no-pager"
echo "  Periksa log     : journalctl -u ${SERVICE_NAME} -n 50 --no-pager"
echo
