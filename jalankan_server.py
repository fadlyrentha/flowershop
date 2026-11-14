"""Peluncur server Rasty Florist.

Membaca rasty.conf (dibuat oleh installer) lalu menjalankan server waitress.
Bisa dijalankan langsung: python jalankan_server.py
"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(BASE, "rasty.conf")

# Nilai bawaan bila rasty.conf belum ada (jalankan installer dulu).
BAWAAN = {
    "RASTY_HOST": "127.0.0.1",
    "RASTY_PORT": "5000",
    "RASTY_THREADS": "8",
    "RASTY_DEBUG": "0",
}


def baca_conf(path):
    """Baca rasty.conf menjadi dict. Baris kosong dan komentar diabaikan."""
    data = {}
    if not os.path.isfile(path):
        return data
    with open(path, encoding="utf-8") as berkas:
        for baris in berkas:
            baris = baris.strip()
            if not baris or baris.startswith("#") or "=" not in baris:
                continue
            kunci, nilai = baris.split("=", 1)
            data[kunci.strip()] = nilai.strip()
    return data


def siapkan_lingkungan(data):
    nilai = dict(BAWAAN)
    nilai.update({k: v for k, v in data.items() if v})
    for kunci, isi in nilai.items():
        # Variabel lingkungan yang sudah ada tidak ditimpa (bisa dikustom).
        os.environ.setdefault(kunci, isi)
    if "RASTY_DATABASE" not in os.environ:
        os.environ["RASTY_DATABASE"] = os.path.join(BASE, "rasty_florist.db")
    return nilai


def main():
    data = baca_conf(CONF)
    if not data:
        print("rasty.conf belum ada - memakai nilai bawaan.")
        print("Jalankan pemasang lebih dulu: python installer\\install.py")
        print()
    nilai = siapkan_lingkungan(data)
    os.chdir(BASE)
    sys.path.insert(0, BASE)

    os.environ["RASTY_SEED_DEMO"] = os.environ.get("RASTY_SEED_DEMO", "0")

    import serve
    print("Database : %s" % os.environ["RASTY_DATABASE"])
    print("Alamat   : http://%s:%s" % (nilai["RASTY_HOST"], nilai["RASTY_PORT"]))
    print()
    serve.main()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nServer dihentikan.")
