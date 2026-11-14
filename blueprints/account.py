"""Akun pengguna: profil dan kata sandi untuk semua peran."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import db as database
import helpers

bp = Blueprint("account", __name__, url_prefix="/akun")

MIN_SANDI = 6


@bp.route("/profil", methods=["GET", "POST"])
@helpers.login_required
def profile():
    user = helpers.current_user()
    if request.method == "POST":
        nama = request.form.get("nama", "").strip()
        if not nama:
            flash("Nama tidak boleh kosong.", "danger")
            return redirect(url_for("account.profile"))
        database.execute(
            "UPDATE users SET nama = ?, telepon = ?, email = ?, alamat = ? WHERE id = ?",
            (nama, request.form.get("telepon", "").strip(),
             request.form.get("email", "").strip(),
             request.form.get("alamat", "").strip(), user["id"]))
        flash("Data profil berhasil diperbarui.", "success")
        return redirect(url_for("account.profile"))
    return render_template("account/profile.html", user=user)


@bp.route("/kata-sandi", methods=["GET", "POST"])
@helpers.login_required
def password():
    user = helpers.current_user()
    if request.method == "POST":
        lama = request.form.get("lama", "")
        baru = request.form.get("baru", "")
        ulang = request.form.get("ulang", "")
        if not check_password_hash(user["password_hash"], lama):
            flash("Kata sandi lama tidak sesuai.", "danger")
        elif len(baru) < MIN_SANDI:
            flash("Kata sandi baru minimal %d karakter." % MIN_SANDI, "danger")
        elif baru != ulang:
            flash("Konfirmasi kata sandi baru tidak cocok.", "danger")
        else:
            database.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                             (generate_password_hash(baru), user["id"]))
            flash("Kata sandi berhasil diubah.", "success")
            return redirect(url_for("account.profile"))
    return render_template("account/password.html", user=user, minimal=MIN_SANDI)
