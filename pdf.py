"""Pembuat berkas PDF ringan tanpa pustaka tambahan (dipakai untuk ekspor faktur)."""
import struct
import zlib

A4 = (595.28, 841.89)
MARGIN = 48.0

# Lebar karakter font Helvetica standar (per 1000 unit em) untuk ASCII 32-126.
_HELV = {
    " ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667, "'": 191,
    "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333, ".": 278, "/": 278,
    "0": 556, "1": 556, "2": 556, "3": 556, "4": 556, "5": 556, "6": 556, "7": 556,
    "8": 556, "9": 556, ":": 278, ";": 278, "<": 584, "=": 584, ">": 584, "?": 556,
    "@": 1015, "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 500, "K": 667, "L": 556, "M": 833, "N": 722, "O": 778,
    "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722, "V": 667, "W": 944,
    "X": 667, "Y": 667, "Z": 611, "[": 278, "\\": 278, "]": 278, "^": 469, "_": 556,
    "`": 333, "a": 556, "b": 556, "c": 500, "d": 556, "e": 556, "f": 278, "g": 556,
    "h": 556, "i": 222, "j": 222, "k": 500, "l": 222, "m": 833, "n": 556, "o": 556,
    "p": 556, "q": 556, "r": 333, "s": 500, "t": 278, "u": 556, "v": 500, "w": 722,
    "x": 500, "y": 500, "z": 500, "{": 334, "|": 260, "}": 334, "~": 584,
}


def _lebar_char(ch, bold=False):
    dasar = _HELV.get(ch, 556)
    # Helvetica-Bold sedikit lebih lebar; dilebihkan agar perataan kanan tidak meluber.
    return dasar * 1.08 if bold else dasar


def text_width(s, size=10, bold=False):
    return sum(_lebar_char(c, bold) for c in str(s)) * size / 1000.0


def _esc(s):
    return (str(s).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            .replace("\r", " ").replace("\n", " "))


def potong(s, max_w, size=10, bold=False):
    """Potong teks agar muat selebar max_w, tambahkan elipsis bila terpotong."""
    s = str(s)
    if text_width(s, size, bold) <= max_w:
        return s
    keluar = ""
    for c in s:
        if text_width(keluar + c + "...", size, bold) > max_w:
            break
        keluar += c
    return keluar + "..."


