# Khansa Collection API — Dokumentasi

**Base URL:** `https://api.khansakirana.my.id`

> Interactive docs (Swagger UI): `https://api.khansakirana.my.id/docs`  
> ReDoc: `https://api.khansakirana.my.id/redoc`

---

## Autentikasi

Endpoint yang memerlukan autentikasi menggunakan **Bearer Token** (JWT).

Tambahkan header berikut pada setiap request yang membutuhkan auth:

```
Authorization: Bearer <access_token>
```

### Role yang tersedia

| Role | Akses |
|------|-------|
| `super_admin` | Semua endpoint |
| `admin` | Semua kecuali manajemen admin |
| `editor` | Update content saja |

---

## Health Check

### `GET /health`

Cek status server.

**Response:**
```json
{
  "ok": true,
  "name": "Khansa Collection Backend",
  "time": "2024-01-01T00:00:00+00:00"
}
```

---

## Auth

### `POST /auth/login`

Login admin.

**Request Body:**
```json
{
  "email": "admin@example.com",
  "password": "password123"
}
```

**Response:**
```json
{
  "access_token": "<jwt_token>",
  "token_type": "bearer",
  "admin": {
    "id": "uuid",
    "email": "admin@example.com",
    "name": "Admin",
    "role": "admin",
    "is_active": true,
    "last_login_at": "2024-01-01T00:00:00",
    "created_at": "2024-01-01T00:00:00"
  }
}
```

---

### `GET /auth/me` 🔒

Ambil profil admin yang sedang login.

**Response:**
```json
{
  "id": "uuid",
  "email": "admin@example.com",
  "name": "Admin",
  "role": "admin",
  "is_active": true
}
```

---

### `POST /auth/change-password` 🔒

Ganti password sendiri.

**Request Body:**
```json
{
  "new_password": "newpassword123"
}
```

**Response:** `{ "ok": true }`

---

## Admins (Super Admin Only)

### `GET /admins` 🔒 `super_admin`

Daftar semua admin.

**Response:** Array of admin objects.

---

### `POST /admins` 🔒 `super_admin`

Tambah admin baru.

**Request Body:**
```json
{
  "email": "newadmin@example.com",
  "password": "password123",
  "name": "New Admin",
  "role": "admin"
}
```

**Role valid:** `super_admin`, `admin`, `editor`

---

### `PUT /admins/{admin_id}/status` 🔒 `super_admin`

Update status aktif admin.

**Request Body:**
```json
{ "is_active": false }
```

---

### `DELETE /admins/{admin_id}` 🔒 `super_admin`

Hapus admin.

---

## Content (Konten Teks Website)

### `GET /content`

Ambil semua konten. Bisa filter per section.

**Query Params:**
| Param | Type | Deskripsi |
|-------|------|-----------|
| `section` | string | Filter per section (opsional) |

**Response:**
```json
[
  {
    "id": "uuid",
    "key": "hero_title",
    "section": "hero",
    "content_type": "text",
    "value": "Selamat Datang",
    "description": null,
    "updated_at": "2024-01-01T00:00:00"
  }
]
```

---

### `GET /content/{content_key}`

Ambil konten berdasarkan key.

---

### `PUT /content/{content_key}` 🔒 `admin`, `editor`, `super_admin`

Update nilai konten.

**Request Body:**
```json
{ "value": "Nilai baru" }
```

---

### `POST /content` 🔒 `admin`, `super_admin`

Tambah konten baru.

**Request Body:**
```json
{
  "key": "about_text",
  "section": "about",
  "value": "Tentang kami...",
  "content_type": "text",
  "description": "Teks halaman about"
}
```

**content_type:** `text`, `html`, `image`, `url`, dll.

---

### `DELETE /content/{content_key}` 🔒 `admin`, `super_admin`

Hapus konten.

---

## Store Profile

### `GET /store-profile`

Ambil profil toko.

