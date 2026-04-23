from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import settings
from .db import execute, fetch_all, fetch_one
from .security import create_access_token, decode_token, verify_password
from .serialize import normalize_row, normalize_rows


APP_NAME = "Khansa Collection Backend"

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _safe_order_by(value: str, allowed: set[str], default: str) -> str:
    return value if value in allowed else default


_CATALOG_ISLAND_LABELS = {
    "sumatera": "Sumatera",
    "jawa": "Jawa",
    "kalimantan": "Kalimantan",
    "sulawesi": "Sulawesi",
    "bali_nt": "Bali & Nusa Tenggara",
    "maluku_papua": "Maluku & Papua",
}

_CATALOG_ISLAND_RANK = {
    "jawa": 1,
    "sumatera": 2,
    "kalimantan": 3,
    "sulawesi": 4,
    "bali_nt": 5,
    "maluku_papua": 6,
}

_CATALOG_PROVINCE_ISLAND_MAP = {
    "aceh": "sumatera",
    "sumatera utara": "sumatera",
    "sumatera barat": "sumatera",
    "riau": "sumatera",
    "kepulauan riau": "sumatera",
    "jambi": "sumatera",
    "bengkulu": "sumatera",
    "sumatera selatan": "sumatera",
    "bangka belitung": "sumatera",
    "lampung": "sumatera",
    "banten": "jawa",
    "dki jakarta": "jawa",
    "jawa barat": "jawa",
    "jawa tengah": "jawa",
    "di yogyakarta": "jawa",
    "jawa timur": "jawa",
    "bali": "bali_nt",
    "ntb": "bali_nt",
    "ntt": "bali_nt",
    "kalimantan barat": "kalimantan",
    "kalimantan tengah": "kalimantan",
    "kalimantan selatan": "kalimantan",
    "kalimantan timur": "kalimantan",
    "kalimantan utara": "kalimantan",
    "sulawesi utara": "sulawesi",
    "gorontalo": "sulawesi",
    "sulawesi tengah": "sulawesi",
    "sulawesi barat": "sulawesi",
    "sulawesi selatan": "sulawesi",
    "sulawesi tenggara": "sulawesi",
    "maluku": "maluku_papua",
    "maluku utara": "maluku_papua",
    "papua barat": "maluku_papua",
    "papua": "maluku_papua",
}

_HERO_IMAGES_CONTENT_KEY = "hero_images"
_HERO_IMAGES_CONTENT_SECTION = "hero"
_HERO_IMAGES_CONTENT_DESCRIPTION = "URL gambar hero/slideshow beranda"


def _normalize_catalog_island_key(value: str | None) -> str:
    sanitized = "_".join((value or "").strip().lower().split())
    sanitized = sanitized.replace("-", "_")

    if sanitized in {"", "all", "semua"}:
        return ""
    if sanitized == "java":
        return "jawa"
    if sanitized in {"bali_nusa", "bali_nusa_tenggara", "bali_nusatenggara", "bali_nt"}:
        return "bali_nt"
    if sanitized in {"papua", "maluku_papua", "maluku_papua_dan_sekitarnya"}:
        return "maluku_papua"
    return sanitized


