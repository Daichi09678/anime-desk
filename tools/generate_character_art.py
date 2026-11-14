"""Run the user-authorized AGY image-generator job without touching app code."""

import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from ai_providers import run_agy
from cli_process import resolve_binary

STATUS = ROOT / "data/art_generation_status.json"


def report(message):
    STATUS.parent.mkdir(parents=True,exist_ok=True)
    temporary = STATUS.with_suffix(".tmp")
    temporary.write_text(json.dumps({"message":message,"updated":time.time()},ensure_ascii=False,indent=2),encoding="utf-8")
    temporary.replace(STATUS)
    print(message,flush=True)


def main():
    folder = ROOT / "assets/generated/production"
    refs = ROOT / "assets/sprites/references"
    prompt = f"""Pengguna secara eksplisit mengizinkan AGY CLI memakai subagent image-generator
untuk membuat ILUSTRASI BARU. Subagent sistem tersebut dideskripsikan:
Generates or edits images from a brief and replies with the saved file paths.
Panggil invoke_subagent(TypeName='image-generator', Role=..., Prompt=...) untuk
pekerjaan gambar. Jangan mengganti ini dengan crop referensi, Pillow face edits,
SVG karakter, pencarian web, atau hanya menulis prompt. Pengguna menolak crop/edit
potret sebelumnya dan meminta paket pose baru seperti sprite Frieren.

BATAS WORKSPACE: hanya tulis gambar/laporan dalam {folder}. Jangan ubah kode,
config, memory, audio, referensi, atau file lain. Gambar sementara dari generator
boleh berada di artifact generator; salin hasil final ke folder target. Jika
image-generator gagal/tidak tersedia, laporkan kegagalan jujur dan hentikan;
jangan mengklaim sukses atau membuat gambar palsu melalui script.

REFERENSI KANONIK KARAKTER:
Beatrice: {refs / 'beatrice/image.png'} — updo rambut pirang, mata biru, gaun
coklat-marun dengan ornamen emas, bow merah muda, pipe/staff. Ikuti outfit ini.
Waguri Kaoruko: {refs / 'waguri/image.png'} — rambut hitam panjang bergelombang,
mata biru, seragam sailor pink dusty, kerah putih, pita gelap, rok pink.
Gaya ilustrasi target: kualitas anime 2D bersih seperti {ROOT / 'assets/sprites/idle.png'}.

BUAT DUA SPRITE SHEET PNG BARU:
1. beatrice_poses.png
2. waguri_poses.png
Tiap sheet tepat 3 kolom × 4 baris, sel sama besar, target 1536×2048 atau lebih,
tanpa teks/nomor/garis grid. Satu karakter yang sama pada semua sel, kamera dan
proporsi konsisten, tubuh duduk/bust sampai paha, baseline bawah dan pusat kepala
konsisten, ruang aman 8% tiap sisi. Latar flat neon magenta #ff00ff untuk chroma
key (bukan checkerboard). Jangan pakai magenta pada karakter; pink kostum tetap
dusty/desaturated sesuai referensi. Render tiap sel utuh tanpa memotong tangan.
Urutan sel dari kiri ke kanan, atas ke bawah:
idle tenang; membaca buku; berpikir tangan di dagu;
menjelaskan telapak terbuka; berbicara (mulut terbuka, tubuh sama dengan idle);
senang/lambaian kecil; terkejut; memegang cangkir teh; bekerja dengan buku/laptop;
gestur khas percaya diri; peregangan lembut; mengantuk/mata tertutup.
Beatrice: elegan, teatrikal secukupnya, senyum percaya diri. Waguri: lembut,
hangat, sopan, senyum natural. Bukan chibi, bukan pixel, bukan montage foto.

BUAT TIGA LATAR UI TANPA TULISAN/KARAKTER/LOGO:
frieren_scene.png berdasarkan atmosfer/layout {refs / 'frieren/image.png'}:
reruntuhan batu, padang bunga putih/biru, langit dan kastil, parchment ivory,
sentuhan emas tipis, tepi daun. Area tengah lapang dan terang untuk kontrol.
beatrice_scene.png berdasarkan {refs / 'beatrice/image copy.png'}:
perpustakaan gothic hangat, coklat gelap, marun, emas tua, grimoire/teh di bawah,
kupu-kupu emas halus, area tengah gelap bersih untuk kontrol.
waguri_scene.png berdasarkan {refs / 'waguri/image copy.png'}:
ruang baca senja ungu dengan sakura di jendela, buku/cangkir di bawah,
area tengah gelap bersih, aksen lavender. Target tiap scene 1024×1024.
Jangan menyalin teks UI atau karakter yang tertanam di contoh. Frame dan kontrol
interaktif digambar oleh aplikasi, sehingga latar harus bersih dari tulisan.

Jika bisa, jalankan generasi karakter/scene independen secara paralel dengan
subagent image-generator yang sama tipenya. Setelah output ada, verifikasi nama
file, dimensi, dan keberadaan file (tanpa mengubah gambar referensi). Simpan
generation_report.json berisi path output aktual, dimensi, dan kendala nyata.
Laporkan hasil, jangan meminta persetujuan lagi karena pengguna sudah memberi izin.
"""
    images = [refs / "beatrice/image.png", refs / "waguri/image.png",
              refs / "beatrice/image copy.png", refs / "waguri/image copy.png", refs / "frieren/image.png"]
    started = time.monotonic()
    report("AGY image job started")
    reply = run_agy(resolve_binary("agy","agy"),"gemini-3.8-flash-low","low",prompt,
                    [str(p) for p in images],ROOT,True,1800,threading.Event(),
                    lambda s:report(f"[{round(time.monotonic()-started)}s] {s}"),lambda s:None)
    report(reply.text)
    (folder / "agent_report.txt").write_text(reply.text+"\n\n"+reply.log,encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        report(f"Image generation failed: {type(exc).__name__}: {exc}")
        raise