**Response:**
```json
{
  "id": "uuid",
  "store_name": "Khansa Collection",
  "logo_url": "https://...",
  "address": "Jl. ...",
  "gmaps_link": "https://maps.google.com/...",
  "latitude": -6.2,
  "longitude": 106.8,
  "phone": "+62xxx",
  "whatsapp": "+62xxx",
  "instagram_url": "https://instagram.com/...",
  "facebook_url": null,
  "tiktok_url": null,
  "operational_hours": "08.00 - 20.00",
  "created_at": "...",
  "updated_at": "..."
}
```

---

### `PUT /store-profile/{profile_id}` 🔒 `admin`, `super_admin`

Update profil toko. Semua field opsional (hanya field yang dikirim yang diupdate).

**Request Body:**
```json
{
  "store_name": "Khansa Collection",
  "logo_url": "https://...",
  "address": "Jl. Contoh No. 1",
  "gmaps_link": "https://maps.google.com/...",
  "latitude": -6.2,
  "longitude": 106.8,
  "phone": "+62xxx",
  "whatsapp": "+62xxx",
  "instagram_url": "https://instagram.com/...",
  "facebook_url": null,
  "tiktok_url": null,
  "operational_hours": "08.00 - 20.00"
}
```

---

## Products

### `GET /products`

Daftar semua produk.

**Query Params:**
| Param | Type | Default | Deskripsi |
|-------|------|---------|-----------|
| `category` | string | - | Filter kategori |
| `province` | string | - | Filter provinsi |
| `is_available` | bool | - | Filter ketersediaan |
| `order_by` | string | `created_at` | Urut berdasarkan (`created_at`, `updated_at`, `name`, `price`) |
| `ascending` | bool | `false` | Arah urutan |

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "Kebaya Jawa",
    "description": "...",
    "image_url": "https://...",
    "price": 150000,
    "category": "kebaya",
    "province": "Jawa Tengah",
    "traditional_name": "Kebaya Encim",
    "is_available": true,
    "created_at": "...",
    "updated_at": "..."
  }
]
```

---

### `GET /products/{product_id}`

Detail produk berdasarkan ID.

---

### `GET /products/search?q={query}`

Cari produk berdasarkan nama, deskripsi, atau nama tradisional.

**Query Params:**
| Param | Type | Deskripsi |
|-------|------|-----------|
| `q` | string | Kata kunci pencarian (min 1 karakter) |

---

### `GET /products/categories`

Daftar kategori produk yang ada.

**Response:** `["kebaya", "batik", "baju_adat"]`

---

### `GET /products/provinces`

Daftar provinsi produk yang ada.

**Response:** `["Jawa Tengah", "Jawa Barat", "Bali"]`

---

### `POST /products` 🔒 `admin`, `super_admin`

Tambah produk baru.

**Request Body:**
```json
{
  "name": "Kebaya Jawa",
  "description": "Deskripsi produk",
  "image_url": "https://...",
  "price": 150000,
  "category": "kebaya",
  "province": "Jawa Tengah",
  "traditional_name": "Kebaya Encim",
  "is_available": true
}
```

---

### `PUT /products/{product_id}` 🔒 `admin`, `super_admin`

Update produk. Semua field opsional.

---

### `DELETE /products/{product_id}` 🔒 `admin`, `super_admin`

Hapus produk.

---

## Outlets

### `GET /outlets`

Daftar semua outlet.

**Query Params:**
| Param | Type | Deskripsi |
|-------|------|-----------|
| `is_active` | bool | Filter outlet aktif/nonaktif |

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "Outlet Utama",
    "address": "Jl. ...",
    "latitude": -6.2,
    "longitude": 106.8,
    "phone": "+62xxx",
    "whatsapp": "+62xxx",
    "operational_hours": "08.00 - 20.00",
    "is_main": true,
    "is_active": true,
    "created_at": "...",
    "updated_at": "..."
  }
]
```

---

### `GET /outlets/main`

Ambil outlet utama yang aktif.

