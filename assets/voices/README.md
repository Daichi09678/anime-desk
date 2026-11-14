# Sample voice per karakter

Simpan sample di `frieren/`, `beatrice/`, atau `waguri_kaoruko/`.
WAV disarankan; gunakan rekaman tanpa musik latar jika memungkinkan.

| Nama file | Konteks |
| --- | --- |
| greeting.wav | Sapaan atau karakter dipilih |
| thinking.wav | Permintaan sedang diproses |
| explaining.wav | Penjelasan jawaban |
| success.wav | Permintaan benar-benar selesai dengan status berhasil |
| error.wav | Permintaan gagal atau timeout |
| cancelled.wav | Permintaan dibatalkan |

Untuk kategori yang sama, beberapa variasi dapat memakai akhiran angka, seperti
`explaining_01.wav`, `explaining_02.wav`. Isi kalimat sebaiknya cocok dengan konteks
umum kategori itu; hindari sample yang mengklaim aksi khusus yang belum dilakukan.

Nama konteks di atas digunakan pada mode **Klip rekaman**. Pada mode **Narasi**,
engine **Qwen lokal** membuat audio Jepang baru dari terjemahan jawaban AI.
`clone.json` pada folder karakter menyimpan file sumber, offset, dan durasi
referensi. Pilih rentang 3–15 detik di dialog Voice dan dengarkan kebersihannya.
Referensi diproses lokal sebagai speaker embedding, tanpa melatih ulang model
atau mengubah MP3 asli. Setup model terpisah dijelaskan di README akar proyek.
