#!/usr/bin/env bash
#
# Web server (nginx) + HTTPS untuk Rasty Florist di Ubuntu 24.04.
#
# Membuat virtual host nginx, meneruskan permintaan ke aplikasi (gunicorn),
# menyajikan berkas unggahan langsung dari disk, lalu bila DOMAIN diisi dan
# DNS sudah mengarah ke server ini, meminta sertifikat Let's Encrypt.
#
# Jalankan sebagai root:  sudo DOMAIN=toko.example.com bash installer/setup_nginx.sh
#
set -euo pipefail

APP_NAME="rasty-florist"
APP_USER="rasty"
DATA_DIR="/var/lib/${APP_NAME}"
CONF_DIR="/etc/${APP_NAME}"
ENV_FILE="${CONF_DIR}/rasty.env"
SERVICE_NAME="rasty-florist"
LOG_DIR="/var/log/${APP_NAME}"

DOMAIN="${DOMAIN:-}"
EMAIL_SSL="${EMAIL_SSL:-}"
PAKAI_SSL="${PAKAI_SSL:-1}"

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
  gagal "Skrip ini harus dijalankan sebagai root: sudo bash installer/setup_nginx.sh"
fi

if ! command -v nginx >/dev/null 2>&1; then
  gagal "nginx belum terpasang. Jalankan installer/install_ubuntu.sh lebih dulu."
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  gagal "${ENV_FILE} tidak ditemukan. Jalankan installer/install_ubuntu.sh lebih dulu."
fi

# Ambil port aplikasi dari berkas konfigurasi.
PORT="$(grep -E '^RASTY_PORT=' "${ENV_FILE}" | head -n1 | cut -d= -f2- || true)"
PORT="${PORT:-8000}"

SERVER_NAME="${DOMAIN:-_}"
SITUS_ADA="/etc/nginx/sites-available/${APP_NAME}"
SITUS_AKTIF="/etc/nginx/sites-enabled/${APP_NAME}"

judul "Web server nginx untuk Rasty Florist"
echo "  Domain        : ${DOMAIN:-(belum diisi - melayani semua nama host)}"
echo "  Port aplikasi : ${PORT}"

# ------------------------------------------------------- 1. vhost ---------
judul "Langkah 1/5 - Membuat virtual host nginx"

CADANGAN=""
if [[ -f "${SITUS_ADA}" ]]; then
  CADANGAN="${SITUS_ADA}.bak-$(date +%Y%m%d-%H%M%S)"
  cp "${SITUS_ADA}" "${CADANGAN}"
  langkah "Konfigurasi lama dicadangkan ke $(basename "${CADANGAN}")."
fi

install -d -o "${APP_USER}" -g "${APP_USER}" -m 0750 "${LOG_DIR}"

# Batas unggahan 40M = MAX_CONTENT_LENGTH aplikasi (32 MB) + margin multipart.
cat > "${SITUS_ADA}" <<EOF
# Rasty Florist - dibuat otomatis oleh installer/setup_nginx.sh
#
# Meneruskan permintaan ke gunicorn (aplikasi Flask) dan menyajikan berkas
# unggahan langsung dari disk supaya tidak membebani aplikasi.

upstream ${APP_NAME}_app {
    server 127.0.0.1:${PORT} fail_timeout=0;
    keepalive 16;
}

server {
    listen 80;
    listen [::]:80;
    server_name ${SERVER_NAME};

    client_max_body_size 40M;

    # Foto produk, logo, bukti pembayaran, dan desain invoice dilayani nginx
    # langsung dari folder data.
    location /static/uploads/ {
        alias ${DATA_DIR}/uploads/;
        access_log off;
        expires 7d;
        add_header Cache-Control "public";
        # Berkas yang tidak ada ditangani aplikasi (mis. berkas bawaan).
        error_page 404 = @app;
    }

    location @app {
        proxy_pass http://${APP_NAME}_app;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header Connection "";
        proxy_read_timeout 120s;
        proxy_redirect off;
    }

    location / {
        proxy_pass http://${APP_NAME}_app;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header Connection "";
        proxy_read_timeout 120s;
        proxy_redirect off;
    }

    # Berkas tersembunyi dan berkas kode tidak boleh dilayani.
    location ~ /\. {
        deny all;
    }

    # Log nginx disimpan di folder log nginx standar (dimiliki www-data),
    # bukan di folder log aplikasi yang hanya bisa diakses pengguna layanan.
    access_log /var/log/nginx/${APP_NAME}-access.log;
    error_log  /var/log/nginx/${APP_NAME}-error.log;
}
EOF

langkah "Virtual host ditulis di ${SITUS_ADA}."

# ---------------------------------------------- 2. aktifkan & uji ---------
judul "Langkah 2/5 - Mengaktifkan & menguji konfigurasi"

ln -sfn "${SITUS_ADA}" "${SITUS_AKTIF}"

if nginx -t 2>&1 | sed 's/^/     /'; then
  langkah "Konfigurasi nginx valid."
else
  # Konfigurasi tidak valid: kembalikan keadaan semula supaya web server
  # yang sedang melayani situs lain tidak ikut mati.
  rm -f "${SITUS_AKTIF}"
  if [[ -n "${CADANGAN}" ]]; then
    cp "${CADANGAN}" "${SITUS_ADA}"
    ln -sfn "${SITUS_ADA}" "${SITUS_AKTIF}"
    nginx -t >/dev/null 2>&1 && systemctl reload nginx || true
    ingat "Konfigurasi lama dipulihkan."
  else
    rm -f "${SITUS_ADA}"
  fi
  gagal "Konfigurasi nginx tidak valid - perubahan dibatalkan."
