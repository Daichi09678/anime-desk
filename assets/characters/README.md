# Paket ekspresi 2D awal

Karakter yang tersedia: Frieren, Beatrice, Waguri Kaoruko. Pilih karakter dari
panel chat atau menu klik kanan; tema dan persona mengikuti pilihan tersebut.

Beatrice dan Waguri masing-masing memiliki enam ekspresi pada
`<karakter>/expressions/`: netral, senang, berbicara, berpikir, terkejut, dan mata
tertutup. Setiap ekspresi mempunyai frame kedipan. Seluruh varian satu karakter
memakai crop, ukuran, dan alpha yang sama agar tubuh tidak meloncat saat wajah
berubah. Frieren memakai sprite yang sudah ada serta frame kedipan tambahan.

`expressions_preview.png` menampilkan kedua paket; `<karakter>/preview.png`
menampilkan satu karakter. Gambar baru adalah potret olahan referensi dengan
edit wajah lokal, bukan kumpulan pose tubuh penuh baru. Referensi Waguri berasal
dari kolase beresolusi kecil; ketajaman detail mengikuti kualitas sumber tersebut.

Untuk membangun ulang dari referensi yang saat ini tersedia:

```bash
python tools/build_character_expressions.py --build
```

Koordinat penyuntingan dalam skrip dikalibrasi untuk referensi saat ini. Jika
referensi diganti, koordinat perlu diselaraskan lagi. Skrip memverifikasi hash
gambar sumber setelah proses dan tidak menimpa berkas referensi.

Animasi runtime memakai kedipan berinterval bervariasi, gerak mulut berbasis
frame, napas, goyangan ringan, dan reaksi klik. Sprite dimuat hanya untuk karakter
aktif dengan cache terbatas. Rencana pixel/gerak berjalan ada di CHARACTER_PLAN.md.