def _png_rgb(data):
    """Urai PNG 8-bit menjadi (lebar, tinggi, byte RGB). None bila tidak didukung."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, lebar, tinggi, kedalaman, tipe = 8, 0, 0, 0, 0
    interlace = 0
    idat = bytearray()
    palet = b""
    while pos + 8 <= len(data):
        panjang = struct.unpack(">I", data[pos:pos + 4])[0]
        jenis = data[pos + 4:pos + 8]
        isi = data[pos + 8:pos + 8 + panjang]
        pos += 12 + panjang
        if jenis == b"IHDR":
            lebar, tinggi, kedalaman, tipe = struct.unpack(">IIBB", isi[:10])
            interlace = isi[12] if len(isi) > 12 else 0
        elif jenis == b"PLTE":
            palet = isi
        elif jenis == b"IDAT":
            idat += isi
        elif jenis == b"IEND":
            break
    if kedalaman != 8 or tipe not in (0, 2, 3, 4, 6) or interlace:
        return None
    kanal = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[tipe]
    try:
        mentah = zlib.decompress(bytes(idat))
    except zlib.error:
        return None
    langkah = lebar * kanal
    if len(mentah) < (langkah + 1) * tinggi:
        return None
    hasil = bytearray()
    sebelum = bytearray(langkah)
    for baris in range(tinggi):
        awal = baris * (langkah + 1)
        jenis_filter = mentah[awal]
        kini = bytearray(mentah[awal + 1:awal + 1 + langkah])
        for i in range(langkah):
            kiri = kini[i - kanal] if i >= kanal else 0
            atas = sebelum[i]
            kiri_atas = sebelum[i - kanal] if i >= kanal else 0
            if jenis_filter == 1:
                kini[i] = (kini[i] + kiri) & 0xFF
            elif jenis_filter == 2:
                kini[i] = (kini[i] + atas) & 0xFF
            elif jenis_filter == 3:
                kini[i] = (kini[i] + ((kiri + atas) >> 1)) & 0xFF
            elif jenis_filter == 4:
                p = kiri + atas - kiri_atas
                pa, pb, pc = abs(p - kiri), abs(p - atas), abs(p - kiri_atas)
                pred = kiri if (pa <= pb and pa <= pc) else (atas if pb <= pc else kiri_atas)
                kini[i] = (kini[i] + pred) & 0xFF
        sebelum = kini
        for x in range(lebar):
            px = kini[x * kanal:(x + 1) * kanal]
            if tipe == 0:
                hasil += bytes((px[0], px[0], px[0]))
            elif tipe == 2:
                hasil += px
            elif tipe == 3:
                idx = px[0] * 3
                hasil += palet[idx:idx + 3] if idx + 3 <= len(palet) else b"\x00\x00\x00"
            elif tipe == 4:
                # Abu + alpha: campur ke latar putih agar transparansi tidak jadi hitam.
                a = px[1]
                v = (px[0] * a + 255 * (255 - a)) // 255
                hasil += bytes((v, v, v))
            else:
                # RGB + alpha: campur ke latar putih.
                a = px[3]
                hasil += bytes((px[c] * a + 255 * (255 - a)) // 255 for c in range(3))
    return lebar, tinggi, bytes(hasil)


def _jpeg_info(data):
    """Ambil (lebar, tinggi, jumlah komponen) dari JPEG. None bila bukan JPEG baseline."""
    if data[:2] != b"\xff\xd8":
        return None
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            pos += 1
            continue
        penanda = data[pos + 1]
        if penanda in (0xD8, 0xD9) or 0xD0 <= penanda <= 0xD7:
            pos += 2
            continue
        panjang = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        # SOF0/SOF1/SOF2 = baseline, extended, dan progresif — semuanya didukung DCTDecode.
        if penanda in (0xC0, 0xC1, 0xC2):
            tinggi, lebar = struct.unpack(">HH", data[pos + 5:pos + 9])
            komponen = data[pos + 9]
            return lebar, tinggi, komponen
        pos += 2 + panjang
    return None


def load_image(path):
    """Baca berkas gambar menjadi data siap tempel di PDF. None bila gagal."""
    try:
        with open(path, "rb") as berkas:
            data = berkas.read()
    except OSError:
        return None
    if data[:2] == b"\xff\xd8":
        info = _jpeg_info(data)
        if info is None:
            return None
        lebar, tinggi, komponen = info
        # CMYK JPEG butuh /Decode terbalik; lebih aman ditolak daripada salah warna.
        ruang = {1: "/DeviceGray", 3: "/DeviceRGB"}.get(komponen)
        if ruang is None:
            return None
        return {"w": lebar, "h": tinggi, "ruang": ruang, "data": data, "filter": "/DCTDecode"}
    png = _png_rgb(data)
    if png is None:
        return None
    lebar, tinggi, rgb = png
    return {"w": lebar, "h": tinggi, "ruang": "/DeviceRGB",
            "data": zlib.compress(rgb, 6), "filter": "/FlateDecode"}


def wrap(s, max_w, size=10, bold=False, maks_baris=3):
    """Bungkus teks menjadi beberapa baris sesuai lebar kolom."""
    baris, kini = [], ""
    for kata in str(s).split():
        uji = (kini + " " + kata).strip()
        if kini and text_width(uji, size, bold) > max_w:
            baris.append(kini)
            kini = kata
        else:
            kini = uji
    if kini:
        baris.append(kini)
    if len(baris) > maks_baris:
        baris = baris[:maks_baris]
        baris[-1] = potong(baris[-1], max_w, size, bold)
    return baris or [""]


class Canvas:
    """Kanvas PDF sederhana. Koordinat y dihitung dari atas halaman."""

    def __init__(self, ukuran=A4):
        self.w, self.h = ukuran
        self.halaman = []
        self.ops = []
        self.gambar_aset = []
        self.new_page()

    def new_page(self):
        self.ops = []
        self.halaman.append(self.ops)

    def _y(self, y):
        return self.h - y

    def text(self, x, y, s, size=10, bold=False, align="left", abu=0.0):
        s = str(s)
        if align == "right":
            x = x - text_width(s, size, bold)
        elif align == "center":
            x = x - text_width(s, size, bold) / 2.0
        self.ops.append("%.3f g BT %s %.2f Tf 1 0 0 1 %.2f %.2f Tm (%s) Tj ET"
                        % (abu, "/F2" if bold else "/F1", size, x, self._y(y), _esc(s)))

    def garis(self, x1, y1, x2, y2, lebar=0.6, abu=0.65):
        self.ops.append("%.3f G %.2f w %.2f %.2f m %.2f %.2f l S"
                        % (abu, lebar, x1, self._y(y1), x2, self._y(y2)))

    def kotak(self, x, y, w, h, isi=None, garis=None, lebar=0.6):
        """y adalah sisi atas kotak."""
        bawah = self._y(y + h)
        if isi is not None:
            self.ops.append("%.3f %.3f %.3f rg %.2f %.2f %.2f %.2f re f"
                            % (isi[0], isi[1], isi[2], x, bawah, w, h))
        if garis is not None:
            self.ops.append("%.3f %.3f %.3f RG %.2f w %.2f %.2f %.2f %.2f re S"
                            % (garis[0], garis[1], garis[2], lebar, x, bawah, w, h))

    def gambar(self, x, y, w, h, aset):
        """Tempel gambar (hasil load_image) pada kotak x,y selebar w setinggi h."""
        if aset not in self.gambar_aset:
            self.gambar_aset.append(aset)
        nama = "/Im%d" % (self.gambar_aset.index(aset) + 1)
        self.ops.append("q %.2f 0 0 %.2f %.2f %.2f cm %s Do Q"
                        % (w, h, x, self._y(y + h), nama))

    def output(self):
        jumlah = len(self.halaman)
        # Objek 1-4 tetap; gambar menyusul; lalu pasangan halaman+isi.
        awal_halaman = 5 + len(self.gambar_aset)
        kids = " ".join("%d 0 R" % (awal_halaman + 2 * i) for i in range(jumlah))
        objs = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            ("<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, jumlah)).encode("latin-1"),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        ]
        for aset in self.gambar_aset:
            objs.append(
                ("<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s"
                 " /BitsPerComponent 8 /Filter %s /Length %d >>\nstream\n"
                 % (aset["w"], aset["h"], aset["ruang"], aset["filter"], len(aset["data"])
                    )).encode("latin-1") + aset["data"] + b"\nendstream")
        xobj = " ".join("/Im%d %d 0 R" % (i + 1, 5 + i) for i in range(len(self.gambar_aset)))
        for i, ops in enumerate(self.halaman):
            isi = "\n".join(ops).encode("latin-1", "replace")
            objs.append(
                ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f]"
                 " /Resources << /Font << /F1 3 0 R /F2 4 0 R >>"
                 " /XObject << %s >> >> /Contents %d 0 R >>"
                 % (self.w, self.h, xobj, awal_halaman + 2 * i + 1)).encode("latin-1"))
            objs.append(b"<< /Length %d >>\nstream\n" % len(isi) + isi + b"\nendstream")

        keluar = bytearray(b"%PDF-1.4\n")
        offset = []
        for i, badan in enumerate(objs):
            offset.append(len(keluar))
            keluar += b"%d 0 obj\n" % (i + 1) + badan + b"\nendobj\n"
        xref = len(keluar)
        n = len(objs) + 1
        keluar += b"xref\n0 %d\n" % n + b"0000000000 65535 f \n"
        for off in offset:
            keluar += b"%010d 00000 n \n" % off
        keluar += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (n, xref)
        return bytes(keluar)