---

### `GET /outlets/{outlet_id}`

Detail outlet berdasarkan ID.

---

### `POST /outlets` 🔒 `admin`, `super_admin`

Tambah outlet baru.

**Request Body:**
```json
{
  "name": "Outlet Baru",
  "address": "Jl. ...",
  "latitude": -6.2,
  "longitude": 106.8,
  "phone": "+62xxx",
  "whatsapp": "+62xxx",
  "operational_hours": "08.00 - 20.00",
  "is_main": false,
  "is_active": true
}
```

---

### `PUT /outlets/{outlet_id}` 🔒 `admin`, `super_admin`

Update outlet. Semua field opsional.

---

### `PUT /outlets/{outlet_id}/status` 🔒 `admin`, `super_admin`

Toggle status aktif outlet.

**Request Body:** `{ "is_active": false }`

---

### `PUT /outlets/{outlet_id}/set-main` 🔒 `admin`, `super_admin`

Set outlet sebagai outlet utama (outlet main lainnya akan di-unset).

---

### `DELETE /outlets/{outlet_id}` 🔒 `admin`, `super_admin`

Hapus outlet.

---

## Testimonials

### `GET /testimonials`

Daftar testimoni.

**Query Params:**
| Param | Type | Deskripsi |
|-------|------|-----------|
| `is_active` | bool | Filter aktif/nonaktif |

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "Budi Santoso",
    "occasion": "Pernikahan",
    "review": "Pelayanan sangat baik...",
    "rating": 5.0,
    "is_active": true,
    "sort_order": 0,
    "created_at": "...",
    "updated_at": "..."
  }
]
```

---

### `POST /testimonials` 🔒 `admin`, `super_admin`

Tambah testimoni.

**Request Body:**
```json
{
  "name": "Budi Santoso",
  "occasion": "Pernikahan",
  "review": "Pelayanan sangat baik!",
  "rating": 5.0,
  "is_active": true,
  "sort_order": 0
}
```

---

### `PUT /testimonials/{testimonial_id}` 🔒 `admin`, `super_admin`

Update testimoni. Semua field opsional.

---

### `PUT /testimonials/{testimonial_id}/toggle-active` 🔒 `admin`, `super_admin`

Toggle status aktif testimoni.

**Request Body:** `{ "is_active": false }`

---

### `DELETE /testimonials/{testimonial_id}` 🔒 `admin`, `super_admin`

Hapus testimoni.

---

## Gallery

### `GET /gallery`

Daftar item galeri.

**Query Params:**
| Param | Type | Deskripsi |
|-------|------|-----------|
| `is_active` | bool | Filter aktif/nonaktif |

**Response:**
```json
[
  {
    "id": "uuid",
    "title": "Foto Produk",
    "category": "kebaya",
    "image_url": "https://...",
    "cross_axis_cell_count": 2,
    "main_axis_cell_count": 1,
    "is_active": true,
    "sort_order": 0,
    "created_at": "...",
    "updated_at": "..."
  }
]
```

---

### `POST /gallery` 🔒 `admin`, `super_admin`

Tambah item galeri.

**Request Body:**
```json
{
  "title": "Foto Produk",
  "category": "kebaya",
  "image_url": "https://...",
  "cross_axis_cell_count": 2,
  "main_axis_cell_count": 1,
  "is_active": true,
  "sort_order": 0
}
```

---

### `PUT /gallery/{item_id}` 🔒 `admin`, `super_admin`

Update item galeri. Semua field opsional.

---

### `PUT /gallery/{item_id}/toggle-active` 🔒 `admin`, `super_admin`

Toggle status aktif item galeri.

**Request Body:** `{ "is_active": false }`

---

### `DELETE /gallery/{item_id}` 🔒 `admin`, `super_admin`

Hapus item galeri.

---

## Catalog

### `GET /catalog/islands`

Daftar grup pulau.

**Response:**
```json
[
  { "id": "uuid", "key": "jawa", "name": "Jawa", "sort_order": 1 }
]
```

---

### `GET /catalog/provinces`

Daftar provinsi katalog pakaian adat.

**Query Params:**
| Param | Type | Deskripsi |
|-------|------|-----------|
| `is_active` | bool | Filter aktif/nonaktif |

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "Jawa Tengah",
    "island_key": "jawa",
    "costume_name": "Kebaya Jawa",
    "description": "...",
    "image_url": "https://...",
    "price_from": "Rp 125.000",
    "is_active": true,
    "sort_order": 1
  }
]
```

