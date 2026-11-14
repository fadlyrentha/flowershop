#!/usr/bin/env bash
#
# Kelola akun Rasty Florist di server Ubuntu (daftar akun, ganti kata sandi,
# aktif/nonaktifkan akun) tanpa membuka aplikasi lewat browser.
#
# Jalankan sebagai root:
#   sudo bash installer/set_sandi_ubuntu.sh --daftar
#   sudo bash installer/set_sandi_ubuntu.sh --user admin
#   sudo bash installer/set_sandi_ubuntu.sh --user admin --password SandiBaru123
#   sudo bash installer/set_sandi_ubuntu.sh --user staffqc --nonaktif
#
set -euo pipefail

APP_NAME="rasty-florist"
APP_USER="rasty"
APP_DIR="/opt/${APP_NAME}"
DATA_DIR="/var/lib/${APP_NAME}"
ENV_FILE="/etc/${APP_NAME}/rasty.env"
VENV_PY="/opt/${APP_NAME}/.venv/bin/python"

AKSI=""
USERNAME=""
PASSWORD=""
AKTIF=""

petunjuk() {
  cat <<'EOF'
Pemakaian: sudo bash installer/set_sandi_ubuntu.sh [pilihan]

  --daftar                 tampilkan semua akun
  --user NAMA              akun yang kata sandinya diganti
  --password SANDI         kata sandi baru (bila dikosongkan akan ditanya)
  --nonaktif               nonaktifkan akun
  --aktifkan               aktifkan kembali akun
  -h, --help               tampilkan bantuan ini

Contoh:
  sudo bash installer/set_sandi_ubuntu.sh --daftar
  sudo bash installer/set_sandi_ubuntu.sh --user admin --password RahasiaToko2026
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --daftar) AKSI="daftar" ;;
    --user) USERNAME="${2:-}"; shift ;;
    --password) PASSWORD="${2:-}"; shift ;;
    --nonaktif) AKTIF="0" ;;
    --aktifkan) AKTIF="1" ;;
    -h|--help) petunjuk; exit 0 ;;
    *) printf 'Pilihan tidak dikenal: %s\n\n' "$1" >&2; petunjuk; exit 1 ;;
  esac
  shift
done

if [[ "${EUID}" -ne 0 ]]; then
  printf '\033[1;31m  x Harus dijalankan sebagai root: sudo bash %s\033[0m\n' "$0" >&2
  exit 1
fi

if [[ ! -x "${VENV_PY}" ]]; then
  printf '\033[1;31m  x %s tidak ditemukan. Jalankan install_ubuntu.sh lebih dulu.\033[0m\n' "${VENV_PY}" >&2
  exit 1
fi

if [[ -z "${AKSI}" && -z "${USERNAME}" ]]; then
  petunjuk
  exit 1
fi

# Baca konfigurasi aplikasi (lokasi database, kunci sesi) untuk diteruskan.
if [[ ! -f "${ENV_FILE}" ]]; then
  printf '\033[1;31m  x %s tidak ditemukan. Jalankan install_ubuntu.sh lebih dulu.\033[0m\n' "${ENV_FILE}" >&2
  exit 1
fi
# shellcheck disable=SC1090
set -a
. "${ENV_FILE}"
set +a

# Utilitas Python dijalankan sebagai pengguna layanan supaya berkas database
# tetap dimiliki pengguna itu.
jalankan_utilitas() {
  sudo -u "${APP_USER}" env \
    RASTY_SECRET="${RASTY_SECRET:-}" \
    RASTY_DATABASE="${RASTY_DATABASE:-${DATA_DIR}/rasty_florist.db}" \
    RASTY_UPLOAD_FOLDER="${RASTY_UPLOAD_FOLDER:-${DATA_DIR}/uploads}" \
    RASTY_BACKUP_FOLDER="${RASTY_BACKUP_FOLDER:-${DATA_DIR}/backups}" \
    RASTY_SEED_DEMO=0 \
    "${VENV_PY}" "${APP_DIR}/installer/set_sandi.py" "$@"
}


if [[ "${AKSI}" == "daftar" ]]; then
  jalankan_utilitas --daftar
  exit 0
fi

if [[ -z "${PASSWORD}" && -z "${AKTIF}" ]]; then
  # Tanya dua kali tanpa menampilkan di layar.
  read -r -s -p "Kata sandi baru untuk '${USERNAME}': " PASSWORD; echo
  read -r -s -p "Ulangi kata sandi: " PASSWORD2; echo
  if [[ "${PASSWORD}" != "${PASSWORD2}" ]]; then
    printf '\033[1;31m  x Kata sandi tidak sama.\033[0m\n' >&2
    exit 1
  fi
  unset PASSWORD2
fi

if [[ -n "${PASSWORD}" && ${#PASSWORD} -lt 6 ]]; then
  printf '\033[1;31m  x Kata sandi minimal 6 karakter.\033[0m\n' >&2
  exit 1
fi

ARG=(--user "${USERNAME}")
[[ -n "${PASSWORD}" ]] && ARG+=(--password "${PASSWORD}")
[[ -n "${AKTIF}" ]] && ARG+=(--aktif "${AKTIF}")

jalankan_utilitas "${ARG[@]}"
