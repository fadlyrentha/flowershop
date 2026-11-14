"""Konfigurasi menu sidebar per peran."""

# Menu monitoring bersama untuk semua peran selain pelanggan.
MONITORING_MENU = ("Monitoring", [
    ("Monitoring Harian", "monitoring.daily", "monitoring_harian", "calendar2-check"),
    ("List Order", "monitoring.orders", "monitoring", "clipboard-data"),
    ("List Stok", "monitoring.stock", "monitoring", "box-seam"),
    ("Status Pesanan", "monitoring.status", "monitoring", "kanban"),
    ("Lacak Pesanan", "monitoring.track", "monitoring", "geo-alt"),
])

# Menu akun bersama; setiap peran punya halaman profil dan kata sandi sendiri.
AKUN_MENU = ("Akun", [
    ("Profil Saya", "account.profile", "profil", "person-gear"),
    ("Kata Sandi", "account.password", "profil", "key"),
])

MENUS = {
    "pelanggan": [
        ("Utama", [
            ("Dashboard", "customer.dashboard", "dashboard", "speedometer2"),
            ("Profil Saya", "account.profile", "profil", "person-gear"),
        ]),
        ("Pesanan", [
            ("Buat Pesanan", "customer.new_order", "pesanan_baru", "cart-plus"),
            ("Pesanan Saya", "customer.orders", "pesanan", "bag"),
            ("Lacak Pesanan", "customer.track", "lacak", "geo-alt"),
            ("Ringkasan Pembelian", "customer.summary", "pesanan", "clipboard-data"),
        ]),
        ("Layanan", [
            ("Komplain", "customer.complaints", "komplain", "chat-left-text"),
            ("Notifikasi", "customer.notifications", "notifikasi", "bell"),
        ]),
    ],
    "staff_admin": [
        ("Utama", [
            ("Dashboard", "staff.dashboard", "dashboard", "speedometer2"),
        ]),
        ("Operasional", [
            ("Data Pelanggan", "staff.customers", "pelanggan", "people"),
            ("Pesanan Baru", "staff.new_order", "pesanan_baru", "cart-plus"),
            ("Konfirmasi Order", "staff.confirm_orders", "konfirmasi_order", "check2-circle"),
            ("Data Pesanan", "staff.orders", "pesanan", "bag-check"),
            ("Notifikasi Order", "staff.notifications", "notifikasi", "bell"),
        ]),
        ("Produk & Stok", [
            ("Data Produk", "staff.products", "produk", "flower2"),
            ("Stok", "staff.stock", "stok", "box-seam"),
        ]),
        ("Layanan", [
            ("Data Komplain", "staff.complaints", "komplain", "chat-left-text"),
            ("Laporan", "staff.reports", "laporan", "graph-up"),
        ]),
        MONITORING_MENU,
        AKUN_MENU,
    ],
    "staff_kantor": [
        ("Utama", [
            ("Dashboard", "staff.dashboard", "dashboard", "speedometer2"),
        ]),
        ("Kantor", [
            ("Data Pelanggan", "staff.customers", "pelanggan", "people"),
            ("Data Pesanan", "staff.orders", "pesanan", "bag-check"),
            ("Data Produk", "staff.products", "produk", "flower2"),
            ("Stok Masuk/Keluar", "staff.stock", "stok", "box-seam"),
        ]),
        ("Layanan", [
            ("Data Komplain", "staff.complaints", "komplain", "chat-left-text"),
            ("CMS Beranda", "admin.cms", "cms", "layout-text-window"),
            ("Notifikasi", "staff.notifications", "notifikasi", "bell"),
            ("Laporan", "staff.reports", "laporan", "graph-up"),
        ]),
        MONITORING_MENU,
        AKUN_MENU,
    ],
    "staff_gudang": [
        ("Utama", [
            ("Dashboard", "staff.dashboard", "dashboard", "speedometer2"),
        ]),
        ("Gudang", [
            ("Daftar Pesanan", "staff.orders", "pesanan", "bag-check"),
            ("Data Produk", "staff.products", "produk", "flower2"),
            ("Stok Masuk/Keluar", "staff.stock", "stok", "box-seam"),
            ("Notifikasi Order", "staff.notifications", "notifikasi", "bell"),
        ]),
        MONITORING_MENU,
        AKUN_MENU,
    ],
    "staff_qc": [
        ("Utama", [
            ("Dashboard", "qc.dashboard", "dashboard", "speedometer2"),
        ]),
        ("Quality Kontrol", [
            ("Daftar Order", "qc.orders", "qc_verifikasi", "clipboard-check"),
            ("Ganti Produk", "qc.replace_product", "ganti_produk", "arrow-left-right"),
            ("Komplain", "qc.complaints", "komplain", "chat-left-text"),
            ("Status Pengiriman", "qc.shipments", "pengiriman", "truck"),
            ("Notifikasi", "qc.notifications", "notifikasi", "bell"),
        ]),
        MONITORING_MENU,
        AKUN_MENU,
    ],
    "staff_keuangan": [
        ("Utama", [
            ("Dashboard", "finance.dashboard", "dashboard", "speedometer2"),
        ]),
        ("Keuangan", [
            ("Checklist QC", "finance.qc_list", "qc_list", "clipboard-check"),
            ("Pesanan Manual", "finance.new_order", "pesanan_baru", "cart-plus"),
            ("Konfirmasi Order", "staff.confirm_orders", "konfirmasi_order", "check2-circle"),
            ("Data Pesanan", "staff.orders", "pesanan", "bag-check"),
            ("Faktur / Tagihan", "finance.invoices", "faktur", "receipt"),
            ("Verifikasi Pembayaran", "finance.payments", "pembayaran", "credit-card"),
            ("Keluhan Pelanggan", "finance.complaints", "keluhan", "chat-left-text"),
            ("Stok Masuk/Keluar", "finance.stock", "stok", "box-seam"),
            ("Laporan Keuangan", "finance.reports", "laporan", "graph-up"),
        ]),
        ("Master Data", [
            ("Data Produk", "finance.products", "produk", "flower2"),
            ("Rekening Bank", "finance.rekening", "rekening", "bank"),
        ]),
        MONITORING_MENU,
        AKUN_MENU,
    ],
    "administrator": [
        ("Utama", [
            ("Dashboard", "admin.dashboard", "dashboard", "speedometer2"),
            ("Panel Staff", "staff.dashboard", "pesanan", "grid"),
            ("Panel Keuangan", "finance.dashboard", "faktur", "cash-stack"),
            ("Panel QC", "qc.dashboard", "qc_verifikasi", "clipboard-check"),
        ]),
        ("Website", [
            ("CMS Beranda", "admin.cms", "cms", "layout-text-window"),
            ("Pengaturan Situs", "admin.settings", "pengaturan", "gear"),
            ("Kolom Katalog", "admin.katalog", "katalog_seksi", "layout-three-columns"),
            ("Menu Halaman Depan", "admin.menu_publik", "menu_publik", "menu-app"),
            ("Data Pelanggan", "staff.customers", "pelanggan", "people"),
        ]),
        ("Konfigurasi", [
            ("Metode Pengiriman", "admin.pengiriman", "pengiriman_metode", "truck"),
            ("Jam Operasional", "admin.jam_operasional", "jam_operasional", "clock-history"),
        ]),
        ("Master Data", [
            ("Data Produk", "staff.products", "produk", "flower2"),
            ("Stok Masuk/Keluar", "staff.stock", "stok", "box-seam"),
            ("Data Pesanan", "staff.orders", "pesanan", "bag-check"),
            ("Konfirmasi Order", "staff.confirm_orders", "konfirmasi_order", "check2-circle"),
            ("Data Komplain", "staff.complaints", "komplain", "chat-left-text"),
            ("Faktur", "finance.invoices", "faktur", "receipt"),
            ("Ubah Format Nomor", "admin.nomor_format", "format_nomor", "123"),
            ("Ganti Template Invoice", "admin.invoice_template", "template_invoice", "file-earmark-richtext"),
            ("Rekening Bank Faktur", "admin.rekening", "rekening", "bank"),

            ("Verifikasi Pembayaran", "finance.payments", "pembayaran", "credit-card"),
            ("Laporan Keuangan", "finance.reports", "laporan", "graph-up"),
            ("Checklist QC", "finance.qc_list", "qc_list", "clipboard-check"),
            ("Status Pengiriman", "qc.shipments", "pengiriman", "truck"),
        ]),
        ("Administrasi", [
            ("Akun Staff", "admin.accounts", "akun_staff", "person-badge"),
            ("Hak Akses", "admin.permissions", "hak_akses", "shield-lock"),
            ("Backup Data", "admin.backup", "backup", "database-down"),
            ("Pembaruan Aplikasi", "admin.update", "update", "cloud-arrow-down"),
            ("Reset Pengaturan", "admin.reset", "reset", "arrow-counterclockwise"),
            ("Notifikasi", "admin.notifications", "notifikasi", "bell"),
        ]),
        MONITORING_MENU,
        AKUN_MENU,
    ],
}
