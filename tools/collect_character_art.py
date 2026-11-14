"""Collect the five user-authorized AGY image-generator outputs."""

from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ai_providers import run_agy
from cli_process import resolve_binary
from tools.generate_character_art import report


def main():
    target = ROOT / "assets/generated/production"
    prompt = f"""Pengguna mengizinkan AGY/image-generator untuk pekerjaan ini. Lima subagent
image-generator sudah diluncurkan pada giliran sebelumnya. Sekarang lanjutkan
dengan manage_subagents untuk memeriksa dan MENUNGGU hasil setiap id berikut:
Beatrice sprites: 087dd172-3807-406e-9759-ef20c7aeb447
Waguri sprites: 9e63e766-1e07-407c-b41f-eab78641f66b
Frieren scene: aeb980c5-d9ff-496b-b8a6-d81cc99f41d9
Beatrice scene: 83496e03-9afb-494f-bf3b-ade5c09e737f
Waguri scene: 1596249e-4a7b-4fab-aa99-f90de1134dba
Ambil output file path asli generator, lalu salin PNG final ke {target} dengan
nama beatrice_poses.png, waguri_poses.png, frieren_scene.png,
beatrice_scene.png, waguri_scene.png. Boleh memakai run_command/Pillow hanya
untuk MEMERIKSA dimensi dan MENYALIN file output, bukan menggambar/crop/face edits
sebagai pengganti gambar baru. Jangan ubah file referensi, kode, konfigurasi,
audio, atau file lain. Simpan generation_report.json dengan sumber/output dan
dimensi sebenarnya. Jangan berhenti hanya dengan laporan 'sedang diproses';
tunggu sampai hasil tersedia atau laporkan error nyata tiap subagent. Jangan
mengklaim selesai jika file tidak ada. Jika id tidak dapat diakses dari sesi
ini, jelaskan kendalanya secara spesifik dan jangan meluncurkan duplikat dulu.
"""
    report("Collecting image-generator outputs")
    reply = run_agy(resolve_binary("agy","agy"),"gemini-3.8-flash-low","low",prompt,[],ROOT,True,
                    1200,threading.Event(),report,lambda text:None)
    report(reply.text)
    (target / "collection_report.txt").write_text(reply.text+"\n\n"+reply.log,encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        report(f"Image collection failed: {type(exc).__name__}: {exc}")
        raise
