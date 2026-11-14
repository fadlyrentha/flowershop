"""Autentikasi: login, register, logout."""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import db as database
import helpers

bp = Blueprint("auth", __name__)

STAFF_ROLES = {"staff_admin", "staff_kantor", "staff_gudang", "staff_qc", "staff_keuangan", "administrator"}


def home_for(role):
    if role == "pelanggan":
        return url_for("customer.dashboard")
    if role == "staff_qc":
        return url_for("qc.dashboard")
    if role == "staff_keuangan":
        return url_for("finance.dashboard")
    if role == "administrator":
        return url_for("admin.dashboard")
    return url_for("staff.dashboard")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if helpers.current_user():
        return redirect(home_for(helpers.current_user()["role"]))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = database.query("SELECT * FROM users WHERE username = ?", (username,), one=True)
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Username atau password salah.", "danger")
        elif not user["aktif"]:
            flash("Akun Anda dinonaktifkan. Hubungi administrator.", "danger")
        else:
            session.clear()
            session["user_id"] = user["id"]
            flash("Selamat datang, %s." % user["nama"], "success")
            nxt = request.args.get("next")
            return redirect(nxt if nxt and nxt.startswith("/") else home_for(user["role"]))
    return render_template("auth/login.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if helpers.current_user():
        return redirect(home_for(helpers.current_user()["role"]))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        konfirmasi = request.form.get("konfirmasi", "")
        nama = request.form.get("nama", "").strip()
        telepon = request.form.get("telepon", "").strip()
        email = request.form.get("email", "").strip()
        alamat = request.form.get("alamat", "").strip()

        errors = []
        if len(username) < 4:
            errors.append("Username minimal 4 karakter.")
        if len(password) < 6:
            errors.append("Password minimal 6 karakter.")
        if password != konfirmasi:
            errors.append("Konfirmasi password tidak cocok.")
        if not nama:
            errors.append("Nama lengkap wajib diisi.")
        if database.query("SELECT id FROM users WHERE username = ?", (username,), one=True):
            errors.append("Username sudah digunakan.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("auth/register.html", form=request.form)

        database.execute(
            "INSERT INTO users (username, password_hash, nama, role, telepon, email, alamat, aktif, created_at)"
            " VALUES (?, ?, ?, 'pelanggan', ?, ?, ?, 1, ?)",
            (username, generate_password_hash(password), nama, telepon, email, alamat, database.now()),
        )
        helpers.notify_roles(["staff_admin", "administrator"], "Pelanggan baru mendaftar",
                             "%s (%s) baru membuat akun." % (nama, username), url_for("staff.customers"))
        flash("Registrasi berhasil. Silakan masuk untuk mulai berbelanja.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/register.html", form={})


@bp.route("/logout")
def logout():
    session.clear()
    flash("Anda telah keluar.", "info")
    return redirect(url_for("public.index"))
