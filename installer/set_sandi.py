"""Utilitas akun Rasty Florist: lihat daftar akun dan ganti kata sandi.

Pemakaian:
    python installer\\set_sandi.py --daftar
    python installer\\set_sandi.py --user admin
    python installer\\set_sandi.py --user admin --password sandi-baru
"""
import argparse
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.chdir(BASE)
os.environ.setdefault("RASTY_SEED_DEMO", "0")

import app as application  # noqa: E402  - impor memicu init_db
import db as database  # noqa: E402


def daftar_akun():
    baris = database.query(
        "SELECT username, nama, role, aktif FROM users ORDER BY role, username")
    if not baris:
        print("Belum ada akun di database.")
        return
    print("%-16s %-26s %-18s %s" % ("USERNAME", "NAMA", "PERAN", "STATUS"))
    print("-" * 70)
    for row in baris:
        print("%-16s %-26s %-18s %s" % (
            row["username"], (row["nama"] or "")[:26],
            database.ROLE_LABEL.get(row["role"], row["role"]),
            "aktif" if row["aktif"] else "nonaktif"))


def tanya_sandi():
    import getpass
    sandi = getpass.getpass("Kata sandi baru: ").strip()
    if len(sandi) < 6:
        print("! Kata sandi minimal 6 karakter.")
        return ""
    if sandi != getpass.getpass("Ulangi kata sandi: ").strip():
        print("! Kata sandi tidak sama.")
        return ""
    return sandi


def main():
    parser = argparse.ArgumentParser(description="Kelola akun Rasty Florist")
    parser.add_argument("--daftar", action="store_true", help="tampilkan semua akun")
    parser.add_argument("--user", default="", help="username yang kata sandinya diganti")
    parser.add_argument("--password", default="", help="kata sandi baru (opsional)")
    parser.add_argument("--aktif", default="", choices=["", "0", "1"],
                        help="1 = aktifkan akun, 0 = nonaktifkan akun")
    opsi = parser.parse_args()

    with application.app.app_context():
        if opsi.daftar:
            daftar_akun()
            return 0

        if not opsi.user:
            print("Sebutkan akun dengan --user, contoh: --user admin")
            print()
            daftar_akun()
            return 1

        user = database.query("SELECT * FROM users WHERE username = ?",
                              (opsi.user,), one=True)
        if user is None:
            print("! Akun '%s' tidak ditemukan." % opsi.user)
            daftar_akun()
            return 1

        # Mode --aktif saja: ubah status tanpa menyentuh kata sandi.
        if opsi.aktif != "" and not opsi.password:
            aktif = int(opsi.aktif)
            database.execute("UPDATE users SET aktif = ? WHERE username = ?",
                             (aktif, user["username"]))
            print("Akun '%s' %s." % (user["username"],
                                     "diaktifkan" if aktif else "dinonaktifkan"))
            return 0

        sandi = opsi.password or tanya_sandi()
        if not sandi:
            return 1

        from werkzeug.security import generate_password_hash
        # Mengganti sandi sekaligus mengaktifkan kembali akun (pemulihan).
        aktif = int(opsi.aktif) if opsi.aktif != "" else 1
        database.execute("UPDATE users SET password_hash = ?, aktif = ? WHERE username = ?",
                         (generate_password_hash(sandi), aktif, user["username"]))
        print("Kata sandi '%s' berhasil diganti." % user["username"])
        if opsi.aktif == "0":
            print("Akun '%s' dinonaktifkan." % user["username"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nDibatalkan.")
        sys.exit(130)
