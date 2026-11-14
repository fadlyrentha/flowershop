"""Entry point WSGI untuk gunicorn di Linux.

Gunicorn dijalankan dengan:  gunicorn wsgi:app
Konfigurasi dibaca dari variabel lingkungan (lihat /etc/rasty-florist/rasty.env).
"""
import app as application

app = application.app