def _normalize_catalog_province_name(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _catalog_island_key_for_province(province_name: str | None) -> str:
    return _CATALOG_PROVINCE_ISLAND_MAP.get(
        _normalize_catalog_province_name(province_name),
        "",
    )


def _catalog_price_from_product_price(value: Any) -> str:
    try:
        price = float(value or 0)
    except (TypeError, ValueError):
        return "Rp 125.000"

    if price <= 0:
        return "Rp 125.000"

    return f"Rp {int(round(price)):,.0f}".replace(",", ".")


def _load_catalog_province_rows(is_active: bool | None = None) -> list[dict[str, Any]]:
    sql = (
        "SELECT id, name, island_key, costume_name, description, image_url, price_from, is_active, sort_order, created_at, updated_at "
        "FROM catalog_provinces WHERE 1=1"
    )
    params: list[Any] = []

    if is_active is not None:
        sql += " AND is_active=%s"
        params.append(_bool_to_int(is_active))

    sql += " ORDER BY sort_order ASC"

    try:
        return fetch_all(sql, tuple(params))
    except Exception:
        return []


def _load_catalog_product_location_rows(is_active: bool = True) -> list[dict[str, Any]]:
    sql = (
        "SELECT province, traditional_name, name, image_url, price "
        "FROM products WHERE province IS NOT NULL AND TRIM(province) <> ''"
    )
    params: list[Any] = []

    if is_active:
        sql += " AND is_available=1"

    sql += " ORDER BY province ASC, updated_at DESC, created_at DESC"

    try:
        return fetch_all(sql, tuple(params))
    except Exception:
        return []


def _catalog_province_payloads(is_active: bool | None = None) -> list[dict[str, Any]]:
    province_map: dict[str, dict[str, Any]] = {}
    now = _utc_now()

    for row in _load_catalog_province_rows(is_active=is_active):
        province_name = (row.get("name") or "").strip()
        if not province_name:
            continue

        normalized_name = _normalize_catalog_province_name(province_name)
        province_map[normalized_name] = {
            **row,
            "name": province_name,
            "island_key": _normalize_catalog_island_key(
                row.get("island_key") or _catalog_island_key_for_province(province_name)
            ),
            "costume_name": (row.get("costume_name") or "").strip(),
            "description": (row.get("description") or "").strip(),
            "price_from": (row.get("price_from") or "").strip(),
        }

    if is_active is not False:
        for row in _load_catalog_product_location_rows(is_active=True):
            province_name = (row.get("province") or "").strip()
            if not province_name:
                continue

            normalized_name = _normalize_catalog_province_name(province_name)
            island_key = _catalog_island_key_for_province(province_name)
            if not island_key:
                continue

            costume_name = (row.get("traditional_name") or row.get("name") or "").strip()
            image_url = (row.get("image_url") or "").strip() or None
            price_from = _catalog_price_from_product_price(row.get("price"))

            existing = province_map.get(normalized_name)
            if existing is not None:
                if not existing.get("island_key"):
                    existing["island_key"] = island_key
                if not existing.get("costume_name") and costume_name:
                    existing["costume_name"] = costume_name
                if not existing.get("image_url") and image_url:
                    existing["image_url"] = image_url
                if not existing.get("price_from"):
                    existing["price_from"] = price_from
                continue

            province_map[normalized_name] = {
                "id": f"fallback-{normalized_name.replace(' ', '-')}",
                "name": province_name,
                "island_key": island_key,
                "costume_name": costume_name or province_name,
                "description": "",
                "image_url": image_url,
                "price_from": price_from,
                "is_active": 1,
                "sort_order": 0,
                "created_at": now,
                "updated_at": now,
            }

    rows = [row for row in province_map.values() if row.get("island_key")]

    rows.sort(
        key=lambda row: (
            _CATALOG_ISLAND_RANK.get(row.get("island_key") or "", 999),
            0 if int(row.get("sort_order") or 0) > 0 else 1,
            int(row.get("sort_order") or 0) if int(row.get("sort_order") or 0) > 0 else 9999,
            _normalize_catalog_province_name(row.get("name")),
        )
    )

    for index, row in enumerate(rows, start=1):
        if int(row.get("sort_order") or 0) <= 0:
            row["sort_order"] = index
        if row.get("is_active") is None:
            row["is_active"] = 1

    return rows


def _catalog_island_payloads() -> list[dict[str, Any]]:
    island_map: dict[str, dict[str, Any]] = {}

    try:
        island_rows = fetch_all(
            "SELECT id, `key`, name, sort_order FROM island_groups ORDER BY sort_order ASC"
        )
    except Exception:
        island_rows = []

    for row in island_rows:
        island_key = _normalize_catalog_island_key(row.get("key") or row.get("name"))
        if not island_key:
            continue

        island_map[island_key] = {
            **row,
            "key": island_key,
            "name": _CATALOG_ISLAND_LABELS.get(
                island_key,
                (row.get("name") or island_key.replace("_", " ").title()),
            ),
        }

    for province in _catalog_province_payloads(is_active=True):
        island_key = province.get("island_key") or ""
        if not island_key:
            continue
        if island_key not in island_map:
            island_map[island_key] = {
                "id": f"fallback-{island_key}",
                "key": island_key,
                "name": _CATALOG_ISLAND_LABELS.get(
                    island_key,
                    island_key.replace("_", " ").title(),
                ),
                "sort_order": _CATALOG_ISLAND_RANK.get(island_key, 999),
            }

    if not island_map:
        for island_key, island_name in _CATALOG_ISLAND_LABELS.items():
            island_map[island_key] = {
                "id": f"fallback-{island_key}",
                "key": island_key,
                "name": island_name,
                "sort_order": _CATALOG_ISLAND_RANK.get(island_key, 999),
            }

    rows = list(island_map.values())
    rows.sort(
        key=lambda row: (
            int(row.get("sort_order") or _CATALOG_ISLAND_RANK.get(row.get("key") or "", 999)),
            _CATALOG_ISLAND_RANK.get(row.get("key") or "", 999),
            (row.get("name") or "").strip().lower(),
        )
    )
    return rows


def _get_primary_store_profile_id() -> str | None:
    try:
        row = fetch_one("SELECT id FROM store_profile ORDER BY created_at ASC LIMIT 1")
    except Exception:
        return None

    if not row or not row.get("id"):
        return None

    return str(row["id"])


def _get_site_content_value(content_key: str) -> str:
    try:
        row = fetch_one("SELECT value FROM site_content WHERE `key`=%s", (content_key,))
    except Exception:
        return ""

    if not row:
        return ""

    return str(row.get("value") or "").strip()


def _upsert_site_content_value(
    content_key: str,
    *,
    section: str,
    value: str,
    description: str | None = None,
) -> None:
    try:
        existing = fetch_one("SELECT id FROM site_content WHERE `key`=%s", (content_key,))
        if existing:
            if description is None:
                execute(
                    "UPDATE site_content SET section=%s, content_type=%s, value=%s, updated_at=UTC_TIMESTAMP() WHERE `key`=%s",
                    (section, "text", value, content_key),
                )
            else:
                execute(
                    "UPDATE site_content SET section=%s, content_type=%s, value=%s, description=%s, updated_at=UTC_TIMESTAMP() WHERE `key`=%s",
                    (section, "text", value, description, content_key),
                )
            return

        execute(
            "INSERT INTO site_content (id, `key`, section, content_type, value, description, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, UTC_TIMESTAMP())",
            (str(uuid.uuid4()), content_key, section, "text", value, description),
        )
    except Exception:
        return


def _sync_store_profile_hero_images(value: str) -> None:
    profile_id = _get_primary_store_profile_id()
    if not profile_id:
        return

    try:
        execute(
            "UPDATE store_profile SET hero_images=%s, updated_at=UTC_TIMESTAMP() WHERE id=%s",
            (value, profile_id),
        )
    except Exception:
        return


def _public_admin(admin_row: dict[str, Any]) -> dict[str, Any]:
    admin_row = dict(admin_row)
    admin_row.pop("password_hash", None)
    return normalize_row(admin_row, bool_fields={"is_active"})


bearer = HTTPBearer(auto_error=False)


def require_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict[str, Any]:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        payload = decode_token(creds.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    admin_id = payload.get("sub")
    if not admin_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    admin = fetch_one(
        "SELECT id, email, name, role, is_active, last_login_at, created_at, password_hash "
        "FROM admin_users WHERE id=%s",
        (admin_id,),
    )
    if not admin:
        raise HTTPException(status_code=401, detail="User not found")

    if not bool(admin.get("is_active")):
        raise HTTPException(status_code=403, detail="Account inactive")

    return admin


def require_role(allowed_roles: set[str]):
    def _dep(admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        if admin.get("role") not in allowed_roles:
            raise HTTPException(status_code=403, detail="Forbidden")
        return admin

    return _dep


app = FastAPI(title=APP_NAME)

cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if not cors_origins:
    cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"] ,
    allow_headers=["*"] ,
)

app.mount("/static", StaticFiles(directory=str(UPLOAD_DIR)), name="static")


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "name": APP_NAME, "time": _utc_now().isoformat()}


# =============================================================================
# AUTH
# =============================================================================


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    admin: dict[str, Any]


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> dict[str, Any]:
    admin = fetch_one(
        "SELECT id, email, name, role, is_active, last_login_at, created_at, password_hash "
        "FROM admin_users WHERE email=%s",
        (payload.email,),
    )

    if not admin:
        raise HTTPException(status_code=401, detail="Email atau password salah")

    if not bool(admin.get("is_active")):
        raise HTTPException(status_code=403, detail="Akun admin tidak aktif")

    if not verify_password(payload.password, admin.get("password_hash") or ""):
        raise HTTPException(status_code=401, detail="Email atau password salah")

    execute(
        "UPDATE admin_users SET last_login_at=UTC_TIMESTAMP() WHERE id=%s",
        (admin["id"],),
    )

    token = create_access_token(
        admin_id=admin["id"], email=admin["email"], role=admin.get("role") or "admin"
    )

    return {"access_token": token, "token_type": "bearer", "admin": _public_admin(admin)}


@app.get("/auth/me")
def me(admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    return _public_admin(admin)


class PasswordUpdateRequest(BaseModel):
    new_password: str = Field(min_length=6)


@app.post("/auth/change-password")
def change_password(
    payload: PasswordUpdateRequest,
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    # Import here to avoid circular
    from .security import hash_password

    execute(
        "UPDATE admin_users SET password_hash=%s WHERE id=%s",
        (hash_password(payload.new_password), admin["id"]),
    )
    return {"ok": True}


# =============================================================================
# ADMINS (Super Admin)
# =============================================================================


class AdminCreateRequest(BaseModel):
    email: str
    password: str = Field(min_length=6)
    name: str | None = None
    role: str = "admin"  # super_admin, admin, editor


@app.get("/admins")
def list_admins(
    _admin: dict[str, Any] = Depends(require_role({"super_admin"})),
) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT id, email, name, role, is_active, last_login_at, created_at "
        "FROM admin_users ORDER BY created_at DESC"
    )
    return normalize_rows(rows, bool_fields={"is_active"})


@app.post("/admins")
def create_admin(
    payload: AdminCreateRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin"})),
) -> dict[str, Any]:
    from .security import hash_password

    admin_id = str(uuid.uuid4())

    try:
        execute(
            "INSERT INTO admin_users (id, email, name, role, is_active, password_hash, created_at) "
            "VALUES (%s, %s, %s, %s, 1, %s, UTC_TIMESTAMP())",
            (
                admin_id,
                payload.email,
                payload.name,
                payload.role,
                hash_password(payload.password),
            ),
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Gagal membuat admin (email mungkin sudah terpakai)")

    created = fetch_one(
        "SELECT id, email, name, role, is_active, last_login_at, created_at FROM admin_users WHERE id=%s",
        (admin_id,),
    )
    if not created:
        raise HTTPException(status_code=500, detail="Admin created but cannot be loaded")

    return normalize_row(created, bool_fields={"is_active"})


class AdminStatusRequest(BaseModel):
    is_active: bool


@app.put("/admins/{admin_id}/status")
def update_admin_status(
    admin_id: str,
    payload: AdminStatusRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin"})),
) -> dict[str, Any]:
    execute(
        "UPDATE admin_users SET is_active=%s WHERE id=%s",
        (_bool_to_int(payload.is_active), admin_id),
    )
    return {"ok": True}


@app.delete("/admins/{admin_id}")
def delete_admin(
    admin_id: str,
    _admin: dict[str, Any] = Depends(require_role({"super_admin"})),
) -> dict[str, Any]:
    execute("DELETE FROM admin_users WHERE id=%s", (admin_id,))
    return {"ok": True}


# =============================================================================
# CONTENT
# =============================================================================


class ContentCreateRequest(BaseModel):
    key: str
    section: str
    value: str = ""
    content_type: str = "text"
    description: str | None = None


class ContentUpdateRequest(BaseModel):
    value: str


@app.get("/content")
def get_all_content(section: str | None = None) -> list[dict[str, Any]]:
    if section:
        rows = fetch_all(
            "SELECT id, `key`, section, content_type, value, description, updated_at "
            "FROM site_content WHERE section=%s ORDER BY `key` ASC",
            (section,),
        )
    else:
        rows = fetch_all(
            "SELECT id, `key`, section, content_type, value, description, updated_at "
            "FROM site_content ORDER BY section ASC, `key` ASC"
        )
    return normalize_rows(rows)


@app.get("/content/{content_key}")
def get_content_by_key(content_key: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT id, `key`, section, content_type, value, description, updated_at "
        "FROM site_content WHERE `key`=%s",
        (content_key,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Content not found")
    return normalize_row(row)


@app.put("/content/{content_key}")
def update_content(
    content_key: str,
    payload: ContentUpdateRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin", "editor"})),
) -> dict[str, Any]:
    affected = execute(
        "UPDATE site_content SET value=%s, updated_at=UTC_TIMESTAMP() WHERE `key`=%s",
        (payload.value, content_key),
    )
    if affected == 0:
        raise HTTPException(status_code=404, detail="Content not found")

    if content_key == _HERO_IMAGES_CONTENT_KEY:
        _sync_store_profile_hero_images(payload.value)

    return {"ok": True}


@app.post("/content")
def create_content(
    payload: ContentCreateRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    content_id = str(uuid.uuid4())
    try:
        execute(
            "INSERT INTO site_content (id, `key`, section, content_type, value, description, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, UTC_TIMESTAMP())",
            (
                content_id,
                payload.key,
                payload.section,
                payload.content_type,
                payload.value,
                payload.description,
            ),
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Key sudah ada atau data tidak valid")

    row = fetch_one(
        "SELECT id, `key`, section, content_type, value, description, updated_at "
        "FROM site_content WHERE id=%s",
        (content_id,),
    )
    if not row:
        raise HTTPException(status_code=500, detail="Content created but cannot be loaded")

    if payload.key == _HERO_IMAGES_CONTENT_KEY:
        _sync_store_profile_hero_images(payload.value)

    return normalize_row(row)


@app.delete("/content/{content_key}")
def delete_content(
    content_key: str,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    execute("DELETE FROM site_content WHERE `key`=%s", (content_key,))
    return {"ok": True}


# =============================================================================
# STORE PROFILE
# =============================================================================


class StoreProfileUpdateRequest(BaseModel):
    store_name: str | None = None
    logo_url: str | None = None
    address: str | None = None
    gmaps_link: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    phone: str | None = None
    whatsapp: str | None = None
    instagram_url: str | None = None
    facebook_url: str | None = None
    tiktok_url: str | None = None
    operational_hours: str | None = None
    hero_images: str | None = None


@app.get("/store-profile")
def get_store_profile() -> dict[str, Any] | None:
    row = fetch_one(
        "SELECT id, store_name, logo_url, address, gmaps_link, latitude, longitude, phone, whatsapp, "
        "instagram_url, facebook_url, tiktok_url, operational_hours, hero_images, created_at, updated_at "
        "FROM store_profile ORDER BY created_at ASC LIMIT 1"
    )
    if not row:
        return None

    hero_images = str(row.get("hero_images") or "").strip()
    if not hero_images:
        legacy_hero_images = _get_site_content_value(_HERO_IMAGES_CONTENT_KEY)
        if legacy_hero_images:
            row = dict(row)
            row["hero_images"] = legacy_hero_images

    return normalize_row(row)


@app.put("/store-profile/{profile_id}")
def update_store_profile(
    profile_id: str,
    payload: StoreProfileUpdateRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    fields: list[str] = []
    params: list[Any] = []

    for column in [
        "store_name",
        "logo_url",
        "address",
        "gmaps_link",
        "latitude",
        "longitude",
        "phone",
        "whatsapp",
        "instagram_url",
        "facebook_url",
        "tiktok_url",
        "operational_hours",
        "hero_images",
    ]:
        value = getattr(payload, column)
        if value is not None:
            fields.append(f"{column}=%s")
            params.append(value)

    if not fields:
        return {"ok": True}

    fields.append("updated_at=UTC_TIMESTAMP()")
    params.append(profile_id)

    execute(
        f"UPDATE store_profile SET {', '.join(fields)} WHERE id=%s",
        tuple(params),
    )

    if payload.hero_images is not None:
        _upsert_site_content_value(
            _HERO_IMAGES_CONTENT_KEY,
            section=_HERO_IMAGES_CONTENT_SECTION,
            value=payload.hero_images,
            description=_HERO_IMAGES_CONTENT_DESCRIPTION,
        )

    return {"ok": True}


# =============================================================================
# PRODUCTS
# =============================================================================


class ProductCreateRequest(BaseModel):
    name: str
    description: str | None = ""
    image_url: str | None = ""
    price: float = 0
    category: str
    province: str | None = ""
    traditional_name: str | None = None
    is_available: bool = True
    show_in_gallery: bool = False


class ProductUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    image_url: str | None = None
    price: float | None = None
    category: str | None = None
    province: str | None = None
    traditional_name: str | None = None
    is_available: bool | None = None
    show_in_gallery: bool | None = None


def _load_product_images_map(product_ids: list[str]) -> dict[str, list[str]]:
    if not product_ids:
        return {}

    try:
        placeholders = ", ".join(["%s"] * len(product_ids))
        rows = fetch_all(
            "SELECT product_id, image_url FROM product_images "
            f"WHERE product_id IN ({placeholders}) "
            "ORDER BY sort_order ASC, created_at ASC",
            tuple(product_ids),
        )
    except Exception:
        return {}

    grouped: dict[str, list[str]] = {}
    for row in rows:
        product_id = row.get("product_id")
        image_url = (row.get("image_url") or "").strip()
        if not product_id or not image_url:
            continue
        grouped.setdefault(product_id, []).append(image_url)
    return grouped


def _attach_product_images(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not products:
        return products

    product_ids = [str(product.get("id")) for product in products if product.get("id")]
    image_map = _load_product_images_map(product_ids)

    for product in products:
        product_id = str(product.get("id") or "")
        images = image_map.get(product_id, [])
        primary = str(product.get("image_url") or "").strip()

        if primary and primary not in images:
            images = [primary, *images]

        product["images"] = images
        if images and not primary:
            product["image_url"] = images[0]

    return products


@app.get("/products")
def list_products(
    category: str | None = None,
    province: str | None = None,
    is_available: bool | None = None,
    show_in_gallery: bool | None = None,
    order_by: str = "created_at",
    ascending: bool = False,
) -> list[dict[str, Any]]:
    sql = (
        "SELECT id, name, description, image_url, price, category, province, traditional_name, "
        "is_available, show_in_gallery, created_at, updated_at FROM products WHERE 1=1"
    )
    params: list[Any] = []

    if category:
        sql += " AND category=%s"
        params.append(category)

    if province:
        sql += " AND province=%s"
        params.append(province)

    if is_available is not None:
        sql += " AND is_available=%s"
        params.append(_bool_to_int(is_available))

    if show_in_gallery is not None:
        sql += " AND show_in_gallery=%s"
        params.append(_bool_to_int(show_in_gallery))

    order = _safe_order_by(order_by, {"created_at", "updated_at", "name", "price"}, "created_at")
    direction = "ASC" if ascending else "DESC"
    sql += f" ORDER BY {order} {direction}"

    rows = fetch_all(sql, tuple(params))
    products = normalize_rows(rows, bool_fields={"is_available", "show_in_gallery"})
    return _attach_product_images(products)


@app.get("/products/{product_id}")
def get_product(product_id: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT id, name, description, image_url, price, category, province, traditional_name, "
        "is_available, show_in_gallery, created_at, updated_at FROM products WHERE id=%s",
        (product_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    products = _attach_product_images(
        [normalize_row(row, bool_fields={"is_available", "show_in_gallery"})]
    )
    return products[0]


@app.post("/products")
def create_product(
    payload: ProductCreateRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    product_id = str(uuid.uuid4())

    execute(
        "INSERT INTO products (id, name, description, image_url, price, category, province, traditional_name, is_available, show_in_gallery, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, UTC_TIMESTAMP(), UTC_TIMESTAMP())",
        (
            product_id,
            payload.name,
            payload.description or "",
            payload.image_url or "",
            payload.price,
            payload.category,
            payload.province or "",
            payload.traditional_name,
            _bool_to_int(payload.is_available),
            _bool_to_int(payload.show_in_gallery),
        ),
    )

    row = fetch_one(
        "SELECT id, name, description, image_url, price, category, province, traditional_name, "
        "is_available, show_in_gallery, created_at, updated_at FROM products WHERE id=%s",
        (product_id,),
    )
    if not row:
        raise HTTPException(status_code=500, detail="Product created but cannot be loaded")

    products = _attach_product_images(
        [normalize_row(row, bool_fields={"is_available", "show_in_gallery"})]
    )
    return products[0]


@app.put("/products/{product_id}")
def update_product(
    product_id: str,
    payload: ProductUpdateRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    fields: list[str] = []
    params: list[Any] = []

    mapping = {
        "name": payload.name,
        "description": payload.description,
        "image_url": payload.image_url,
        "price": payload.price,
        "category": payload.category,
        "province": payload.province,
        "traditional_name": payload.traditional_name,
    }

    for column, value in mapping.items():
        if value is not None:
            fields.append(f"{column}=%s")
            params.append(value)

    if payload.is_available is not None:
        fields.append("is_available=%s")
        params.append(_bool_to_int(payload.is_available))

    if payload.show_in_gallery is not None:
        fields.append("show_in_gallery=%s")
        params.append(_bool_to_int(payload.show_in_gallery))

    if not fields:
        return {"ok": True}

    fields.append("updated_at=UTC_TIMESTAMP()")
    params.append(product_id)

    execute(
        f"UPDATE products SET {', '.join(fields)} WHERE id=%s",
        tuple(params),
    )

    return {"ok": True}


@app.delete("/products/{product_id}")
def delete_product(
    product_id: str,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    execute("DELETE FROM products WHERE id=%s", (product_id,))
    return {"ok": True}


@app.get("/products/search")
def search_products(q: str = Query(min_length=1)) -> list[dict[str, Any]]:
    like = f"%{q}%"
    rows = fetch_all(
        "SELECT id, name, description, image_url, price, category, province, traditional_name, "
        "is_available, show_in_gallery, created_at, updated_at FROM products "
        "WHERE is_available=1 AND (name LIKE %s OR description LIKE %s OR traditional_name LIKE %s) "
        "ORDER BY name ASC",
        (like, like, like),
    )
    products = normalize_rows(rows, bool_fields={"is_available", "show_in_gallery"})
    return _attach_product_images(products)


@app.get("/products/categories")
def product_categories() -> list[str]:
    rows = fetch_all(
        "SELECT DISTINCT category FROM products WHERE category <> '' ORDER BY category ASC"
    )
    return [r["category"] for r in rows if r.get("category")]


@app.get("/products/provinces")
def product_provinces() -> list[str]:
    rows = fetch_all(
        "SELECT DISTINCT province FROM products WHERE province <> '' ORDER BY province ASC"
    )
    return [r["province"] for r in rows if r.get("province")]


# =============================================================================
# OUTLETS
# =============================================================================


class OutletCreateRequest(BaseModel):
    name: str
    address: str = ""
    latitude: float
    longitude: float
    phone: str | None = None
    whatsapp: str | None = None
    operational_hours: str | None = None
    is_main: bool = False
    is_active: bool = True


class OutletUpdateRequest(BaseModel):
    name: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    phone: str | None = None
    whatsapp: str | None = None
    operational_hours: str | None = None
    is_main: bool | None = None
    is_active: bool | None = None


@app.get("/outlets")
def list_outlets(is_active: bool | None = None) -> list[dict[str, Any]]:
    sql = (
        "SELECT id, name, address, latitude, longitude, phone, whatsapp, operational_hours, is_main, is_active, created_at, updated_at "
        "FROM outlet_locations WHERE 1=1"
    )
    params: list[Any] = []

    if is_active is not None:
        sql += " AND is_active=%s"
        params.append(_bool_to_int(is_active))

    sql += " ORDER BY is_main DESC, name ASC"

    rows = fetch_all(sql, tuple(params))
    return normalize_rows(rows, bool_fields={"is_active", "is_main"})


@app.get("/outlets/main")
def main_outlet() -> dict[str, Any] | None:
    row = fetch_one(
        "SELECT id, name, address, latitude, longitude, phone, whatsapp, operational_hours, is_main, is_active, created_at, updated_at "
        "FROM outlet_locations WHERE is_main=1 AND is_active=1 LIMIT 1"
    )
    if not row:
        return None
    return normalize_row(row, bool_fields={"is_active", "is_main"})


@app.get("/outlets/{outlet_id}")
def get_outlet(outlet_id: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT id, name, address, latitude, longitude, phone, whatsapp, operational_hours, is_main, is_active, created_at, updated_at "
        "FROM outlet_locations WHERE id=%s",
        (outlet_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Outlet not found")
    return normalize_row(row, bool_fields={"is_active", "is_main"})


@app.post("/outlets")
def create_outlet(
    payload: OutletCreateRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    outlet_id = str(uuid.uuid4())

    if payload.is_main:
        execute("UPDATE outlet_locations SET is_main=0 WHERE is_main=1", ())

    execute(
        "INSERT INTO outlet_locations (id, name, address, latitude, longitude, phone, whatsapp, operational_hours, is_main, is_active, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, UTC_TIMESTAMP(), UTC_TIMESTAMP())",
        (
            outlet_id,
            payload.name,
            payload.address,
            payload.latitude,
            payload.longitude,
            payload.phone,
            payload.whatsapp,
            payload.operational_hours,
            _bool_to_int(payload.is_main),
            _bool_to_int(payload.is_active),
        ),
    )

    row = fetch_one(
        "SELECT id, name, address, latitude, longitude, phone, whatsapp, operational_hours, is_main, is_active, created_at, updated_at "
        "FROM outlet_locations WHERE id=%s",
        (outlet_id,),
    )
    if not row:
        raise HTTPException(status_code=500, detail="Outlet created but cannot be loaded")

    return normalize_row(row, bool_fields={"is_active", "is_main"})


@app.put("/outlets/{outlet_id}")
def update_outlet(
    outlet_id: str,
    payload: OutletUpdateRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    if payload.is_main is True:
        execute(
            "UPDATE outlet_locations SET is_main=0 WHERE is_main=1 AND id<>%s",
            (outlet_id,),
        )

    fields: list[str] = []
    params: list[Any] = []

    for column in [
        "name",
        "address",
        "latitude",
        "longitude",
        "phone",
        "whatsapp",
        "operational_hours",
    ]:
        value = getattr(payload, column)
        if value is not None:
            fields.append(f"{column}=%s")
            params.append(value)

    if payload.is_main is not None:
        fields.append("is_main=%s")
        params.append(_bool_to_int(payload.is_main))

    if payload.is_active is not None:
        fields.append("is_active=%s")
        params.append(_bool_to_int(payload.is_active))

    if not fields:
        return {"ok": True}

    fields.append("updated_at=UTC_TIMESTAMP()")
    params.append(outlet_id)

    execute(
        f"UPDATE outlet_locations SET {', '.join(fields)} WHERE id=%s",
        tuple(params),
    )

    return {"ok": True}


@app.put("/outlets/{outlet_id}/status")
def toggle_outlet_status(
    outlet_id: str,
    payload: AdminStatusRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    execute(
        "UPDATE outlet_locations SET is_active=%s, updated_at=UTC_TIMESTAMP() WHERE id=%s",
        (_bool_to_int(payload.is_active), outlet_id),
    )
    return {"ok": True}


@app.put("/outlets/{outlet_id}/set-main")
def set_main_outlet(
    outlet_id: str,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    execute("UPDATE outlet_locations SET is_main=0 WHERE is_main=1", ())
    execute(
        "UPDATE outlet_locations SET is_main=1, updated_at=UTC_TIMESTAMP() WHERE id=%s",
        (outlet_id,),
    )
    return {"ok": True}


@app.delete("/outlets/{outlet_id}")
def delete_outlet(
    outlet_id: str,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    execute("DELETE FROM outlet_locations WHERE id=%s", (outlet_id,))
    return {"ok": True}


# =============================================================================
# TESTIMONIALS
# =============================================================================


class TestimonialCreateRequest(BaseModel):
    name: str
    occasion: str
    review: str
    rating: float = 5.0
    is_active: bool = True
    sort_order: int = 0


class TestimonialUpdateRequest(BaseModel):
    name: str | None = None
    occasion: str | None = None
    review: str | None = None
    rating: float | None = None
    is_active: bool | None = None
    sort_order: int | None = None


@app.get("/testimonials")
def list_testimonials(is_active: bool | None = None) -> list[dict[str, Any]]:
    sql = (
        "SELECT id, name, occasion, review, rating, is_active, sort_order, created_at, updated_at "
        "FROM testimonials WHERE 1=1"
    )
    params: list[Any] = []

    if is_active is not None:
        sql += " AND is_active=%s"
        params.append(_bool_to_int(is_active))

    sql += " ORDER BY sort_order ASC, created_at DESC"
    rows = fetch_all(sql, tuple(params))
    return normalize_rows(rows, bool_fields={"is_active"})


@app.post("/testimonials")
def create_testimonial(
    payload: TestimonialCreateRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    testimonial_id = str(uuid.uuid4())

    execute(
        "INSERT INTO testimonials (id, name, occasion, review, rating, is_active, sort_order, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, UTC_TIMESTAMP(), UTC_TIMESTAMP())",
        (
            testimonial_id,
            payload.name,
            payload.occasion,
            payload.review,
            payload.rating,
            _bool_to_int(payload.is_active),
            payload.sort_order,
        ),
    )

    row = fetch_one(
        "SELECT id, name, occasion, review, rating, is_active, sort_order, created_at, updated_at "
        "FROM testimonials WHERE id=%s",
        (testimonial_id,),
    )
    if not row:
        raise HTTPException(status_code=500, detail="Testimonial created but cannot be loaded")

    return normalize_row(row, bool_fields={"is_active"})


@app.put("/testimonials/{testimonial_id}")
def update_testimonial(
    testimonial_id: str,
    payload: TestimonialUpdateRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    fields: list[str] = []
    params: list[Any] = []

    for column in ["name", "occasion", "review", "rating", "sort_order"]:
        value = getattr(payload, column)
        if value is not None:
            fields.append(f"{column}=%s")
            params.append(value)

    if payload.is_active is not None:
        fields.append("is_active=%s")
        params.append(_bool_to_int(payload.is_active))

    if not fields:
        return {"ok": True}

    fields.append("updated_at=UTC_TIMESTAMP()")
    params.append(testimonial_id)

    execute(
        f"UPDATE testimonials SET {', '.join(fields)} WHERE id=%s",
        tuple(params),
    )
    return {"ok": True}


@app.put("/testimonials/{testimonial_id}/toggle-active")
def toggle_testimonial_active(
    testimonial_id: str,
    payload: AdminStatusRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    execute(
        "UPDATE testimonials SET is_active=%s, updated_at=UTC_TIMESTAMP() WHERE id=%s",
        (_bool_to_int(payload.is_active), testimonial_id),
    )
    return {"ok": True}


@app.delete("/testimonials/{testimonial_id}")
def delete_testimonial(
    testimonial_id: str,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    execute("DELETE FROM testimonials WHERE id=%s", (testimonial_id,))
    return {"ok": True}


# =============================================================================
# GALLERY
# =============================================================================


class GalleryCreateRequest(BaseModel):
    title: str
    category: str = ""
    image_url: str
    cross_axis_cell_count: int = 2
    main_axis_cell_count: int = 1
    is_active: bool = True
    sort_order: int = 0


class GalleryUpdateRequest(BaseModel):
    title: str | None = None
    category: str | None = None
    image_url: str | None = None
    cross_axis_cell_count: int | None = None
    main_axis_cell_count: int | None = None
    is_active: bool | None = None
    sort_order: int | None = None


@app.get("/gallery")
def list_gallery(is_active: bool | None = None) -> list[dict[str, Any]]:
    sql = (
        "SELECT id, title, category, image_url, cross_axis_cell_count, main_axis_cell_count, is_active, sort_order, created_at, updated_at "
        "FROM gallery_items WHERE 1=1"
    )
    params: list[Any] = []

    if is_active is not None:
        sql += " AND is_active=%s"
        params.append(_bool_to_int(is_active))

    sql += " ORDER BY sort_order ASC, created_at DESC"

    rows = fetch_all(sql, tuple(params))
    return normalize_rows(rows, bool_fields={"is_active"})


@app.post("/gallery")
def create_gallery_item(
    payload: GalleryCreateRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    item_id = str(uuid.uuid4())

    execute(
        "INSERT INTO gallery_items (id, title, category, image_url, cross_axis_cell_count, main_axis_cell_count, is_active, sort_order, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, UTC_TIMESTAMP(), UTC_TIMESTAMP())",
        (
            item_id,
            payload.title,
            payload.category,
            payload.image_url,
            payload.cross_axis_cell_count,
            payload.main_axis_cell_count,
            _bool_to_int(payload.is_active),
            payload.sort_order,
        ),
    )

    row = fetch_one(
        "SELECT id, title, category, image_url, cross_axis_cell_count, main_axis_cell_count, is_active, sort_order, created_at, updated_at "
        "FROM gallery_items WHERE id=%s",
        (item_id,),
    )
    if not row:
        raise HTTPException(status_code=500, detail="Gallery item created but cannot be loaded")

    return normalize_row(row, bool_fields={"is_active"})


@app.put("/gallery/{item_id}")
def update_gallery_item(
    item_id: str,
    payload: GalleryUpdateRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    fields: list[str] = []
    params: list[Any] = []

    for column in [
        "title",
        "category",
        "image_url",
        "cross_axis_cell_count",
        "main_axis_cell_count",
        "sort_order",
    ]:
        value = getattr(payload, column)
        if value is not None:
            fields.append(f"{column}=%s")
            params.append(value)

    if payload.is_active is not None:
        fields.append("is_active=%s")
        params.append(_bool_to_int(payload.is_active))

    if not fields:
        return {"ok": True}

    fields.append("updated_at=UTC_TIMESTAMP()")
    params.append(item_id)

    execute(
        f"UPDATE gallery_items SET {', '.join(fields)} WHERE id=%s",
        tuple(params),
    )

    return {"ok": True}


@app.put("/gallery/{item_id}/toggle-active")
def toggle_gallery_active(
    item_id: str,
    payload: AdminStatusRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    execute(
        "UPDATE gallery_items SET is_active=%s, updated_at=UTC_TIMESTAMP() WHERE id=%s",
        (_bool_to_int(payload.is_active), item_id),
    )
    return {"ok": True}


@app.delete("/gallery/{item_id}")
def delete_gallery_item(
    item_id: str,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    execute("DELETE FROM gallery_items WHERE id=%s", (item_id,))
    return {"ok": True}


# =============================================================================
# CATALOG
# =============================================================================


class CatalogProvinceCreateRequest(BaseModel):
    name: str
    island_key: str = ""
    costume_name: str = ""
    description: str = ""
    image_url: str | None = None
    price_from: str = "Rp 125.000"
    is_active: bool = True
    sort_order: int = 0


class CatalogProvinceUpdateRequest(BaseModel):
    name: str | None = None
    island_key: str | None = None
    costume_name: str | None = None
    description: str | None = None
    image_url: str | None = None
    price_from: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


@app.get("/catalog/islands")
def get_islands() -> list[dict[str, Any]]:
    rows = _catalog_island_payloads()
    return normalize_rows(rows)


@app.get("/catalog/provinces")
def list_catalog_provinces(is_active: bool | None = None) -> list[dict[str, Any]]:
    rows = _catalog_province_payloads(is_active=is_active)
    return normalize_rows(rows, bool_fields={"is_active"})


@app.get("/catalog/provinces/names")
def catalog_province_names() -> list[str]:
    rows = _catalog_province_payloads(is_active=True)
    return [str(row["name"]) for row in rows if row.get("name")]


@app.post("/catalog/provinces")
def create_catalog_province(
    payload: CatalogProvinceCreateRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    prov_id = str(uuid.uuid4())
    island_key = _normalize_catalog_island_key(payload.island_key) or _catalog_island_key_for_province(payload.name)

    execute(
        "INSERT INTO catalog_provinces (id, name, island_key, costume_name, description, image_url, price_from, is_active, sort_order, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, UTC_TIMESTAMP(), UTC_TIMESTAMP())",
        (
            prov_id,
            payload.name,
            island_key,
            payload.costume_name,
            payload.description,
            payload.image_url,
            payload.price_from,
            _bool_to_int(payload.is_active),
            payload.sort_order,
        ),
    )

    row = fetch_one(
        "SELECT id, name, island_key, costume_name, description, image_url, price_from, is_active, sort_order, created_at, updated_at "
        "FROM catalog_provinces WHERE id=%s",
        (prov_id,),
    )
    if not row:
        raise HTTPException(status_code=500, detail="Province created but cannot be loaded")

    return normalize_row(row, bool_fields={"is_active"})


@app.put("/catalog/provinces/{province_id}")
def update_catalog_province(
    province_id: str,
    payload: CatalogProvinceUpdateRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    fields: list[str] = []
    params: list[Any] = []

    for column in [
        "name",
        "costume_name",
        "description",
        "image_url",
        "price_from",
        "sort_order",
    ]:
        value = getattr(payload, column)
        if value is not None:
            fields.append(f"{column}=%s")
            params.append(value)

    if payload.island_key is not None:
        fields.append("island_key=%s")
        params.append(_normalize_catalog_island_key(payload.island_key))

    if payload.is_active is not None:
        fields.append("is_active=%s")
        params.append(_bool_to_int(payload.is_active))

    if not fields:
        return {"ok": True}

    fields.append("updated_at=UTC_TIMESTAMP()")
    params.append(province_id)

    execute(
        f"UPDATE catalog_provinces SET {', '.join(fields)} WHERE id=%s",
        tuple(params),
    )

    return {"ok": True}


@app.put("/catalog/provinces/{province_id}/toggle-active")
def toggle_catalog_province_active(
    province_id: str,
    payload: AdminStatusRequest,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    execute(
        "UPDATE catalog_provinces SET is_active=%s, updated_at=UTC_TIMESTAMP() WHERE id=%s",
        (_bool_to_int(payload.is_active), province_id),
    )
    return {"ok": True}


@app.delete("/catalog/provinces/{province_id}")
def delete_catalog_province(
    province_id: str,
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    execute("DELETE FROM catalog_provinces WHERE id=%s", (province_id,))
    return {"ok": True}


# =============================================================================
# STORAGE (UPLOAD)
# =============================================================================


class UploadResponse(BaseModel):
    url: str


class DeleteUploadResponse(BaseModel):
    ok: bool = True
    deleted: bool


def _guess_ext(filename: str | None) -> str:
    if not filename:
        return "bin"
    _, ext = os.path.splitext(filename)
    ext = ext.lstrip(".").lower()
    return ext or "bin"


@app.post("/storage/upload", response_model=UploadResponse)
def upload_file(
    folder: str = Query(min_length=1, max_length=64),
    file: UploadFile = File(...),
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    # basic folder sanitization: keep alnum, dash, underscore
    safe_folder = "".join(ch for ch in folder if ch.isalnum() or ch in {"-", "_"}).strip()
    if not safe_folder:
        raise HTTPException(status_code=400, detail="Invalid folder")

    ext = _guess_ext(file.filename)
    stamp = int(_utc_now().timestamp())
    rand = secrets.token_hex(3)
    stored_name = f"{safe_folder}_{stamp}_{rand}.{ext}"

    target_dir = UPLOAD_DIR / safe_folder
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / stored_name

    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    target_path.write_bytes(content)

    # Return public URL (served by /static mount)
    # /static maps to UPLOAD_DIR
    return {"url": f"/static/{safe_folder}/{stored_name}"}


@app.delete("/storage/delete", response_model=DeleteUploadResponse)
def delete_uploaded_file(
    url: str = Query(min_length=1),
    _admin: dict[str, Any] = Depends(require_role({"super_admin", "admin"})),
) -> dict[str, Any]:
    raw = url.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Invalid url")

    parsed = urlparse(raw)
    path = parsed.path if parsed.scheme else raw
    path = unquote(path)

    if not path.startswith("/"):
        path = f"/{path}"

    if not path.startswith("/static/"):
        raise HTTPException(status_code=400, detail="Invalid url")

    rel = path[len("/static/") :].lstrip("/")
    if not rel:
        raise HTTPException(status_code=400, detail="Invalid url")

    base_dir = UPLOAD_DIR.resolve()
    target = (UPLOAD_DIR / rel).resolve()

    try:
        target.relative_to(base_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if target.exists() and target.is_dir():
        raise HTTPException(status_code=400, detail="Invalid path")

    deleted = False
    if target.exists():
        target.unlink()
        deleted = True

    return {"ok": True, "deleted": deleted}