fi

# Situs bawaan Ubuntu menangkap semua nama host; matikan agar vhost ini dipakai.
DEFAULT_DIMATIKAN=0
if [[ -L /etc/nginx/sites-enabled/default ]]; then
  rm -f /etc/nginx/sites-enabled/default
  DEFAULT_DIMATIKAN=1
  langkah "Situs bawaan nginx ('default') dinonaktifkan."
fi

systemctl reload nginx
langkah "nginx dimuat ulang."

# ------------------------------------------------- 3. uji lewat nginx -----
judul "Langkah 3/5 - Uji akses lewat nginx"

KODE="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${DOMAIN:-localhost}" "http://127.0.0.1/" || echo 000)"
case "${KODE}" in
  200)
    langkah "Halaman beranda lewat nginx: HTTP 200."
    ;;
  301|302)
    langkah "Halaman beranda lewat nginx: HTTP ${KODE} (pengalihan - wajar bila HTTPS aktif)."
    ;;
  000)
    ingat "Tidak bisa menghubungi nginx - periksa: systemctl status nginx"
    ;;
  *)
    ingat "Halaman beranda: HTTP ${KODE} - periksa /var/log/nginx/${APP_NAME}-error.log"
    ;;
esac

# ------------------------------------------------------- 4. HTTPS ---------
judul "Langkah 4/5 - HTTPS (Let's Encrypt)"

if [[ -z "${DOMAIN}" ]]; then
  ingat "DOMAIN belum diisi, HTTPS dilewati."
  echo "     Setelah domain diarahkan ke IP server ini, jalankan:"
  echo "       sudo DOMAIN=toko.example.com bash /opt/${APP_NAME}/installer/setup_nginx.sh"
elif [[ "${PAKAI_SSL}" != "1" ]]; then
  ingat "PAKAI_SSL=0 - HTTPS dilewati."
else
  # DNS harus sudah mengarah ke server ini sebelum sertifikat diminta.
  IP_SERVER="$(curl -s --max-time 10 https://api.ipify.org || true)"
  IP_DOMAIN="$(getent hosts "${DOMAIN}" | awk '{ print $1 }' | head -n1 || true)"

  if [[ -z "${IP_DOMAIN}" ]]; then
    ingat "Domain ${DOMAIN} belum bisa diterjemahkan DNS. HTTPS dilewati."
    echo "     Arahkan A record ${DOMAIN} ke ${IP_SERVER:-IP server ini}, tunggu propagasi,"
    echo "     lalu jalankan ulang skrip ini."
  elif [[ -n "${IP_SERVER}" && "${IP_DOMAIN}" != "${IP_SERVER}" ]]; then
    ingat "DNS ${DOMAIN} mengarah ke ${IP_DOMAIN}, bukan ${IP_SERVER}."
    echo "     Sertifikat Let's Encrypt hanya bisa diterbitkan bila DNS sudah tepat."
    echo "     Bila server ini di belakang Cloudflare/proxy, gunakan mode DNS challenge."
  else
    ARG_EMAIL=()
    if [[ -n "${EMAIL_SSL}" ]]; then
      ARG_EMAIL=(--email "${EMAIL_SSL}")
    else
      ARG_EMAIL=(--register-unsafely-without-email)
    fi
    langkah "Meminta sertifikat untuk ${DOMAIN}"
    if certbot --nginx --non-interactive --agree-tos --redirect \
        "${ARG_EMAIL[@]}" -d "${DOMAIN}"; then
      langkah "HTTPS aktif. Perpanjangan otomatis lewat systemd timer certbot."
      systemctl list-timers certbot.timer --no-pager 2>/dev/null | head -n3 | sed 's/^/     /' || true
    else
      ingat "certbot gagal. Aplikasi tetap berjalan lewat HTTP."
      echo "     Jalankan manual setelah DNS benar:"
      echo "       sudo certbot --nginx -d ${DOMAIN}"
    fi
  fi
fi

# ------------------------------------------------------- 5. ringkasan -----
judul "Langkah 5/5 - Selesai"

echo "  Konfigurasi nginx : ${SITUS_ADA}"
echo "  Uji konfigurasi   : sudo nginx -t"
echo "  Muat ulang        : sudo systemctl reload nginx"
echo "  Log akses         : /var/log/nginx/${APP_NAME}-access.log"
echo "  Log galat         : /var/log/nginx/${APP_NAME}-error.log"
echo
if [[ -n "${DOMAIN}" ]]; then
  echo "  Alamat : https://${DOMAIN}  (http://${DOMAIN} bila HTTPS dilewati)"
else
  echo "  Alamat : http://<IP-server>/"
fi
echo
echo "  Aplikasi (gunicorn) : systemctl status ${SERVICE_NAME}"
echo "  Panduan lengkap     : /opt/${APP_NAME}/PANDUAN-INSTALL-UBUNTU.md"
echo

if [[ "${DEFAULT_DIMATIKAN}" == "1" ]]; then
  echo "  Catatan: situs bawaan nginx dimatikan agar aplikasi ini dilayani"
  echo "  pada semua nama host. Aktifkan kembali dengan:"
  echo "    sudo ln -sfn /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default"
  echo
fi
