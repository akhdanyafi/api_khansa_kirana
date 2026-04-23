# Implementasi Backend

Tanggal implementasi: 23 April 2026

## File yang diubah

- `backend/app/main.py`
- `backend/API_DOCS.md`

## Ringkasan perubahan

### 1. Fallback katalog di level API

Endpoint yang terdampak:

- `GET /catalog/islands`
- `GET /catalog/provinces`
- `GET /catalog/provinces/names`

Perubahan:

- Backend sekarang menormalkan key pulau agar konsisten, termasuk mapping lama seperti `bali_nusa -> bali_nt`, `papua -> maluku_papua`, dan `java -> jawa`.
- Jika tabel `catalog_provinces` kosong atau belum lengkap, backend akan membentuk fallback provinsi dari tabel `products` yang aktif.
- Jika tabel `island_groups` kosong atau key lama masih tersimpan, backend akan membentuk fallback pulau dari data provinsi/produk aktif.
- Saat admin membuat provinsi katalog baru, `island_key` akan dinormalisasi sebelum disimpan.

Tujuan:

- Filter provinsi di halaman katalog tetap terisi walaupun data master katalog belum lengkap.
- Klik pulau/provinsi di frontend tidak lagi bergantung penuh pada isi tabel katalog manual.

### 2. Sinkronisasi `hero_images`

Endpoint yang terdampak:

- `GET /store-profile`
- `PUT /store-profile/{profile_id}`
- `PUT /content/{content_key}`
- `POST /content`

Perubahan:

- `GET /store-profile` sekarang akan fallback ke `site_content.hero_images` jika kolom `store_profile.hero_images` kosong.
- `PUT /store-profile/{profile_id}` sekarang akan otomatis meng-upsert `site_content.hero_images` ketika field `hero_images` dikirim.
- `PUT /content/hero_images` dan `POST /content` dengan key `hero_images` sekarang akan menyinkronkan nilai yang sama ke `store_profile.hero_images`.

Tujuan:

- Upload banner hero dari admin tetap tersimpan walaupun deployment frontend/backend campur antara kontrak lama dan baru.
- Tampilan hero di landing page tetap konsisten walaupun sumber data sebelumnya masih split antara `store_profile` dan `site_content`.

## SQL / data tambahan

### Tidak ada SQL wajib untuk bugfix ini

Bugfix utama sudah ditutup di level kode backend, jadi katalog tetap bisa berjalan walaupun tabel master katalog kosong dan hero banner tetap bisa sinkron tanpa migrasi tambahan.

### SQL opsional yang disarankan

Kalau ingin metadata katalog lebih rapi dan lengkap di admin/server production, jalankan seed yang sudah ada di repo:

- `database/mysql/seed_all_backend_tables.sql`

File tersebut sudah mengisi:

- `island_groups`
- `catalog_provinces`
- row default `store_profile`

### SQL opsional untuk memastikan row `hero_images` ada

Jalankan hanya jika tabel `site_content` sudah ada tetapi key `hero_images` belum ada.

```sql
INSERT INTO site_content (
  id,
  `key`,
  section,
  content_type,
  value,
  description,
  updated_at
) VALUES (
  UUID(),
  'hero_images',
  'hero',
  'text',
  '',
  'URL gambar hero/slideshow beranda',
  UTC_TIMESTAMP()
)
ON DUPLICATE KEY UPDATE
  section = VALUES(section),
  content_type = VALUES(content_type),
  description = VALUES(description),
  updated_at = UTC_TIMESTAMP();
```

## Catatan penting deploy

### 1. Jangan drop `site_content`

Jangan jalankan file berikut di server yang masih memakai endpoint `/content` atau sinkronisasi hero banner:

- `database/mysql/migration_drop_unused_tables.sql`

Alasannya: file itu menghapus tabel `site_content`, padahal tabel tersebut masih dipakai untuk kompatibilitas `hero_images`.

### 2. Langkah deploy backend

Contoh urutan aman:

1. Upload perubahan file backend ke server.
2. Install dependency jika perlu:

   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. Restart service FastAPI / gunicorn / systemd yang dipakai server.
4. Uji endpoint berikut setelah restart:

   - `GET /health`
   - `GET /catalog/islands`
   - `GET /catalog/provinces?is_active=true`
   - `GET /store-profile`

5. Uji dari panel admin:

   - simpan perubahan profile toko
   - upload / ubah banner hero
   - buka halaman katalog dan cek filter provinsi/pulau

## Validasi lokal yang sudah dijalankan

- `python -m py_compile backend/app/main.py`
- editor diagnostics untuk `backend/app/main.py`: bersih