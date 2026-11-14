"""Server produksi Rasty Florist.

Menjalankan aplikasi dengan waitress (WSGI server untuk Windows/Linux).
Bila waitress belum terpasang, jatuh ke server bawaan Flask.

Konfigurasi lewat variabel lingkungan:
    RASTY_HOST          alamat bind (default 0.0.0.0)
    RASTY_PORT          port (default 5000)
    RASTY_THREADS       jumlah thread waitress (default 8)
    RASTY_SECRET        kunci sesi Flask
    RASTY_DATABASE      lokasi berkas .db (default rasty_florist.db di folder app)
    RASTY_SEED_DEMO     1 = isi data contoh saat database kosong (default 0 di sini)
"""
import os

import app as application

app = application.app

HOST = os.environ.get("RASTY_HOST", "0.0.0.0")
PORT = int(os.environ.get("RASTY_PORT", "5000"))
THREADS = int(os.environ.get("RASTY_THREADS", "8"))


def main():
    try:
        from waitress import serve
    except ImportError:
        print("waitress belum terpasang - memakai server bawaan Flask.")
        print("Pasang dengan: python -m pip install waitress")
        app.run(host=HOST, port=PORT, debug=False)
        return

    print("Rasty Florist berjalan di http://%s:%d" % (HOST, PORT))
    print("Tekan Ctrl+C untuk menghentikan server.")
    serve(app, host=HOST, port=PORT, threads=THREADS)


if __name__ == "__main__":
    main()