---

### `GET /catalog/provinces/names`

Daftar nama provinsi aktif saja.

**Response:** `["Jawa Tengah", "Jawa Barat", "Bali"]`

---

### `POST /catalog/provinces` 🔒 `admin`, `super_admin`

Tambah provinsi katalog.

**Request Body:**
```json
{
  "name": "Jawa Tengah",
  "island_key": "jawa",
  "costume_name": "Kebaya Jawa",
  "description": "Pakaian adat Jawa Tengah",
  "image_url": "https://...",
  "price_from": "Rp 125.000",
  "is_active": true,
  "sort_order": 1
}
```

---

### `PUT /catalog/provinces/{province_id}` 🔒 `admin`, `super_admin`

Update provinsi katalog. Semua field opsional.

---

### `PUT /catalog/provinces/{province_id}/toggle-active` 🔒 `admin`, `super_admin`

Toggle status aktif provinsi katalog.

**Request Body:** `{ "is_active": false }`

---

### `DELETE /catalog/provinces/{province_id}` 🔒 `admin`, `super_admin`

Hapus provinsi katalog.

---

## Storage (Upload File)

### `POST /storage/upload` 🔒 `admin`, `super_admin`

Upload file gambar.

**Query Params:**
| Param | Type | Deskripsi |
|-------|------|-----------|
| `folder` | string | Nama folder tujuan upload (alfanumerik, `-`, `_`) |

**Request:** `multipart/form-data` dengan field `file`.

**Response:**
```json
{ "url": "/static/products/products_1700000000_abc123.jpg" }
```

File dapat diakses di: `https://api.khansakirana.my.id/static/products/products_1700000000_abc123.jpg`

---

### `DELETE /storage/delete` 🔒 `admin`, `super_admin`

Hapus file yang sudah diupload.

**Query Params:**
| Param | Type | Deskripsi |
|-------|------|-----------|
| `url` | string | URL file yang ingin dihapus (contoh: `/static/products/file.jpg`) |

**Response:** `{ "ok": true, "deleted": true }`

---

## Error Responses

| HTTP Code | Deskripsi |
|-----------|-----------|
| `400` | Bad Request — data tidak valid |
| `401` | Unauthorized — token tidak ada atau tidak valid |
| `403` | Forbidden — role tidak cukup atau akun nonaktif |
| `404` | Not Found — data tidak ditemukan |
| `500` | Internal Server Error |

**Format error:**
```json
{ "detail": "Pesan error di sini" }
```

---

## Setup HTTPS (SSL)

Untuk mengaktifkan HTTPS pada domain `api.khansakirana.my.id`, install Certbot:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d api.khansakirana.my.id
```

Certbot akan otomatis mengupdate konfigurasi Nginx dan membuat sertifikat SSL gratis via Let's Encrypt.

---

## Deployment & Manajemen Service

Service berjalan sebagai `systemd` service yang auto-start saat boot.

```bash
# Cek status
sudo systemctl status api-khansa-kirana

# Restart manual
sudo systemctl restart api-khansa-kirana

# Lihat log
sudo journalctl -u api-khansa-kirana -f

# Update kode (setelah pull dari git)
sudo cp -r . /opt/api_khansa_kirana/
sudo systemctl restart api-khansa-kirana
```

**Environment variables** disimpan di `/etc/api-khansa-kirana.env`.
