"""Pasang pembaruan kode Rasty Florist dari folder atau arsip .zip.

Dipakai oleh ``installer/update_ubuntu.sh`` (dijalankan sebagai root) dan bisa
juga dijalankan manual. Aturan berkas yang dilindungi sama persis dengan yang
dipakai panel web, karena keduanya memakai modul ``updater.py``.

Contoh:
    python installer/update.py --sumber /tmp/rasty-florist
    python installer/update.py --zip /tmp/rasty-florist.zip
    python installer/update.py --online
    python installer/update.py --sumber /tmp/rasty-florist --dry-run

Keluar dengan kode 0 bila berhasil, 1 bila gagal.
"""
import argparse
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import updater  # noqa: E402
import version  # noqa: E402


def main():
    pilihan = argparse.ArgumentParser(description="Pasang pembaruan Rasty Florist.")
    sumber = pilihan.add_mutually_exclusive_group(required=True)
    sumber.add_argument("--sumber", help="folder kode baru (memuat app.py)")
    sumber.add_argument("--zip", help="arsip .zip kode baru")
    sumber.add_argument("--online", action="store_true",
                        help="unduh cabang terbaru dari GitHub")
    pilihan.add_argument("--app-dir", default=updater.ROOT,
                         help="folder aplikasi tujuan (bawaan: folder proyek ini)")
    pilihan.add_argument("--dry-run", action="store_true",
                         help="hitung berkas saja, tidak menulis")
    arg = pilihan.parse_args()

    app_dir = os.path.abspath(arg.app_dir)
    print("Folder aplikasi : %s" % app_dir)
    print("Versi sekarang  : %s" % updater.versi_sekarang())

    if not arg.dry_run and not updater.bisa_menulis(app_dir):
        print("! Folder aplikasi tidak dapat ditulis. Jalankan sebagai root.")
        return 1

    if arg.online:
        print("Mengunduh %s (cabang %s)..." % (version.REPO, version.CABANG))
        ringkas = updater.pasang_online(app_dir=app_dir, dry_run=arg.dry_run)
    elif arg.zip:
        ringkas = updater.pasang_dari_zip(arg.zip, app_dir=app_dir, dry_run=arg.dry_run)
    else:
        ringkas = updater.pasang_dari_folder(arg.sumber, app_dir=app_dir, dry_run=arg.dry_run)

    if not ringkas["berhasil"]:
        print("x Pembaruan gagal: %s" % ringkas["pesan"])
        return 1

    print("  %s" % ringkas["pesan"])
    if arg.dry_run:
        print("  (uji coba - tidak ada berkas yang ditulis)")
        return 0
    print("Versi terpasang : %s" % updater.versi_sekarang())
    return 0


if __name__ == "__main__":
    sys.exit(main())
