# Tahapan karakter dan animasi

## Pengerjaan aktif: ekspresi, tema, dan interaksi

1. Olah referensi pengguna tanpa menimpa gambar sumber. Siapkan enam ekspresi
   dengan jangkar wajah yang konsisten serta frame mata tertutup untuk kedipan.
2. Tambahkan pilihan karakter dan persona: Frieren, Beatrice, Waguri Kaoruko.
3. Animasikan kedipan, mulut saat berbicara, napas, dan goyangan kecil. Gunakan
   satu karakter aktif dan cache terbatas; hentikan timer ketika tersembunyi.
4. Terapkan tema putih/abu-abu Frieren, emas Beatrice, ungu Waguri ke input,
   bubble, panel chat, popup model, dan menu klik kanan yang memiliki header avatar.
5. Buat ukuran panel chat dapat diubah pengguna dengan size grip dan simpan
   ukuran terakhir. Periksa ukuran ringkas maupun lebar agar kontrol tetap terbaca.
6. Verifikasi render ekspresi/tema, pergantian karakter berulang, cache, serta tes
   AI/chat yang sudah ada sebelum meluncurkan aplikasi.

### Voice

- Folder: `assets/voices/frieren`, `assets/voices/beatrice`,
  `assets/voices/waguri_kaoruko`. Panduan nama sample ada di folder induknya.
- Klip dipilih berdasarkan konteks: sapaan, berpikir, penjelasan, sukses, gagal,
  pembatalan. Status sukses/gagal harus mengikuti hasil nyata backend.
- Playback harus dapat dinonaktifkan, tidak menumpuk, dan tidak memuat semua audio
  ke RAM. Sample yang belum tersedia tidak diputar.
- Narasi seluruh jawaban dinamis memerlukan engine text-to-speech terpisah;
  kumpulan sample bukan pengganti engine tersebut.

### Tahap lanjutan

Versi pixel dan gerakan berpindah/berjalan pada desktop memerlukan aset/frame
khusus. Keduanya dilanjutkan setelah ekspresi 2D, animasi wajah, dan tema stabil.

## 1. Frieren: fondasi ringan (sudah diterapkan, perlu penilaian visual pengguna)

- Menggunakan 22 PNG yang sudah ada, tanpa mengubah gambar sumber.
- Napas halus dengan tubuh bawah sebagai jangkar, goyangan kecil sesuai pose.
- Pose membaca, minum, dan memakai laptop lebih stabil daripada pose berbicara.
- Transisi dengan easing dan satu buffer untuk pergantian pose yang terinterupsi.
- Jeda idle bervariasi 24–48 detik, lebih sering memakai pose tenang.
- Membatasi perubahan pose berpikir; sapaan saat AI bekerja tidak menimpa statusnya.
- Pilihan Gerakan Karakter di menu klik kanan/tray: Natural, Hemat, Nonaktif.
- Maksimal enam gambar berukuran tampilan di cache; tidak menyimpan seluruh gambar
  resolusi asli di RAM. Timer gerakan berhenti saat karakter tersembunyi/mini.

Ini adalah animasi gambar utuh. Kedipan, gerak mulut, rambut, tangan, atau properti
yang independen belum tersedia dan memerlukan frame/lapisan gambar tambahan.
Cross-fade juga belum menggantikan frame perantara untuk perubahan tangan besar.

## 2. Penyesuaian artwork Frieren

1. Nilai tampilan idle → thinking → talking → pleased → idle pada ukuran nyata.
2. Samakan posisi mata, proporsi kepala, potongan tubuh, dan jangkar bawah antarpose.
3. Siapkan frame perantara untuk mengambil/meletakkan teh, membuka buku, dan melambai.
4. Tambahkan mata terbuka/setengah/tertutup dan mulut netral/berbicara bila tersedia.
5. Pisahkan kepala, rambut, tubuh, serta properti jika perlu gerakan independen.
6. Kalibrasi setiap pose; hindari memaksa gambar utuh menyerupai rig berlapis.

## 3. Referensi dari pengguna

Taruh referensi di subfolder berikut agar tidak tertukar dengan PNG aktif:

```text
assets/sprites/references/
  frieren/
  beatrice/
  waguri_kaoruko/
```

Nama yang disarankan: `front.png`, `thinking.png`, `smile.png`, `outfit.png`.
PNG/JPG/WebP boleh digunakan sebagai referensi. Pilih gambar wajah jelas, kostum
konsisten, dan tubuh/tangan tidak terpotong jika bagian tersebut perlu dianimasikan.
Referensi tidak otomatis menjadi sprite siap animasi: perlu pemilihan, pemisahan
latar/lapisan, penyelarasan pose, dan pengecekan hasil.
Jangan menimpa `assets/sprites/idle.png` dan PNG aktif lainnya dengan foto referensi.

## 4. Tiga karakter dan dua gaya

- Bangun profil karakter terpisah: Frieren, Beatrice (Umineko), Waguri Kaoruko.
- Masing-masing memiliki gaya 2D dan pixel, pilihan terakhir tersimpan.
- Awali dengan delapan pose inti: idle, berpikir, analisis, bekerja, berbicara,
  berhasil, kendala, istirahat. Tambah variasi setelah pose inti konsisten.
- Frieren tenang; Beatrice elegan/teatrikal; Waguri lembut/ramah.
- Aset pixel digambar dan dianimasikan khusus; gunakan nearest-neighbor.
- Hanya karakter/gaya aktif yang dimuat. Jangan memuat enam paket sekaligus.

## 5. Verifikasi sumber daya dan interaksi

- Ukur baseline RAM aplikasi, kemudian idle, animasi, resize, hide, dan pergantian
  pose berulang. Ukur proses Codex/AGY secara terpisah.
- Batas cache gambar adalah batas tekstur, bukan jaminan total RAM proses Qt.
- Periksa klik pada karakter selama gerakan/transisi, fokus input, menu, serta tray.
- Evaluasi naturalitas langsung pada desktop; tes otomatis tidak menilai estetika.

## Perkembangan prioritas aplikasi

1. Diterapkan: timeout selama proses, stdout/stderr bersamaan, pembatalan dan cleanup proses.
2. Diterapkan: katalog Codex/AGY dari CLI dan model aktif tersimpan.
3. Diterapkan: folder proyek, proyek terakhir, serta riwayat/fakta per proyek.
4. Sistem karakter/gaya dan penyempurnaan animasi di atas.
5. Diterapkan: input multiline, panel chat besar, output/salin, thumbnail, serta memori relevan.

Penyempurnaan artwork, tiga karakter, dan gaya pixel tetap mengikuti tahapan aset
di atas. Panduan aplikasi terbaru tersedia di README.md.
