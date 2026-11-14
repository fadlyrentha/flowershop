"""Rasty Florist - Sistem Manajemen Toko Bunga."""
import os
import time

from flask import Flask, render_template, send_from_directory, session

import db as database
import helpers

# Cek jadwal backup paling sering sekali per jam agar tidak membebani tiap request.
_BACKUP_CHECK = {"at": 0.0}
_BACKUP_INTERVAL = 3600


def env_flag(name, default=False):
    """Baca saklar dari variabel lingkungan (1/true/ya/yes/on)."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "ya", "yes", "on")


def create_app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("RASTY_SECRET", "rasty-florist-dev-secret-key"),
        DATABASE=os.environ.get("RASTY_DATABASE") or os.path.join(app.root_path, "rasty_florist.db"),
        UPLOAD_FOLDER=(os.environ.get("RASTY_UPLOAD_FOLDER")
                       or os.path.join(app.root_path, "static", "uploads")),
        MAX_CONTENT_LENGTH=32 * 1024 * 1024,
    )

    # Di belakang reverse proxy (nginx), header X-Forwarded-* dipakai agar
    # url_for(_external=True) menghasilkan alamat publik, bukan 127.0.0.1.
    # Hanya diaktifkan bila proxy memang tepercaya (RASTY_PROXY=1).
    if env_flag("RASTY_PROXY", False):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    app.teardown_appcontext(database.close_db)

    @app.route("/static/uploads/<path:nama>")
    def unggahan(nama):
        """Sajikan berkas unggahan dari UPLOAD_FOLDER.

        Folder unggahan bisa berada di luar folder aplikasi (di server Linux
        dipindah ke /var/lib supaya kode tetap hanya-baca), jadi rute ini
        menggantikan penyajian statis bawaan Flask.
        """
        return send_from_directory(app.config["UPLOAD_FOLDER"], nama)

    from blueprints.auth import bp as auth_bp
    from blueprints.public import bp as public_bp
    from blueprints.account import bp as account_bp
    from blueprints.customer import bp as customer_bp
    from blueprints.staff import bp as staff_bp
    from blueprints.qc import bp as qc_bp
    from blueprints.finance import bp as finance_bp
    from blueprints.admin import bp as admin_bp
    from blueprints.monitoring import bp as monitoring_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(qc_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(monitoring_bp)

    @app.context_processor
    def inject_globals():
        user = helpers.current_user()
        settings = database.all_settings()
        features = database.role_features(user["role"]) if user else {}
        features_aktif = {k for k, v in features.items() if v}
        panel = "#"
        notif_url = None
        notif_map = {
            "pelanggan": "customer.notifications",
            "staff_qc": "qc.notifications",
            "staff_keuangan": "finance.notifications",
            "administrator": "admin.notifications",
        }
        if user:
            from flask import url_for
            panel = {
                "pelanggan": url_for("customer.dashboard"),
                "staff_qc": url_for("qc.dashboard"),
                "staff_keuangan": url_for("finance.dashboard"),
                "administrator": url_for("admin.dashboard"),
            }.get(user["role"], url_for("staff.dashboard"))
            target = notif_map.get(user["role"], "staff.notifications")
            if target.split(".")[1] in features_aktif:
                notif_url = url_for(target)
        from nav import MENUS
        return {
            "current_user": user,
            "settings": settings,
            "features": features,
            "features_aktif": features_aktif,
            "menu": MENUS.get(user["role"], []) if user else [],
            "unread": helpers.unread_count(),
            "panel_url": panel,
            "notif_url": notif_url,
            "rupiah": helpers.rupiah,
            "is_video": helpers.is_video,
            "ROLE_LABEL": database.ROLE_LABEL,
            "ORDER_STATUS": database.ORDER_STATUS,
            "QC_STATUS": database.QC_STATUS,
            "KODE_TAGIHAN": database.KODE_TAGIHAN,
            "STATUS_KELUHAN": database.STATUS_KELUHAN,
            "KATALOG_SEKSI": database.KATALOG_SEKSI,
            "PENGIRIMAN_METODE": database.PENGIRIMAN_METODE,
            "MENU_PUBLIK": database.MENU_PUBLIK,
            "INVOICE_LOGO_UKURAN": database.INVOICE_LOGO_UKURAN,
            "invoice_logo_px": database.invoice_logo_px(settings),
            "katalog": database.katalog_dari(settings),
            "pengiriman_list": database.pengiriman_metode(settings),
            "menu_publik": database.menu_publik(settings),
            "jam_daftar": database.jam_daftar(settings),
            "jam_ringkas": database.jam_ringkas(settings),
            "toko_buka": database.toko_buka(settings),
            "sameday_sekarang": database.sameday_tersedia(settings),
            "wa_link": helpers.wa_link,
        }

    @app.before_request
    def jadwal_backup():
        sekarang = time.time()
        if sekarang - _BACKUP_CHECK["at"] < _BACKUP_INTERVAL:
            return
        _BACKUP_CHECK["at"] = sekarang
        try:
            database.auto_backup()
        except Exception:  # noqa: BLE001 - backup gagal tidak boleh memblokir halaman
            pass

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("error.html", kode=403,
                               pesan="Anda tidak memiliki hak akses ke halaman ini."), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", kode=404,
                               pesan="Halaman yang Anda cari tidak ditemukan."), 404

    @app.errorhandler(413)
    def too_large(_e):
        return render_template("error.html", kode=413,
                               pesan="Berkas yang diunggah terlalu besar (maksimal 32 MB)."), 413

    with app.app_context():
        database.init_db()
        if env_flag("RASTY_SEED_DEMO", True):
            database.seed_demo()
        else:
            # Instalasi toko sungguhan: cukup satu akun administrator.
            database.seed_admin(
                username=os.environ.get("RASTY_ADMIN_USER", "admin"),
                password=os.environ.get("RASTY_ADMIN_PASSWORD", "admin123"),
                nama=os.environ.get("RASTY_ADMIN_NAMA", "Administrator"),
                email=os.environ.get("RASTY_ADMIN_EMAIL", ""),
            )
        database.auto_backup()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(
        debug=env_flag("RASTY_DEBUG", True),
        host=os.environ.get("RASTY_HOST", "127.0.0.1"),
        port=int(os.environ.get("RASTY_PORT", "5000")),
    )
