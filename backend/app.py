import json
import requests
from datetime import timedelta
from fastapi import FastAPI, Request, HTTPException, Depends, Header, status
from pydantic import BaseModel, EmailStr, conint
from sqlalchemy import create_engine, text, bindparam
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Query
from typing import Optional, Any, Dict, List
import uuid
from reportlab.platypus import SimpleDocTemplate, Image
from reportlab.lib.pagesizes import A4
import os
from datetime import datetime, date
from fastapi.staticfiles import StaticFiles
from collections import defaultdict
import re
from dotenv import load_dotenv
from jose import JWTError, jwt
from datetime import datetime, timedelta

from fastapi.security import OAuth2PasswordBearer
import base64
import hashlib
import hmac
import secrets
import bcrypt as _bcrypt_lib

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import sys


DEV_MODE = os.getenv("DEV_MODE", "false").lower() in ("1", "true", "yes")
    
# Ensure Windows console can print Unicode safely
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")



UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

WHATSAPP_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whatsapp_templates")
os.makedirs(WHATSAPP_TEMPLATES_DIR, exist_ok=True)


def _get_public_api_base_url() -> str:
    """Base URL for links sent on WhatsApp (set API_PUBLIC_BASE_URL in prod)."""
    return (os.getenv("API_PUBLIC_BASE_URL") or os.getenv("PUBLIC_API_URL") or "http://localhost:8000").rstrip(
        "/"
    )


def _ensure_whatsapp_excel_templates() -> None:
    """Create blank .xlsx templates matching frontend downloadTemplate.js headers."""
    try:
        from openpyxl import Workbook
    except Exception:
        return
    specs = [
        (
            "daily_entry_template.xlsx",
            "Daily Entry",
            [
                "entry_date",
                "mortality",
                "mortality_reason",
                "culling",
                "culling_reason",
                "feed_consumption_kg",
                "water_consumed_ltrs",
                "lighting_hours",
                "temperature",
                "medical_attention",
                "medical_notes",
            ],
        ),
        (
            "egg_collection_template.xlsx",
            "Egg Collection",
            ["entry_date", "good_eggs", "floor_eggs", "broken_cracked_eggs", "mishapped_eggs"],
        ),
        (
            "egg_dispatch_template.xlsx",
            "Egg Dispatch",
            ["dispatch_date", "dispatched_good_eggs", "dispatched_floor_mis_eggs"],
        ),
    ]
    for fn, sheet_title, headers in specs:
        path = os.path.join(WHATSAPP_TEMPLATES_DIR, fn)
        if os.path.isfile(path):
            continue
        wb = Workbook()
        ws = wb.active
        ws.title = (sheet_title or "Sheet")[:31]
        ws.append(headers)
        wb.save(path)


_ensure_whatsapp_excel_templates()


# ======================================================
# 🔷 FASTAPI INIT
# ======================================================
app = FastAPI()


app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/whatsapp_templates", StaticFiles(directory=WHATSAPP_TEMPLATES_DIR), name="whatsapp_templates")

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    if DEV_MODE:
        DATABASE_URL = "postgresql://mahir@localhost:5432/flockify1"
    else:
        raise RuntimeError("DATABASE_URL environment variable is required")
engine = create_engine(DATABASE_URL, future=True)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30

PASSWORD_ENC_KEY_BASE64 = os.getenv("PASSWORD_ENC_KEY_BASE64", base64.b64encode(b"0" * 32).decode())

# Allow comma-separated origins from env, with local dev fallbacks
FRONTEND_URLS = [u.strip() for u in FRONTEND_URL.split(",") if u.strip()]
_LOCAL_DEV = [
    "http://localhost:5173", "http://localhost:5174", "http://localhost:5175",
    "http://127.0.0.1:5173", "http://127.0.0.1:5174",
]
for u in _LOCAL_DEV:
    if u not in FRONTEND_URLS:
        FRONTEND_URLS.append(u)

try:
    _PASSWORD_ENC_KEY = base64.b64decode(PASSWORD_ENC_KEY_BASE64)
    if len(_PASSWORD_ENC_KEY) != 32:
        _PASSWORD_ENC_KEY = b"0" * 32
except Exception:
    _PASSWORD_ENC_KEY = b"0" * 32

# ======================================================
# 🔷 SMTP CONFIG (for password reset emails)
# ======================================================
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM") or SMTP_USERNAME
SMTP_USE_TLS = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_URLS,  # secure (explicit allowlist)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ======================================================
# 🔷 DB INITIALIZATION FUNCTION
# ======================================================
def init_db(engine):
    # ── Phase 1: DDL – all CREATE TABLE first, then all ALTER TABLE ───────────
    with engine.begin() as conn:

        # ── CREATE TABLES (FK dependency order) ──────────────────────────────

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS adminusers (
                admin_id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                farm_name TEXT,
                owner_name TEXT,
                phone_number TEXT,
                address TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS farms (
                farm_id SERIAL PRIMARY KEY,
                admin_id INTEGER NOT NULL REFERENCES adminusers(admin_id) ON DELETE CASCADE,
                farm_name TEXT NOT NULL,
                supervisor_name TEXT NOT NULL,
                supervisor_phone TEXT NOT NULL,
                farm_location TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sheds (
                shed_id SERIAL PRIMARY KEY,
                farm_id INTEGER NOT NULL REFERENCES farms(farm_id) ON DELETE CASCADE,
                shed_number TEXT NOT NULL,
                bird_category TEXT,
                bird_breed TEXT,
                initial_bird_count INTEGER,
                area_value NUMERIC NOT NULL,
                area_unit TEXT NOT NULL,
                placement_date DATE,
                shed_status TEXT NOT NULL DEFAULT 'active',
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS batches (
                batch_id SERIAL PRIMARY KEY,
                shed_id INTEGER NOT NULL REFERENCES sheds(shed_id) ON DELETE CASCADE,
                farm_id INTEGER NOT NULL REFERENCES farms(farm_id) ON DELETE CASCADE,
                placement_date DATE NOT NULL,
                depletion_date DATE,
                bird_category TEXT,
                bird_breed TEXT,
                initial_bird_count INTEGER NOT NULL,
                final_bird_count INTEGER,
                status TEXT NOT NULL DEFAULT 'active',
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS supervisors (
                supervisor_id SERIAL PRIMARY KEY,
                admin_id INTEGER NOT NULL REFERENCES adminusers(admin_id) ON DELETE CASCADE,
                farm_id INTEGER NOT NULL REFERENCES farms(farm_id) ON DELETE CASCADE,
                supervisor_name TEXT NOT NULL,
                supervisor_phone TEXT NOT NULL,
                supervisor_email TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dailyentries (
                entry_id SERIAL PRIMARY KEY,
                shed_id INTEGER NOT NULL REFERENCES sheds(shed_id) ON DELETE CASCADE,
                entry_date DATE NOT NULL,
                mortality INTEGER NOT NULL DEFAULT 0,
                culling INTEGER NOT NULL DEFAULT 0,
                culling_reason TEXT,
                feed_consumption_kg NUMERIC,
                temperature NUMERIC,
                ammonia_level INTEGER,
                medical_attention BOOLEAN DEFAULT FALSE,
                medical_notes TEXT,
                proof_pdf TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eggdailyrecords (
                egg_id SERIAL PRIMARY KEY,
                farm_id INTEGER NOT NULL REFERENCES farms(farm_id) ON DELETE CASCADE,
                shed_id INTEGER NOT NULL REFERENCES sheds(shed_id) ON DELETE CASCADE,
                batch_no TEXT NOT NULL,
                collection_date DATE NOT NULL DEFAULT CURRENT_DATE,
                collection_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
                good_eggs INTEGER NOT NULL DEFAULT 0,
                floor_eggs INTEGER NOT NULL DEFAULT 0,
                broken_cracked_eggs INTEGER NOT NULL DEFAULT 0,
                mishapped_eggs INTEGER NOT NULL DEFAULT 0,
                wastage INTEGER GENERATED ALWAYS AS (broken_cracked_eggs + mishapped_eggs) STORED,
                proof_pdf TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eggdispatchrecords (
                dispatch_id SERIAL PRIMARY KEY,
                farm_id INTEGER NOT NULL REFERENCES farms(farm_id) ON DELETE CASCADE,
                shed_id INTEGER REFERENCES sheds(shed_id) ON DELETE CASCADE,
                batch_id INTEGER REFERENCES batches(batch_id) ON DELETE CASCADE,
                dispatched_good_eggs INTEGER NOT NULL DEFAULT 0,
                dispatched_floor_mis_eggs INTEGER NOT NULL DEFAULT 0,
                dispatch_date DATE NOT NULL DEFAULT CURRENT_DATE,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eggfarmstockhistory (
                id SERIAL PRIMARY KEY,
                farm_id INTEGER NOT NULL REFERENCES farms(farm_id) ON DELETE CASCADE,
                record_date DATE NOT NULL,
                opening_good INTEGER NOT NULL DEFAULT 0,
                opening_floor_mis INTEGER NOT NULL DEFAULT 0,
                collected_good INTEGER NOT NULL DEFAULT 0,
                collected_floor_mis INTEGER NOT NULL DEFAULT 0,
                dispatched_good INTEGER NOT NULL DEFAULT 0,
                dispatched_floor_mis INTEGER NOT NULL DEFAULT 0,
                closing_good INTEGER NOT NULL,
                closing_floor_mis INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS birdstockhistory (
                id SERIAL PRIMARY KEY,
                shed_id INTEGER NOT NULL REFERENCES sheds(shed_id) ON DELETE CASCADE,
                entry_date DATE NOT NULL,
                mortality INTEGER NOT NULL DEFAULT 0,
                culling INTEGER NOT NULL DEFAULT 0,
                birds_opening INTEGER NOT NULL,
                birds_closing INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS birdtransfers (
                transfer_id SERIAL PRIMARY KEY,
                farm_id INTEGER NOT NULL REFERENCES farms(farm_id) ON DELETE CASCADE,
                from_shed_id INTEGER NOT NULL REFERENCES sheds(shed_id) ON DELETE CASCADE,
                to_shed_id INTEGER NOT NULL REFERENCES sheds(shed_id) ON DELETE CASCADE,
                bird_count INTEGER NOT NULL CHECK (bird_count > 0),
                transferred_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS weeklyentries (
                weekly_id SERIAL PRIMARY KEY,
                farm_id INT NOT NULL REFERENCES farms(farm_id) ON DELETE CASCADE,
                shed_id INT NOT NULL REFERENCES sheds(shed_id) ON DELETE CASCADE,
                entry_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                ammonia_level FLOAT,
                avg_bird_weight FLOAT,
                weekly_notes TEXT,
                proof_pdf TEXT
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS superadmins (
                super_admin_id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS allowedusers (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id SERIAL PRIMARY KEY,
                email TEXT NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

        # ── ALTER TABLES (all tables guaranteed to exist above) ───────────────

        conn.execute(text("""
            ALTER TABLE adminusers
            ADD COLUMN IF NOT EXISTS password_hash TEXT,
            ADD COLUMN IF NOT EXISTS password_salt TEXT,
            ADD COLUMN IF NOT EXISTS password_enc TEXT,
            ADD COLUMN IF NOT EXISTS password_nonce TEXT;
        """))

        conn.execute(text("""
            ALTER TABLE farms
            ADD COLUMN IF NOT EXISTS farm_owner_name TEXT,
            ADD COLUMN IF NOT EXISTS farm_owner_phone TEXT,
            ADD COLUMN IF NOT EXISTS farm_owner_email TEXT,
            ADD COLUMN IF NOT EXISTS farm_seq INTEGER;
        """))

        conn.execute(text("ALTER TABLE sheds ADD COLUMN IF NOT EXISTS shed_seq INTEGER;"))
        conn.execute(text("ALTER TABLE sheds ADD COLUMN IF NOT EXISTS no_of_feeders INTEGER;"))
        conn.execute(text("ALTER TABLE sheds ADD COLUMN IF NOT EXISTS no_of_water_nipples INTEGER;"))
        conn.execute(text("ALTER TABLE sheds ADD COLUMN IF NOT EXISTS perch_angle INTEGER;"))
        conn.execute(text("ALTER TABLE sheds ADD COLUMN IF NOT EXISTS perch_length_value NUMERIC;"))
        conn.execute(text("ALTER TABLE sheds ADD COLUMN IF NOT EXISTS perch_length_unit TEXT DEFAULT 'ft';"))
        conn.execute(text("ALTER TABLE sheds ADD COLUMN IF NOT EXISTS shed_type TEXT DEFAULT 'free_range';"))
        conn.execute(text("ALTER TABLE sheds ADD COLUMN IF NOT EXISTS open_area_value NUMERIC;"))
        conn.execute(text("ALTER TABLE sheds ADD COLUMN IF NOT EXISTS open_area_unit TEXT DEFAULT 'sqft';"))

        conn.execute(text("""
            ALTER TABLE dailyentries
            DROP COLUMN IF EXISTS ammonia_level,
            ADD COLUMN IF NOT EXISTS water_consumed_ltrs NUMERIC,
            ADD COLUMN IF NOT EXISTS lighting_hours NUMERIC,
            ADD COLUMN IF NOT EXISTS mortality_reason TEXT,
            ADD COLUMN IF NOT EXISTS batch_id INTEGER REFERENCES batches(batch_id);
        """))

        conn.execute(text("ALTER TABLE eggdailyrecords ADD COLUMN IF NOT EXISTS batch_id INTEGER REFERENCES batches(batch_id);"))

        conn.execute(text("ALTER TABLE eggdispatchrecords ADD COLUMN IF NOT EXISTS status TEXT;"))
        conn.execute(text("UPDATE eggdispatchrecords SET status = 'pending' WHERE status IS NULL;"))
        conn.execute(text("ALTER TABLE eggdispatchrecords ALTER COLUMN status SET DEFAULT 'pending';"))
        conn.execute(text("ALTER TABLE eggdispatchrecords ALTER COLUMN status SET NOT NULL;"))
        conn.execute(text("ALTER TABLE eggdispatchrecords ADD COLUMN IF NOT EXISTS shed_id INTEGER REFERENCES sheds(shed_id) ON DELETE CASCADE;"))
        conn.execute(text("ALTER TABLE eggdispatchrecords ADD COLUMN IF NOT EXISTS batch_id INTEGER REFERENCES batches(batch_id) ON DELETE CASCADE;"))
        conn.execute(text("ALTER TABLE eggdispatchrecords ADD COLUMN IF NOT EXISTS batch_no TEXT;"))
        conn.execute(text("ALTER TABLE eggdispatchrecords ADD COLUMN IF NOT EXISTS dispatched_good_eggs INTEGER NOT NULL DEFAULT 0;"))
        conn.execute(text("ALTER TABLE eggdispatchrecords ADD COLUMN IF NOT EXISTS dispatched_floor_mis_eggs INTEGER NOT NULL DEFAULT 0;"))
        conn.execute(text("ALTER TABLE eggdispatchrecords DROP COLUMN IF EXISTS dispatched_qty;"))
        conn.execute(text("""
            DO $$
            BEGIN
                ALTER TABLE eggdispatchrecords
                DROP CONSTRAINT IF EXISTS uq_eggdispatchrecords_shed_batch_date;
            EXCEPTION
                WHEN undefined_object THEN NULL;
            END $$;
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_eggdispatchrecords_shed_batch_date
            ON eggdispatchrecords (shed_id, batch_id, dispatch_date);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_eggdispatchrecords_shed_batch
            ON eggdispatchrecords (shed_id, batch_id);
        """))

        conn.execute(text("ALTER TABLE birdstockhistory ADD COLUMN IF NOT EXISTS batch_id INTEGER REFERENCES batches(batch_id) ON DELETE CASCADE;"))
        conn.execute(text("ALTER TABLE weeklyentries ADD COLUMN IF NOT EXISTS batch_id INTEGER REFERENCES batches(batch_id);"))

        for _drop_sql in (
            "DROP TABLE IF EXISTS warehouseeggintake CASCADE",
            "DROP TABLE IF EXISTS warehouseeggintakes CASCADE",
            "DROP TABLE IF EXISTS clientorders CASCADE",
            "DROP TABLE IF EXISTS dealtemplates CASCADE",
            "DROP TABLE IF EXISTS clients CASCADE",
            "DROP TABLE IF EXISTS warehouseadmins CASCADE",
        ):
            conn.execute(text(_drop_sql))

    # ── Phase 2: Auth columns (separate transaction so DDL commits first) ─────
    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE adminusers
            ADD COLUMN IF NOT EXISTS user_id TEXT,
            ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'admin',
            ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS last_login TIMESTAMP,
            ADD COLUMN IF NOT EXISTS last_entry_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS bcrypt_hash TEXT,
            ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS start_date DATE,
            ADD COLUMN IF NOT EXISTS end_date DATE;
        """))

    try:
        with engine.begin() as conn:
            conn.execute(text("""
                ALTER TABLE adminusers ADD CONSTRAINT adminusers_user_id_key UNIQUE (user_id);
            """))
    except Exception:
        pass

    # ── Phase 3: Data seeds (separate transaction) ───────────────────────────
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE adminusers SET user_id = email
            WHERE user_id IS NULL AND email IS NOT NULL;
        """))
        conn.execute(text("""
            UPDATE adminusers SET user_id = 'user_' || admin_id::text
            WHERE user_id IS NULL;
        """))
        conn.execute(text("""
            SELECT setval('adminusers_admin_id_seq',
                GREATEST((SELECT COALESCE(MAX(admin_id), 0) FROM adminusers), 1));
        """))

        _sa_hash = _bcrypt_lib.hashpw(b"admin123", _bcrypt_lib.gensalt()).decode()
        conn.execute(text("""
            INSERT INTO adminusers (user_id, email, name, role, must_change_password, bcrypt_hash)
            VALUES ('mahirmadhani@gmail.com', 'mahirmadhani@gmail.com', 'Super Admin', 'superadmin', false, :h)
            ON CONFLICT (email) DO UPDATE
                SET user_id              = 'mahirmadhani@gmail.com',
                    role                 = 'superadmin',
                    must_change_password = false,
                    bcrypt_hash          = COALESCE(adminusers.bcrypt_hash, EXCLUDED.bcrypt_hash);
        """), {"h": _sa_hash})

        conn.execute(text("""
            UPDATE farms f SET farm_seq = sub.rn
            FROM (SELECT farm_id, ROW_NUMBER() OVER (PARTITION BY admin_id ORDER BY farm_id) AS rn FROM farms) sub
            WHERE f.farm_id = sub.farm_id AND f.farm_seq IS NULL;
        """))
        conn.execute(text("""
            UPDATE sheds s SET shed_seq = sub.rn
            FROM (SELECT shed_id, ROW_NUMBER() OVER (PARTITION BY farm_id ORDER BY shed_id) AS rn FROM sheds) sub
            WHERE s.shed_id = sub.shed_id AND s.shed_seq IS NULL;
        """))


@app.on_event("startup")
def startup_event():
    try:
        print("🚀 Starting DB init...")
        init_db(engine)
        print("✅ DB init complete")
    except Exception as e:
        import traceback
        print("❌ DB INIT FAILED:", str(e))
        traceback.print_exc()


# ======================================================
# 🔷 BCRYPT HELPERS
# ======================================================
def _hash_password(password: str) -> str:
    return _bcrypt_lib.hashpw(password.encode(), _bcrypt_lib.gensalt()).decode()

def _verify_password(password: str, hashed: str) -> bool:
    try:
        return _bcrypt_lib.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


# ======================================================
# 🔷 JWT DEPENDENCIES
# ======================================================
def _decode_jwt(authorization: str | None) -> dict:
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_current_admin(authorization: str = Header(None)) -> int:
    payload = _decode_jwt(authorization)
    admin_id = payload.get("admin_id")
    if not admin_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return int(admin_id)


def _require_superadmin(authorization: str = Header(None)):
    payload = _decode_jwt(authorization)
    if payload.get("role") not in ("superadmin", "super_admin"):
        raise HTTPException(status_code=403, detail="Superadmin access required")


@app.get("/api/admin/all-data")
def admin_all_data(_=Depends(_require_superadmin)):
    try:
        with engine.begin() as conn:
            def fetch(sql):
                rows = conn.execute(text(sql)).mappings().fetchall()
                return [dict(r) for r in rows]

            # Summary stats
            stats = {}
            for tbl, col in [
                ("AdminUsers", "admin_id"), ("Farms", "farm_id"),
                ("Sheds", "shed_id"), ("Batches", "batch_id"),
                ("DailyEntries", "entry_id"), ("EggDailyRecords", "egg_id"),
                ("EggDispatchRecords", "dispatch_id"), ("WeeklyEntries", "weekly_id"),
            ]:
                try:
                    stats[tbl] = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar() or 0
                except Exception:
                    stats[tbl] = 0

            # Egg totals
            try:
                egg_totals = conn.execute(text("""
                    SELECT COALESCE(SUM(good_eggs),0) AS good,
                           COALESCE(SUM(floor_eggs),0) AS floor,
                           COALESCE(SUM(broken_cracked_eggs+mishapped_eggs),0) AS wastage
                    FROM EggDailyRecords
                """)).mappings().fetchone()
                stats["total_good_eggs"]   = int(egg_totals["good"])
                stats["total_floor_eggs"]  = int(egg_totals["floor"])
                stats["total_egg_wastage"] = int(egg_totals["wastage"])
            except Exception:
                pass

            # Active batches
            try:
                stats["active_batches"] = conn.execute(
                    text("SELECT COUNT(*) FROM Batches WHERE status='active'")).scalar() or 0
            except Exception:
                pass

            # Rich user list with farm counts
            users_rich = conn.execute(text("""
                SELECT u.admin_id, u.user_id, u.email, u.name, u.role,
                       u.must_change_password, u.is_active, u.start_date, u.end_date,
                       u.last_login, u.last_entry_at, u.created_at,
                       COUNT(DISTINCT f.farm_id) AS farms_count
                FROM AdminUsers u
                LEFT JOIN Farms f ON f.admin_id = u.admin_id
                GROUP BY u.admin_id
                ORDER BY u.admin_id
            """)).mappings().fetchall()

            return {
                "status":   True,
                "stats":    stats,
                "users":    [dict(r) for r in users_rich],
                "farms":    fetch("SELECT * FROM Farms ORDER BY created_at DESC"),
                "sheds":    fetch("SELECT * FROM Sheds ORDER BY created_at DESC"),
                "batches":  fetch("SELECT * FROM Batches ORDER BY created_at DESC"),
                "entries":  fetch("SELECT * FROM DailyEntries ORDER BY entry_date DESC LIMIT 500"),
                "egg":      fetch("SELECT * FROM EggDailyRecords ORDER BY collection_date DESC LIMIT 500"),
                "dispatch": fetch("SELECT * FROM EggDispatchRecords ORDER BY dispatch_date DESC LIMIT 500"),
                "weekly":   fetch("SELECT * FROM WeeklyEntries ORDER BY entry_date DESC LIMIT 500"),
            }
    except Exception as e:
        print("\u274c admin all-data error:", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/user-drill/{target_admin_id}")
def admin_user_drill(target_admin_id: int, _=Depends(_require_superadmin)):
    """Superadmin drill-down: all data for one user."""
    try:
        with engine.begin() as conn:
            def fetch_d(sql, params=None):
                rows = conn.execute(text(sql), params or {}).mappings().fetchall()
                return [dict(r) for r in rows]

            user = fetch_d(
                "SELECT admin_id, user_id, email, name, role, last_login, last_entry_at, created_at FROM AdminUsers WHERE admin_id=:aid",
                {"aid": target_admin_id}
            )
            if not user:
                raise HTTPException(404, "User not found")

            farms = fetch_d("SELECT * FROM Farms WHERE admin_id=:aid ORDER BY created_at DESC", {"aid": target_admin_id})
            farm_ids = [f["farm_id"] for f in farms]

            if not farm_ids:
                return {"status": True, "user": user[0], "farms": [], "sheds": [], "batches": [], "entries": [], "egg": [], "dispatch": []}

            id_list = ",".join(str(i) for i in farm_ids)
            sheds    = fetch_d(f"SELECT * FROM Sheds WHERE farm_id IN ({id_list}) ORDER BY created_at DESC")
            batches  = fetch_d(f"SELECT * FROM Batches WHERE farm_id IN ({id_list}) ORDER BY created_at DESC")
            entries  = fetch_d(f"SELECT * FROM DailyEntries WHERE shed_id IN (SELECT shed_id FROM Sheds WHERE farm_id IN ({id_list})) ORDER BY entry_date DESC LIMIT 200")
            egg      = fetch_d(f"SELECT * FROM EggDailyRecords WHERE farm_id IN ({id_list}) ORDER BY collection_date DESC LIMIT 200")
            dispatch = fetch_d(f"SELECT * FROM EggDispatchRecords WHERE farm_id IN ({id_list}) ORDER BY dispatch_date DESC LIMIT 200")

            return {"status": True, "user": user[0], "farms": farms, "sheds": sheds,
                    "batches": batches, "entries": entries, "egg": egg, "dispatch": dispatch}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

from fastapi import Cookie

@app.post("/api/logout")
def logout():
    from fastapi.responses import JSONResponse as _JSONResponse
    response = _JSONResponse(content={"message": "Logged out"})
    response.delete_cookie("access_token")
    return response


# ======================================================
# NEW AUTH ENDPOINTS
# ======================================================

class AuthLoginModel(BaseModel):
    user_id: str
    password: str


class AuthChangePasswordModel(BaseModel):
    current_password: str
    new_password: str


class AuthCreateUserModel(BaseModel):
    user_id: str
    name: str
    email: str | None = None
    temp_password: str
    role: str = "admin"


class AuthResetPasswordModel(BaseModel):
    target_user_id: str
    new_password: str


def _update_last_entry_at(conn, admin_id: int):
    """Stamp last_entry_at inside an active transaction."""
    try:
        conn.execute(text(
            "UPDATE AdminUsers SET last_entry_at=NOW() WHERE admin_id=:aid"
        ), {"aid": admin_id})
    except Exception:
        pass


@app.post("/api/auth/login")
def auth_login(data: AuthLoginModel):
    with engine.begin() as conn:
        identifier = data.user_id.strip()
        # Accept login by user_id OR by email (whichever matches first)
        row = conn.execute(text("""
            SELECT admin_id, user_id, email, name, role,
                   bcrypt_hash, must_change_password, is_active, end_date
            FROM AdminUsers
            WHERE user_id = :uid OR email = :uid
            ORDER BY
                CASE WHEN user_id = :uid THEN 0 ELSE 1 END
            LIMIT 1
        """), {"uid": identifier}).mappings().fetchone()

        if not row or not row["bcrypt_hash"]:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if not _verify_password(data.password, row["bcrypt_hash"]):
            raise HTTPException(status_code=401, detail="Invalid user ID or password")

        if not row["is_active"]:
            raise HTTPException(status_code=403, detail="Account is disabled. Contact your administrator.")

        if row["end_date"] and row["end_date"] < date.today():
            raise HTTPException(status_code=403, detail="Account access has expired. Contact your administrator.")

        conn.execute(text(
            "UPDATE AdminUsers SET last_login=NOW() WHERE admin_id=:aid"
        ), {"aid": row["admin_id"]})

    token = create_access_token({
        "admin_id": row["admin_id"],
        "user_id":  row["user_id"],
        "role":     row["role"],
    }, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    return {
        "status": True,
        "access_token": token,
        "must_change_password": bool(row["must_change_password"]),
        "data": {
            "admin_id": row["admin_id"],
            "user_id":  row["user_id"],
            "name":     row["name"],
            "email":    row["email"],
            "role":     row["role"],
        },
    }


@app.post("/api/auth/change-password")
def auth_change_password(
    data: AuthChangePasswordModel,
    authorization: str = Header(None),
):
    payload = _decode_jwt(authorization)
    admin_id = int(payload["admin_id"])

    if len(data.new_password) < 6:
        raise HTTPException(400, "New password must be at least 6 characters")

    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT bcrypt_hash, must_change_password FROM AdminUsers WHERE admin_id=:aid"
        ), {"aid": admin_id}).mappings().fetchone()

        if not row:
            raise HTTPException(404, "User not found")

        if not row["must_change_password"]:
            if not row["bcrypt_hash"] or not _verify_password(data.current_password, row["bcrypt_hash"]):
                raise HTTPException(401, "Current password is incorrect")

        new_hash = _hash_password(data.new_password)
        conn.execute(text("""
            UPDATE AdminUsers
            SET bcrypt_hash=:h, must_change_password=false
            WHERE admin_id=:aid
        """), {"h": new_hash, "aid": admin_id})

    return {"status": True, "message": "Password changed successfully"}


@app.post("/api/auth/create-user")
def auth_create_user(data: AuthCreateUserModel, _=Depends(_require_superadmin)):
    if len(data.temp_password) < 6:
        raise HTTPException(400, "Temp password must be at least 6 characters")
    if data.role not in ("admin", "superadmin"):
        raise HTTPException(400, "Role must be admin or superadmin")

    hashed = _hash_password(data.temp_password)
    try:
        with engine.begin() as conn:
            existing = conn.execute(text(
                "SELECT admin_id FROM AdminUsers WHERE user_id=:uid"
            ), {"uid": data.user_id.strip()}).fetchone()
            if existing:
                raise HTTPException(409, f"user_id already exists")

            new_user = conn.execute(text("""
                INSERT INTO AdminUsers (user_id, email, name, role, bcrypt_hash, must_change_password)
                VALUES (:uid, :email, :name, :role, :h, true)
                RETURNING admin_id, user_id, email, name, role, must_change_password, created_at
            """), {
                "uid":   data.user_id.strip(),
                "email": data.email or f"{data.user_id}@flockify.local",
                "name":  data.name,
                "role":  data.role,
                "h":     hashed,
            }).mappings().fetchone()

        return {"status": True, "message": "User created", "data": dict(new_user)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/auth/reset-password")
def auth_reset_password(data: AuthResetPasswordModel, _=Depends(_require_superadmin)):
    if len(data.new_password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    hashed = _hash_password(data.new_password)
    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE AdminUsers
            SET bcrypt_hash=:h, must_change_password=true
            WHERE user_id=:uid
            RETURNING admin_id, user_id, name
        """), {"h": hashed, "uid": data.target_user_id}).mappings().fetchone()

        if not result:
            raise HTTPException(404, f"user_id not found")

    return {"status": True, "message": f"Password reset for {data.target_user_id}"}


@app.post("/api/admin/toggle-user")
def admin_toggle_user(data: dict, _=Depends(_require_superadmin)):
    """Enable or disable a user account. Cannot disable superadmin."""
    target_user_id = data.get("target_user_id")
    if not target_user_id:
        raise HTTPException(400, "target_user_id required")
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT admin_id, role, is_active FROM AdminUsers WHERE user_id=:uid"
        ), {"uid": target_user_id}).mappings().fetchone()
        if not row:
            raise HTTPException(404, "User not found")
        if row["role"] in ("superadmin", "super_admin"):
            raise HTTPException(400, "Cannot disable a superadmin account")
        new_state = not bool(row["is_active"])
        conn.execute(text(
            "UPDATE AdminUsers SET is_active=:s WHERE user_id=:uid"
        ), {"s": new_state, "uid": target_user_id})
    return {"status": True, "is_active": new_state,
            "message": f"User {'enabled' if new_state else 'disabled'}"}


@app.post("/api/admin/set-validity")
def admin_set_validity(data: dict, _=Depends(_require_superadmin)):
    """Set start_date / end_date for a user. end_date=null means unlimited."""
    target_user_id = data.get("target_user_id")
    if not target_user_id:
        raise HTTPException(400, "target_user_id required")
    start_d = data.get("start_date")  # ISO string or null
    end_d   = data.get("end_date")    # ISO string or null
    try:
        sd = date.fromisoformat(start_d) if start_d else None
        ed = date.fromisoformat(end_d)   if end_d   else None
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD.")
    with engine.begin() as conn:
        row = conn.execute(text("SELECT admin_id FROM AdminUsers WHERE user_id=:uid"), {"uid": target_user_id}).fetchone()
        if not row:
            raise HTTPException(404, "User not found")
        conn.execute(text(
            "UPDATE AdminUsers SET start_date=:sd, end_date=:ed WHERE user_id=:uid"
        ), {"sd": sd, "ed": ed, "uid": target_user_id})
    return {"status": True, "message": "Validity updated",
            "start_date": str(sd) if sd else None,
            "end_date": str(ed) if ed else None}


@app.get("/api/admin/export-user/{target_admin_id}")
def admin_export_user(target_admin_id: int, _=Depends(_require_superadmin)):
    """Export all user data as human-readable multi-sheet Excel."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, PatternFill
    from openpyxl.utils import get_column_letter
    from fastapi.responses import StreamingResponse
    import io

    def fmt_d(v):
        """Format a date/datetime value as DD/MM/YYYY."""
        if v is None: return ""
        try:
            s = str(v).split("T")[0].split(" ")[0]
            y, m, d_ = s.split("-")
            return f"{d_}/{m}/{y}"
        except Exception:
            return str(v)

    with engine.begin() as conn:
        def fetch(sql, params=None):
            return [dict(r) for r in conn.execute(text(sql), params or {}).mappings().fetchall()]

        user = conn.execute(text(
            "SELECT admin_id, user_id, email, name, role, created_at, end_date FROM AdminUsers WHERE admin_id=:aid"
        ), {"aid": target_admin_id}).mappings().fetchone()
        if not user:
            raise HTTPException(404, "User not found")
        user = dict(user)
        user_name = user.get("name") or user.get("user_id") or str(target_admin_id)

        farms = fetch(
            "SELECT farm_id, farm_seq, farm_name, farm_location, farm_owner_name, supervisor_name, supervisor_phone, created_at "
            "FROM Farms WHERE admin_id=:aid ORDER BY COALESCE(farm_seq,farm_id)",
            {"aid": target_admin_id}
        )
        farm_ids = [f["farm_id"] for f in farms]

        if not farm_ids:
            sheds = daily = egg = dispatch = weekly = []
        else:
            id_csv = ",".join(str(i) for i in farm_ids)
            sheds = fetch(
                f"SELECT s.shed_id, s.shed_seq, s.shed_number, s.bird_category, s.bird_breed, "
                f"s.initial_bird_count, s.placement_date, s.shed_type, s.shed_status, f.farm_name "
                f"FROM Sheds s JOIN Farms f ON f.farm_id=s.farm_id "
                f"WHERE s.farm_id IN ({id_csv}) ORDER BY f.farm_id, COALESCE(s.shed_seq,s.shed_id)"
            )
            shed_ids = ",".join(str(s["shed_id"]) for s in sheds) if sheds else "0"
            daily = fetch(
                f"SELECT f.farm_name, s.shed_number, de.entry_date, "
                f"de.mortality, de.mortality_reason, de.culling, de.culling_reason, "
                f"de.feed_consumption_kg, de.water_consumed_ltrs, de.lighting_hours, "
                f"de.temperature, de.medical_attention, de.medical_notes "
                f"FROM DailyEntries de "
                f"JOIN Sheds s ON s.shed_id=de.shed_id "
                f"JOIN Farms f ON f.farm_id=s.farm_id "
                f"WHERE de.shed_id IN ({shed_ids}) "
                f"ORDER BY f.farm_name, s.shed_number, de.entry_date"
            )
            egg = fetch(
                f"SELECT f.farm_name, s.shed_number, er.collection_date AS entry_date, "
                f"er.good_eggs, er.floor_eggs, er.broken_cracked_eggs, er.mishapped_eggs, "
                f"(er.good_eggs + er.floor_eggs + er.broken_cracked_eggs + er.mishapped_eggs) AS total_eggs "
                f"FROM EggDailyRecords er "
                f"JOIN Sheds s ON s.shed_id=er.shed_id "
                f"JOIN Farms f ON f.farm_id=s.farm_id "
                f"WHERE er.shed_id IN ({shed_ids}) "
                f"ORDER BY f.farm_name, s.shed_number, er.collection_date"
            )
            dispatch = fetch(
                f"SELECT f.farm_name, s.shed_number, dr.dispatch_date AS entry_date, "
                f"dr.dispatched_good_eggs, dr.dispatched_floor_mis_eggs, "
                f"(dr.dispatched_good_eggs + dr.dispatched_floor_mis_eggs) AS total_dispatched "
                f"FROM EggDispatchRecords dr "
                f"JOIN Sheds s ON s.shed_id=dr.shed_id "
                f"JOIN Farms f ON f.farm_id=s.farm_id "
                f"WHERE dr.shed_id IN ({shed_ids}) "
                f"ORDER BY f.farm_name, s.shed_number, dr.dispatch_date"
            )
            weekly = fetch(
                f"SELECT f.farm_name, s.shed_number, we.entry_date, "
                f"we.ammonia_level, we.avg_bird_weight, we.weekly_notes "
                f"FROM WeeklyEntries we "
                f"JOIN Sheds s ON s.shed_id=we.shed_id "
                f"JOIN Farms f ON f.farm_id=s.farm_id "
                f"WHERE we.shed_id IN ({shed_ids}) "
                f"ORDER BY f.farm_name, s.shed_number, we.entry_date"
            )

    wb = Workbook()
    BLUE  = "2563EB"; LBLUE = "DBEAFE"; GRAY = "F8FAFC"; DKGRAY = "475569"
    hdr_font  = Font(bold=True, color="FFFFFF", size=10)
    hdr_fill  = PatternFill("solid", fgColor=BLUE)
    sub_font  = Font(bold=True, color=DKGRAY, size=10)
    sub_fill  = PatternFill("solid", fgColor=LBLUE)
    ctr       = Alignment(horizontal="center", vertical="center")
    thin      = Border(bottom=Side(style="thin", color="E2E8F0"))

    # Human-readable column display names
    COL_NAMES = {
        "farm_name": "Farm Name", "shed_number": "Shed",
        "entry_date": "Date", "collection_date": "Date", "dispatch_date": "Date",
        "mortality": "Mortality", "mortality_reason": "Mortality Reason",
        "culling": "Culling", "culling_reason": "Culling Reason",
        "feed_consumption_kg": "Feed (kg)", "water_consumed_ltrs": "Water (L)",
        "lighting_hours": "Lighting (hrs)", "temperature": "Temp (°C)",
        "medical_attention": "Medical", "medical_notes": "Notes",
        "good_eggs": "Good Eggs", "floor_eggs": "Floor Eggs",
        "broken_cracked_eggs": "Broken/Cracked", "mishapped_eggs": "Mishapped",
        "total_eggs": "Total Eggs",
        "dispatched_good_eggs": "Good Dispatched", "dispatched_floor_mis_eggs": "Floor/Mis Dispatched",
        "total_dispatched": "Total Dispatched",
        "ammonia_level": "Ammonia (ppm)", "avg_bird_weight": "Avg Weight (g)",
        "weekly_notes": "Notes",
        "farm_seq": "Farm #", "shed_seq": "Shed #",
        "bird_category": "Category", "bird_breed": "Breed",
        "initial_bird_count": "Initial Birds", "placement_date": "Placement Date",
        "shed_type": "Shed Type", "shed_status": "Status",
        "farm_location": "Location", "farm_owner_name": "Owner",
        "supervisor_name": "Supervisor", "supervisor_phone": "Supervisor Phone",
    }
    DATE_COLS = {"entry_date", "collection_date", "dispatch_date", "placement_date", "created_at"}

    def col_label(k): return COL_NAMES.get(k, k.replace("_", " ").title())

    def auto_width(ws):
        for col in ws.columns:
            width = max((len(str(c.value or "")) for c in col), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 42)

    def write_data_sheet(ws, rows_data, date_col="entry_date"):
        if not rows_data:
            ws.append(["No data for this user."]); return
        keys = list(rows_data[0].keys())
        # Header row
        ws.append([col_label(k) for k in keys])
        for cell in ws[ws.max_row]:
            cell.font = hdr_font; cell.fill = hdr_fill; cell.alignment = ctr
        # Group rows: add a subtle separator row when farm or shed changes
        prev_farm = prev_shed = None
        for row in rows_data:
            farm = row.get("farm_name", "")
            shed = row.get("shed_number", "")
            if (farm, shed) != (prev_farm, prev_shed) and prev_farm is not None:
                # blank separator
                ws.append([""] * len(keys))
            # Sub-header when farm/shed group changes
            if (farm, shed) != (prev_farm, prev_shed):
                label = f"{farm}  ›  Shed: {shed}" if shed else farm
                ws.append([label] + [""] * (len(keys) - 1))
                for cell in ws[ws.max_row]:
                    cell.font = sub_font; cell.fill = sub_fill
                prev_farm, prev_shed = farm, shed
            vals = []
            for k in keys:
                v = row.get(k)
                if k in DATE_COLS:
                    vals.append(fmt_d(v))
                elif v is None:
                    vals.append("")
                elif isinstance(v, bool):
                    vals.append("Yes" if v else "No")
                else:
                    vals.append(v)
            ws.append(vals)
            for cell in ws[ws.max_row]:
                cell.border = thin
        auto_width(ws)

    # ── Sheet 1: Summary ──────────────────────────────────────────────────────
    ws0 = wb.active
    ws0.title = "Summary"
    ws0.append(["Flockify Data Export"])
    ws0["A1"].font = Font(bold=True, size=14, color=BLUE)
    ws0.append([])
    ws0.append(["User Name",   user_name])
    ws0.append(["User ID",     user.get("user_id", "")])
    ws0.append(["Email",       user.get("email", "")])
    ws0.append(["Role",        user.get("role", "")])
    ws0.append(["Exported On", fmt_d(str(date.today()))])
    ws0.append([])
    ws0.append(["Farms",            len(farms)])
    ws0.append(["Sheds",            len(sheds)])
    ws0.append(["Daily Entries",    len(daily)])
    ws0.append(["Egg Records",      len(egg)])
    ws0.append(["Dispatch Records", len(dispatch)])
    ws0.append(["Weekly Entries",   len(weekly)])
    ws0.append([])
    if farms:
        ws0.append(["Farm #", "Farm Name", "Location", "Sheds"])
        for cell in ws0[ws0.max_row]: cell.font = sub_font; cell.fill = sub_fill
        for f in farms:
            shed_count = sum(1 for s in sheds if s.get("farm_name") == f["farm_name"])
            ws0.append([f.get("farm_seq") or "—", f["farm_name"], f.get("farm_location") or "—", shed_count])
    ws0.column_dimensions["A"].width = 22
    ws0.column_dimensions["B"].width = 36

    # ── Sheets 2-5: Data by type ─────────────────────────────────────────────
    ws_d = wb.create_sheet("Daily Entries")
    write_data_sheet(ws_d, daily)

    ws_e = wb.create_sheet("Egg Collection")
    write_data_sheet(ws_e, egg, date_col="entry_date")

    ws_x = wb.create_sheet("Egg Dispatch")
    write_data_sheet(ws_x, dispatch, date_col="entry_date")

    ws_w = wb.create_sheet("Weekly Entries")
    write_data_sheet(ws_w, weekly)

    # ── Sheet 6: Farm & Shed reference ───────────────────────────────────────
    ws_f = wb.create_sheet("Farms & Sheds")
    if sheds:
        shed_keys = ["farm_name", "shed_number", "shed_seq", "bird_category", "bird_breed",
                     "initial_bird_count", "placement_date", "shed_type", "shed_status"]
        ws_f.append([col_label(k) for k in shed_keys])
        for cell in ws_f[1]: cell.font = hdr_font; cell.fill = hdr_fill; cell.alignment = ctr
        for row in sheds:
            ws_f.append([
                fmt_d(row.get(k)) if k in DATE_COLS else (row.get(k) if row.get(k) is not None else "")
                for k in shed_keys
            ])
            for cell in ws_f[ws_f.max_row]: cell.border = thin
        auto_width(ws_f)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (user.get("user_id") or str(target_admin_id)))
    filename = f"export_{safe}_{date.today()}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Legacy login endpoint — supports both user_id and email key
@app.post("/api/login")
async def login_legacy(request: Request):
    body = await request.json()
    uid = body.get("user_id") or body.get("email", "")
    pwd = body.get("password", "")
    return auth_login(AuthLoginModel(user_id=uid, password=pwd))


# Superadmin login via user_id/password
@app.post("/api/superadmin_login")
async def superadmin_login_legacy(request: Request):
    body = await request.json()
    uid = body.get("user_id") or body.get("email", "superadmin")
    pwd = body.get("password", "")
    result = auth_login(AuthLoginModel(user_id=uid, password=pwd))
    if result["data"]["role"] not in ("superadmin", "super_admin"):
        raise HTTPException(403, "Not a superadmin account")
    result["token"] = result["access_token"]
    return result
# ======================================================
# 🔷 PASSWORD CRYPTO HELPERS (AES-256-GCM + PBKDF2)
# ======================================================
_PBKDF2_ITERS = 200_000

def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")

def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("utf-8"))

def _pbkdf2_hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERS, dklen=32)

def encrypt_password(password: str, email: str) -> dict:
    salt = secrets.token_bytes(16)
    pwd_hash = _pbkdf2_hash(password, salt)

    nonce = secrets.token_bytes(12)  # AESGCM nonce must be unique
    aesgcm = AESGCM(_PASSWORD_ENC_KEY)
    ct = aesgcm.encrypt(nonce, password.encode("utf-8"), email.lower().encode("utf-8"))

    return {
        "password_hash": _b64e(pwd_hash),
        "password_salt": _b64e(salt),
        "password_enc": _b64e(ct),
        "password_nonce": _b64e(nonce),
    }

def verify_password(password: str, email: str, password_hash_b64: str, password_salt_b64: str) -> bool:
    try:
        salt = _b64d(password_salt_b64)
        expected = _b64d(password_hash_b64)
    except Exception:
        return False

    computed = _pbkdf2_hash(password, salt)
    return hmac.compare_digest(computed, expected)

# ======================================================
# 🔷 PASSWORD RESET (email reset link via SMTP)
# ======================================================
class PasswordResetRequestModel(BaseModel):
    email: EmailStr


class PasswordResetConfirmModel(BaseModel):
    token: str
    new_password: str


def _hash_reset_token(token: str) -> str:
    # Hash the raw token before storing (so DB compromise won't reveal tokens)
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _generate_reset_token() -> str:
    # URL-safe raw token that we only send via email (never store raw)
    return secrets.token_urlsafe(48)


def _send_password_reset_email(to_email: str, reset_url: str) -> None:
    print(f"EMAIL SKIPPED - DEV MODE | To: {to_email} | URL: {reset_url}")


@app.post("/api/password_reset/request")
async def password_reset_request(
    data: PasswordResetRequestModel,
    origin: Optional[str] = Header(None),
):
    email = data.email.lower().strip()

    # Pick the best frontend base for reset link (use request Origin if it matches)
    frontend_base = FRONTEND_URLS[0]
    if origin and origin in FRONTEND_URLS:
        frontend_base = origin

    # Always return a generic message to avoid user enumeration.
    generic_response = {
        "status": True,
        "message": "If the email exists, we sent a password reset link.",
    }

    try:
        with engine.begin() as conn:
            allowed = conn.execute(
                text("SELECT * FROM AllowedUsers WHERE email = :email"),
                {"email": email},
            ).mappings().fetchone()

            if not allowed:
                return generic_response

            # Invalidate previous unused tokens for this email
            conn.execute(
                text("""
                    UPDATE password_reset_tokens
                    SET used_at = NOW()
                    WHERE email = :email AND used_at IS NULL
                """),
                {"email": email},
            )

            token = _generate_reset_token()
            token_hash = _hash_reset_token(token)
            conn.execute(
                text("""
                    INSERT INTO password_reset_tokens (email, token_hash, expires_at, used_at)
                    VALUES (:email, :token_hash, NOW() + INTERVAL '30 minutes', NULL)
                """),
                {
                    "email": email,
                    "token_hash": token_hash,
                },
            )

        reset_url = f"{frontend_base}/reset-password?token={token}"
        _send_password_reset_email(email, reset_url)
    except Exception as e:
        # Do not reveal internals to the client; just log server-side.
        print("❌ Password reset request error:", str(e))

    return generic_response


@app.post("/api/password_reset/confirm")
async def password_reset_confirm(data: PasswordResetConfirmModel):
    token = data.token
    new_password = data.new_password

    if not token or len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Invalid token or password.")

    token_hash = _hash_reset_token(token)

    with engine.begin() as conn:
        row = conn.execute(
            text("""
                SELECT email
                FROM password_reset_tokens
                WHERE token_hash = :token_hash
                  AND used_at IS NULL
                  AND expires_at > NOW()
                LIMIT 1
            """),
            {"token_hash": token_hash},
        ).mappings().fetchone()

        if not row:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token.")

        email = str(row["email"]).lower()

        allowed = conn.execute(
            text("SELECT * FROM AllowedUsers WHERE email = :email"),
            {"email": email},
        ).mappings().fetchone()

        if not allowed:
            raise HTTPException(status_code=403, detail="Email is not allowed.")

        # Encrypt + hash password fields (PBKDF2 hash + AES-256-GCM encryption)
        enc = encrypt_password(new_password, email)

        admin = conn.execute(
            text("SELECT * FROM AdminUsers WHERE email = :email"),
            {"email": email},
        ).mappings().fetchone()

        if admin:
            conn.execute(
                text("""
                    UPDATE AdminUsers
                    SET password_hash = :password_hash,
                        password_salt = :password_salt,
                        password_enc = :password_enc,
                        password_nonce = :password_nonce
                    WHERE email = :email
                """),
                {"email": email, **enc},
            )
        else:
            # SQLAlchemy row mappings behave like dicts; access via keys to avoid .get surprises
            name = allowed["name"] if allowed and allowed["name"] else email
            conn.execute(
                text("""
                    INSERT INTO AdminUsers (email, name, password_hash, password_salt, password_enc, password_nonce)
                    VALUES (:email, :name, :password_hash, :password_salt, :password_enc, :password_nonce)
                """),
                {"email": email, "name": name, **enc},
            )

        conn.execute(
            text("""
                UPDATE password_reset_tokens
                SET used_at = NOW()
                WHERE token_hash = :token_hash
            """),
            {"token_hash": token_hash},
        )

    return {"status": True, "message": "Password reset successful. You can now log in."}

# Dummy JWT creation — Add your real JWT function here
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


class AdminAuthModel(BaseModel):
    email: EmailStr
    password: str


@app.post("/api/login")
async def login(data: AdminAuthModel):
    print(f"DEV MODE: Auto-login for {data.email}")
    return {"status": True, "access_token": "dev", "data": {"admin_id": 1}}


class AdminFarmUpdate(BaseModel):
    farm_name: str
    owner_name: str
    phone_number: str
    address: str

@app.post("/api/admin_update_details")
async def admin_update_details(admin_id: int, data: AdminFarmUpdate):

    try:
        with engine.begin() as conn:

            updated = conn.execute(
                text("""
                    UPDATE AdminUsers
                    SET farm_name = :farm_name,
                        owner_name = :owner_name,
                        phone_number = :phone_number,
                        address = :address
                    WHERE admin_id = :admin_id
                    RETURNING admin_id, email, name, farm_name, owner_name, phone_number, address, created_at
                """),
                {
                    "farm_name": data.farm_name,
                    "owner_name": data.owner_name,
                    "phone_number": data.phone_number,
                    "address": data.address,
                    "admin_id": admin_id
                }
            ).mappings().fetchone()

            if not updated:
                raise HTTPException(404, "Admin not found")

            print("✅ Admin details updated:", updated["admin_id"])

            return {
                "status": True,
                "message": "Admin details updated",
                "data": updated
            }

    except Exception as e:
        print("❌ Admin update error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

class AddFarmModel(BaseModel):
    farm_name: str

    farm_owner_name: str
    farm_owner_phone: str
    farm_owner_email: str

    supervisor_name: str
    supervisor_phone: str
    farm_location: str

@app.post("/api/add_farm")
async def add_farm(
    data: AddFarmModel,
    admin_id: int = Depends(get_current_admin)
):

    try:
        with engine.begin() as conn:

            # 1️⃣ Create the farm (admin_id comes from JWT)
            new_farm = conn.execute(
                text("""
                    INSERT INTO Farms (
                        admin_id, farm_seq,
                        farm_name,
                        farm_owner_name, farm_owner_phone, farm_owner_email,
                        supervisor_name, supervisor_phone, farm_location
                    )
                    VALUES (
                        :admin_id,
                        (SELECT COALESCE(MAX(farm_seq), 0) + 1 FROM Farms WHERE admin_id = :admin_id),
                        :farm_name,
                        :farm_owner_name, :farm_owner_phone, :farm_owner_email,
                        :supervisor_name, :supervisor_phone, :farm_location
                    )
                    RETURNING *
                """),
                {
                    "admin_id": admin_id,
                    "farm_name": data.farm_name,
                    "farm_owner_name": data.farm_owner_name,
                    "farm_owner_phone": data.farm_owner_phone,
                    "farm_owner_email": data.farm_owner_email,
                    "supervisor_name": data.supervisor_name,
                    "supervisor_phone": data.supervisor_phone,
                    "farm_location": data.farm_location,
                }
            ).mappings().fetchone()

            farm_id = new_farm["farm_id"]

            # 2️⃣ Create Supervisor record
            conn.execute(
                text("""
                    INSERT INTO Supervisors (
                        admin_id,
                        farm_id,
                        supervisor_name,
                        supervisor_phone,
                        supervisor_email
                    )
                    VALUES (
                        :admin_id,
                        :farm_id,
                        :supervisor_name,
                        :supervisor_phone,
                        :supervisor_email
                    )
                """),
                {
                    "admin_id": admin_id,
                    "farm_id": farm_id,
                    "supervisor_name": data.supervisor_name,
                    "supervisor_phone": data.supervisor_phone,
                    "supervisor_email": data.farm_owner_email
                }
            )

        print("✅ Farm created:", dict(new_farm))

        return {
            "status": True,
            "message": "Farm + Supervisor created successfully",
            "data": dict(new_farm)
        }

    except Exception as e:
        print("❌ Error adding farm:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/farms")
async def get_farms(
    admin_id: int = Depends(get_current_admin)
):

    try:
        with engine.begin() as conn:
            farms = conn.execute(
                text("""
                    SELECT
                        farm_id,
                        farm_name,
                        farm_owner_name,
                        farm_owner_phone,
                        farm_owner_email,
                        supervisor_name,
                        supervisor_phone,
                        farm_location,
                        created_at
                    FROM Farms
                    WHERE admin_id = :admin_id
                    ORDER BY created_at DESC
                """),
                {"admin_id": admin_id}
            ).mappings().fetchall()

        return {
            "status": True,
            "data": [dict(f) for f in farms]
        }

    except Exception as e:
        print("❌ Error fetching farms:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


class UpdateFarmModel(BaseModel):
    farm_name: str

    farm_owner_name: str
    farm_owner_phone: str
    farm_owner_email: str

    supervisor_name: str
    supervisor_phone: str
    farm_location: str
@app.put("/api/update_farm")
async def update_farm(
    farm_id: int,
    data: UpdateFarmModel,
    admin_id: int = Depends(get_current_admin)
):

    try:
        with engine.begin() as conn:

            # 🔐 1️⃣ Verify ownership
            farm_check = conn.execute(text("""
                SELECT farm_id
                FROM Farms
                WHERE farm_id = :fid
                  AND admin_id = :aid
            """), {
                "fid": farm_id,
                "aid": admin_id
            }).fetchone()

            if not farm_check:
                raise HTTPException(
                    status_code=403,
                    detail="Not authorized to update this farm"
                )

            # 2️⃣ Perform update
            updated = conn.execute(text("""
                UPDATE Farms
                SET 
                    farm_name = :farm_name,

                    farm_owner_name = :farm_owner_name,
                    farm_owner_phone = :farm_owner_phone,
                    farm_owner_email = :farm_owner_email,

                    supervisor_name = :supervisor_name,
                    supervisor_phone = :supervisor_phone,
                    farm_location = :farm_location
                WHERE farm_id = :farm_id
                RETURNING *
            """), {
                "farm_id": farm_id,
                "farm_name": data.farm_name,
                "farm_owner_name": data.farm_owner_name,
                "farm_owner_phone": data.farm_owner_phone,
                "farm_owner_email": data.farm_owner_email,
                "supervisor_name": data.supervisor_name,
                "supervisor_phone": data.supervisor_phone,
                "farm_location": data.farm_location,
            }).mappings().fetchone()

        if not updated:
            raise HTTPException(status_code=404, detail="Farm not found")

        print("✅ Farm updated:", dict(updated))

        return {
            "status": True,
            "message": "Farm updated successfully",
            "data": dict(updated)
        }

    except HTTPException:
        raise

    except Exception as e:
        print("❌ Error updating farm:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
@app.delete("/api/delete_farm")
async def delete_farm(
    farm_id: int,
    admin_id: int = Depends(get_current_admin)
):

    try:
        with engine.begin() as conn:

            # 🔐 1️⃣ Verify farm belongs to this admin
            farm = conn.execute(
                text("""
                    SELECT farm_id
                    FROM Farms
                    WHERE farm_id = :fid
                      AND admin_id = :aid
                """),
                {
                    "fid": farm_id,
                    "aid": admin_id
                }
            ).fetchone()

            if not farm:
                raise HTTPException(
                    status_code=403,
                    detail="Not authorized to delete this farm"
                )

            # 2️⃣ Delete farm (cascade handles sheds, batches, etc.)
            conn.execute(
                text("""
                    DELETE FROM Farms
                    WHERE farm_id = :fid
                """),
                {"fid": farm_id}
            )

        return {
            "status": True,
            "message": "Farm deleted successfully"
        }

    except HTTPException:
        raise

    except Exception as e:
        print("❌ Delete farm error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

class AddShedModel(BaseModel):
    farm_id: int 
    shed_number: str
    shed_type: str
    bird_category: str | None = None
    bird_breed: str | None = None
    initial_bird_count: int | None = None

    # Inside area (already exists)
    area_value: float
    area_unit: str

    # ⬇️ NEW: Outside area for Free Range
    open_area_value: float | None = None
    open_area_unit: str | None = "sqft"

    placement_date: date | None = None
    shed_status: str = "active"
    notes: str | None = None

    # Equipment
    no_of_feeders: int | None = None
    no_of_water_nipples: int | None = None

    # Perch
    perch_angle: int | None = None
    perch_length_value: float | None = None
    perch_length_unit: str | None = "ft"

@app.post("/api/add_shed")
async def add_shed(
    data: AddShedModel,
    current_admin: int = Depends(get_current_admin)
):

    try:
        with engine.begin() as conn:

            # 🔐 1️⃣ VERIFY FARM BELONGS TO ADMIN
            farm_check = conn.execute(
                text("""
                    SELECT farm_id
                    FROM Farms
                    WHERE farm_id = :fid
                      AND admin_id = :aid
                """),
                {
                    "fid": data.farm_id,
                    "aid": current_admin
                }
            ).fetchone()

            if not farm_check:
                raise HTTPException(403, "Unauthorized access to this farm")

            # Check for duplicate shed name within this farm
            dup_shed = conn.execute(
                text("SELECT 1 FROM Sheds WHERE shed_number = :sn AND farm_id = :fid LIMIT 1"),
                {"sn": data.shed_number, "fid": data.farm_id}
            ).fetchone()
            if dup_shed:
                raise HTTPException(status_code=409, detail=f"A shed named '{data.shed_number}' already exists in this farm")

            # 2️⃣ CREATE SHED
            new_shed = conn.execute(
                text("""
                    INSERT INTO Sheds (
                        farm_id, shed_seq, shed_number, shed_type,
                        bird_category, bird_breed, initial_bird_count,
                        area_value, area_unit, open_area_value, open_area_unit,
                        placement_date, shed_status, notes,
                        no_of_feeders, no_of_water_nipples,
                        perch_angle, perch_length_value, perch_length_unit
                    )
                    VALUES (
                        :farm_id,
                        (SELECT COALESCE(MAX(shed_seq), 0) + 1 FROM Sheds WHERE farm_id = :farm_id),
                        :shed_number, :shed_type,
                        :bird_category, :bird_breed, :initial_bird_count,
                        :area_value, :area_unit, :open_area_value, :open_area_unit,
                        :placement_date, :shed_status, :notes,
                        :no_of_feeders, :no_of_water_nipples,
                        :perch_angle, :perch_length_value, :perch_length_unit
                    )
                    RETURNING shed_id, initial_bird_count, placement_date
                """),
                data.dict()
            ).mappings().fetchone()

            shed_id = new_shed["shed_id"]
            initial_count = new_shed["initial_bird_count"]
            placement_date = new_shed["placement_date"] or date.today()

            # 3️⃣ CREATE FIRST BATCH
            batch = conn.execute(
                text("""
                    INSERT INTO Batches (
                        shed_id, farm_id,
                        placement_date,
                        bird_category, bird_breed,
                        initial_bird_count,
                        final_bird_count,
                        status, notes
                    )
                    VALUES (
                        :shed_id, :farm_id,
                        :placement_date,
                        :bird_category, :bird_breed,
                        :initial_bird_count,
                        :initial_bird_count,
                        'active', :notes
                    )
                    RETURNING batch_id
                """),
                {
                    "shed_id": shed_id,
                    "farm_id": data.farm_id,
                    "placement_date": placement_date,
                    "bird_category": data.bird_category,
                    "bird_breed": data.bird_breed,
                    "initial_bird_count": initial_count,
                    "notes": data.notes
                }
            ).mappings().fetchone()

            batch_id = batch["batch_id"]

            # 4️⃣ INSERT OPENING STOCK
            conn.execute(
                text("""
                    INSERT INTO BirdStockHistory (
                        shed_id, batch_id,
                        entry_date,
                        mortality, culling,
                        birds_opening, birds_closing
                    )
                    VALUES (
                        :shed_id, :batch_id,
                        :entry_date,
                        0, 0,
                        :opening, :opening
                    )
                """),
                {
                    "shed_id": shed_id,
                    "batch_id": batch_id,
                    "entry_date": placement_date,
                    "opening": initial_count
                }
            )

        return {
            "status": True,
            "message": "Shed added and first batch created.",
            "data": {
                "shed_id": shed_id,
                "batch_id": batch_id,
                "placement_date": placement_date,
                "initial_birds": initial_count
            }
        }

    except Exception as e:
        print("❌ Error adding shed:", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/edit_shed")
def edit_shed(
    data: dict,
    admin_id: int = Depends(get_current_admin)
):
    shed_id = data.get("shed_id")
    new_initial = data.get("initial_bird_count")

    if not shed_id:
        raise HTTPException(400, "shed_id is required")
    if new_initial is None:
        raise HTTPException(400, "initial_bird_count is required")

    try:
        with engine.begin() as conn:

            # 🔐 1️⃣ VERIFY SHED BELONGS TO THIS ADMIN
            ownership = conn.execute(text("""
                SELECT s.initial_bird_count, s.farm_id
                FROM Sheds s
                JOIN Farms f ON f.farm_id = s.farm_id
                WHERE s.shed_id = :sid
                  AND f.admin_id = :aid
            """), {
                "sid": shed_id,
                "aid": admin_id
            }).mappings().fetchone()

            if not ownership:
                raise HTTPException(403, "You are not authorized to edit this shed")

            old_initial = ownership["initial_bird_count"]
            farm_id = ownership["farm_id"]

            delta = new_initial - old_initial

            # 2️⃣ Update shed info
            conn.execute(text("""
                UPDATE Sheds SET
                    shed_number = :shed_number,
                    shed_type = :shed_type,
                    bird_category = :bird_category,
                    bird_breed = :bird_breed,
                    initial_bird_count = :initial_bird_count,
                    area_value = :area_value,
                    area_unit = :area_unit,
                    open_area_value = :open_area_value,
                    open_area_unit = :open_area_unit,
                    placement_date = :placement_date,
                    shed_status = :shed_status,
                    notes = :notes,
                    no_of_feeders = :no_of_feeders,
                    no_of_water_nipples = :no_of_water_nipples,
                    perch_angle = :perch_angle,
                    perch_length_value = :perch_length_value,
                    perch_length_unit = :perch_length_unit
                WHERE shed_id = :shed_id
            """), data)

            # 3️⃣ Update latest BirdStockHistory
            latest = conn.execute(text("""
                SELECT id, birds_opening, birds_closing
                FROM BirdStockHistory
                WHERE shed_id = :sid
                ORDER BY entry_date DESC, id DESC
                LIMIT 1
            """), {"sid": shed_id}).mappings().fetchone()

            if not latest:
                raise HTTPException(500, "No BirdStockHistory found")

            new_opening = latest["birds_opening"] + delta
            new_closing = latest["birds_closing"] + delta

            conn.execute(text("""
                UPDATE BirdStockHistory
                SET birds_opening = :o,
                    birds_closing = :c
                WHERE id = :id
            """), {
                "o": new_opening,
                "c": new_closing,
                "id": latest["id"]
            })

            # 4️⃣ Sync active batch
            active_batch = conn.execute(text("""
                SELECT batch_id
                FROM Batches
                WHERE shed_id = :sid
                  AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 1
            """), {"sid": shed_id}).mappings().fetchone()

            if active_batch:
                batch_id = active_batch["batch_id"]

                conn.execute(text("""
                    UPDATE Batches
                    SET initial_bird_count = :ni,
                        final_bird_count = :nf
                    WHERE batch_id = :bid
                """), {
                    "bid": batch_id,
                    "ni": new_initial,
                    "nf": new_closing
                })
            else:
                new_batch = conn.execute(text("""
                    INSERT INTO Batches (
                        shed_id,
                        farm_id,
                        status,
                        initial_bird_count,
                        final_bird_count,
                        placement_date,
                        created_at
                    )
                    VALUES (
                        :sid,
                        :fid,
                        'active',
                        :initial,
                        :final,
                        NOW(),
                        NOW()
                    )
                    RETURNING batch_id
                """), {
                    "sid": shed_id,
                    "fid": farm_id,
                    "initial": new_initial,
                    "final": new_closing
                }).mappings().fetchone()

                batch_id = new_batch["batch_id"]

        return {
            "status": True,
            "message": "Shed updated securely",
            "batch_id": batch_id
        }

    except Exception as e:
        print("❌ Error in edit_shed:", e)
        raise HTTPException(500, str(e))
  
@app.get("/api/get_farm_details")
async def get_farm_details(
    farm_id: int,
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            # --------------------------------------
            # 1️⃣ FETCH FARM WITH OWNERSHIP CHECK
            # --------------------------------------
            farm = conn.execute(
                text("""
                    SELECT 
                        farm_id,
                        farm_name,
                        farm_owner_name,
                        farm_owner_phone,
                        farm_owner_email,
                        supervisor_name,
                        supervisor_phone,
                        farm_location,
                        created_at
                    FROM Farms
                    WHERE farm_id = :farm_id
                      AND admin_id = :admin_id
                """),
                {
                    "farm_id": farm_id,
                    "admin_id": current_admin
                }
            ).mappings().fetchone()

            if not farm:
                raise HTTPException(
                    status_code=404,
                    detail="Farm not found or access denied"
                )

            # --------------------------------------
            # 2️⃣ FETCH ALL SHEDS
            # --------------------------------------
            sheds = conn.execute(
                text("""
                    SELECT
                        shed_id,
                        shed_number,
                        shed_type,
                        bird_category,
                        bird_breed,
                        initial_bird_count,
                        area_value,
                        area_unit,
                        open_area_value,
                        open_area_unit,
                        placement_date,
                        shed_status,
                        notes,
                        no_of_feeders,
                        no_of_water_nipples,
                        perch_angle,
                        perch_length_value,
                        perch_length_unit,
                        created_at
                    FROM Sheds
                    WHERE farm_id = :farm_id
                    ORDER BY created_at DESC
                """),
                {"farm_id": farm_id}
            ).mappings().fetchall()

            shed_ids = [s["shed_id"] for s in sheds]

            if not shed_ids:
                return {
                    "status": True,
                    "data": {
                        **dict(farm),
                        "sheds": [],
                        "metrics": {
                            "total_initial_birds": 0,
                            "total_live_birds": 0
                        }
                    }
                }

            # --------------------------------------
            # 3️⃣ ACTIVE BATCHES
            # --------------------------------------
            active_batches = conn.execute(
                text("""
                    SELECT 
                        batch_id,
                        shed_id,
                        placement_date
                    FROM Batches
                    WHERE shed_id = ANY(:shed_ids)
                      AND status = 'active'
                      AND depletion_date IS NULL
                """),
                {"shed_ids": shed_ids}
            ).mappings().fetchall()

            active_batch_map = {
                b["shed_id"]: b for b in active_batches
            }

            # --------------------------------------
            # 4️⃣ LATEST STOCK ENTRY
            # --------------------------------------
            stock = conn.execute(
                text("""
                    SELECT DISTINCT ON (shed_id)
                        shed_id,
                        birds_closing,
                        entry_date,
                        created_at
                    FROM BirdStockHistory
                    WHERE shed_id = ANY(:shed_ids)
                    ORDER BY shed_id, entry_date DESC, created_at DESC
                """),
                {"shed_ids": shed_ids}
            ).mappings().fetchall()
            transfer_rows = conn.execute(
                text("""
                    SELECT
                        bt.transfer_id,
                        bt.from_shed_id,
                        bt.to_shed_id,
                        fs.shed_number AS from_shed_number,
                        ts.shed_number AS to_shed_number,
                        bt.bird_count,
                        bt.transferred_at
                    FROM BirdTransfers bt
                    JOIN Sheds fs ON fs.shed_id = bt.from_shed_id
                    JOIN Sheds ts ON ts.shed_id = bt.to_shed_id
                    WHERE bt.farm_id = :farm_id
                      AND (bt.from_shed_id = ANY(:shed_ids) OR bt.to_shed_id = ANY(:shed_ids))
                    ORDER BY bt.transferred_at DESC
                """),
                {"farm_id": farm_id, "shed_ids": shed_ids}
            ).mappings().fetchall()

        # Outside transaction
        stock_map = {row["shed_id"]: row for row in stock}
        transfer_map = {sid: [] for sid in shed_ids}
        for t in transfer_rows:
            when = t["transferred_at"].isoformat() if t["transferred_at"] else None
            if t["from_shed_id"] in transfer_map:
                transfer_map[t["from_shed_id"]].append({
                    "transfer_id": t["transfer_id"],
                    "direction": "outgoing",
                    "other_shed_id": t["to_shed_id"],
                    "other_shed_number": t["to_shed_number"],
                    "bird_count": t["bird_count"],
                    "transferred_at": when,
                })
            if t["to_shed_id"] in transfer_map:
                transfer_map[t["to_shed_id"]].append({
                    "transfer_id": t["transfer_id"],
                    "direction": "incoming",
                    "other_shed_id": t["from_shed_id"],
                    "other_shed_number": t["from_shed_number"],
                    "bird_count": t["bird_count"],
                    "transferred_at": when,
                })

        # --------------------------------------
        # 5️⃣ ENRICH DATA
        # --------------------------------------
        from datetime import date

        total_initial = 0
        total_live = 0
        enriched_sheds = []

        for s in sheds:
            shed = dict(s)
            sid = shed["shed_id"]

            initial = shed["initial_bird_count"] or 0
            total_initial += initial

            closing = stock_map.get(sid, {}).get("birds_closing", initial)
            total_live += closing

            # Density calculations
            shed["density_inside"] = (
                closing / shed["area_value"]
                if shed["area_value"] else None
            )

            shed["birds_per_feeder"] = (
                closing / shed["no_of_feeders"]
                if shed["no_of_feeders"] else None
            )

            shed["birds_per_nipple"] = (
                closing / shed["no_of_water_nipples"]
                if shed["no_of_water_nipples"] else None
            )

            shed["birds_per_perch_length"] = (
                closing / shed["perch_length_value"]
                if shed["perch_length_value"] else None
            )

            # Age
            if shed["placement_date"]:
                age_days = (date.today() - shed["placement_date"]).days
                shed["age_days"] = age_days
                shed["age_weeks"] = age_days // 7
            else:
                shed["age_days"] = None
                shed["age_weeks"] = None

            # Active batch
            if sid in active_batch_map:
                shed["has_active_batch"] = True
                shed["active_batch_id"] = active_batch_map[sid]["batch_id"]
                shed["active_batch_placement_date"] = active_batch_map[sid]["placement_date"]
            else:
                shed["has_active_batch"] = False
                shed["active_batch_id"] = None
                shed["active_batch_placement_date"] = None

            shed["final_bird_count"] = closing
            shed["transfer_history"] = transfer_map.get(sid, [])

            enriched_sheds.append(shed)

        farm_dict = dict(farm)
        farm_dict["sheds"] = enriched_sheds
        farm_dict["metrics"] = {
            "total_initial_birds": total_initial,
            "total_live_birds": total_live
        }

        return {
            "status": True,
            "data": farm_dict
        }

    except Exception as e:
        print("❌ Error fetching farm details:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


class UpdateShedModel(BaseModel):
    shed_number: str
    shed_purpose: Optional[str] = None
    bird_category: Optional[str] = None
    bird_breed: Optional[str] = None
    initial_bird_count: Optional[int] = None
    area_value: float
    area_unit: str
    placement_date: Optional[date] = None
    notes: Optional[str] = None

@app.put("/api/update_shed")
async def update_shed(
    shed_id: int,
    data: UpdateShedModel,
    admin_id: int = Depends(get_current_admin)
):

    try:
        with engine.begin() as conn:

            # 🔐 1️⃣ VERIFY OWNERSHIP
            shed_check = conn.execute(text("""
                SELECT s.shed_id
                FROM Sheds s
                JOIN Farms f ON f.farm_id = s.farm_id
                WHERE s.shed_id = :sid
                  AND f.admin_id = :aid
            """), {
                "sid": shed_id,
                "aid": admin_id
            }).fetchone()

            if not shed_check:
                raise HTTPException(
                    status_code=403,
                    detail="Not authorized to update this shed"
                )

            # 2️⃣ Perform update
            updated_shed = conn.execute(text("""
                UPDATE Sheds
                SET
                    shed_number = :shed_number,
                    shed_purpose = :shed_purpose,
                    bird_category = :bird_category,
                    bird_breed = :bird_breed,
                    initial_bird_count = :initial_bird_count,
                    area_value = :area_value,
                    area_unit = :area_unit,
                    placement_date = :placement_date,
                    notes = :notes
                WHERE shed_id = :shed_id
                RETURNING *
            """), {
                "shed_id": shed_id,
                **data.dict()
            }).mappings().fetchone()

        if not updated_shed:
            raise HTTPException(status_code=404, detail="Shed not found")

        print("✅ Shed updated:", dict(updated_shed))

        return {
            "status": True,
            "message": "Shed updated successfully",
            "data": dict(updated_shed)
        }

    except Exception as e:
        print("❌ Error updating shed:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/delete_shed")
async def delete_shed(shed_id: int):

    try:
        with engine.begin() as conn:
            deleted = conn.execute(
                text("""
                    DELETE FROM Sheds
                    WHERE shed_id = :shed_id
                    RETURNING shed_id
                """),
                {"shed_id": shed_id}
            ).fetchone()

        if not deleted:
            raise HTTPException(status_code=404, detail="Shed not found")


        return {
            "status": True,
            "message": "Shed deleted successfully"
        }

    except Exception as e:
        print("❌ Error deleting shed:", str(e))
        raise HTTPException(status_code=500, detail=str(e))




class EggCollectionModel(BaseModel):
    farm_id: int
    collection_date: date

    opening_stock: int = 0
    collected: int = 0
    broken: int = 0
    wasted: int = 0
    misshaped: int = 0
    dispatched: int = 0


@app.post("/api/egg_collection")
async def add_egg_collection(data: EggCollectionModel):
    try:
        closing_stock = (
            data.opening_stock
            + data.collected
            - data.broken
            - data.wasted
            - data.misshaped
            - data.dispatched
        )

        with engine.begin() as conn:
            new_entry = conn.execute(
                text("""
                    INSERT INTO EggCollections (
                        farm_id,
                        collection_date,
                        opening_stock,
                        collected,
                        broken,
                        wasted,
                        misshaped,
                        dispatched,
                        closing_stock
                    )
                    VALUES (
                        :farm_id,
                        :collection_date,
                        :opening_stock,
                        :collected,
                        :broken,
                        :wasted,
                        :misshaped,
                        :dispatched,
                        :closing_stock
                    )
                    RETURNING *
                """),
                {**data.dict(), "closing_stock": closing_stock}
            ).mappings().fetchone()

        return {"status": True, "data": new_entry}

    except Exception as e:
        print("❌ Egg collection error:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/egg_collections")
async def get_egg_collections(farm_id: int):
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        egg_id,
                        farm_id,
                        collection_date,
                        opening_stock,
                        collected,
                        broken,
                        wasted,
                        misshaped,
                        dispatched,
                        closing_stock,
                        created_at
                    FROM EggCollections
                    WHERE farm_id = :farm_id
                    ORDER BY collection_date DESC
                """),
                {"farm_id": farm_id}
            ).mappings().fetchall()

        return {
            "status": True,
            "data": [dict(r) for r in rows]
        }

    except Exception as e:
        print("❌ Fetch egg collections error:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/egg_collections/latest")
async def get_latest_egg_collection(farm_id: int):
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text("""
                    SELECT *
                    FROM EggCollections
                    WHERE farm_id = :farm_id
                    ORDER BY collection_date DESC
                    LIMIT 1
                """),
                {"farm_id": farm_id}
            ).mappings().fetchone()

        return {
            "status": True,
            "data": dict(row) if row else None
        }

    except Exception as e:
        print("❌ Fetch latest egg collection error:", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/daily_entries_by_date")
async def get_daily_entries_by_date(shed_id: int):
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT *
                    FROM DailyEntries
                    WHERE shed_id = :shed_id
                    ORDER BY entry_date DESC, created_at DESC
                """),
                {"shed_id": shed_id}
            ).mappings().fetchall()

        grouped = {}
        for r in rows:
            d = r["entry_date"].isoformat()
            grouped.setdefault(d, []).append(dict(r))

        return {
            "status": True,
            "data": grouped
        }

    except Exception as e:
        print("❌ Daily entries fetch error:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/all_updates")
async def get_admin_updates(admin_id: int):
    try:
        with engine.begin() as conn:
            farm = conn.execute(
                text("""
                    SELECT farm_id
                    FROM Farms
                    WHERE admin_id = :admin_id
                    LIMIT 1
                """),
                {"admin_id": admin_id}
            ).mappings().fetchone()

        if not farm:
            raise HTTPException(status_code=404, detail="No farm assigned to this admin.")

        farm_id = farm["farm_id"]

        with engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        'daily' AS record_type,
                        d.entry_id AS id,
                        d.entry_date,
                        d.created_at,

                        f.farm_id,
                        f.farm_name,

                        s.shed_id,
                        s.shed_number,

                        d.mortality,
                        d.culling,
                        d.culling_reason,
                        d.feed_consumption_kg,
                        d.temperature,
                        d.ammonia_level,
                        d.avg_weight,
                        d.sick_updates,
                        d.medical_attention,
                        d.medical_notes,

                        NULL AS opening_stock,
                        NULL AS collected,
                        NULL AS broken,
                        NULL AS wasted,
                        NULL AS misshaped,
                        NULL AS dispatched,
                        NULL AS closing_stock

                    FROM DailyEntries d
                    JOIN Sheds s ON d.shed_id = s.shed_id
                    JOIN Farms f ON s.farm_id = f.farm_id
                    WHERE f.farm_id = :farm_id

                    ORDER BY d.entry_date DESC, d.created_at DESC
                """),
                {"farm_id": farm_id}
            ).mappings().fetchall()

        return {
            "status": True,
            "data": [dict(r) for r in rows]
        }

    except Exception as e:
        print("❌ Admin updates error:", e)
        raise HTTPException(status_code=500, detail=str(e))


    except Exception as e:
        print("❌ /test/daily ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))

def save_egg_stock_record(farm_id, shed_id, collected, dispatched):
    today = date.today()

    with engine.begin() as conn:

        # 1️⃣ Get yesterday's closing stock
        prev = conn.execute(text("""
            SELECT closing_eggs
            FROM EggStockHistory
            WHERE shed_id = :shed
            ORDER BY record_date DESC
            LIMIT 1
        """), {"shed": shed_id}).fetchone()

        opening = prev[0] if prev else 0

        # 2️⃣ Calculate closing
        closing = opening + collected - dispatched
        if closing < 0:
            closing = 0

        # 3️⃣ Insert new record
        res = conn.execute(text("""
            INSERT INTO EggStockHistory (
                farm_id, shed_id, record_date,
                opening_eggs, collected_eggs, dispatched_eggs,
                closing_eggs
            )
            VALUES (
                :farm_id, :shed_id, :date,
                :opening, :collected, :dispatched,
                :closing
            )
            RETURNING id
        """), {
            "farm_id": farm_id,
            "shed_id": shed_id,
            "date": today,
            "opening": opening,
            "collected": collected,
            "dispatched": dispatched,
            "closing": closing
        }).fetchone()

        return res[0]




def get_farm_stock(farm_id):
    with engine.begin() as conn:

        collected = conn.execute(text("""
            SELECT 
                COALESCE(SUM(good_eggs), 0) AS good_sum,
                COALESCE(SUM(floor_eggs + mishapped_eggs), 0) AS floor_sum
            FROM EggDailyRecords
            WHERE farm_id = :fid
        """), {"fid": farm_id}).mappings().first()

        dispatched = conn.execute(text("""
            SELECT 
                COALESCE(SUM(dispatched_good_eggs), 0) AS good_sum,
                COALESCE(SUM(dispatched_floor_mis_eggs), 0) AS floor_sum
            FROM EggDispatchRecords
            WHERE farm_id = :fid
        """), {"fid": farm_id}).mappings().first()

        opening_good = collected["good_sum"] - dispatched["good_sum"]
        opening_floor = collected["floor_sum"] - dispatched["floor_sum"]

        return opening_good, opening_floor


def get_shed_batch_stock(shed_id, batch_id):
    with engine.begin() as conn:
        collected = conn.execute(text("""
            SELECT
                COALESCE(SUM(good_eggs), 0) AS good_sum,
                COALESCE(SUM(floor_eggs + mishapped_eggs), 0) AS floor_sum
            FROM EggDailyRecords
            WHERE shed_id = :sid
              AND batch_id = :bid
        """), {"sid": shed_id, "bid": batch_id}).mappings().first()

        dispatched = conn.execute(text("""
            SELECT
                COALESCE(SUM(dispatched_good_eggs), 0) AS good_sum,
                COALESCE(SUM(dispatched_floor_mis_eggs), 0) AS floor_sum
            FROM EggDispatchRecords
            WHERE shed_id = :sid
              AND batch_id = :bid
        """), {"sid": shed_id, "bid": batch_id}).mappings().first()

        opening_good = int(collected["good_sum"] or 0) - int(dispatched["good_sum"] or 0)
        opening_floor = int(collected["floor_sum"] or 0) - int(dispatched["floor_sum"] or 0)

        return max(opening_good, 0), max(opening_floor, 0)

# ===============================
# GET FARM & SHEDS BY SUPERVISOR
# ===============================

# ===============================
# DAILY ENTRY QUESTIONS (ORDERED)
# ===============================
DAILY_QUESTIONS = [
    ("mortality", "1️⃣ Enter *Mortality Count*:"),
    ("culling", "2️⃣ Enter *Culling Count*:"),
    ("feed", "3️⃣ Enter *Feed Consumed (kg)*:"),
    ("temperature", "4️⃣ Enter *Temperature (°C)*:"),
    ("water_consumed", "5️⃣ Enter *Water Consumed (litres)*:"),
    ("lighting_hours", "6️⃣ Enter *Lighting Hours*:"),
    ("medical_yes_no", "7️⃣ Any Medical Attention Today?")
]

EGG_QUESTIONS = [
    ("good_eggs", " Enter *Total Good Eggs*:"),
    ("floor_eggs", " Enter *Floor Laid Eggs*:"),
    ("broken_eggs", " Enter *Broken / Cracked Eggs*:"),
    ("mishapped_eggs", " Enter *Mishapped / Oversized Eggs*:"),
]
WEEKLY_QUESTIONS = [
    ("ammonia_level", "Enter *Ammonia Level* (ppm):"),
    ("avg_bird_weight", "Enter *Average Bird Weight* (grams):"),
    ("weekly_notes", "Any additional weekly observations?"),
]



def get_active_batch_id(conn, shed_id):
    """Return the active batch_id for a shed."""
    return conn.execute(
        text("""
            SELECT batch_id
            FROM Batches
            WHERE shed_id = :sid AND status = 'active'
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"sid": shed_id}
    ).scalar()

# ===============================
# SAVE DAILY ENTRY
# ===============================
def save_daily_entry(shed_id, answers):
    today = date.today()
    mortality = int(answers.get("mortality", 0))
    culling = int(answers.get("culling", 0))

    with engine.begin() as conn:

        # ⭐ 0️⃣ GET ACTIVE BATCH ID
        batch_id = get_active_batch_id(conn, shed_id)

        # 1️⃣ GET YESTERDAY'S CLOSING BIRD COUNT
        prev = conn.execute(
            text("""
                SELECT birds_closing
                FROM BirdStockHistory
                WHERE shed_id = :sid
                ORDER BY entry_date DESC, id DESC
                LIMIT 1
            """),
            {"sid": shed_id}
        ).mappings().fetchone()

        if prev:
            opening_birds = prev["birds_closing"]
        else:
            init_row = conn.execute(
                text("SELECT initial_bird_count FROM Sheds WHERE shed_id = :sid"),
                {"sid": shed_id}
            ).mappings().fetchone()

            opening_birds = init_row["initial_bird_count"] if init_row else 0

        # 2️⃣ CALCULATE CLOSING BIRDS
        closing_birds = max(opening_birds - (mortality + culling), 0)

        # 3️⃣ INSERT DAILY ENTRY (WITH BATCH)
        result = conn.execute(
            text("""
                INSERT INTO DailyEntries (
                    shed_id,
                    batch_id,
                    entry_date,
                    mortality,
                    mortality_reason,
                    culling,
                    culling_reason,
                    feed_consumption_kg,
                    temperature,
                    water_consumed_ltrs,
                    lighting_hours,
                    medical_attention,
                    medical_notes
                )
                VALUES (
                    :shed_id,
                    :batch_id,
                    :entry_date,
                    :mortality,
                    :mortality_reason,
                    :culling,
                    :culling_reason,
                    :feed,
                    :temperature,
                    :water_consumed,
                    :lighting_hours,
                    :medical_attention,
                    :medical_notes
                )
                RETURNING entry_id
            """),
            {
                "shed_id": shed_id,
                "batch_id": batch_id,
                "entry_date": today,

                "mortality": mortality,
                "mortality_reason": answers.get("mortality_reason"),

                "culling": culling,
                "culling_reason": answers.get("culling_reason"),

                "feed": float(answers.get("feed", 0)),
                "temperature": float(answers.get("temperature", 0)),
                "water_consumed": float(answers.get("water_consumed", 0)),
                "lighting_hours": float(answers.get("lighting_hours", 0)),

                "medical_attention": answers.get("medical_attention", False),
                "medical_notes": answers.get("medical_notes"),
            }
        ).mappings().fetchone()

        entry_id = result["entry_id"]

        # 4️⃣ INSERT BIRD STOCK HISTORY (WITH BATCH)
        conn.execute(
            text("""
                INSERT INTO BirdStockHistory (
                    shed_id,
                    batch_id,
                    entry_date,
                    mortality,
                    culling,
                    birds_opening,
                    birds_closing
                )
                VALUES (
                    :shed_id,
                    :batch_id,
                    :entry_date,
                    :mortality,
                    :culling,
                    :opening_birds,
                    :closing_birds
                )
            """),
            {
                "shed_id": shed_id,
                "batch_id": batch_id,
                "entry_date": today,
                "mortality": mortality,
                "culling": culling,
                "opening_birds": opening_birds,
                "closing_birds": closing_birds
            }
        )

        # ⭐ 5️⃣ UPDATE ACTIVE BATCH FINAL BIRD COUNT (IMPORTANT)
        if batch_id:
            conn.execute(
                text("""
                    UPDATE Batches
                    SET final_bird_count = :closing
                    WHERE batch_id = :bid
                """),
                {"closing": closing_birds, "bid": batch_id}
            )

    return entry_id


def save_weekly_entry(farm_id, shed_id, answers):
    today = date.today()  # Should be a Friday if triggered correctly

    with engine.begin() as conn:
        res = conn.execute(text("""
            INSERT INTO WeeklyEntries (
                farm_id,
                shed_id,
                entry_date,
                ammonia_level,
                avg_bird_weight,
                weekly_notes
            )
            VALUES (
                :farm_id,
                :shed_id,
                :entry_date,
                :ammonia_level,
                :avg_bird_weight,
                :weekly_notes
            )
            RETURNING weekly_id
        """), {
            "farm_id": farm_id,
            "shed_id": shed_id,
            "entry_date": today,
            "ammonia_level": float(answers.get("ammonia_level") or 0),
            "avg_bird_weight": float(answers.get("avg_bird_weight") or 0),
            "weekly_notes": answers.get("weekly_notes")
        }).mappings().fetchone()

        return res["weekly_id"]

def _to_int_safe(v, default=0):
    try:
        if v is None or v == "":
            return default
        return int(float(v))
    except Exception:
        return default


def _to_float_safe(v, default=0.0):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def _to_bool_safe(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "y"}


def _normalize_header(h):
    if h is None:
        return ""
    return str(h).strip().lower()



def save_daily_entry_website(shed_id, answers, entry_date, conn=None):
    """
    Website version of daily entry save (supports backdated entries).
    """
    mortality = _to_int_safe(answers.get("mortality", 0))
    culling = _to_int_safe(answers.get("culling", 0))

    def _run(db_conn):
        batch_id = get_active_batch_id(db_conn, shed_id)
        if not batch_id:
            raise HTTPException(
                status_code=400, 
                detail=f"No active batch for shed_id={shed_id}"
            )

        dup_check = db_conn.execute(
            text("""
                SELECT entry_id
                FROM DailyEntries
                WHERE shed_id = :sid
                  AND batch_id = :bid
                  AND entry_date = :ed
                LIMIT 1
            """),
            {"sid": shed_id, "bid": batch_id, "ed": entry_date}
        ).scalar()

        if dup_check:
            raise HTTPException(
                status_code=400,
                detail=f"Daily entry already exists for shed_id={shed_id} on {entry_date}"
            )

        prev = db_conn.execute(
            text("""
                SELECT birds_closing
                FROM BirdStockHistory
                WHERE shed_id = :sid
                  AND batch_id = :bid
                  AND entry_date < :ed
                ORDER BY entry_date DESC, id DESC
                LIMIT 1
            """),
            {"sid": shed_id, "bid": batch_id, "ed": entry_date}
        ).mappings().fetchone()

        if prev:
            opening_birds = _to_int_safe(prev["birds_closing"], 0)
        else:
            init_row = db_conn.execute(
                text("""
                    SELECT initial_bird_count
                    FROM Batches
                    WHERE batch_id = :bid
                """),
                {"bid": batch_id}
            ).mappings().fetchone()

            if not init_row:
                raise HTTPException(
                    status_code=500,
                    detail=f"Batch {batch_id} not found"
                )

            opening_birds = _to_int_safe(init_row["initial_bird_count"], 0)

        closing_birds = max(opening_birds - (mortality + culling), 0)

        db_conn.execute(
            text("""
                INSERT INTO DailyEntries (
                    shed_id,
                    batch_id,
                    entry_date,
                    mortality,
                    mortality_reason,
                    culling,
                    culling_reason,
                    feed_consumption_kg,
                    temperature,
                    water_consumed_ltrs,
                    lighting_hours,
                    medical_attention,
                    medical_notes
                )
                VALUES (
                    :shed_id,
                    :batch_id,
                    :entry_date,
                    :mortality,
                    :mortality_reason,
                    :culling,
                    :culling_reason,
                    :feed,
                    :temperature,
                    :water_consumed,
                    :lighting_hours,
                    :medical_attention,
                    :medical_notes
                )
            """),
            {
                "shed_id": shed_id,
                "batch_id": batch_id,
                "entry_date": entry_date,
                "mortality": mortality,
                "mortality_reason": answers.get("mortality_reason"),
                "culling": culling,
                "culling_reason": answers.get("culling_reason"),
                "feed": _to_float_safe(answers.get("feed", 0)),
                "temperature": _to_float_safe(answers.get("temperature", 0)),
                "water_consumed": _to_float_safe(answers.get("water_consumed", 0)),
                "lighting_hours": _to_float_safe(answers.get("lighting_hours", 0)),
                "medical_attention": bool(answers.get("medical_attention", False)),
                "medical_notes": answers.get("medical_notes"),
            }
        )

        try:
            db_conn.execute(
                text("""
                    INSERT INTO BirdStockHistory (
                        shed_id,
                        batch_id,
                        entry_date,
                        mortality,
                        culling,
                        birds_opening,
                        birds_closing
                    )
                    VALUES (
                        :shed_id,
                        :batch_id,
                        :entry_date,
                        :mortality,
                        :culling,
                        :opening_birds,
                        :closing_birds
                    )
                """),
                {
                    "shed_id": shed_id,
                    "batch_id": batch_id,
                    "entry_date": entry_date,
                    "mortality": mortality,
                    "culling": culling,
                    "opening_birds": opening_birds,
                    "closing_birds": closing_birds
                }
            )
        except Exception:
            db_conn.execute(
                text("""
                    UPDATE BirdStockHistory
                    SET
                        mortality = :mortality,
                        culling = :culling,
                        birds_opening = :opening_birds,
                        birds_closing = :closing_birds,
                        updated_at = NOW()
                    WHERE shed_id = :shed_id
                      AND batch_id = :batch_id
                      AND entry_date = :entry_date
                """),
                {
                    "shed_id": shed_id,
                    "batch_id": batch_id,
                    "entry_date": entry_date,
                    "mortality": mortality,
                    "culling": culling,
                    "opening_birds": opening_birds,
                    "closing_birds": closing_birds
                }
            )

        db_conn.execute(
            text("""
                UPDATE Batches
                SET final_bird_count = :closing
                WHERE batch_id = :bid
            """),
            {"closing": closing_birds, "bid": batch_id}
        )

        return batch_id

    if conn is not None:
        return _run(conn)
    else:
        with engine.begin() as local_conn:
            return _run(local_conn)



def rebuild_bird_stock_from_date(conn, shed_id, batch_id, start_date):
    """
    Rebuild BirdStockHistory for a shed+batch from start_date onward
    using only existing BirdStockHistory columns.
    """

    prev_closing = conn.execute(
        text("""
            SELECT birds_closing
            FROM BirdStockHistory
            WHERE shed_id = :sid
              AND batch_id = :bid
              AND entry_date < :sd
            ORDER BY entry_date DESC, id DESC
            LIMIT 1
        """),
        {"sid": shed_id, "bid": batch_id, "sd": start_date}
    ).scalar()

    if prev_closing is None:
        init_count = conn.execute(
            text("""
                SELECT initial_bird_count
                FROM Batches
                WHERE batch_id = :bid
            """),
            {"bid": batch_id}
        ).scalar()
        running_opening = _to_int_safe(init_count, 0)
    else:
        running_opening = _to_int_safe(prev_closing, 0)

    daily_rows = conn.execute(
        text("""
            SELECT
                entry_date,
                COALESCE(SUM(mortality), 0) AS mortality,
                COALESCE(SUM(culling), 0) AS culling
            FROM DailyEntries
            WHERE shed_id = :sid
              AND batch_id = :bid
              AND entry_date >= :sd
            GROUP BY entry_date
            ORDER BY entry_date ASC
        """),
        {"sid": shed_id, "bid": batch_id, "sd": start_date}
    ).mappings().fetchall()

    for r in daily_rows:
        d = r["entry_date"]
        mort = _to_int_safe(r["mortality"], 0)
        cull = _to_int_safe(r["culling"], 0)

        opening = running_opening
        closing = max(opening - (mort + cull), 0)

        upd = conn.execute(
            text("""
                UPDATE BirdStockHistory
                SET
                    mortality = :mort,
                    culling = :cull,
                    birds_opening = :opn,
                    birds_closing = :cls,
                    updated_at = NOW()
                WHERE shed_id = :sid
                  AND batch_id = :bid
                  AND entry_date = :ed
            """),
            {
                "mort": mort,
                "cull": cull,
                "opn": opening,
                "cls": closing,
                "sid": shed_id,
                "bid": batch_id,
                "ed": d
            }
        )

        if upd.rowcount == 0:
            conn.execute(
                text("""
                    INSERT INTO BirdStockHistory (
                        shed_id, batch_id, entry_date,
                        mortality, culling, birds_opening, birds_closing
                    )
                    VALUES (
                        :sid, :bid, :ed,
                        :mort, :cull, :opn, :cls
                    )
                """),
                {
                    "sid": shed_id,
                    "bid": batch_id,
                    "ed": d,
                    "mort": mort,
                    "cull": cull,
                    "opn": opening,
                    "cls": closing
                }
            )

        running_opening = closing

    latest_closing = conn.execute(
        text("""
            SELECT birds_closing
            FROM BirdStockHistory
            WHERE shed_id = :sid
              AND batch_id = :bid
            ORDER BY entry_date DESC, id DESC
            LIMIT 1
        """),
        {"sid": shed_id, "bid": batch_id}
    ).scalar()

    conn.execute(
        text("""
            UPDATE Batches
            SET final_bird_count = :fb
            WHERE batch_id = :bid
        """),
        {"fb": _to_int_safe(latest_closing, 0), "bid": batch_id}
    )


def _assert_admin_farm_shed(conn, admin_id: int, farm_id: int, shed_id: int) -> None:
    row = conn.execute(
        text("""
            SELECT 1
            FROM Sheds s
            JOIN Farms f ON f.farm_id = s.farm_id
            WHERE s.shed_id = :sid
              AND s.farm_id = :fid
              AND f.admin_id = :aid
            LIMIT 1
        """),
        {"sid": shed_id, "fid": farm_id, "aid": admin_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=403, detail="Unauthorized farm or shed")


def _verify_farm_supervisor_owns_shed(conn, phone: str, shed_id: int) -> int:
    normalized = normalize_phone(phone)
    row = conn.execute(
        text("""
            SELECT s.farm_id, f.supervisor_phone
            FROM Sheds s
            JOIN Farms f ON f.farm_id = s.farm_id
            WHERE s.shed_id = :sid
            LIMIT 1
        """),
        {"sid": shed_id},
    ).mappings().fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Shed not found")
    farm_digits = normalize_phone("".join(filter(str.isdigit, str(row["supervisor_phone"] or ""))))
    if farm_digits == normalized:
        return int(row["farm_id"])
    sup_ok = conn.execute(
        text("""
            SELECT 1 FROM Supervisors s
            WHERE s.farm_id = :fid
              AND LENGTH(regexp_replace(COALESCE(s.supervisor_phone, ''), '[^0-9]', '', 'g')) >= 10
              AND RIGHT(regexp_replace(COALESCE(s.supervisor_phone, ''), '[^0-9]', '', 'g'), 10) = :p0
            LIMIT 1
        """),
        {"fid": int(row["farm_id"]), "p0": normalized},
    ).fetchone()
    if not sup_ok:
        raise HTTPException(status_code=403, detail="Unauthorized shed")
    return int(row["farm_id"])


def _import_daily_excel_body(conn, farm_id: int, shed_id: int, content: bytes) -> dict:
    try:
        from openpyxl import load_workbook
        from io import BytesIO
        import zipfile as _zf
    except Exception:
        raise HTTPException(status_code=500, detail="openpyxl is required on server")

    # Pre-validate: xlsx files are ZIP archives. Reject anything that isn't.
    if not _zf.is_zipfile(BytesIO(content)):
        raise HTTPException(
            status_code=400,
            detail=(
                "File is not a valid .xlsx file. "
                "Make sure you are uploading an Excel file saved in .xlsx format "
                "(not .xls, .csv, or a renamed file)."
            ),
        )

    try:
        wb = load_workbook(BytesIO(content), data_only=True)
        ws = wb.active
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not read Excel file: {str(e)}. Re-save the file from Excel or Google Sheets as .xlsx and try again.",
        )

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(status_code=400, detail="Excel file is empty")

    headers = [_normalize_header(h) for h in rows[0]]
    idx = {h: i for i, h in enumerate(headers) if h}

    def val(row, *keys, default=None):
        for k in keys:
            i = idx.get(k)
            if i is not None and i < len(row):
                return row[i]
        return default

    if "entry_date" not in idx:
        raise HTTPException(status_code=400, detail="Missing required column: entry_date")

    parsed_rows = []
    row_errors = []

    for excel_row_no, r in enumerate(rows[1:], start=2):
        if r is None:
            continue
        if all((c is None or str(c).strip() == "") for c in r):
            continue

        raw_date = val(r, "entry_date")
        if raw_date is None:
            row_errors.append({"row": excel_row_no, "error": "entry_date is required"})
            continue

        if isinstance(raw_date, datetime):
            # +12h guard: tools like Google Sheets store midnight in UTC. A user in
            # UTC+5:30 gets datetime(Apr 9, 18:30) for "Apr 10". Adding 12h ensures
            # any tz-shifted value ≤ 23:59 still maps to the correct date.
            d = (raw_date + timedelta(hours=12)).date()
        elif isinstance(raw_date, date):
            d = raw_date
        else:
            s = str(raw_date).strip()
            try:
                d = datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                row_errors.append({"row": excel_row_no, "error": "entry_date must be YYYY-MM-DD"})
                continue


        parsed_rows.append({
            "row_no": excel_row_no,
            "entry_date": d,
            "mortality": _to_int_safe(val(r, "mortality")),
            "culling": _to_int_safe(val(r, "culling")),
            "feed": _to_float_safe(val(r, "feed", "feed_consumption_kg")),
            "temperature": _to_float_safe(val(r, "temperature")),
            "water_consumed": _to_float_safe(val(r, "water_consumed", "water_consumed_ltrs")),
            "lighting_hours": _to_float_safe(val(r, "lighting_hours")),
            "medical_attention": _to_bool_safe(val(r, "medical_attention", "medical_yes_no")),
            "medical_notes": (str(val(r, "medical_notes", default="")).strip() or None),
            "mortality_reason": (str(val(r, "mortality_reason", default="")).strip() or None),
            "culling_reason": (str(val(r, "culling_reason", default="")).strip() or None),
        })

    grouped = {}
    for pr in parsed_rows:
        d = pr["entry_date"]
        if d not in grouped:
            grouped[d] = {
                "entry_date": d,
                "source_rows": [],
                "mortality": 0,
                "culling": 0,
                "feed": 0.0,
                "temperature_sum": 0.0,
                "temperature_count": 0,
                "water_consumed": 0.0,
                "lighting_hours": 0.0,
                "medical_attention": False,
                "medical_notes": [],
                "mortality_reason": [],
                "culling_reason": []
            }

        g = grouped[d]
        g["source_rows"].append(pr["row_no"])
        g["mortality"] += pr["mortality"]
        g["culling"] += pr["culling"]
        g["feed"] += pr["feed"]
        g["temperature_sum"] += pr["temperature"]
        g["temperature_count"] += 1
        g["water_consumed"] += pr["water_consumed"]
        g["lighting_hours"] += pr["lighting_hours"]
        g["medical_attention"] = g["medical_attention"] or pr["medical_attention"]

        if pr["medical_notes"]:
            g["medical_notes"].append(pr["medical_notes"])
        if pr["mortality_reason"]:
            g["mortality_reason"].append(pr["mortality_reason"])
        if pr["culling_reason"]:
            g["culling_reason"].append(pr["culling_reason"])

    inserted = []
    skipped = []
    failed = []
    used_batch_id = None

    farm_ok = conn.execute(
        text("SELECT 1 FROM Farms WHERE farm_id = :fid LIMIT 1"),
        {"fid": farm_id}
    ).fetchone()
    if not farm_ok:
        raise HTTPException(status_code=404, detail="Farm not found")

    shed_ok = conn.execute(
        text("""
            SELECT 1 FROM Sheds
            WHERE shed_id = :sid AND farm_id = :fid
            LIMIT 1
        """),
        {"sid": shed_id, "fid": farm_id}
    ).fetchone()
    if not shed_ok:
        raise HTTPException(status_code=400, detail="shed_id does not belong to farm_id")

    batch_id = get_active_batch_id(conn, shed_id)
    if not batch_id:
        raise HTTPException(status_code=400, detail="No active batch for selected shed")
    used_batch_id = batch_id

    for d in sorted(grouped.keys()):
        g = grouped[d]

        exists = conn.execute(
            text("""
                SELECT 1 FROM DailyEntries
                WHERE shed_id = :sid AND batch_id = :bid AND entry_date = :ed
                LIMIT 1
            """),
            {"sid": shed_id, "bid": batch_id, "ed": d}
        ).fetchone()

        if exists:
            skipped.append({
                "entry_date": str(d),
                "rows": g["source_rows"],
                "reason": "Duplicate exists for shed+batch+date"
            })
            continue

        try:
            avg_temp = (
                g["temperature_sum"] / g["temperature_count"]
                if g["temperature_count"] > 0 else 0.0
            )

            answers = {
                "mortality": g["mortality"],
                "culling": g["culling"],
                "feed": g["feed"],
                "temperature": avg_temp,
                "water_consumed": g["water_consumed"],
                "lighting_hours": g["lighting_hours"],
                "medical_attention": g["medical_attention"],
                "medical_notes": " | ".join(g["medical_notes"]) if g["medical_notes"] else None,
                "mortality_reason": " | ".join(g["mortality_reason"]) if g["mortality_reason"] else None,
                "culling_reason": " | ".join(g["culling_reason"]) if g["culling_reason"] else None,
            }

            save_daily_entry_website(
                shed_id=shed_id,
                answers=answers,
                entry_date=d,
                conn=conn
            )

            inserted.append({
                "entry_date": str(d),
                "rows": g["source_rows"]
            })

        except Exception as ex:
            failed.append({
                "entry_date": str(d),
                "rows": g["source_rows"],
                "error": str(ex)
            })

    if grouped:
        rebuild_bird_stock_from_date(
            conn=conn,
            shed_id=shed_id,
            batch_id=batch_id,
            start_date=min(grouped.keys())
        )

    return {
        "status": True,
        "message": "Daily Excel import completed",
        "summary": {
            "farm_id": farm_id,
            "shed_id": shed_id,
            "batch_id": used_batch_id,
            "total_file_rows": len(parsed_rows),
            "grouped_dates": len(grouped),
            "inserted_count": len(inserted),
            "skipped_duplicate_count": len(skipped),
            "failed_count": len(failed) + len(row_errors),
        },
        "inserted": inserted,
        "skipped": skipped,
        "errors": row_errors + failed
    }


# Excel import removed — use /api/daily-entry/bulk instead
# @app.post("/api/admin/import_daily_excel") — REMOVED


@app.get("/api/admin/daily_entries")
async def admin_daily_entries(admin_id: int):
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        d.entry_id,
                        d.shed_id,
                        s.shed_number,
                        f.farm_name,
                        d.entry_date,
                        d.mortality,
                        d.culling,
                        d.culling_reason,
                        d.feed_consumption_kg,
                        d.temperature,
                        d.ammonia_level,
                        d.sick_updates,
                        d.medical_attention,
                        d.medical_notes,
                        d.avg_weight,
                        d.proof_pdf,
                        d.created_at
                    FROM DailyEntries d
                    JOIN Sheds s ON d.shed_id = s.shed_id
                    JOIN Farms f ON s.farm_id = f.farm_id
                    WHERE f.admin_id = :admin_id
                    ORDER BY d.entry_date DESC, d.created_at DESC
                """),
                {"admin_id": admin_id}
            ).mappings().fetchall()

        return {
            "status": True,
            "count": len(rows),
            "data": [dict(r) for r in rows]
        }

    except Exception as e:
        print("❌ Admin daily entries fetch error:", e)
        raise HTTPException(500, "Error fetching admin daily entries")



def save_egg_entry_website(shed_id, answers, entry_date, conn=None):
    """
    Website-only egg save helper for backdated imports.
    Inserts into EggDailyRecords with explicit collection_date.
    """

    # Normalize date input
    if isinstance(entry_date, datetime):
        entry_date = entry_date.date()
    if not isinstance(entry_date, date):
        raise HTTPException(status_code=400, detail="entry_date must be a valid date")

    # Normalize values
    good_eggs = max(0, _to_int_safe(answers.get("good_eggs", 0)))
    floor_eggs = max(0, _to_int_safe(answers.get("floor_eggs", 0)))
    broken_eggs = max(
        0,
        _to_int_safe(
            answers.get("broken_cracked_eggs", answers.get("broken_eggs", 0))
        ),
    )
    mishapped_eggs = max(0, _to_int_safe(answers.get("mishapped_eggs", 0)))

    def _run(db_conn):
        # Resolve shed + farm
        shed_row = db_conn.execute(
            text("""
                SELECT s.shed_id, s.shed_number, s.farm_id, f.farm_name
                FROM Sheds s
                JOIN Farms f ON f.farm_id = s.farm_id
                WHERE s.shed_id = :sid
                LIMIT 1
            """),
            {"sid": shed_id}
        ).mappings().fetchone()

        if not shed_row:
            raise HTTPException(status_code=404, detail=f"Shed not found: {shed_id}")

        farm_id = shed_row["farm_id"]
        shed_number = str(shed_row["shed_number"] or "")
        farm_name = str(shed_row["farm_name"] or "Farm")

        # Active batch required
        batch_id = get_active_batch_id(db_conn, shed_id)
        if not batch_id:
            raise HTTPException(status_code=400, detail=f"No active batch for shed_id={shed_id}")

        # Duplicate check: one egg row per shed+batch+date
        dup = db_conn.execute(
            text("""
                SELECT egg_id
                FROM EggDailyRecords
                WHERE shed_id = :sid
                  AND batch_id = :bid
                  AND collection_date = :cd
                LIMIT 1
            """),
            {"sid": shed_id, "bid": batch_id, "cd": entry_date}
        ).scalar()

        if dup:
            raise HTTPException(
                status_code=400,
                detail=f"Egg entry already exists for shed_id={shed_id} on {entry_date}"
            )

        # Keep a readable batch_no string (webhook-compatible style)
        batch_no = f"{farm_name.replace(' ', '')}_{shed_number}_{entry_date.strftime('%Y%m%d')}"

        row = db_conn.execute(
            text("""
                INSERT INTO EggDailyRecords (
                    farm_id,
                    shed_id,
                    batch_no,
                    batch_id,
                    collection_date,
                    good_eggs,
                    floor_eggs,
                    broken_cracked_eggs,
                    mishapped_eggs
                )
                VALUES (
                    :farm_id,
                    :shed_id,
                    :batch_no,
                    :batch_id,
                    :collection_date,
                    :good_eggs,
                    :floor_eggs,
                    :broken_eggs,
                    :mishapped_eggs
                )
                RETURNING egg_id
            """),
            {
                "farm_id": farm_id,
                "shed_id": shed_id,
                "batch_no": batch_no,
                "batch_id": batch_id,
                "collection_date": entry_date,
                "good_eggs": good_eggs,
                "floor_eggs": floor_eggs,
                "broken_eggs": broken_eggs,
                "mishapped_eggs": mishapped_eggs,
            }
        ).mappings().fetchone()

        return row["egg_id"], batch_id, farm_id

    if conn is not None:
        return _run(conn)

    with engine.begin() as local_conn:
        return _run(local_conn)



def _import_egg_excel_body(conn, farm_id: int, shed_id: int, content: bytes) -> dict:
    try:
        from openpyxl import load_workbook
        from io import BytesIO
        import zipfile as _zf
    except Exception:
        raise HTTPException(status_code=500, detail="openpyxl is required on server")

    if not _zf.is_zipfile(BytesIO(content)):
        raise HTTPException(
            status_code=400,
            detail=(
                "File is not a valid .xlsx file. "
                "Make sure you are uploading an Excel file saved in .xlsx format "
                "(not .xls, .csv, or a renamed file)."
            ),
        )

    try:
        wb = load_workbook(BytesIO(content), data_only=True)
        ws = wb.active
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not read Excel file: {str(e)}. Re-save the file from Excel or Google Sheets as .xlsx and try again.",
        )

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(status_code=400, detail="Excel file is empty")

    headers = [_normalize_header(h) for h in rows[0]]
    idx = {h: i for i, h in enumerate(headers) if h}

    if "entry_date" not in idx:
        raise HTTPException(status_code=400, detail="Missing required column: entry_date")

    def val(row, *keys, default=None):
        for k in keys:
            i = idx.get(k)
            if i is not None and i < len(row):
                return row[i]
        return default

    parsed_rows = []
    row_errors = []

    for excel_row_no, r in enumerate(rows[1:], start=2):
        if r is None:
            continue
        if all((c is None or str(c).strip() == "") for c in r):
            continue

        raw_date = val(r, "entry_date")
        if raw_date is None:
            row_errors.append({"row": excel_row_no, "error": "entry_date is required"})
            continue

        if isinstance(raw_date, datetime):
            # +12h guard: same timezone fix as daily import
            d = (raw_date + timedelta(hours=12)).date()
        elif isinstance(raw_date, date):
            d = raw_date
        else:
            s = str(raw_date).strip()
            try:
                d = datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                row_errors.append({"row": excel_row_no, "error": "entry_date must be YYYY-MM-DD"})
                continue


        parsed_rows.append({
            "row_no": excel_row_no,
            "entry_date": d,
            "good_eggs": max(0, _to_int_safe(val(r, "good_eggs", "good"))),
            "floor_eggs": max(0, _to_int_safe(val(r, "floor_eggs", "floor"))),
            "broken_cracked_eggs": max(0, _to_int_safe(val(r, "broken_cracked_eggs", "broken_eggs", "broken"))),
            "mishapped_eggs": max(0, _to_int_safe(val(r, "mishapped_eggs", "mishapped", "mis"))),
        })

    grouped = {}
    for pr in parsed_rows:
        d = pr["entry_date"]
        if d not in grouped:
            grouped[d] = {
                "entry_date": d,
                "source_rows": [],
                "good_eggs": 0,
                "floor_eggs": 0,
                "broken_cracked_eggs": 0,
                "mishapped_eggs": 0,
            }

        g = grouped[d]
        g["source_rows"].append(pr["row_no"])
        g["good_eggs"] += pr["good_eggs"]
        g["floor_eggs"] += pr["floor_eggs"]
        g["broken_cracked_eggs"] += pr["broken_cracked_eggs"]
        g["mishapped_eggs"] += pr["mishapped_eggs"]

    inserted = []
    skipped = []
    failed = []
    used_batch_id = None

    farm_ok = conn.execute(
        text("SELECT 1 FROM Farms WHERE farm_id = :fid LIMIT 1"),
        {"fid": farm_id}
    ).fetchone()
    if not farm_ok:
        raise HTTPException(status_code=404, detail="Farm not found")

    shed_ok = conn.execute(
        text("""
            SELECT 1
            FROM Sheds
            WHERE shed_id = :sid
              AND farm_id = :fid
            LIMIT 1
        """),
        {"sid": shed_id, "fid": farm_id}
    ).fetchone()

    if not shed_ok:
        raise HTTPException(status_code=400, detail="shed_id does not belong to farm_id")

    batch_id = get_active_batch_id(conn, shed_id)
    if not batch_id:
        raise HTTPException(status_code=400, detail="No active batch for selected shed")
    used_batch_id = batch_id

    for d in sorted(grouped.keys()):
        g = grouped[d]

        exists = conn.execute(
            text("""
                SELECT 1
                FROM EggDailyRecords
                WHERE shed_id = :sid
                  AND batch_id = :bid
                  AND collection_date = :cd
                LIMIT 1
            """),
            {"sid": shed_id, "bid": batch_id, "cd": d}
        ).fetchone()

        if exists:
            skipped.append({
                "entry_date": str(d),
                "rows": g["source_rows"],
                "reason": "Duplicate exists for shed+batch+date"
            })
            continue

        try:
            with conn.begin_nested():
                egg_id, _, _ = save_egg_entry_website(
                    shed_id=shed_id,
                    entry_date=d,
                    answers={
                        "good_eggs": g["good_eggs"],
                        "floor_eggs": g["floor_eggs"],
                        "broken_cracked_eggs": g["broken_cracked_eggs"],
                        "mishapped_eggs": g["mishapped_eggs"],
                    },
                    conn=conn
                )

            inserted.append({
                "egg_id": egg_id,
                "entry_date": str(d),
                "rows": g["source_rows"]
            })

        except HTTPException as ex:
            failed.append({
                "entry_date": str(d),
                "rows": g["source_rows"],
                "error": ex.detail
            })
        except Exception as ex:
            failed.append({
                "entry_date": str(d),
                "rows": g["source_rows"],
                "error": str(ex)
            })

    return {
        "status": True,
        "message": "Egg Excel import completed",
        "summary": {
            "farm_id": farm_id,
            "shed_id": shed_id,
            "batch_id": used_batch_id,
            "total_file_rows": len(parsed_rows),
            "grouped_dates": len(grouped),
            "inserted_count": len(inserted),
            "skipped_duplicate_count": len(skipped),
            "failed_count": len(failed),
            "validation_error_count": len(row_errors),
        },
        "inserted": inserted,
        "skipped": skipped,
        "errors": row_errors + failed
    }


# Excel import removed — use /api/egg-entry/bulk instead
# @app.post("/api/admin/import_egg_excel") — REMOVED



def save_egg_dispatch_entry_website(shed_id, answers, entry_date, conn=None):
    """
    Shed-level dispatch saver.
    Writes into EggDispatchRecords using: farm_id, shed_id, batch_id, dispatch_date.
    """
    if isinstance(entry_date, datetime):
        entry_date = entry_date.date()
    if not isinstance(entry_date, date):
        raise HTTPException(status_code=400, detail="dispatch_date must be a valid date")

    answers = answers or {}

    def _run(db_conn):
        # Resolve farm from shed (endpoint currently passes shed_id)
        shed_row = db_conn.execute(
            text("""
                SELECT s.shed_id, s.farm_id
                FROM Sheds s
                WHERE s.shed_id = :sid
                LIMIT 1
            """),
            {"sid": shed_id}
        ).mappings().fetchone()

        if not shed_row:
            raise HTTPException(status_code=404, detail=f"Shed not found: {shed_id}")

        farm_id = int(shed_row["farm_id"])

        requested_batch_id = _to_int_safe(answers.get("batch_id"), 0)
        # Default to active batch for older flows, but allow explicit batch from web UI.
        batch_id = requested_batch_id if requested_batch_id > 0 else get_active_batch_id(db_conn, shed_id)
        if not batch_id:
            raise HTTPException(status_code=400, detail=f"No active batch for shed_id={shed_id}")
        
        batch_exists = db_conn.execute(
            text("""
                SELECT b.batch_id
                FROM Batches b
                WHERE b.batch_id = :bid AND b.shed_id = :sid
                LIMIT 1
            """),
            {"bid": batch_id, "sid": shed_id}
        ).scalar()
        if not batch_exists:
            raise HTTPException(status_code=400, detail=f"batch_id={batch_id} does not belong to shed_id={shed_id}")

        batch_no = (str(answers.get("batch_no", "")).strip() or None)
        if not batch_no:
            bn_row = db_conn.execute(
                text("""
                    SELECT e.batch_no
                    FROM EggDailyRecords e
                    WHERE e.shed_id = :sid
                      AND e.batch_id = :bid
                      AND e.batch_no IS NOT NULL
                    ORDER BY e.collection_date DESC, e.collection_timestamp DESC
                    LIMIT 1
                """),
                {"sid": shed_id, "bid": batch_id}
            ).mappings().fetchone()
            batch_no = (str((bn_row or {}).get("batch_no", "")).strip() or f"BATCH-{batch_id}")

        # Normalize dispatch values (allow aliases from excel/webhook-style keys)
        dispatched_good_eggs = max(0, _to_int_safe(
            answers.get("dispatched_good_eggs", answers.get("good_eggs", 0))
        ))
        dispatched_floor_mis_eggs = max(0, _to_int_safe(
            answers.get("dispatched_floor_mis_eggs", answers.get("floor_mis_eggs", 0))
        ))

        total_dispatch = dispatched_good_eggs + dispatched_floor_mis_eggs
        if total_dispatch <= 0:
            raise HTTPException(status_code=400, detail="Dispatch quantity must be > 0")

        # Availability check (shed+batch level, up to dispatch date)
        collected = db_conn.execute(
            text("""
                SELECT
                    COALESCE(SUM(good_eggs), 0) AS good,
                    COALESCE(SUM(floor_eggs), 0) AS floor,
                    COALESCE(SUM(mishapped_eggs), 0) AS mish
                FROM EggDailyRecords
                WHERE shed_id = :sid
                  AND batch_id = :bid
                  AND collection_date <= :dd
            """),
            {"sid": shed_id, "bid": batch_id, "dd": entry_date}
        ).mappings().fetchone()

        collected_good = _to_int_safe(collected["good"], 0)
        collected_floor_mis = _to_int_safe(collected["floor"], 0) + _to_int_safe(collected["mish"], 0)

        already_dispatched = db_conn.execute(
            text("""
                SELECT
                    COALESCE(SUM(dispatched_good_eggs), 0) AS good,
                    COALESCE(SUM(dispatched_floor_mis_eggs), 0) AS floor_mis
                FROM EggDispatchRecords
                WHERE shed_id = :sid
                  AND batch_id = :bid
                  AND dispatch_date <= :dd
            """),
            {"sid": shed_id, "bid": batch_id, "dd": entry_date}
        ).mappings().fetchone()

        dispatched_good_till = _to_int_safe(already_dispatched["good"], 0)
        dispatched_floor_mis_till = _to_int_safe(already_dispatched["floor_mis"], 0)

        available_good = collected_good - dispatched_good_till
        available_floor_mis = collected_floor_mis - dispatched_floor_mis_till

        if dispatched_good_eggs > available_good:
            raise HTTPException(
                status_code=400,
                detail=f"Dispatched good eggs exceed available on {entry_date}. "
                       f"available_good={available_good}, requested={dispatched_good_eggs}"
            )

        if dispatched_floor_mis_eggs > available_floor_mis:
            raise HTTPException(
                status_code=400,
                detail=f"Dispatched floor/mis eggs exceed available on {entry_date}. "
                       f"available_floor_mis={available_floor_mis}, requested={dispatched_floor_mis_eggs}"
            )

        row = db_conn.execute(
            text("""
                INSERT INTO EggDispatchRecords (
                    farm_id,
                    shed_id,
                    batch_id,
                    batch_no,
                    dispatched_good_eggs,
                    dispatched_floor_mis_eggs,
                    dispatch_date,
                    status
                )
                VALUES (
                    :farm_id,
                    :shed_id,
                    :batch_id,
                    :batch_no,
                    :dispatched_good_eggs,
                    :dispatched_floor_mis_eggs,
                    :dispatch_date,
                    'pending'
                )
                RETURNING dispatch_id
            """),
            {
                "farm_id": farm_id,
                "shed_id": shed_id,
                "batch_id": batch_id,
                "batch_no": batch_no,
                "dispatched_good_eggs": dispatched_good_eggs,
                "dispatched_floor_mis_eggs": dispatched_floor_mis_eggs,
                "dispatch_date": entry_date
            }
        ).mappings().fetchone()

        _mark_dispatch_collected_for_batch(db_conn, batch_id, shed_id=shed_id)

        # Keep tuple shape compatible with existing endpoint usage
        return row["dispatch_id"], batch_id, farm_id

    if conn is not None:
        return _run(conn)

    with engine.begin() as local_conn:
        return _run(local_conn)


@app.post("/api/admin/egg_dispatch")
async def create_egg_dispatch_entry(
    payload: dict,
    current_admin: int = Depends(get_current_admin),
):
    try:
        farm_id = _to_int_safe(payload.get("farm_id"), 0)
        shed_id = _to_int_safe(payload.get("shed_id"), 0)
        batch_id = _to_int_safe(payload.get("batch_id"), 0)
        good = max(0, _to_int_safe(payload.get("dispatched_good_eggs"), 0))
        floor_mis = max(0, _to_int_safe(payload.get("dispatched_floor_mis_eggs"), 0))
        raw_date = payload.get("dispatch_date")
        batch_no = (str(payload.get("batch_no", "")).strip() or None)

        if not farm_id or not shed_id or not batch_id:
            raise HTTPException(status_code=400, detail="farm_id, shed_id and batch_id are required")
        if good + floor_mis <= 0:
            raise HTTPException(status_code=400, detail="Dispatch quantity must be > 0")

        dispatch_date = date.today()
        if raw_date:
            if isinstance(raw_date, datetime):
                # +12h guard: same timezone fix as daily/egg imports
                dispatch_date = (raw_date + timedelta(hours=12)).date()
            elif isinstance(raw_date, date):
                dispatch_date = raw_date
            else:
                try:
                    dispatch_date = datetime.strptime(str(raw_date).strip(), "%Y-%m-%d").date()
                except Exception:
                    raise HTTPException(status_code=400, detail="dispatch_date must be YYYY-MM-DD")

        with engine.begin() as conn:
            _assert_admin_farm_shed(conn, current_admin, farm_id, shed_id)
            dispatch_id, used_batch_id, used_farm_id = save_egg_dispatch_entry_website(
                shed_id=shed_id,
                answers={
                    "batch_id": batch_id,
                    "batch_no": batch_no,
                    "dispatched_good_eggs": good,
                    "dispatched_floor_mis_eggs": floor_mis,
                },
                entry_date=dispatch_date,
                conn=conn,
            )

        return {
            "status": True,
            "message": "Egg dispatch saved",
            "data": {
                "dispatch_id": int(dispatch_id),
                "farm_id": int(used_farm_id),
                "shed_id": int(shed_id),
                "batch_id": int(used_batch_id),
                "dispatch_date": dispatch_date.isoformat(),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _mark_dispatch_collected_for_batch(conn, batch_id: int, shed_id: int | None = None):
    params = {"bid": batch_id}
    shed_filter = ""
    if shed_id is not None:
        shed_filter = " AND shed_id = :sid"
        params["sid"] = shed_id

    collected = conn.execute(text(f"""
        SELECT
            COALESCE(SUM(good_eggs), 0) AS good,
            COALESCE(SUM(floor_eggs), 0) + COALESCE(SUM(mishapped_eggs), 0) AS floor_mis
        FROM EggDailyRecords
        WHERE batch_id = :bid
          {shed_filter}
    """), params).mappings().fetchone()

    dispatched = conn.execute(text(f"""
        SELECT
            COALESCE(SUM(dispatched_good_eggs), 0) AS good,
            COALESCE(SUM(dispatched_floor_mis_eggs), 0) AS floor_mis
        FROM EggDispatchRecords
        WHERE batch_id = :bid
          {shed_filter}
    """), params).mappings().fetchone()

    available_good = int(collected["good"] or 0) - int(dispatched["good"] or 0)
    available_floor_mis = int(collected["floor_mis"] or 0) - int(dispatched["floor_mis"] or 0)

    if available_good <= 0 and available_floor_mis <= 0:
        conn.execute(text(f"""
            UPDATE EggDispatchRecords
            SET status = 'completed'
            WHERE batch_id = :bid
              {shed_filter}
        """), params)
    else:
        conn.execute(text(f"""
            UPDATE EggDispatchRecords
            SET status = 'pending'
            WHERE batch_id = :bid
              {shed_filter}
              AND COALESCE(status, 'pending') <> 'pending'
        """), params)



# Excel import removed — use /api/egg-dispatch/bulk instead
# @app.post("/api/admin/import_egg_dispatch_excel") — REMOVED


@app.get("/api/admin/daily_entries_by_date")
async def admin_daily_entries_by_date(admin_id: int):
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        d.*,
                        s.shed_number,
                        f.farm_name
                    FROM DailyEntries d
                    JOIN Sheds s ON d.shed_id = s.shed_id
                    JOIN Farms f ON s.farm_id = f.farm_id
                    WHERE f.admin_id = :admin_id
                    ORDER BY d.entry_date DESC, d.created_at DESC
                """),
                {"admin_id": admin_id}
            ).mappings().fetchall()

        grouped = {}
        for r in rows:
            date_key = r["entry_date"].isoformat()

            if date_key not in grouped:
                grouped[date_key] = []

            grouped[date_key].append(dict(r))

        return {
            "status": True,
            "total_dates": len(grouped),
            "data": grouped
        }

    except Exception as e:
        print("❌ Admin daily entries group error:", e)
        raise HTTPException(500, "Error fetching grouped admin entries")

@app.get("/api/admin/farms")
async def get_admin_farms(current_admin: int = Depends(get_current_admin)):

    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT farm_id, farm_name
                    FROM Farms
                    WHERE admin_id = :admin_id
                    ORDER BY farm_name ASC
                """),
                {"admin_id": current_admin}
            ).mappings().fetchall()

        return {"status": True, "data": [dict(r) for r in rows]}

    except Exception as e:
        print("❌ Error fetching farms:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/farm_sheds")
async def get_farm_sheds(farm_id: int):
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT shed_id, shed_number
                FROM Sheds
                WHERE farm_id = :farm_id
                ORDER BY shed_number ASC
            """),
            {"farm_id": farm_id}
        ).mappings().fetchall()

    return {"status": True, "data": [dict(r) for r in rows]}


@app.get("/api/admin/all_farm_entries")
async def admin_all_farm_entries(
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:
            sheds = conn.execute(
                text("""
                    SELECT
                        s.shed_id,
                        s.shed_number,
                        f.farm_id,
                        f.farm_name,
                        ab.batch_id
                    FROM Sheds s
                    JOIN Farms f ON f.farm_id = s.farm_id
                    LEFT JOIN LATERAL (
                        SELECT b.batch_id
                        FROM Batches b
                        WHERE b.shed_id = s.shed_id
                          AND b.status = 'active'
                        ORDER BY b.created_at DESC
                        LIMIT 1
                    ) ab ON TRUE
                    WHERE f.admin_id = :admin_id
                    ORDER BY f.farm_name ASC, s.shed_number ASC
                """),
                {"admin_id": current_admin}
            ).mappings().fetchall()

            sheds = [dict(s) for s in sheds]

            shed_label_map = {}
            for s in sheds:
                label = f"{s['farm_name']} | {s['shed_number']}"
                s["shed_label"] = label
                shed_label_map[s["shed_id"]] = label

            daily = conn.execute(
                text("""
                    SELECT
                        d.*,
                        s.shed_number,
                        f.farm_id,
                        f.farm_name
                    FROM DailyEntries d
                    JOIN Sheds s ON d.shed_id = s.shed_id
                    JOIN Farms f ON s.farm_id = f.farm_id
                    WHERE f.admin_id = :admin_id
                      AND d.batch_id = (
                          SELECT b.batch_id
                          FROM Batches b
                          WHERE b.shed_id = d.shed_id
                            AND b.status = 'active'
                          ORDER BY b.created_at DESC
                          LIMIT 1
                      )
                    ORDER BY d.entry_date DESC, d.created_at DESC
                """),
                {"admin_id": current_admin}
            ).mappings().fetchall()

            daily = [dict(e) for e in daily]

            egg = conn.execute(
                text("""
                    SELECT
                        e.*,
                        s.shed_number,
                        f.farm_id,
                        f.farm_name
                    FROM EggDailyRecords e
                    JOIN Sheds s ON e.shed_id = s.shed_id
                    JOIN Farms f ON s.farm_id = f.farm_id
                    WHERE f.admin_id = :admin_id
                      AND e.batch_id = (
                          SELECT b.batch_id
                          FROM Batches b
                          WHERE b.shed_id = e.shed_id
                            AND b.status = 'active'
                          ORDER BY b.created_at DESC
                          LIMIT 1
                      )
                    ORDER BY e.collection_date DESC, e.collection_timestamp DESC
                """),
                {"admin_id": current_admin}
            ).mappings().fetchall()

            egg = [dict(r) for r in egg]

        result = {}
        all_dates = set()

        all_dates.update([d["entry_date"].isoformat() for d in daily])
        all_dates.update([e["collection_date"].isoformat() for e in egg])

        for dt in all_dates:
            result[dt] = {}
            for s in sheds:
                result[dt][s["shed_label"]] = {"daily": [], "egg": []}

        for d in daily:
            dt = d["entry_date"].isoformat()
            label = shed_label_map.get(d["shed_id"], f"{d['farm_name']} | {d['shed_number']}")
            result[dt][label]["daily"].append(d)

        for e in egg:
            dt = e["collection_date"].isoformat()
            label = shed_label_map.get(e["shed_id"], f"{e['farm_name']} | {e['shed_number']}")
            result[dt][label]["egg"].append(e)

        result = dict(sorted(result.items(), reverse=True))

        return {
            "status": True,
            "data": result,
            "sheds": sheds
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ All farm entries error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/all_farm_weekly_entries")
async def admin_all_farm_weekly_entries(
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            active_batches = conn.execute(text("""
                SELECT
                    b.shed_id,
                    b.batch_id,
                    s.shed_number,
                    f.farm_name,
                    f.farm_id
                FROM Batches b
                JOIN Sheds s ON s.shed_id = b.shed_id
                JOIN Farms f ON f.farm_id = s.farm_id
                WHERE f.admin_id = :admin_id
                  AND b.status = 'active'
            """), {"admin_id": current_admin}).mappings().fetchall()

            if not active_batches:
                return {"status": True, "data": []}

            active_map = {
                row["shed_id"]: row["batch_id"]
                for row in active_batches
            }

            shed_ids = list(active_map.keys())

            weekly = conn.execute(text("""
                SELECT
                    w.weekly_id,
                    w.shed_id,
                    w.batch_id,
                    w.farm_id,
                    w.entry_date,
                    w.created_at,
                    w.ammonia_level,
                    w.avg_bird_weight,
                    w.weekly_notes,
                    w.proof_pdf,
                    s.shed_number,
                    f.farm_name
                FROM WeeklyEntries w
                JOIN Sheds s ON s.shed_id = w.shed_id
                JOIN Farms f ON f.farm_id = w.farm_id
                WHERE w.shed_id = ANY(:sids)
                ORDER BY w.entry_date DESC, w.created_at DESC
            """), {"sids": shed_ids}).mappings().fetchall()

        result = []
        for row in weekly:
            active_batch = active_map.get(row["shed_id"])
            if row["batch_id"] != active_batch:
                continue
            result.append(dict(row))

        return {"status": True, "data": result}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ All farm weekly entries error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/farm_entries")
async def admin_farm_entries(
    farm_id: int,
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            # 🔒 STEP 0 — Verify farm belongs to this admin
            farm_check = conn.execute(
                text("""
                    SELECT farm_id
                    FROM Farms
                    WHERE farm_id = :farm_id
                    AND admin_id = :admin_id
                """),
                {
                    "farm_id": farm_id,
                    "admin_id": current_admin
                }
            ).fetchone()

            if not farm_check:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have access to this farm."
                )

            # 1️⃣ Fetch sheds + active batch
            sheds = conn.execute(
                text("""
                    SELECT 
                        s.shed_id, 
                        s.shed_number,
                        b.batch_id
                    FROM Sheds s
                    LEFT JOIN Batches b 
                        ON b.shed_id = s.shed_id AND b.status = 'active'
                    WHERE s.farm_id = :farm_id
                    ORDER BY s.shed_number ASC
                """),
                {"farm_id": farm_id}
            ).mappings().fetchall()

            sheds = [dict(s) for s in sheds]

            # 2️⃣ Fetch DAILY entries
            daily = conn.execute(
                text("""
                    SELECT d.*, s.shed_number
                    FROM DailyEntries d
                    JOIN Sheds s ON d.shed_id = s.shed_id
                    WHERE s.farm_id = :farm_id
                    AND d.batch_id = (
                        SELECT batch_id FROM Batches 
                        WHERE shed_id = d.shed_id AND status = 'active'
                        ORDER BY created_at DESC LIMIT 1
                    )
                    ORDER BY d.entry_date DESC, d.created_at DESC
                """),
                {"farm_id": farm_id}
            ).mappings().fetchall()

            daily = [dict(e) for e in daily]

            # 3️⃣ Fetch EGG entries
            egg = conn.execute(
                text("""
                    SELECT e.*, s.shed_number
                    FROM EggDailyRecords e
                    JOIN Sheds s ON e.shed_id = s.shed_id
                    WHERE e.farm_id = :farm_id
                    AND e.batch_id = (
                        SELECT batch_id FROM Batches
                        WHERE shed_id = e.shed_id AND status = 'active'
                        ORDER BY created_at DESC LIMIT 1
                    )
                    ORDER BY e.collection_date DESC, e.collection_timestamp DESC
                """),
                {"farm_id": farm_id}
            ).mappings().fetchall()

            egg = [dict(r) for r in egg]

        # -----------------------------
        # GROUPING LOGIC (unchanged)
        # -----------------------------
        result = {}
        all_dates = set()

        all_dates.update([d["entry_date"].isoformat() for d in daily])
        all_dates.update([e["collection_date"].isoformat() for e in egg])

        for date in all_dates:
            result[date] = {}
            for s in sheds:
                result[date][s["shed_number"]] = {"daily": [], "egg": []}

        for d in daily:
            date = d["entry_date"].isoformat()
            shed_no = d["shed_number"]
            result[date][shed_no]["daily"].append(d)

        for e in egg:
            date = e["collection_date"].isoformat()
            shed_no = e["shed_number"]
            result[date][shed_no]["egg"].append(e)

        result = dict(sorted(result.items(), reverse=True))

        return {
            "status": True,
            "data": result,
            "sheds": sheds
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Farm entries error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/farm_egg_summary")
async def farm_egg_summary(
    farm_id: int,
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            # 🔒 STEP 0 — Verify farm belongs to current admin
            farm_check = conn.execute(
                text("""
                    SELECT farm_id
                    FROM Farms
                    WHERE farm_id = :farm_id
                    AND admin_id = :admin_id
                """),
                {
                    "farm_id": farm_id,
                    "admin_id": current_admin
                }
            ).fetchone()

            if not farm_check:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have access to this farm."
                )

            # 1️⃣ Fetch sheds + active batches
            sheds = conn.execute(
                text("""
                    SELECT 
                        s.shed_id,
                        b.batch_id
                    FROM Sheds s
                    LEFT JOIN Batches b 
                        ON b.shed_id = s.shed_id AND b.status = 'active'
                    WHERE s.farm_id = :fid
                """),
                {"fid": farm_id}
            ).mappings().fetchall()

            active_batches = [s["batch_id"] for s in sheds if s["batch_id"]]

            if not active_batches:
                return {
                    "status": True,
                    "summary": {
                        "collected_good_total": 0,
                        "collected_floor_total": 0,
                        "collected_mishapped_total": 0,
                        "collected_broken_total": 0,
                        "collected_wastage_total": 0,
                        "collected_floor_mis_total": 0,
                        "dispatched_good_total": 0,
                        "dispatched_floor_mis_total": 0,
                        "closing_good": 0,
                        "closing_floor_mis": 0
                    }
                }

            batch_ids_sql = tuple(active_batches)

            # 2️⃣ Fetch collected eggs
            collected = conn.execute(
                text("""
                    SELECT
                        COALESCE(SUM(good_eggs), 0) AS collected_good,
                        COALESCE(SUM(floor_eggs), 0) AS collected_floor,
                        COALESCE(SUM(broken_cracked_eggs), 0) AS collected_broken,
                        COALESCE(SUM(mishapped_eggs), 0) AS collected_mishapped
                    FROM EggDailyRecords
                    WHERE farm_id = :fid
                    AND batch_id IN :batches
                """),
                {"fid": farm_id, "batches": batch_ids_sql}
            ).mappings().first()

            # 3️⃣ Fetch dispatched eggs
            dispatched = conn.execute(
                text("""
                    SELECT
                        COALESCE(SUM(dispatched_good_eggs), 0) AS dispatched_good,
                        COALESCE(SUM(dispatched_floor_mis_eggs), 0) AS dispatched_floor_mis
                    FROM EggDispatchRecords
                    WHERE farm_id = :fid
                """),
                {"fid": farm_id}
            ).mappings().first()

        # ===============================
        # 4️⃣ Derived Calculations
        # ===============================

        collected_good = collected["collected_good"]
        collected_floor = collected["collected_floor"]
        collected_broken = collected["collected_broken"]
        collected_mishapped = collected["collected_mishapped"]

        collected_floor_mis = collected_floor + collected_mishapped
        collected_wastage = collected_broken

        dispatched_good = dispatched["dispatched_good"]
        dispatched_floor_mis = dispatched["dispatched_floor_mis"]

        closing_good = max(collected_good - dispatched_good, 0)
        closing_floor_mis = max(collected_floor_mis - dispatched_floor_mis, 0)

        summary = {
            "collected_good_total": collected_good,
            "collected_floor_total": collected_floor,
            "collected_mishapped_total": collected_mishapped,
            "collected_broken_total": collected_broken,
            "collected_wastage_total": collected_wastage,
            "collected_floor_mis_total": collected_floor_mis,
            "dispatched_good_total": dispatched_good,
            "dispatched_floor_mis_total": dispatched_floor_mis,
            "closing_good": closing_good,
            "closing_floor_mis": closing_floor_mis
        }

        return {"status": True, "summary": summary}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Farm egg summary error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/all_farm_egg_dispatch")
async def all_farm_egg_dispatch(
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT d.dispatch_id, d.farm_id, d.shed_id, d.batch_id,
                       f.farm_name,
                       s.shed_number,
                       COALESCE(d.batch_no, e.batch_no, CONCAT('BATCH-', d.batch_id::text)) AS batch_no,
                       d.dispatched_good_eggs,
                       d.dispatched_floor_mis_eggs,
                       d.dispatch_date, d.created_at
                FROM EggDispatchRecords d
                JOIN Farms f ON f.farm_id = d.farm_id
                LEFT JOIN Sheds s ON s.shed_id = d.shed_id
                LEFT JOIN LATERAL (
                    SELECT e.batch_no
                    FROM EggDailyRecords e
                    WHERE e.shed_id = d.shed_id
                      AND e.batch_id = d.batch_id
                      AND e.collection_date = d.dispatch_date
                    LIMIT 1
                ) e ON TRUE
                WHERE f.admin_id = :admin_id
                ORDER BY d.dispatch_date DESC
            """), {"admin_id": current_admin}).mappings().fetchall()

        return {"status": True, "data": [dict(r) for r in rows]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        

@app.get("/api/admin/missing_entries_today")
async def missing_entries_today(
    current_admin: int = Depends(get_current_admin)
):
    try:
        today = date.today()

        with engine.begin() as conn:

            # 1️⃣ Fetch all sheds with ACTIVE batches for this admin
            active_sheds = conn.execute(
                text("""
                    SELECT 
                        s.shed_id,
                        s.shed_number,
                        f.farm_name,
                        b.batch_id
                    FROM Sheds s
                    JOIN Farms f ON s.farm_id = f.farm_id
                    JOIN Batches b ON b.shed_id = s.shed_id
                    WHERE f.admin_id = :admin_id
                      AND b.status = 'active'
                    ORDER BY f.farm_name, s.shed_number
                """),
                {"admin_id": current_admin}
            ).mappings().fetchall()

            if not active_sheds:
                return {
                    "status": True,
                    "date": today.isoformat(),
                    "data": []
                }

            # 2️⃣ Get sheds that HAVE daily entries today

            entered_today = conn.execute(
                text("""
                    SELECT DISTINCT d.shed_id
                    FROM DailyEntries d
                    JOIN Sheds s ON s.shed_id = d.shed_id
                    JOIN Farms f ON f.farm_id = s.farm_id
                    WHERE d.entry_date = :today
                    AND f.admin_id = :admin_id
                """),
                {"today": today, "admin_id": current_admin}
            ).scalars().all()

        # 3️⃣ Build missing list
        missing = [
            {
                "farm_name": s["farm_name"],
                "shed_number": s["shed_number"],
                "shed_id": s["shed_id"],
                "batch_id": s["batch_id"]
            }
            for s in active_sheds
            if s["shed_id"] not in entered_today
        ]

        print("🔥 Missing entries:", missing)

        return {
            "status": True,
            "date": today.isoformat(),
            "data": missing
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Missing entries error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))




@app.get("/api/admin/farm_bird_summary")
async def farm_bird_summary(
    farm_id: int,
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            # 🔒 STEP 0 — Verify farm belongs to current admin
            farm_check = conn.execute(
                text("""
                    SELECT farm_id
                    FROM Farms
                    WHERE farm_id = :farm_id
                    AND admin_id = :admin_id
                """),
                {
                    "farm_id": farm_id,
                    "admin_id": current_admin
                }
            ).fetchone()

            if not farm_check:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have access to this farm."
                )

            # 1️⃣ Fetch only sheds WITH ACTIVE BATCHES
            sheds = conn.execute(
                text("""
                    SELECT 
                        s.shed_id,
                        s.shed_number,
                        b.batch_id,
                        b.initial_bird_count AS placed
                    FROM Sheds s
                    JOIN Batches b 
                        ON b.shed_id = s.shed_id 
                       AND b.status = 'active'
                    WHERE s.farm_id = :farm_id
                    ORDER BY s.shed_number ASC
                """),
                {"farm_id": farm_id}
            ).mappings().fetchall()

            if not sheds:
                return {
                    "status": True,
                    "summary": {
                        "total_opening": 0,
                        "total_closing": 0,
                        "mortality": 0,
                        "culling": 0
                    },
                    "by_shed": []
                }

            shed_ids = [s["shed_id"] for s in sheds]

            # 2️⃣ Fetch latest stock ONLY for active sheds
            stock = conn.execute(
                text("""
                    SELECT DISTINCT ON (b.shed_id)
                        b.shed_id,
                        b.batch_id,
                        b.birds_opening,
                        b.birds_closing,
                        b.mortality,
                        b.culling
                    FROM BirdStockHistory b
                    WHERE b.shed_id = ANY(:shed_ids)
                    ORDER BY b.shed_id, b.entry_date DESC, b.id DESC
                """),
                {"shed_ids": shed_ids}
            ).mappings().fetchall()

        # -----------------------------
        # Processing logic (unchanged)
        # -----------------------------

        stock_map = {row["shed_id"]: row for row in stock}

        total_opening = 0
        total_closing = 0
        total_mort = 0
        total_cull = 0
        by_shed = []

        for shed in sheds:
            sid = shed["shed_id"]
            batch_id = shed["batch_id"]
            placed = shed["placed"]

            row = stock_map.get(sid)

            if row and row["batch_id"] == batch_id:
                opening = row["birds_opening"]
                closing = row["birds_closing"]
                mort = row["mortality"]
                cull = row["culling"]
            else:
                opening = placed
                closing = placed
                mort = 0
                cull = 0

            total_opening += opening
            total_closing += closing
            total_mort += mort
            total_cull += cull

            by_shed.append({
                "shed_id": sid,
                "shed_number": shed["shed_number"],
                "batch_id": batch_id,
                "opening": opening,
                "closing": closing,
                "mortality": mort,
                "culling": cull
            })

        return {
            "status": True,
            "summary": {
                "total_opening": total_opening,
                "total_closing": total_closing,
                "mortality": total_mort,
                "culling": total_cull
            },
            "by_shed": by_shed
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Farm bird summary error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/farm_weekly_entries")
def get_farm_weekly_entries(
    farm_id: int,
    current_admin: int = Depends(get_current_admin)
):

    print("\n" + "-"*60)
    print(f"🐔 WEEKLY ENTRY DEBUG (farm_id={farm_id})")
    print("-"*60 + "\n")

    try:
        with engine.begin() as conn:

            # 🔒 STEP 0 — Verify farm belongs to current admin
            farm_check = conn.execute(
                text("""
                    SELECT farm_id
                    FROM Farms
                    WHERE farm_id = :farm_id
                    AND admin_id = :admin_id
                """),
                {
                    "farm_id": farm_id,
                    "admin_id": current_admin
                }
            ).fetchone()

            if not farm_check:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have access to this farm."
                )

            # 1️⃣ Get active batches per shed
            active_batches = conn.execute(text("""
                SELECT 
                    shed_id,
                    batch_id
                FROM Batches
                WHERE farm_id = :fid
                  AND status = 'active'
            """), {"fid": farm_id}).mappings().fetchall()

            active_map = {
                row["shed_id"]: row["batch_id"]
                for row in active_batches
            }

            # 2️⃣ Fetch weekly entries
            weekly_rows = conn.execute(text("""
                SELECT 
                    w.weekly_id,
                    w.farm_id,
                    w.shed_id,
                    s.shed_number,
                    w.entry_date,
                    w.created_at,
                    w.ammonia_level,
                    w.avg_bird_weight,
                    w.weekly_notes,
                    w.proof_pdf,
                    w.batch_id
                FROM WeeklyEntries w
                JOIN Sheds s ON w.shed_id = s.shed_id
                WHERE w.farm_id = :fid
                ORDER BY w.entry_date DESC, w.created_at DESC
            """), {"fid": farm_id}).mappings().fetchall()

        # ----------------------------
        # Filtering logic (unchanged)
        # ----------------------------

        filtered = []

        for row in weekly_rows:
            shed_id = row["shed_id"]
            batch_id = row["batch_id"]
            active_batch = active_map.get(shed_id)

            if active_batch is not None and batch_id == active_batch:
                filtered.append(row)

        return {
            "status": "success",
            "count": len(filtered),
            "data": filtered
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Weekly entries error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/farm_productivity")
def farm_productivity(
    farm_id: int,
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            # 🔒 STEP 0 — Verify farm belongs to current admin
            farm_check = conn.execute(
                text("""
                    SELECT farm_id
                    FROM Farms
                    WHERE farm_id = :farm_id
                    AND admin_id = :admin_id
                """),
                {
                    "farm_id": farm_id,
                    "admin_id": current_admin
                }
            ).fetchone()

            if not farm_check:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have access to this farm."
                )

            # 0️⃣ Fetch active batches
            active_batches = conn.execute(text("""
                SELECT shed_id, batch_id
                FROM Batches
                WHERE farm_id = :fid
                  AND status = 'active'
            """), {"fid": farm_id}).mappings().fetchall()

            active_sheds = {row["shed_id"] for row in active_batches}

            if not active_sheds:
                return {"status": "success", "data": []}

            # 1️⃣ Load bird closing stock (only active sheds)
            birds = conn.execute(text("""
                SELECT 
                    b.shed_id,
                    s.shed_number,
                    b.entry_date,
                    b.birds_closing
                FROM BirdStockHistory b
                JOIN Sheds s ON s.shed_id = b.shed_id
                WHERE s.farm_id = :fid
                  AND b.shed_id = ANY(:active_sheds)
                ORDER BY b.entry_date
            """), {
                "fid": farm_id,
                "active_sheds": list(active_sheds)
            }).mappings().fetchall()

            # 2️⃣ Load egg collection (only active sheds)
            eggs = conn.execute(text("""
                SELECT 
                    e.shed_id,
                    s.shed_number,
                    e.collection_date AS entry_date,
                    e.good_eggs,
                    e.floor_eggs,
                    e.broken_cracked_eggs,
                    e.mishapped_eggs
                FROM EggDailyRecords e
                JOIN Sheds s ON s.shed_id = e.shed_id
                WHERE s.farm_id = :fid
                  AND e.shed_id = ANY(:active_sheds)
                ORDER BY e.collection_date
            """), {
                "fid": farm_id,
                "active_sheds": list(active_sheds)
            }).mappings().fetchall()

        # ---------- MERGE ----------
        merged = {}

        for b in birds:
            date_key = b["entry_date"]
            shed_id = b["shed_id"]

            if date_key not in merged:
                merged[date_key] = {}

            merged[date_key][shed_id] = {
                "shed_number": b["shed_number"],
                "closing_birds": b["birds_closing"],
                "good_eggs": 0,
                "broken": 0,
                "floor": 0,
                "mishap": 0
            }

        for e in eggs:
            date_key = e["entry_date"]
            shed_id = e["shed_id"]

            if date_key not in merged or shed_id not in merged[date_key]:
                continue

            merged[date_key][shed_id]["good_eggs"] += e["good_eggs"]
            merged[date_key][shed_id]["broken"] += e["broken_cracked_eggs"]
            merged[date_key][shed_id]["floor"] += e["floor_eggs"]
            merged[date_key][shed_id]["mishap"] += e["mishapped_eggs"]

        # ---------- ANALYTICS ----------
        result = []

        for date, sheds_data in merged.items():
            for shed_id, v in sheds_data.items():

                birds_count = v["closing_birds"]
                good = v["good_eggs"]
                broken = v["broken"]
                floor = v["floor"]
                mishap = v["mishap"]

                if birds_count <= 0:
                    continue

                if good == 0 and broken == 0 and floor == 0 and mishap == 0:
                    continue

                result.append({
                    "date": str(date),
                    "shed_id": shed_id,
                    "shed_number": v["shed_number"],
                    "closing_birds": birds_count,
                    "good_eggs": good,
                    "broken_eggs": broken,
                    "floor_eggs": floor,
                    "mishapped_eggs": mishap,
                    "productivity_ratio": round(good / birds_count, 4),
                    "wastage_ratio": round(broken / birds_count, 4),
                    "floor_mishap_ratio": round((floor + mishap) / birds_count, 4),
                })

        return {"status": "success", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Farm productivity error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/farm_fcr_weekly")
def farm_fcr_weekly(
    farm_id: int,
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            # 🔒 STEP 0 — Verify farm belongs to current admin
            farm_check = conn.execute(
                text("""
                    SELECT farm_id
                    FROM Farms
                    WHERE farm_id = :farm_id
                    AND admin_id = :admin_id
                """),
                {
                    "farm_id": farm_id,
                    "admin_id": current_admin
                }
            ).fetchone()

            if not farm_check:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have access to this farm."
                )

            # 0️⃣ Fetch ACTIVE batches
            active_batches = conn.execute(text("""
                SELECT shed_id, batch_id
                FROM Batches
                WHERE farm_id = :fid
                  AND status = 'active'
            """), {"fid": farm_id}).mappings().fetchall()

            active_sheds = {row["shed_id"] for row in active_batches}

            if not active_sheds:
                return {"status": "success", "data": []}

            # 1️⃣ DAILY FEED
            feed_rows = conn.execute(text("""
                SELECT 
                    d.shed_id,
                    s.shed_number,
                    d.entry_date,
                    COALESCE(d.feed_consumption_kg, 0) AS feed_kg
                FROM DailyEntries d
                JOIN Sheds s ON s.shed_id = d.shed_id
                WHERE s.farm_id = :fid
                  AND d.shed_id = ANY(:active_sheds)
                ORDER BY d.entry_date
            """), {
                "fid": farm_id,
                "active_sheds": list(active_sheds)
            }).mappings().fetchall()

            # 2️⃣ WEEKLY WEIGHTS
            weight_rows = conn.execute(text("""
                SELECT
                    w.shed_id,
                    s.shed_number,
                    w.entry_date,
                    COALESCE(w.avg_bird_weight, 0) AS avg_weight
                FROM WeeklyEntries w
                JOIN Sheds s ON s.shed_id = w.shed_id
                WHERE s.farm_id = :fid
                  AND w.shed_id = ANY(:active_sheds)
                ORDER BY w.entry_date
            """), {
                "fid": farm_id,
                "active_sheds": list(active_sheds)
            }).mappings().fetchall()

            # 3️⃣ BIRD STOCK HISTORY
            bird_rows = conn.execute(text("""
                SELECT
                    b.shed_id,
                    b.entry_date,
                    b.birds_closing
                FROM BirdStockHistory b
                JOIN Sheds s ON s.shed_id = b.shed_id
                WHERE s.farm_id = :fid
                  AND b.shed_id = ANY(:active_sheds)
                ORDER BY b.entry_date
            """), {
                "fid": farm_id,
                "active_sheds": list(active_sheds)
            }).mappings().fetchall()

        # ---------- ORGANIZE DATA ----------
        from collections import defaultdict

        bird_by_shed = defaultdict(list)
        for b in bird_rows:
            bird_by_shed[b["shed_id"]].append(
                (b["entry_date"], b["birds_closing"])
            )

        for sid in bird_by_shed:
            bird_by_shed[sid].sort()

        weights = defaultdict(list)
        for w in weight_rows:
            weights[w["shed_id"]].append(w)

        for sid in weights:
            weights[sid].sort(key=lambda x: x["entry_date"])

        feed_by_shed = defaultdict(list)
        for f in feed_rows:
            feed_by_shed[f["shed_id"]].append(
                (f["entry_date"], float(f["feed_kg"]))
            )

        # ---------- CALCULATE FCR ----------
        result = []

        for shed_id, weekly_list in weights.items():

            if len(weekly_list) < 2:
                continue

            for i in range(1, len(weekly_list)):

                prev = weekly_list[i - 1]
                curr = weekly_list[i]

                gain_per_bird = (
                    (curr["avg_weight"] - prev["avg_weight"]) / 1000.0
                )

                if gain_per_bird <= 0:
                    continue

                closing_birds = None
                for date, birds in bird_by_shed[shed_id]:
                    if date <= curr["entry_date"]:
                        closing_birds = birds
                    else:
                        break

                if not closing_birds:
                    continue

                total_weight_gain = closing_birds * gain_per_bird

                feed_total = sum(
                    feed for (d, feed) in feed_by_shed[shed_id]
                    if prev["entry_date"] < d <= curr["entry_date"]
                )

                if feed_total <= 0:
                    continue

                fcr = round(feed_total / total_weight_gain, 3)

                result.append({
                    "shed_id": shed_id,
                    "shed_number": curr["shed_number"],
                    "week": curr["entry_date"].isocalendar().week,
                    "date_from": str(prev["entry_date"]),
                    "date_to": str(curr["entry_date"]),
                    "avg_weight_prev": prev["avg_weight"],
                    "avg_weight_curr": curr["avg_weight"],
                    "gain_per_bird_kg": round(gain_per_bird, 4),
                    "closing_birds": closing_birds,
                    "total_weight_gain_kg": round(total_weight_gain, 2),
                    "weekly_feed_kg": round(feed_total, 2),
                    "fcr": fcr
                })

        return {"status": "success", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Farm FCR error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/api/admin/mortality_culling_trend")
def mortality_culling_trend(
    farm_id: int,
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            # 🔒 STEP 0 — Verify farm belongs to current admin
            farm_check = conn.execute(
                text("""
                    SELECT farm_id
                    FROM Farms
                    WHERE farm_id = :farm_id
                    AND admin_id = :admin_id
                """),
                {
                    "farm_id": farm_id,
                    "admin_id": current_admin
                }
            ).fetchone()

            if not farm_check:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have access to this farm."
                )

            # 1️⃣ Get sheds with ACTIVE batches only
            active_sheds = conn.execute(text("""
                SELECT shed_id
                FROM Batches
                WHERE farm_id = :fid
                  AND status = 'active'
            """), {"fid": farm_id}).scalars().all()

            if not active_sheds:
                return {"status": "success", "data": []}

            # 2️⃣ Clean SELECT using DISTINCT ON
            rows = conn.execute(text("""
                WITH latest_daily AS (
                    SELECT DISTINCT ON (shed_id, entry_date)
                        shed_id, entry_date, mortality, culling
                    FROM DailyEntries
                    WHERE shed_id = ANY(:sids)
                    ORDER BY shed_id, entry_date DESC, entry_id DESC
                ),
                latest_stock AS (
                    SELECT DISTINCT ON (shed_id, entry_date)
                        shed_id, entry_date, birds_closing
                    FROM BirdStockHistory
                    WHERE shed_id = ANY(:sids)
                    ORDER BY shed_id, entry_date DESC, id DESC
                )
                SELECT 
                    d.shed_id,
                    s.shed_number,
                    d.entry_date,
                    d.mortality,
                    d.culling,
                    b.birds_closing
                FROM latest_daily d
                JOIN latest_stock b 
                    ON b.shed_id = d.shed_id 
                   AND b.entry_date = d.entry_date
                JOIN Sheds s ON s.shed_id = d.shed_id
                ORDER BY d.entry_date ASC
            """), {"sids": active_sheds}).mappings().fetchall()

        # 3️⃣ Build output
        final = []
        for r in rows:
            closing = r["birds_closing"]

            if not closing or closing <= 0:
                continue

            final.append({
                "date": str(r["entry_date"]),
                "shed": r["shed_number"],
                "mortality_pct": round((r["mortality"] / closing) * 100, 3),
                "culling_pct": round((r["culling"] / closing) * 100, 3)
            })

        return {"status": True, "data": final}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Mortality trend error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/api/admin/farm_water_trend")
def farm_water_trend(
    farm_id: int,
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            # 🔒 STEP 0 — Verify farm belongs to current admin
            farm_check = conn.execute(
                text("""
                    SELECT farm_id
                    FROM Farms
                    WHERE farm_id = :farm_id
                    AND admin_id = :admin_id
                """),
                {
                    "farm_id": farm_id,
                    "admin_id": current_admin
                }
            ).fetchone()

            if not farm_check:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have access to this farm."
                )

            # 1️⃣ Fetch active-batch sheds only
            active_sheds = conn.execute(text("""
                SELECT shed_id
                FROM Batches
                WHERE farm_id = :fid
                  AND status = 'active'
            """), {"fid": farm_id}).scalars().all()

            if not active_sheds:
                return {"status": "success", "data": []}

            # 2️⃣ Sum WATER per shed per date
            water_rows = conn.execute(text("""
                SELECT
                    d.shed_id,
                    s.shed_number,
                    d.entry_date,
                    SUM(COALESCE(d.water_consumed_ltrs, 0)) AS total_water
                FROM DailyEntries d
                JOIN Sheds s ON s.shed_id = d.shed_id
                WHERE d.shed_id = ANY(:sids)
                GROUP BY d.shed_id, s.shed_number, d.entry_date
                ORDER BY d.entry_date
            """), {"sids": active_sheds}).mappings().fetchall()

            # 3️⃣ Get latest bird stock per shed per date
            stock_rows = conn.execute(text("""
                SELECT DISTINCT ON (b.shed_id, b.entry_date)
                    b.shed_id,
                    b.entry_date,
                    b.birds_closing
                FROM BirdStockHistory b
                WHERE b.shed_id = ANY(:sids)
                ORDER BY b.shed_id, b.entry_date, b.id DESC
            """), {"sids": active_sheds}).mappings().fetchall()

        # -------------------------------------
        # BUILD STOCK LOOKUP MAP
        # -------------------------------------
        from collections import defaultdict
        stock_map = defaultdict(dict)

        for b in stock_rows:
            stock_map[b["entry_date"]][b["shed_id"]] = b["birds_closing"]

        # -------------------------------------
        # FINAL TREND RESULTS
        # -------------------------------------
        result = []

        for row in water_rows:
            shed_id = row["shed_id"]
            date = row["entry_date"]
            shed_no = row["shed_number"]
            total_water = float(row["total_water"])

            closing = stock_map.get(date, {}).get(shed_id)
            if closing is None or closing <= 0:
                continue

            result.append({
                "date": str(date),
                "shed_id": shed_id,
                "shed_number": shed_no,
                "water_ltrs": round(total_water, 2),
                "closing_birds": closing,
                "water_per_bird": round(total_water / closing, 4)
            })

        return {"status": "success", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Farm water trend error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/feed_water_correlation")
def feed_water_correlation(
    farm_id: int,
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            # 🔒 STEP 0 — Verify farm belongs to current admin
            farm_check = conn.execute(
                text("""
                    SELECT farm_id
                    FROM Farms
                    WHERE farm_id = :farm_id
                    AND admin_id = :admin_id
                """),
                {
                    "farm_id": farm_id,
                    "admin_id": current_admin
                }
            ).fetchone()

            if not farm_check:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have access to this farm."
                )

            # 1️⃣ Fetch ACTIVE batch sheds
            active_sheds = conn.execute(text("""
                SELECT shed_id
                FROM Batches
                WHERE farm_id = :fid 
                  AND status = 'active'
            """), {"fid": farm_id}).scalars().all()

            if not active_sheds:
                return {"status": "success", "data": []}

            # 2️⃣ SUM feed + water per shed per date
            daily = conn.execute(text("""
                SELECT 
                    d.shed_id,
                    s.shed_number,
                    d.entry_date,
                    SUM(COALESCE(d.feed_consumption_kg, 0)) AS total_feed,
                    SUM(COALESCE(d.water_consumed_ltrs, 0)) AS total_water,
                    SUM(COALESCE(d.mortality, 0)) AS mortality,
                    SUM(COALESCE(d.culling, 0)) AS culling,
                    MAX(d.temperature) AS temperature
                FROM DailyEntries d
                JOIN Sheds s ON s.shed_id = d.shed_id
                WHERE d.shed_id = ANY(:sids)
                GROUP BY d.shed_id, s.shed_number, d.entry_date
                ORDER BY d.entry_date
            """), {"sids": active_sheds}).mappings().fetchall()

            # 3️⃣ Latest closing birds
            birds = conn.execute(text("""
                SELECT DISTINCT ON (b.shed_id, b.entry_date)
                    b.shed_id,
                    b.entry_date,
                    b.birds_closing
                FROM BirdStockHistory b
                WHERE b.shed_id = ANY(:sids)
                ORDER BY b.shed_id, b.entry_date, b.id DESC
            """), {"sids": active_sheds}).mappings().fetchall()

        # -------------------------------------
        # Build bird lookup
        # -------------------------------------
        bird_map = {
            (b["shed_id"], b["entry_date"]): b["birds_closing"]
            for b in birds
        }

        # -------------------------------------
        # Final calculation
        # -------------------------------------
        result = []

        for d in daily:
            closing = bird_map.get((d["shed_id"], d["entry_date"]))

            if not closing or closing <= 0:
                continue

            feed_per_bird = (
                d["total_feed"] / closing if d["total_feed"] else 0
            )

            water_per_bird = (
                d["total_water"] / closing if d["total_water"] else 0
            )

            mortality_pct = (
                (d["mortality"] / closing) * 100 if d["mortality"] else 0
            )

            culling_pct = (
                (d["culling"] / closing) * 100 if d["culling"] else 0
            )

            result.append({
                "date": str(d["entry_date"]),
                "shed_id": d["shed_id"],
                "shed_number": d["shed_number"],
                "feed_per_bird": round(feed_per_bird, 4),
                "water_per_bird": round(water_per_bird, 4),
                "temperature": d["temperature"],
                "mortality_pct": round(mortality_pct, 4),
                "culling_pct": round(culling_pct, 4),
            })

        return {"status": "success", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Feed-water correlation error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/temp_water_mortality")
def temp_water_mortality(
    farm_id: int,
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            # 🔒 Verify farm ownership
            farm_check = conn.execute(
                text("""
                    SELECT farm_id
                    FROM Farms
                    WHERE farm_id = :farm_id
                      AND admin_id = :admin_id
                """),
                {
                    "farm_id": farm_id,
                    "admin_id": current_admin
                }
            ).fetchone()

            if not farm_check:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have access to this farm."
                )

            # Active sheds only
            active_sheds = conn.execute(text("""
                SELECT shed_id
                FROM Batches
                WHERE farm_id = :fid
                  AND status = 'active'
            """), {"fid": farm_id}).scalars().all()

            if not active_sheds:
                return {"status": "success", "data": []}

            # Daily aggregation
            daily = conn.execute(text("""
                SELECT 
                    d.shed_id,
                    s.shed_number,
                    d.entry_date,
                    SUM(COALESCE(d.water_consumed_ltrs, 0)) AS total_water,
                    SUM(COALESCE(d.mortality, 0)) AS total_mortality,
                    MAX(d.temperature) AS temperature
                FROM DailyEntries d
                JOIN Sheds s ON s.shed_id = d.shed_id
                WHERE d.shed_id = ANY(:sids)
                GROUP BY d.shed_id, s.shed_number, d.entry_date
                ORDER BY d.entry_date
            """), {"sids": active_sheds}).mappings().fetchall()

            birds = conn.execute(text("""
                SELECT DISTINCT ON (b.shed_id, b.entry_date)
                    b.shed_id,
                    b.entry_date,
                    b.birds_closing
                FROM BirdStockHistory b
                WHERE b.shed_id = ANY(:sids)
                ORDER BY b.shed_id, b.entry_date, b.id DESC
            """), {"sids": active_sheds}).mappings().fetchall()

        bird_map = {
            (b["shed_id"], b["entry_date"]): b["birds_closing"]
            for b in birds
        }

        result = []

        for d in daily:
            closing = bird_map.get((d["shed_id"], d["entry_date"]))
            if not closing or closing <= 0:
                continue

            water_per_bird = d["total_water"] / closing if d["total_water"] else 0
            mort_pct = (d["total_mortality"] / closing) * 100 if d["total_mortality"] else 0

            result.append({
                "date": str(d["entry_date"]),
                "shed_id": d["shed_id"],
                "shed_number": d["shed_number"],
                "temperature": d["temperature"],
                "water_per_bird": round(water_per_bird, 4),
                "mortality_pct": round(mort_pct, 4)
            })

        return {"status": "success", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Temp-water-mortality error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/weekly_ammonia_trend")
def weekly_ammonia_trend(
    farm_id: int,
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            # 🔒 Verify farm ownership
            farm_check = conn.execute(
                text("""
                    SELECT farm_id
                    FROM Farms
                    WHERE farm_id = :farm_id
                      AND admin_id = :admin_id
                """),
                {
                    "farm_id": farm_id,
                    "admin_id": current_admin
                }
            ).fetchone()

            if not farm_check:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have access to this farm."
                )

            active_rows = conn.execute(text("""
                SELECT shed_id, batch_id
                FROM Batches
                WHERE farm_id = :fid
                  AND status = 'active'
            """), {"fid": farm_id}).mappings().fetchall()

            active_map = {
                row["shed_id"]: row["batch_id"]
                for row in active_rows
            }

            active_sheds = list(active_map.keys())

            if not active_sheds:
                return {"status": True, "data": []}

            weekly = conn.execute(text("""
                SELECT 
                    w.entry_date,
                    w.shed_id,
                    w.batch_id,
                    s.shed_number,
                    w.ammonia_level,
                    w.avg_bird_weight
                FROM WeeklyEntries w
                JOIN Sheds s ON s.shed_id = w.shed_id
                WHERE w.shed_id = ANY(:sids)
                ORDER BY w.entry_date
            """), {"sids": active_sheds}).mappings().fetchall()

        result = []

        for r in weekly:
            active_batch = active_map.get(r["shed_id"])
            if r["batch_id"] != active_batch:
                continue

            result.append({
                "date": str(r["entry_date"]),
                "shed_id": r["shed_id"],
                "shed_number": r["shed_number"],
                "ammonia_level": r["ammonia_level"],
                "avg_bird_weight": r["avg_bird_weight"],
            })

        return {"status": True, "data": result}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Weekly ammonia error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


def summarize_daily_entries(entries):
    """
    Summaries all entries for a shed + date
    Morning + evening + multiple entries merged
    """

    if not entries:
        return None

    mortality_total = 0
    culling_total = 0
    feed_total = 0
    water_total = 0
    lighting_total = 0
    temp_min = None
    temp_max = None
    medical_attention = False
    medical_notes = []
    proofs = []

    for e in entries:
        mortality_total += e["mortality"] or 0
        culling_total += e["culling"] or 0
        feed_total += e["feed_consumption_kg"] or 0
        water_total += e["water_consumed_ltrs"] or 0
        lighting_total += e["lighting_hours"] or 0

        # Min temperature
        if e["temperature"] is not None:
            if temp_min is None or e["temperature"] < temp_min:
                temp_min = e["temperature"]

        # Max temperature
        if e["temperature"] is not None:
            if temp_max is None or e["temperature"] > temp_max:
                temp_max = e["temperature"]

        # Medical
        if e["medical_attention"]:
            medical_attention = True
        if e["medical_notes"]:
            medical_notes.append(e["medical_notes"])

        # Proofs
        if e["proof_pdf"]:
            proofs.append(e["proof_pdf"])

    return {
        "mortality": mortality_total,
        "culling": culling_total,
        "feed_total": float(feed_total),
        "water_total": float(water_total),
        "lighting_total": float(lighting_total),
        "temp_min": temp_min,
        "temp_max": temp_max,
        "medical_attention": medical_attention,
        "medical_notes": medical_notes,
        "proofs": proofs
    }

@app.get("/api/admin/farm_daily_summary")
async def get_daily_summary(farm_id: int):
    try:
        with engine.begin() as conn:
            def _date_key(v):
                if v is None:
                    return None
                if isinstance(v, datetime):
                    v = v.date()
                if isinstance(v, date):
                    return v.isoformat()
                return str(v)

            # 1️⃣ GET SHEDS + THEIR ACTIVE BATCHES
            active_rows = conn.execute(text("""
                SELECT s.shed_id, s.shed_number, b.batch_id
                FROM Sheds s
                LEFT JOIN Batches b 
                    ON b.shed_id = s.shed_id
                   AND b.status = 'active'
                WHERE s.farm_id = :fid
            """), {"fid": farm_id}).mappings().fetchall()

            # Only keep sheds that HAVE an active batch
            active_sheds = {
                row["shed_id"]: row["batch_id"]
                for row in active_rows
                if row["batch_id"] is not None
            }

            if not active_sheds:
                print("⚠ No active batches – returning empty summary")
                return {"status": True, "data": []}

            # Map shed_id → shed_number
            shed_map = {row["shed_id"]: row["shed_number"] for row in active_rows}
            shed_id_list = list(active_sheds.keys())

            # 2️⃣ PULL DAILY ENTRIES ONLY FOR ACTIVE SHEDS
            rows = conn.execute(text("""
                SELECT 
                    entry_id,
                    shed_id,
                    batch_id,
                    entry_date,
                    mortality,
                    culling,
                    culling_reason,
                    feed_consumption_kg,
                    water_consumed_ltrs,
                    temperature,
                    lighting_hours,
                    medical_attention,
                    medical_notes,
                    proof_pdf,
                    created_at
                FROM DailyEntries
                WHERE shed_id = ANY(:shed_ids)
                ORDER BY entry_date ASC, created_at ASC
            """), {"shed_ids": shed_id_list}).mappings().fetchall()

            # egg collection per shed per date ──
            egg_rows = conn.execute(text("""
                SELECT shed_id, collection_date,
                       SUM(good_eggs) AS good_eggs,
                       SUM(floor_eggs) AS floor_eggs,
                       SUM(broken_cracked_eggs) AS broken_eggs,
                       SUM(mishapped_eggs) AS mishapped_eggs
                FROM EggDailyRecords
                WHERE shed_id = ANY(:shed_ids)
                  AND batch_id = ANY(:batch_ids)
                GROUP BY shed_id, collection_date
            """), {
                "shed_ids": shed_id_list,
                "batch_ids": list(active_sheds.values())
            }).mappings().fetchall()

        # egg dispatch per shed per date (active batches only)
            dispatch_rows = conn.execute(text("""
                SELECT shed_id, dispatch_date,
                       SUM(dispatched_good_eggs) AS dispatched_good,
                       SUM(dispatched_floor_mis_eggs) AS dispatched_floor_mis
                FROM EggDispatchRecords
                WHERE shed_id = ANY(:shed_ids)
                  AND batch_id = ANY(:batch_ids)
                GROUP BY shed_id, dispatch_date
            """), {
                "shed_ids": shed_id_list,
                "batch_ids": list(active_sheds.values()),
            }).mappings().fetchall()

        # ── NEW: weekly entries per shed per date ──
            weekly_rows = conn.execute(text("""
                SELECT shed_id, entry_date,
                       ammonia_level, avg_bird_weight, weekly_notes
                FROM WeeklyEntries
                WHERE shed_id = ANY(:shed_ids)
                  AND batch_id = ANY(:batch_ids)
                ORDER BY entry_date ASC
            """), {
                "shed_ids": shed_id_list,
                "batch_ids": list(active_sheds.values())
            }).mappings().fetchall()

            # ── build egg lookup: (shed_id, date) → egg data ──
            egg_map = {}
            for e in egg_rows:
                key = (e["shed_id"], _date_key(e["collection_date"]))
                egg_map[key] = {
                    "good_eggs": int(e["good_eggs"] or 0),
                    "floor_eggs": int(e["floor_eggs"] or 0),
                    "broken_eggs": int(e["broken_eggs"] or 0),
                    "mishapped_eggs": int(e["mishapped_eggs"] or 0),
                }

            # ── build dispatch lookup: (shed_id, date) → dispatch data ──
            dispatch_map = {}
            for d in dispatch_rows:
                dispatch_map[(d["shed_id"], _date_key(d["dispatch_date"]))] = {
                    "dispatched_good": int(d["dispatched_good"] or 0),
                    "dispatched_floor_mis": int(d["dispatched_floor_mis"] or 0),
                }

            # ── build weekly lookup: (shed_id, date) → weekly data ──
            weekly_map = {}
            for w in weekly_rows:
                key = (w["shed_id"], _date_key(w["entry_date"]))
                weekly_map[key] = {
                    "ammonia_level": w["ammonia_level"],
                    "avg_bird_weight": w["avg_bird_weight"],
                    "weekly_notes": w["weekly_notes"],
                }

        # 3️⃣ KEEP ONLY MATCHING ACTIVE BATCH ROWS
        filtered_rows = []
        for r in rows:
            active_batch = active_sheds.get(r["shed_id"])

            # Skip legacy data or wrong batch
            if r["batch_id"] != active_batch:
                continue

            filtered_rows.append(r)

        # 4️⃣ GROUP BY (shed_id, entry_date)
        grouped = {}
        for r in filtered_rows:
            key = (r["shed_id"], _date_key(r["entry_date"]))
            grouped.setdefault(key, []).append(r)

        # 5️⃣ BUILD FINAL SUMMARY LIST
        final_summary = []
        for (shed_id, entry_date), entry_rows in grouped.items():

            summary = summarize_daily_entries(entry_rows)

            egg_key = (shed_id, entry_date)
            dispatch_key = (shed_id, entry_date)
            weekly_key = (shed_id, entry_date)

            # attach egg collection
            summary["egg_collection"] = egg_map.get(egg_key, None)

            # attach dispatch (shed-level, same date)
            summary["egg_dispatch"] = dispatch_map.get(dispatch_key, None)

            # attach weekly
            summary["weekly"] = weekly_map.get(weekly_key, None)


            final_summary.append({
                "shed_id": shed_id,
                "shed_number": shed_map.get(shed_id),
                "entry_date": entry_date,
                **summary
            })

        # 6️⃣ SORT MOST RECENT FIRST
        final_summary.sort(key=lambda x: x["entry_date"], reverse=True)

        return {"status": True, "data": final_summary}

    except Exception as e:
        print("❌ Error summary:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/global_summary_cards")
def global_summary_cards(current_admin: int = Depends(get_current_admin)):

    try:
        with engine.begin() as conn:


            # 1️⃣ Fetch all farms for this admin
            farms = conn.execute(text("""
                SELECT farm_id 
                FROM Farms
                WHERE admin_id = :aid
            """), {"aid": current_admin}).fetchall()

            if not farms:
                return {
                    "status": "success",
                    "data": {
                        "farms": 0,
                        "sheds": 0,
                        "total_birds": 0,
                        "good_eggs": 0,
                        "floor_mishap_eggs": 0,
                        "total_egg_stock": 0
                    }
                }

            farm_ids = tuple(f[0] for f in farms)
            print(f"🏡 Farms ({len(farm_ids)}): {farm_ids}")

            # 2️⃣ Fetch ONLY sheds that have an active batch
            sheds = conn.execute(text("""
                SELECT 
                    s.shed_id,
                    b.batch_id
                FROM Sheds s
                JOIN Batches b 
                    ON b.shed_id = s.shed_id
                   AND b.status = 'active'
                WHERE s.farm_id IN :fids
            """), {"fids": farm_ids}).mappings().fetchall()

            if not sheds:
                print("❗ No sheds with active batches.\n")
                return {
                    "status": "success",
                    "data": {
                        "farms": len(farm_ids),
                        "sheds": 0,
                        "total_birds": 0,
                        "good_eggs": 0,
                        "floor_mishap_eggs": 0,
                        "total_egg_stock": 0
                    }
                }

            shed_ids = tuple(s["shed_id"] for s in sheds)
            print(f"🐤 Active-Batch Sheds ONLY ({len(shed_ids)}): {shed_ids}")

            # 3️⃣ LATEST Bird Stock per active shed
            birds = conn.execute(text("""
                SELECT b.shed_id, b.birds_closing
                FROM BirdStockHistory b
                INNER JOIN (
                    SELECT shed_id, MAX(id) AS max_id
                    FROM BirdStockHistory
                    WHERE shed_id IN :sids
                    GROUP BY shed_id
                ) latest ON latest.max_id = b.id
            """), {"sids": shed_ids}).fetchall()

            total_closing_birds = sum(row.birds_closing for row in birds)

            # 4️⃣ GLOBAL Egg Summary (LIVE)
            collected = conn.execute(text("""
                SELECT
                    COALESCE(SUM(good_eggs), 0) AS collected_good,
                    COALESCE(SUM(floor_eggs), 0) AS collected_floor,
                    COALESCE(SUM(mishapped_eggs), 0) AS collected_mishap,
                    COALESCE(SUM(broken_cracked_eggs), 0) AS collected_broken
                FROM EggDailyRecords
                WHERE shed_id IN :sids
            """), {"sids": shed_ids}).mappings().first()

            dispatched = conn.execute(text("""
                SELECT
                    COALESCE(SUM(dispatched_good_eggs), 0) AS dispatched_good,
                    COALESCE(SUM(dispatched_floor_mis_eggs), 0) AS dispatched_floor_mis
                FROM EggDispatchRecords
                WHERE farm_id IN :fids
            """), {"fids": farm_ids}).mappings().first()

            collected_floor_mis = (
                collected["collected_floor"] +
                collected["collected_mishap"]
            )

            closing_good = max(
                collected["collected_good"] - dispatched["dispatched_good"], 0
            )

            closing_floor_mis = max(
                collected_floor_mis - dispatched["dispatched_floor_mis"], 0
            )

            total_egg_stock = closing_good + closing_floor_mis


            return {
                "status": "success",
                "data": {
                    "farms": len(farm_ids),
                    "sheds": len(shed_ids),
                    "total_birds": total_closing_birds,
                    "good_eggs": closing_good,
                    "floor_mishap_eggs": closing_floor_mis,
                    "total_egg_stock": total_egg_stock,
                },
            }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Global summary error:", str(e))
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error"
        )



# ============================================================
# 🔥 1. HELPER: GET ALL SHEDS FOR AN ADMIN
# ============================================================
# ============================================================
# 🔥 1. HELPER: GET ONLY ACTIVE-BATCH SHEDS FOR AN ADMIN
# ============================================================
def get_admin_sheds(conn, admin_id: int):
    rows = conn.execute(text("""
        SELECT 
            s.shed_id,
            s.shed_number,
            b.batch_id
        FROM Sheds s
        JOIN Farms f ON f.farm_id = s.farm_id
        LEFT JOIN Batches b 
            ON b.shed_id = s.shed_id
           AND b.status = 'active'
        WHERE f.admin_id = :aid
    """), {"aid": admin_id}).mappings().fetchall()

    # ❗ Only include sheds that have an active batch
    active_sheds = {
        r.shed_id: r.shed_number
        for r in rows
        if r.batch_id is not None
    }

    print("get_admin_sheds ACTIVE sheds only:", active_sheds)
    return active_sheds


# ============================================================
# 🔥 2. GLOBAL PRODUCTIVITY (ALL FARMS)
# ============================================================

@app.get("/api/admin/global_productivity")
def global_productivity(
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            # 🔒 Get only sheds belonging to this admin (active-batch only)
            shed_map = get_admin_sheds(conn, current_admin)

            if not shed_map:
                return {"status": "success", "data": []}

            shed_ids = list(shed_map.keys())

            # DAILY BIRD STOCK
            birds = conn.execute(
                text("""
                    SELECT shed_id, entry_date, birds_closing
                    FROM BirdStockHistory
                    WHERE shed_id IN :sids
                    ORDER BY entry_date
                """).bindparams(bindparam("sids", expanding=True)),
                {"sids": shed_ids}
            ).mappings().fetchall()

            # DAILY EGGS
            eggs = conn.execute(
                text("""
                    SELECT shed_id, collection_date AS entry_date,
                           good_eggs, floor_eggs,
                           broken_cracked_eggs, mishapped_eggs
                    FROM EggDailyRecords
                    WHERE shed_id IN :sids
                    ORDER BY collection_date
                """).bindparams(bindparam("sids", expanding=True)),
                {"sids": shed_ids}
            ).mappings().fetchall()

        # -------------------------------
        # MERGE LOGIC
        # -------------------------------
        merged = defaultdict(lambda: defaultdict(lambda: {
            "good": 0,
            "broken": 0,
            "floor": 0,
            "mishap": 0,
            "birds": 0,
        }))

        for b in birds:
            merged[b["entry_date"]][b["shed_id"]]["birds"] = b["birds_closing"]

        for e in eggs:
            block = merged[e["entry_date"]][e["shed_id"]]
            block["good"] += e["good_eggs"]
            block["broken"] += e["broken_cracked_eggs"]
            block["floor"] += e["floor_eggs"]
            block["mishap"] += e["mishapped_eggs"]

        # -------------------------------
        # BUILD RESULT
        # -------------------------------
        result = []

        for date, shedData in merged.items():
            for sid, v in shedData.items():

                birds = v["birds"]
                if birds <= 0:
                    continue

                good = v["good"]
                broken = v["broken"]
                floor = v["floor"]
                mishap = v["mishap"]

                if good + broken + floor + mishap == 0:
                    continue

                result.append({
                    "date": str(date),
                    "shed_id": sid,
                    "shed_number": shed_map[sid],
                    "closing_birds": birds,
                    "good_eggs": good,
                    "broken_eggs": broken,
                    "floor_eggs": floor,
                    "mishapped_eggs": mishap,
                    "productivity_ratio": round(good / birds, 4),
                    "wastage_ratio": round(broken / birds, 4),
                    "floor_mishap_ratio": round((floor + mishap) / birds, 4),
                })

        return {"status": "success", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Global productivity error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 🔥 3. GLOBAL FCR (ALL FARMS)
# ============================================================
@app.get("/api/admin/global_fcr_weekly")
def global_fcr_weekly(
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            # 🔒 Only sheds belonging to this admin (active batches only)
            shed_map = get_admin_sheds(conn, current_admin)

            if not shed_map:
                return {"status": "success", "data": []}

            shed_ids = list(shed_map.keys())

            # DAILY FEED
            feed_rows = conn.execute(
                text("""
                    SELECT shed_id, entry_date, feed_consumption_kg
                    FROM DailyEntries
                    WHERE shed_id IN :sids
                    ORDER BY entry_date
                """).bindparams(bindparam("sids", expanding=True)),
                {"sids": shed_ids}
            ).mappings().fetchall()

            # WEEKLY WEIGHTS
            weight_rows = conn.execute(
                text("""
                    SELECT shed_id, entry_date, avg_bird_weight
                    FROM WeeklyEntries
                    WHERE shed_id IN :sids
                    ORDER BY entry_date
                """).bindparams(bindparam("sids", expanding=True)),
                {"sids": shed_ids}
            ).mappings().fetchall()

            # DAILY BIRDS
            bird_rows = conn.execute(
                text("""
                    SELECT shed_id, entry_date, birds_closing
                    FROM BirdStockHistory
                    WHERE shed_id IN :sids
                    ORDER BY entry_date
                """).bindparams(bindparam("sids", expanding=True)),
                {"sids": shed_ids}
            ).mappings().fetchall()

        # ---------------------------
        # ORGANIZE DATA
        # ---------------------------

        bird_by_shed = defaultdict(list)
        for b in bird_rows:
            bird_by_shed[b["shed_id"]].append(
                (b["entry_date"], b["birds_closing"])
            )
        for sid in bird_by_shed:
            bird_by_shed[sid].sort()

        feed_by_shed = defaultdict(list)
        for f in feed_rows:
            feed_by_shed[f["shed_id"]].append(
                (f["entry_date"], float(f["feed_consumption_kg"] or 0))
            )

        weight_by_shed = defaultdict(list)
        for w in weight_rows:
            weight_by_shed[w["shed_id"]].append(w)
        for sid in weight_by_shed:
            weight_by_shed[sid].sort(key=lambda x: x["entry_date"])

        # ---------------------------
        # CALCULATE FCR
        # ---------------------------

        result = []

        for sid, wlist in weight_by_shed.items():
            if len(wlist) < 2:
                continue

            shed_no = shed_map[sid]

            for i in range(1, len(wlist)):
                prev = wlist[i - 1]
                curr = wlist[i]

                gain_per_bird = (
                    (curr["avg_bird_weight"] - prev["avg_bird_weight"]) / 1000
                )

                if gain_per_bird <= 0:
                    continue

                # Find closing birds
                closing = None
                for d, b in bird_by_shed[sid]:
                    if d <= curr["entry_date"]:
                        closing = b
                    else:
                        break

                if not closing:
                    continue

                total_weight_gain = closing * gain_per_bird

                # Feed between prev → curr
                feed_total = sum(
                    feed for (d, feed) in feed_by_shed[sid]
                    if prev["entry_date"] < d <= curr["entry_date"]
                )

                if feed_total <= 0:
                    continue

                result.append({
                    "shed_id": sid,
                    "shed_number": shed_no,
                    "week": curr["entry_date"].isocalendar().week,
                    "date_from": str(prev["entry_date"]),
                    "date_to": str(curr["entry_date"]),
                    "avg_weight_prev": prev["avg_bird_weight"],
                    "avg_weight_curr": curr["avg_bird_weight"],
                    "gain_per_bird_kg": round(gain_per_bird, 4),
                    "closing_birds": closing,
                    "total_weight_gain_kg": round(total_weight_gain, 2),
                    "weekly_feed_kg": round(feed_total, 2),
                    "fcr": round(feed_total / total_weight_gain, 3)
                })

        return {"status": "success", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Global FCR error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# 🔥 GLOBAL MORTALITY & CULLING TREND (JWT SECURED)
# ============================================================
@app.get("/api/admin/global_mortality_culling")
def global_mortality_culling(
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            # 🔒 Only sheds belonging to logged-in admin
            shed_map = get_admin_sheds(conn, current_admin)

            if not shed_map:
                return {"status": "success", "data": []}

            shed_ids = list(shed_map.keys())

            # 2️⃣ Fetch latest entry per shed per date, then aggregate by date
            rows = conn.execute(
                text("""
                    SELECT 
                        d.entry_date,
                        SUM(d.mortality) AS total_mortality,
                        SUM(d.culling) AS total_culling,
                        SUM(b.birds_closing) AS total_closing
                    FROM (
                        SELECT DISTINCT ON (d.shed_id, d.entry_date)
                            d.shed_id,
                            d.entry_date,
                            d.mortality,
                            d.culling,
                            d.created_at
                        FROM DailyEntries d
                        WHERE d.shed_id IN :sids
                        ORDER BY d.shed_id, d.entry_date, d.created_at DESC
                    ) AS d
                    JOIN BirdStockHistory b
                      ON b.shed_id = d.shed_id
                     AND b.entry_date = d.entry_date
                    GROUP BY d.entry_date
                    ORDER BY d.entry_date ASC
                """).bindparams(bindparam("sids", expanding=True)),
                {"sids": shed_ids}
            ).mappings().fetchall()

        # ----------------------------------
        # BUILD RESPONSE
        # ----------------------------------
        result = []

        for r in rows:
            closing = r["total_closing"] or 0

            if closing > 0:
                mort_pct = (r["total_mortality"] / closing) * 100
                cull_pct = (r["total_culling"] / closing) * 100
            else:
                mort_pct = 0
                cull_pct = 0

            result.append({
                "date": str(r["entry_date"]),
                "mortality_pct": round(mort_pct, 3),
                "culling_pct": round(cull_pct, 3),
                "total_mortality": r["total_mortality"],
                "total_culling": r["total_culling"],
            })

        return {"status": "success", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Global mortality error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 🔥 GLOBAL WATER TREND (JWT SECURED)
# ============================================================
@app.get("/api/admin/global_water_trend")
def global_water_trend(
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            # 🔒 Load only sheds belonging to logged-in admin
            shed_map = get_admin_sheds(conn, current_admin)

            if not shed_map:
                return {"status": "success", "data": []}

            shed_ids = list(shed_map.keys())

            # -----------------------------------------------
            # 2️⃣ FETCH WATER — SUM PER DATE
            # -----------------------------------------------
            water_rows = conn.execute(
                text("""
                    SELECT 
                        entry_date,
                        SUM(COALESCE(water_consumed_ltrs, 0)) AS total_water
                    FROM DailyEntries
                    WHERE shed_id IN :sids
                    GROUP BY entry_date
                    ORDER BY entry_date
                """).bindparams(bindparam("sids", expanding=True)),
                {"sids": shed_ids}
            ).mappings().fetchall()

            # -----------------------------------------------
            # 3️⃣ FETCH TOTAL CLOSING BIRDS PER DATE
            # -----------------------------------------------
            bird_rows = conn.execute(
                text("""
                    SELECT 
                        entry_date,
                        SUM(birds_closing) AS total_closing
                    FROM BirdStockHistory
                    WHERE shed_id IN :sids
                    GROUP BY entry_date
                    ORDER BY entry_date
                """).bindparams(bindparam("sids", expanding=True)),
                {"sids": shed_ids}
            ).mappings().fetchall()

        # -----------------------------------------------
        # BUILD LOOKUP MAP
        # -----------------------------------------------
        bird_map = {
            b["entry_date"]: b["total_closing"]
            for b in bird_rows
        }

        result = []

        # -----------------------------------------------
        # BUILD FINAL PER-DATE GLOBAL TREND
        # -----------------------------------------------
        for w in water_rows:
            date = w["entry_date"]
            total_water = float(w["total_water"] or 0)
            total_closing = bird_map.get(date)

            if not total_closing or total_closing <= 0:
                continue

            water_per_bird = round(total_water / total_closing, 4)

            result.append({
                "date": str(date),
                "total_water_ltrs": round(total_water, 2),
                "total_closing_birds": total_closing,
                "water_per_bird": water_per_bird
            })

        return {"status": "success", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Global water trend error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 🔥 6. GLOBAL FEED–WATER CORRELATION
# ============================================================
# ============================================================
# 🔥 GLOBAL FEED–WATER CORRELATION (JWT SECURED)
# ============================================================
@app.get("/api/admin/global_feed_water_correlation")
def global_feed_water_correlation(
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            # 🔒 Only sheds belonging to logged-in admin
            shed_map = get_admin_sheds(conn, current_admin)

            if not shed_map:
                return {"status": "success", "data": []}

            shed_ids = list(shed_map.keys())

            # ----------------------------------------------------
            # 1️⃣ AGGREGATE FEED + WATER + MORTALITY PER DATE
            # ----------------------------------------------------
            daily = conn.execute(
                text("""
                    SELECT 
                        entry_date,
                        SUM(COALESCE(feed_consumption_kg, 0)) AS total_feed,
                        SUM(COALESCE(water_consumed_ltrs, 0)) AS total_water,
                        SUM(COALESCE(mortality, 0)) AS total_mortality,
                        SUM(COALESCE(culling, 0)) AS total_culling,
                        AVG(temperature) AS avg_temperature
                    FROM DailyEntries
                    WHERE shed_id IN :sids
                    GROUP BY entry_date
                    ORDER BY entry_date ASC
                """).bindparams(bindparam("sids", expanding=True)),
                {"sids": shed_ids}
            ).mappings().fetchall()

            # ----------------------------------------------------
            # 2️⃣ AGGREGATE BIRD STOCK PER DATE
            # ----------------------------------------------------
            birds = conn.execute(
                text("""
                    SELECT 
                        entry_date,
                        SUM(birds_closing) AS total_closing_birds
                    FROM BirdStockHistory
                    WHERE shed_id IN :sids
                    GROUP BY entry_date
                    ORDER BY entry_date ASC
                """).bindparams(bindparam("sids", expanding=True)),
                {"sids": shed_ids}
            ).mappings().fetchall()

        # --------------------------------------------
        # BUILD BIRD LOOKUP
        # --------------------------------------------
        bird_map = {
            b["entry_date"]: b["total_closing_birds"]
            for b in birds
        }

        result = []

        # --------------------------------------------
        # BUILD FINAL RESULT
        # --------------------------------------------
        for d in daily:

            date = d["entry_date"]
            closing_birds = bird_map.get(date)

            if not closing_birds or closing_birds <= 0:
                continue

            feed = float(d["total_feed"] or 0)
            water = float(d["total_water"] or 0)
            mortality = d["total_mortality"] or 0
            culling = d["total_culling"] or 0

            feed_per_bird = feed / closing_birds if feed > 0 else 0
            water_per_bird = water / closing_birds if water > 0 else 0
            mortality_pct = (mortality / closing_birds) * 100 if mortality > 0 else 0
            culling_pct = (culling / closing_birds) * 100 if culling > 0 else 0

            result.append({
                "date": str(date),

                # Raw totals
                "total_feed_kg": round(feed, 2),
                "total_water_ltrs": round(water, 2),
                "total_mortality": mortality,
                "total_culling": culling,
                "closing_birds": closing_birds,

                # KPIs
                "feed_per_bird": round(feed_per_bird, 4),
                "water_per_bird": round(water_per_bird, 4),
                "mortality_pct": round(mortality_pct, 4),
                "culling_pct": round(culling_pct, 4),

                # Temperature trend
                "temperature": round(d["avg_temperature"], 2)
                if d["avg_temperature"] else None
            })

        return {"status": "success", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Global feed-water error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# 🔥 7. GLOBAL TEMP–WATER–MORTALITY TREND
# ============================================================
# ============================================================
# 🔥 GLOBAL TEMP–WATER–MORTALITY TREND (JWT SECURED)
# ============================================================
@app.get("/api/admin/global_temp_water_mortality")
def global_temp_water_mortality(
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            # 🔒 Only sheds belonging to logged-in admin
            shed_map = get_admin_sheds(conn, current_admin)

            if not shed_map:
                return {"status": "success", "data": []}

            shed_ids = list(shed_map.keys())

            # ----------------------------------------------------
            # 1️⃣ AGGREGATE WATER + MORTALITY + TEMPERATURE PER DATE
            # ----------------------------------------------------
            daily = conn.execute(
                text("""
                    SELECT 
                        entry_date,
                        SUM(COALESCE(water_consumed_ltrs, 0)) AS total_water,
                        SUM(COALESCE(mortality, 0)) AS total_mortality,
                        AVG(temperature) AS avg_temperature
                    FROM DailyEntries
                    WHERE shed_id IN :sids
                    GROUP BY entry_date
                    ORDER BY entry_date ASC
                """).bindparams(bindparam("sids", expanding=True)),
                {"sids": shed_ids}
            ).mappings().fetchall()

            # ----------------------------------------------------
            # 2️⃣ AGGREGATE CLOSING BIRDS PER DATE
            # ----------------------------------------------------
            birds = conn.execute(
                text("""
                    SELECT 
                        entry_date,
                        SUM(birds_closing) AS total_closing_birds
                    FROM BirdStockHistory
                    WHERE shed_id IN :sids
                    GROUP BY entry_date
                    ORDER BY entry_date ASC
                """).bindparams(bindparam("sids", expanding=True)),
                {"sids": shed_ids}
            ).mappings().fetchall()

        # --------------------------------------------
        # BUILD LOOKUP MAP
        # --------------------------------------------
        bird_map = {
            b["entry_date"]: b["total_closing_birds"]
            for b in birds
        }

        result = []

        # --------------------------------------------
        # BUILD FINAL RESULT
        # --------------------------------------------
        for d in daily:
            date = d["entry_date"]
            closing_birds = bird_map.get(date)

            if not closing_birds or closing_birds <= 0:
                continue

            water = float(d["total_water"] or 0)
            mortality = d["total_mortality"] or 0

            water_per_bird = water / closing_birds if water > 0 else 0
            mortality_pct = (mortality / closing_birds) * 100 if mortality > 0 else 0

            result.append({
                "date": str(date),

                # Raw totals
                "total_water_ltrs": round(water, 2),
                "total_mortality": mortality,
                "closing_birds": closing_birds,

                # KPIs
                "water_per_bird": round(water_per_bird, 4),
                "mortality_pct": round(mortality_pct, 4),

                # Temperature trend
                "temperature": round(d["avg_temperature"], 2)
                if d["avg_temperature"] else None
            })

        return {"status": "success", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Global temp-water-mortality error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


def get_current_super_admin_email(authorization: str = Header(None)) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing token")

    token = authorization.replace("Bearer ", "")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    role = payload.get("role")
    email = payload.get("email")
    if role != "super_admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token")

    return str(email).lower()


@app.get("/api/super_admin/get_user_token")
def get_user_token(
    email: str,
    super_admin_email: str = Depends(get_current_super_admin_email),
):
    with engine.begin() as conn:
        admin = conn.execute(
            text("SELECT admin_id, email, name FROM AdminUsers WHERE email = :email"),
            {"email": email},
        ).mappings().fetchone()

        if not admin:
            raise HTTPException(status_code=404, detail="Admin user not found")

    access_token = create_access_token(
        {"sub": str(admin["admin_id"]), "role": "admin"},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return {"status": True, "access_token": access_token}


@app.get("/api/super_admin/allowed_users")
def list_allowed_users(super_admin_email: str = Depends(get_current_super_admin_email)):

    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT * FROM AllowedUsers ORDER BY id DESC")
        ).mappings().fetchall()

    return {"status": True, "data": rows}


class AllowUserModel(BaseModel):
    email: EmailStr
    name: str | None = None

@app.post("/api/super_admin/add_allowed_user")
def add_allowed_user(
    data: AllowUserModel,
    super_admin_email: str = Depends(get_current_super_admin_email)
):
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO AllowedUsers (email, name)
                VALUES (:email, :name)
                ON CONFLICT (email) DO NOTHING
            """),
            {"email": data.email, "name": data.name}
        )

    return {"status": True, "message": "User added to allowed list"}


@app.post("/api/super_admin/remove_allowed_user")
def remove_allowed_user(
    data: AllowUserModel,
    super_admin_email: str = Depends(get_current_super_admin_email)
):
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM AllowedUsers WHERE email = :email"),
            {"email": data.email}
        )

    return {"status": True, "message": "User removed from allowed list"}


class SetPasswordModel(BaseModel):
    email: EmailStr
    password: str


@app.post("/api/super_admin/set_password")
def super_admin_set_password(
    data: SetPasswordModel,
    super_admin_email: str = Depends(get_current_super_admin_email),
):
    email = data.email.lower()
    if not data.password or len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    enc = encrypt_password(data.password, email)

    with engine.begin() as conn:
        allowed = conn.execute(
            text("SELECT * FROM AllowedUsers WHERE email = :email"),
            {"email": email}
        ).mappings().fetchone()

        if not allowed:
            raise HTTPException(status_code=404, detail="Email not found in AllowedUsers")

        admin = conn.execute(
            text("SELECT * FROM AdminUsers WHERE email = :email"),
            {"email": email}
        ).mappings().fetchone()

        if not admin:
            admin = conn.execute(
                text("""
                    INSERT INTO AdminUsers (email, name, password_hash, password_salt, password_enc, password_nonce)
                    VALUES (:email, :name, :password_hash, :password_salt, :password_enc, :password_nonce)
                    RETURNING admin_id, email, name, farm_name, owner_name, phone_number, address, created_at
                """),
                {
                    "email": email,
                    "name": allowed["name"] if allowed["name"] else email,
                    **enc,
                }
            ).mappings().fetchone()
        else:
            conn.execute(
                text("""
                    UPDATE AdminUsers
                    SET password_hash = :password_hash,
                        password_salt = :password_salt,
                        password_enc = :password_enc,
                        password_nonce = :password_nonce
                    WHERE email = :email
                """),
                {"email": email, **enc}
            )

    return {"status": True, "message": "Password set successfully"}


@app.get("/api/super_admin/user_farms")
def get_user_farms(
    email: str,
    super_admin_email: str = Depends(get_current_super_admin_email),
):
    with engine.begin() as conn:
        admin = conn.execute(
            text("SELECT admin_id FROM AdminUsers WHERE email = :email"),
            {"email": email},
        ).mappings().fetchone()

        if not admin:
            raise HTTPException(status_code=404, detail="User has no farms yet")

        farms = conn.execute(
            text("SELECT farm_id, farm_name FROM Farms WHERE admin_id = :aid ORDER BY farm_name"),
            {"aid": admin["admin_id"]},
        ).mappings().fetchall()

    return {"status": True, "data": [dict(f) for f in farms]}


@app.get("/api/super_admin/user_farm_sheds")
def get_user_farm_sheds(
    farm_id: int,
    super_admin_email: str = Depends(get_current_super_admin_email),
):
    with engine.begin() as conn:
        sheds = conn.execute(
            text("SELECT shed_id, shed_number FROM Sheds WHERE farm_id = :fid ORDER BY shed_number"),
            {"fid": farm_id},
        ).mappings().fetchall()

    return {"status": True, "data": [dict(s) for s in sheds]}

@app.post("/api/admin/update_daily_entry")
def update_daily_entry(
    data: dict,
    current_admin: int = Depends(get_current_admin)
):
    import json
    print("🔵 FULL PAYLOAD RECEIVED:\n", json.dumps(data, indent=2))

    entry_id = data.get("entry_id")

    if not entry_id:
        raise HTTPException(status_code=400, detail="entry_id is required")

    try:
        with engine.begin() as conn:

            # 🔒 1️⃣ Validate entry belongs to logged-in admin
            old = conn.execute(text("""
                SELECT d.entry_date,
                       d.shed_id,
                       d.mortality,
                       d.culling
                FROM DailyEntries d
                JOIN Sheds s ON d.shed_id = s.shed_id
                JOIN Farms f ON s.farm_id = f.farm_id
                WHERE d.entry_id = :eid
                  AND f.admin_id = :admin_id
            """), {
                "eid": entry_id,
                "admin_id": current_admin
            }).mappings().fetchone()

            if not old:
                raise HTTPException(
                    status_code=404,
                    detail="Daily entry not found or unauthorized"
                )

            date_val = old["entry_date"]
            shed_id = old["shed_id"]

            old_mort = int(old["mortality"] or 0)
            old_cull = int(old["culling"] or 0)

            # 2️⃣ Convert new values safely
            new_mort = int(data.get("mortality") or 0)
            new_cull = int(data.get("culling") or 0)

            delta = (new_mort + new_cull) - (old_mort + old_cull)

            # 3️⃣ Update DailyEntries
            conn.execute(text("""
                UPDATE DailyEntries
                SET mortality = :mortality,
                    mortality_reason = :mortality_reason,
                    culling = :culling,
                    culling_reason = :culling_reason,
                    feed_consumption_kg = :feed,
                    water_consumed_ltrs = :water,
                    lighting_hours = :lighting,
                    temperature = :temperature
                WHERE entry_id = :eid
            """), {
                "mortality": new_mort,
                "mortality_reason": data.get("mortality_reason"),
                "culling": new_cull,
                "culling_reason": data.get("culling_reason"),
                "feed": data.get("feed"),
                "water": data.get("water"),
                "lighting": data.get("lighting"),
                "temperature": data.get("temperature"),
                "eid": entry_id
            })

            # 4️⃣ Fetch BirdStockHistory
            bsh = conn.execute(text("""
                SELECT birds_opening, birds_closing
                FROM BirdStockHistory
                WHERE entry_date = :d
                  AND shed_id = :sid
            """), {
                "d": date_val,
                "sid": shed_id
            }).mappings().fetchone()

            if not bsh:
                raise HTTPException(
                    status_code=404,
                    detail="Bird stock history missing"
                )

            closing = int(bsh["birds_closing"] or 0)
            new_closing = max(0, closing - delta)

            # 5️⃣ Update BirdStockHistory
            conn.execute(text("""
                UPDATE BirdStockHistory
                SET mortality = :mortality,
                    culling = :culling,
                    birds_closing = :closing
                WHERE entry_date = :d
                  AND shed_id = :sid
            """), {
                "mortality": new_mort,
                "culling": new_cull,
                "closing": new_closing,
                "d": date_val,
                "sid": shed_id
            })

        return {
            "status": True,
            "message": "Entry updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Error updating daily entry:", str(e))
        raise HTTPException(status_code=500, detail=str(e))



class EggEditModel(BaseModel):
    egg_id: int
    shed_id: int
    date: date

    good: conint(ge=0) | str
    floor: conint(ge=0) | str
    broken: conint(ge=0) | str
    mis: conint(ge=0) | str

@app.post("/api/admin/update_egg_entry")
def update_egg_entry(
    data: EggEditModel,
    current_admin: int = Depends(get_current_admin)
):
    try:
        with engine.begin() as conn:

            # 🔒 Validate entry belongs to current admin
            existing = conn.execute(
                text("""
                    SELECT e.egg_id
                    FROM EggDailyRecords e
                    JOIN Farms f ON e.farm_id = f.farm_id
                    WHERE e.egg_id = :id
                      AND f.admin_id = :admin_id
                """),
                {
                    "id": data.egg_id,
                    "admin_id": current_admin
                }
            ).fetchone()

            if not existing:
                raise HTTPException(
                    status_code=404,
                    detail="Egg entry not found or unauthorized"
                )

            # Convert values safely
            good = int(data.good or 0)
            floor = int(data.floor or 0)
            broken = int(data.broken or 0)
            mis = int(data.mis or 0)

            # 🔒 Update only if ownership verified
            conn.execute(
                text("""
                    UPDATE EggDailyRecords
                    SET 
                        good_eggs = :good,
                        floor_eggs = :floor,
                        broken_cracked_eggs = :broken,
                        mishapped_eggs = :mis,
                        updated_at = NOW()
                    WHERE egg_id = :id
                """),
                {
                    "good": good,
                    "floor": floor,
                    "broken": broken,
                    "mis": mis,
                    "id": data.egg_id
                }
            )

        return {
            "status": True,
            "message": "Egg entry updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Error updating egg entry:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

MSG91_API = "https://control.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/"
AUTH_KEY = os.getenv("AUTH_KEY")
INTEGRATED_NUMBER = os.getenv("INTEGRATED_NUMBER")

print("INTEGRATED_NUMBER", INTEGRATED_NUMBER)

# if not AUTH_KEY or not INTEGRATED_NUMBER:
#     raise ValueError("MSG91 credentials missing from environment variables")


def normalize_phone(phone: str) -> str:
    digits = "".join(filter(str.isdigit, phone))

    # If number starts with 91 → return last 10 digits
    if digits.startswith("91") and len(digits) >= 12:
        return digits[-10:]

    # If number already 10 digits → keep as-is
    if len(digits) == 10:
        return digits

    # If more digits (WhatsApp sometimes adds metadata) → always last 10 digits
    if len(digits) > 10:
        return digits[-10:]

    return digits


def _sql_phone_last10_match(column_expr: str) -> str:
    """PostgreSQL: strip non-digits, take last 10, compare to normalized Indian mobile."""
    return f"""(
        LENGTH(regexp_replace(COALESCE({column_expr}, ''), '[^0-9]', '', 'g')) >= 10
        AND RIGHT(regexp_replace(COALESCE({column_expr}, ''), '[^0-9]', '', 'g'), 10) = :p0
    )"""


def resolve_msg91_user_roles(normalized_phone: str) -> dict:
    """
    Classify WhatsApp user for MSG91 webhook (farm supervisors only).
    Returns dict with kind: none | farm
    """
    p = {"p0": (normalized_phone or "").strip()}
    farm_phone = _sql_phone_last10_match("f.supervisor_phone")
    sup_phone = _sql_phone_last10_match("s.supervisor_phone")
    with engine.begin() as conn:
        farms = conn.execute(
            text(f"""
                SELECT DISTINCT f.farm_id, f.farm_name, f.supervisor_name, f.supervisor_phone
                FROM Farms f
                WHERE {farm_phone}
                   OR EXISTS (
                       SELECT 1 FROM Supervisors s
                       WHERE s.farm_id = f.farm_id
                         AND {sup_phone}
                   )
            """),
            p,
        ).mappings().all()

    if farms:
        return {"kind": "farm", "farms": farms}
    return {"kind": "none"}


############################################
#  MSG91 SEND — TEXT MESSAGE (simple text) #
############################################
def send_msg91_text_message(to_number: str, text: str):
    ten = normalize_phone(str(to_number or ""))
    to_number = "91" + ten if ten else ""
    payload = {
        "integrated_number": INTEGRATED_NUMBER,
        "recipient_number": to_number,
        "content_type": "text",
        "text": text
    }

    headers = {
        "Content-Type": "application/json",
        "accept": "application/json",
        "authkey": AUTH_KEY,
    }


    response = requests.post(MSG91_API, json=payload, headers=headers)
    print("🔥 Outbound MSG91 Response:", response.text)
    return response.text


def send_entry_type_buttons_msg91(phone, shed_name):
    # Monday check (same as your Meta logic)
    is_monday = datetime.now().weekday() == 0

    # Build list rows
    rows = [
        {
            "id": "daily_entry",
            "title": "Daily Entry",
            "description": "Record daily shed data"
        },
        {
            "id": "egg_collection",
            "title": "Egg Collection",
            "description": "Record egg counts"
        },
        {
            "id": "egg_dispatch",
            "title": "Egg Dispatch",
            "description": "Dispatch eggs"
        }
    ]

    # Weekly only on Monday
    if is_monday:
        rows.append({
            "id": "weekly_entry",
            "title": "Weekly Entry",
            "description": "Weekly shed parameters"
        })

    # Section title must be <= 24 chars
    section_title = "Entry Options"

    sections = [{
        "title": section_title,
        "rows": rows
    }]

    header = f"Shed: {shed_name}"
    body = "Choose entry type:"
    footer = "Flockify Assistant"

    return send_msg91_list_message(phone, header, body, footer, sections)


def _download_url_bytes_whatsapp(url: str, timeout: int = 90) -> Optional[bytes]:
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200 and r.content:
            return r.content
    except Exception as e:
        print("_download_url_bytes_whatsapp:", e)
    return None


def extract_document_bytes_from_msg91_payload(payload: dict) -> Optional[bytes]:
    """
    Best-effort: MSG91 inbound payloads vary. Try top-level url, then messages[].url / document.url.
    """
    ct = str(payload.get("contentType") or "").lower()

    for key in ("url", "mediaUrl", "media_url", "fileUrl", "documentUrl"):
        u = payload.get(key)
        if u and str(u).startswith("http"):
            b = _download_url_bytes_whatsapp(str(u))
            if b:
                return b

    try:
        msgs = json.loads(payload.get("messages", "[]"))
    except Exception:
        msgs = []

    for m in msgs:
        if not isinstance(m, dict):
            continue
        doc = m.get("document") if isinstance(m.get("document"), dict) else None
        for u in (
            m.get("url"),
            m.get("mediaUrl"),
            (doc or {}).get("url"),
            (doc or {}).get("link"),
            (m.get("media") or {}).get("url") if isinstance(m.get("media"), dict) else None,
        ):
            if u and str(u).startswith("http"):
                b = _download_url_bytes_whatsapp(str(u))
                if b:
                    return b

    content = payload.get("content")
    if isinstance(content, str) and content.strip().startswith("http"):
        b = _download_url_bytes_whatsapp(content.strip())
        if b:
            return b

    if "document" in ct or "file" in ct or "attachment" in ct:
        for key in ("url", "mediaUrl"):
            u = payload.get(key)
            if u:
                b = _download_url_bytes_whatsapp(str(u))
                if b:
                    return b

    return None


############################################
#  MSG91 SEND — LIST MESSAGE               #
############################################
def send_msg91_list_message(to_number, header, body, footer, sections):
    ten = normalize_phone(str(to_number or ""))
    to_number = "91" + ten if ten else ""
    print("sections", sections)
    payload = {
        "recipient_number": to_number,
        "integrated_number": INTEGRATED_NUMBER,
        "content_type": "interactive",
        "interactive": {
            "type": "list",
            "header": {
                "type": "text",
                "text": header
            },
            "body": {
                "text": body
            },
            "footer": {
                "text": footer
            },
            "action": {
                "button": "Select",
                "sections": sections
            }
        }
    }

    headers = {
        "Content-Type": "application/json",
        "accept": "application/json",
        "authkey": AUTH_KEY,
    }

    res = requests.post(MSG91_API, json=payload, headers=headers)
    print("🔥 MSG91 LIST RESPONSE:", res.text)
    return res.text


############################################
#  BUILD SHED LIST (exact same as Meta)    #
############################################
def send_shed_list_msg91(phone, supervisor_name, farm_name, sheds):

    # 🚫 If no active-batch sheds → send text instead of list
    if not sheds:
        msg = (
            f"Hi {supervisor_name},\n\n"
            f"You currently have no active batches assigned.\n"
            f"Please contact the {farm_name} farm for further support."
        )
        return send_msg91_text_message(phone, msg)

    # ✅ Normal case → build interactive shed list
    sections = [{
        "title": f"{farm_name} Sheds",
        "rows": [
            {
                "id": f"shed_{shed['shed_id']}",
                "title": f"Shed {shed['shed_number']}",
                "description": "Select this shed"
            }
            for shed in sheds
        ]
    }]

    header = f"Welcome {supervisor_name} 👋"
    body = "Please choose a shed to continue:"
    footer = "Flockify Assistant"

    return send_msg91_list_message(phone, header, body, footer, sections)


def get_farm_and_sheds_by_supervisor_1(phone: str):
    normalized = normalize_phone(phone)
    p = {"p0": normalized}
    fp = _sql_phone_last10_match("f.supervisor_phone")
    sup = _sql_phone_last10_match("sv.supervisor_phone")

    with engine.begin() as conn:
        rows = conn.execute(
            text(f"""
                SELECT DISTINCT
                    f.farm_name,
                    f.supervisor_name,
                    s.shed_id,
                    s.shed_number
                FROM Farms f
                JOIN Sheds s ON s.farm_id = f.farm_id
                WHERE {fp}
                   OR EXISTS (
                       SELECT 1 FROM Supervisors sv
                       WHERE sv.farm_id = f.farm_id
                         AND {sup}
                   )
            """),
            p,
        ).mappings().all()

        if not rows:
            return None

        # Filter sheds WITH active batch
        active_sheds = []
        for r in rows:
            sid = r["shed_id"]
            if not sid:
                continue

            batch_id = get_active_batch_id(conn, sid)
            if batch_id:   # keep only sheds having active batch
                active_sheds.append({
                    "shed_id": sid,
                    "shed_number": r["shed_number"]
                })

    return {
        "farm_name": rows[0]["farm_name"],
        "supervisor_name": rows[0]["supervisor_name"],
        "sheds": active_sheds,
    }




def send_yes_no_buttons_msg91(phone, question_text):
    ten = normalize_phone(str(phone or ""))
    payload = {
        "recipient_number": "91" + ten if ten else "",
        "integrated_number": INTEGRATED_NUMBER,
        "content_type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": question_text},
            "action": {
                "buttons": [
                    { "type": "reply", "reply": { "id": "yes", "title": "Yes" }},
                    { "type": "reply", "reply": { "id": "no", "title": "No" }},
                ]
            }
        }
    }

    headers = {
        "Content-Type": "application/json",
        "authkey": AUTH_KEY
    }

    requests.post(MSG91_API, json=payload, headers=headers)


def download_msg91_image(img_url, save_path):
    try:
        r = requests.get(img_url, timeout=10)
        if r.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(r.content)
            return True
        else:
            print("❌ Failed download:", r.status_code, r.text)
            return False
    except Exception as e:
        print("❌ Exception downloading image:", e)
        return False

def merge_images_into_pdf_msg91(image_urls, entry_id):

    # Final PDF stored inside UPLOAD_DIR
    pdf_path = f"{UPLOAD_DIR}/proof_{entry_id}.pdf"

    local_files = []   # Temporary downloaded images
    pdf_images = []    # Image paths to insert into PDF

    # 1️⃣ Download each image to UPLOAD_DIR temporarily
    for i, url in enumerate(image_urls):
        local_path = f"{UPLOAD_DIR}/proof_{entry_id}_{i}.jpg"

        ok = download_msg91_image(url, local_path)
        if ok:
            local_files.append(local_path)
            pdf_images.append(local_path)
        else:
            print("❌ Failed to download image:", url)

    if not pdf_images:
        print("❌ No images downloaded. Cannot create PDF.")
        return None

    # 2️⃣ Generate PDF using temporary local files
    from fpdf import FPDF
    pdf = FPDF()
    pdf.set_auto_page_break(0)

    for img in pdf_images:
        pdf.add_page()
        pdf.image(img, x=0, y=0, w=210)  # Full-width A4

    pdf.output(pdf_path)

    # 3️⃣ Clean up temporary images
    for file_path in local_files:
        try:
            os.remove(file_path)
        except Exception as e:
            print("⚠️ Could not delete temp file:", file_path, e)

    return pdf_path

def send_close_session_button_msg91(phone):
    ten = normalize_phone(str(phone or ""))
    payload = {
        "recipient_number": "91" + ten if ten else "",
        "integrated_number": INTEGRATED_NUMBER,
        "content_type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": "Entry completed.\n\nDo you want to close this session and start fresh next time?"
            },
            "action": {
                "buttons": [
                    { "type": "reply", "reply": { "id": "close_yes", "title": "Yes" }},
                    { "type": "reply", "reply": { "id": "close_no", "title": "No" }},
                ]
            }
        }
    }

    headers = {
        "Content-Type": "application/json",
        "authkey": AUTH_KEY
    }

    res = requests.post(MSG91_API, json=payload, headers=headers)
    print("🔥 Close Session Button Response:", res.text)
    return res.text

def normalize_shed_name(raw: str) -> str:
    print("\n----- NORMALIZE SHED NAME -----")
    print("RAW INPUT:", raw)

    if not raw:
        print("→ EMPTY INPUT")
        return ""

    # Remove leading/trailing spaces
    raw = raw.strip()

    # Remove common words (shed, pen, house, unit), case insensitive
    raw = re.sub(r'(?i)\b(shed|pen|house|unit)\b', '', raw)
    
    # Remove all non-alphanumeric characters
    cleaned = re.sub(r'[^A-Za-z0-9]', '', raw).upper()

    print("AFTER WORD REMOVAL & CLEAN:", cleaned)

    if not cleaned:
        print("→ CLEANED EMPTY")
        return ""

    # LETTER-FIRST (A1, AA20 etc.)
    if cleaned[0].isalpha():
        letters = re.match(r'[A-Z]+', cleaned).group()
        rest = cleaned[len(letters):]
        final = f"{letters}{rest}"
        print("TYPE: LETTER-FIRST → FINAL:", final)
        return final

    # DIGIT-FIRST (1A, 12B etc.)
    if cleaned[0].isdigit():
        digits = re.match(r'[0-9]+', cleaned).group()
        rest = cleaned[len(digits):]
        final = f"{digits}{rest}"
        print("TYPE: DIGIT-FIRST → FINAL:", final)
        return final

    print("DEFAULT RETURN:", cleaned)
    return cleaned


def match_shed(user_input: str, sheds: list):
    user_norm = normalize_shed_name(user_input)

    for shed in sheds:
        db_norm = normalize_shed_name(shed["shed_number"])
        if user_norm == db_norm:
            return shed  # exact match

    return None  # no match

# ===================================================
# GLOBAL FSM STATE (REQUIRED)
# ===================================================

LAST_FLOW = {}       # phone → current flow ('daily', 'egg', 'daily_images', 'session_close', etc.)
LAST_QUESTION = {}   # phone → {index, key}
USER_SHED = {}       # phone → selected shed_id
USER_ANSWERS = {}    # phone → answers dict
USER_SHED_LIST = {}  # ← NEW


########################
#   MSG91 WEBHOOK     #
########################
@app.post("/webhook_msg91")
async def receive_msg91(request: Request):
    payload = await request.json()

    print("\n========== MSG91 WEBHOOK HIT ==========")
    print(json.dumps(payload, indent=2))
    print("======================================\n")

    raw_phone = payload.get("customerNumber")
    user_msg = payload.get("text", "")
    user_msg_lower = user_msg.lower()
    content_type = payload.get("contentType")

    if not raw_phone:
        return {"status": "ignored"}

    phone = normalize_phone(raw_phone)

    # Parse interactive
    interactive = None
    try:
        msgs = json.loads(payload.get("messages", "[]"))
        if msgs:
            interactive = msgs[0].get("interactive")
    except:
        pass

    # Farm supervisor registration (Farms / Supervisors)
    roles = resolve_msg91_user_roles(phone)
    if roles["kind"] == "none":
        send_msg91_text_message(phone, "❌ You are not registered.")
        return {"status": "not_registered"}

    # ------------------------------------------
    # BLOCK GREETINGS WHILE IN ANY ACTIVE FLOW
    # ------------------------------------------
    if LAST_FLOW.get(phone) not in [None, "session_close"]:
        if user_msg_lower in ["hi", "hello", "hey"]:
            return {"status": "ignored_greeting_during_flow"}

    # ------------------------------------------
    # GREETING — ONLY WHEN IDLE
    # ------------------------------------------
    if user_msg_lower in ["hi", "hello", "hey"] and LAST_FLOW.get(phone) is None:
        sup = get_farm_and_sheds_by_supervisor_1(phone)
        if not sup:
            send_msg91_text_message(phone, "❌ Could not fetch sheds.")
            return {"status": "error"}

        # Store shed list for later NLP matching
        USER_SHED_LIST[phone] = sup["sheds"]

        # Move state to shed selection
        LAST_FLOW[phone] = "await_shed_name"

        # Ask user to type shed name manually
        send_msg91_text_message(
            phone,
            f"👋 Hi {sup['supervisor_name']}!\n\n"
            f"Please type your shed name (example: A1, Shed 3, B12).",
        )

        return {"status": "ask_shed_name"}
    

    # ------------------------------------------
# NLP SHED SELECTION FLOW
# ------------------------------------------
    if LAST_FLOW.get(phone) == "await_shed_name":

        shed = match_shed(user_msg, USER_SHED_LIST.get(phone, []))

        if not shed:
            send_msg91_text_message(
                phone,
                "❌ Could not find that shed.\n\n"
                "Please type the exact shed name again (example: A1, 1A, B12)."
            )
            return {"status": "shed_not_found"}

        # Shed matched successfully — choose chat flow vs Excel upload
        USER_SHED[phone] = shed["shed_id"]
        LAST_FLOW[phone] = "farm_choose_input_mode"
        USER_ANSWERS[phone] = {"shed_number": str(shed.get("shed_number") or "—")}

        send_msg91_list_message(
            phone,
            f"Shed: {shed['shed_number']}",
            "How do you want to enter data for this shed?",
            "Flockify Assistant",
            [{
                "title": "Choose one",
                "rows": [
                    {
                        "id": "farm_input_normal",
                        "title": "Chat (step by step)",
                        "description": "Daily, eggs, dispatch in WhatsApp"
                    },
                    {
                        "id": "farm_input_excel",
                        "title": "Excel upload",
                        "description": "Bulk .xlsx import"
                    },
                ],
            }],
        )
        return {"status": "shed_selected_nlp"}


    # ------------------------------------------
    # FARM EXCEL — await inbound .xlsx document
    # ------------------------------------------
    if LAST_FLOW.get(phone) == "farm_excel_await_document":
        shed_id = USER_SHED.get(phone)
        kind = (USER_ANSWERS.get(phone) or {}).get("excel_import_kind")
        if not shed_id or not kind:
            LAST_FLOW[phone] = None
            send_msg91_text_message(phone, "⚠️ Session expired. Type *hi* to start again.")
            return {"status": "farm_excel_expired"}

        doc_bytes = extract_document_bytes_from_msg91_payload(payload)
        if not doc_bytes:
            if user_msg and user_msg.strip() and user_msg_lower not in ("hi", "hello", "hey", "done"):
                send_msg91_text_message(
                    phone,
                    "📎 Please send your spreadsheet as a *document* (.xlsx attachment), not as plain text."
                )
            return {"status": "farm_excel_need_doc"}

        if len(doc_bytes) < 4 or doc_bytes[:2] != b"PK":
            send_msg91_text_message(phone, "❌ File must be a valid *.xlsx* Excel file.")
            return {"status": "farm_excel_bad_file"}

        try:
            with engine.begin() as conn:
                farm_id = _verify_farm_supervisor_owns_shed(conn, phone, shed_id)
                if kind == "daily":
                    result = _import_daily_excel_body(conn, farm_id, shed_id, doc_bytes)
                elif kind == "egg":
                    result = _import_egg_excel_body(conn, farm_id, shed_id, doc_bytes)
                elif kind == "dispatch":
                    result = _import_egg_dispatch_excel_body(conn, farm_id, shed_id, doc_bytes)
                else:
                    raise HTTPException(status_code=400, detail="Unknown import type")
        except HTTPException as ex:
            send_msg91_text_message(phone, f"❌ Import failed: {ex.detail}")
            LAST_FLOW[phone] = "session_close"
            send_close_session_button_msg91(phone)
            return {"status": "farm_excel_http_err"}
        except Exception as ex:
            print("farm_excel import:", ex)
            send_msg91_text_message(phone, "❌ Import failed due to server error.")
            LAST_FLOW[phone] = "session_close"
            send_close_session_button_msg91(phone)
            return {"status": "farm_excel_err"}

        summ = result.get("summary") or {}
        ins = summ.get("inserted_count", 0)
        sk = summ.get("skipped_duplicate_count", 0)
        fail = summ.get("failed_count", 0)
        errs = result.get("errors") or []
        err_preview = ""
        if errs:
            err_preview = f"\n⚠️ First issue: {errs[0]}"
        send_msg91_text_message(
            phone,
            "✅ *Import completed*\n\n"
            f"✓ Inserted: *{ins}*\n"
            f"⏭ Skipped (duplicate): *{sk}*\n"
            f"✗ Failed / validation: *{fail}*{err_preview}"
        )
        send_close_session_button_msg91(phone)
        LAST_FLOW[phone] = "session_close"
        return {"status": "farm_excel_done"}


    # ------------------------------------------
    # SESSION CLOSE BUTTON FLOW
    # ------------------------------------------
    if interactive and interactive.get("type") == "button_reply":
        btn_id = interactive["button_reply"]["id"]

        if LAST_FLOW.get(phone) == "session_close":

            if btn_id == "close_yes":
                LAST_FLOW.pop(phone, None)
                LAST_QUESTION.pop(phone, None)
                USER_SHED.pop(phone, None)
                USER_ANSWERS.pop(phone, None)

                send_msg91_text_message(phone, "🔐 Session closed. Ready for next time!")
                return {"status": "session_closed"}

            elif btn_id == "close_no":
                LAST_FLOW[phone] = None
                send_msg91_text_message(phone, "👍 Session kept active.")
                return {"status": "session_kept_alive"}

    # ------------------------------------------
    # IGNORE LIST REPLIES DURING ANY ACTIVE FLOW
    # ------------------------------------------
    if LAST_FLOW.get(phone) not in [None, "session_close"]:
        if interactive and interactive.get("type") == "list_reply":
            # Allow list replies during farm Excel flows
            if LAST_FLOW.get(phone) in ("farm_choose_input_mode", "farm_excel_choose_type"):
                pass
            elif str(LAST_FLOW.get(phone, "")).startswith("farm_excel"):
                pass
            else:
                return {"status": "ignored_list_during_flow"}

    # ------------------------------------------
    # LIST: SHED SELECT / ENTRY OPTIONS
    # ------------------------------------------
    if interactive and interactive.get("type") == "list_reply":
        reply = interactive["list_reply"]
        list_id = reply["id"]
        title = reply["title"]

        # ===============================
        # FARM: normal vs Excel, then Excel type
        # ===============================
        if list_id == "farm_input_normal":
            if LAST_FLOW.get(phone) != "farm_choose_input_mode":
                return {"status": "ignored"}
            LAST_FLOW[phone] = None
            sn = (USER_ANSWERS.get(phone) or {}).get("shed_number") or "—"
            send_entry_type_buttons_msg91(phone, sn)
            return {"status": "farm_normal_flow"}

        if list_id == "farm_input_excel":
            if LAST_FLOW.get(phone) != "farm_choose_input_mode":
                return {"status": "ignored"}
            base = _get_public_api_base_url()
            LAST_FLOW[phone] = "farm_excel_choose_type"
            send_msg91_text_message(
                phone,
                "📎 *Excel templates* — open each link, download the *.xlsx*, fill rows, then send the file here as a *document*.\n\n"
                f"• Daily entry:\n{base}/whatsapp_templates/daily_entry_template.xlsx\n\n"
                f"• Egg collection:\n{base}/whatsapp_templates/egg_collection_template.xlsx\n\n"
                f"• Egg dispatch:\n{base}/whatsapp_templates/egg_dispatch_template.xlsx\n\n"
                "*(If links do not open on your phone, set env API_PUBLIC_BASE_URL to your API’s public HTTPS URL.)*\n\n"
                "Now choose what you are uploading 👇"
            )
            send_msg91_list_message(
                phone,
                f"Shed: {(USER_ANSWERS.get(phone) or {}).get('shed_number') or '—'}",
                "Which file are you uploading?",
                "Flockify Assistant",
                [{
                    "title": "Import type",
                    "rows": [
                        {
                            "id": "farm_excel_daily",
                            "title": "Daily entry",
                            "description": "daily_entry_template.xlsx"
                        },
                        {
                            "id": "farm_excel_egg",
                            "title": "Egg collection",
                            "description": "egg_collection_template.xlsx"
                        },
                        {
                            "id": "farm_excel_dispatch",
                            "title": "Egg dispatch",
                            "description": "egg_dispatch_template.xlsx"
                        },
                    ],
                }],
            )
            return {"status": "farm_excel_choose"}

        if list_id == "farm_excel_daily":
            if LAST_FLOW.get(phone) != "farm_excel_choose_type":
                return {"status": "ignored"}
            ctx = USER_ANSWERS.get(phone) or {}
            ctx["excel_import_kind"] = "daily"
            USER_ANSWERS[phone] = ctx
            LAST_FLOW[phone] = "farm_excel_await_document"
            send_msg91_text_message(phone, "📤 Send your *.xlsx* file now as a *document* (attachment).")
            return {"status": "farm_excel_await_daily"}

        if list_id == "farm_excel_egg":
            if LAST_FLOW.get(phone) != "farm_excel_choose_type":
                return {"status": "ignored"}
            ctx = USER_ANSWERS.get(phone) or {}
            ctx["excel_import_kind"] = "egg"
            USER_ANSWERS[phone] = ctx
            LAST_FLOW[phone] = "farm_excel_await_document"
            send_msg91_text_message(phone, "📤 Send your *.xlsx* file now as a *document* (attachment).")
            return {"status": "farm_excel_await_egg"}

        if list_id == "farm_excel_dispatch":
            if LAST_FLOW.get(phone) != "farm_excel_choose_type":
                return {"status": "ignored"}
            ctx = USER_ANSWERS.get(phone) or {}
            ctx["excel_import_kind"] = "dispatch"
            USER_ANSWERS[phone] = ctx
            LAST_FLOW[phone] = "farm_excel_await_document"
            send_msg91_text_message(phone, "📤 Send your *.xlsx* file now as a *document* (attachment).")
            return {"status": "farm_excel_await_dispatch"}

        # DAILY
        if list_id == "daily_entry":
            LAST_FLOW[phone] = "daily"
            USER_ANSWERS[phone] = {}
            LAST_QUESTION[phone] = {"index": 0, "key": DAILY_QUESTIONS[0][0]}
            send_msg91_text_message(phone, DAILY_QUESTIONS[0][1])
            return {"status": "daily_start"}

        # EGG
        if list_id == "egg_collection":
            LAST_FLOW[phone] = "egg"
            USER_ANSWERS[phone] = {}
            LAST_QUESTION[phone] = {"index": 0, "key": EGG_QUESTIONS[0][0]}
            send_msg91_text_message(phone, EGG_QUESTIONS[0][1])
            return {"status": "egg_start"}
        
        if list_id == "egg_dispatch":
            # Find shed + farm of selected shed
            with engine.begin() as conn:
                shed_row = conn.execute(
                    text("""
                        SELECT s.farm_id, s.shed_number
                        FROM Sheds s
                        WHERE s.shed_id = :sid
                    """),
                    {"sid": USER_SHED[phone]}
                ).mappings().fetchone()

                batch_id = get_active_batch_id(conn, USER_SHED[phone])

            if not shed_row:
                send_msg91_text_message(phone, "❌ Could not fetch shed details.")
                return {"status": "error"}
            if not batch_id:
                send_msg91_text_message(phone, "❌ No active batch found for this shed.")
                return {"status": "error_no_active_batch"}

            farm_id = int(shed_row["farm_id"])
            shed_number = str(shed_row["shed_number"])

            # Fetch opening stock shed-wise for active batch
            opening_good, opening_floor = get_shed_batch_stock(USER_SHED[phone], batch_id)

            USER_ANSWERS[phone] = {
                "farm_id": farm_id,
                "batch_id": batch_id,
                "shed_number": shed_number,
                "opening_good": opening_good,
                "opening_floor": opening_floor
            }

            LAST_FLOW[phone] = "egg_dispatch_good"

            msg_text = (
                f"🐣 *Egg Dispatch - Shed {shed_number}*\n\n"
                f"🟢 Opening Good Eggs: {opening_good}\n"
                f"🟡 Opening Floor + Mishapped Eggs: {opening_floor}\n\n"
                "Enter *number of dispatched good eggs*:"
            )
            send_msg91_text_message(phone, msg_text)
            return {"status": "dispatch_start"}
        

        # WEEKLY
        if list_id == "weekly_entry":
            LAST_FLOW[phone] = "weekly"
            USER_ANSWERS[phone] = {}
            LAST_QUESTION[phone] = {"index": 0, "key": WEEKLY_QUESTIONS[0][0]}
            send_msg91_text_message(phone, WEEKLY_QUESTIONS[0][1])
            return {"status": "weekly_start"}


    # ============================================================
    # ======================  EGG FLOW  ==========================
    # ============================================================
    if LAST_FLOW.get(phone) == "egg":

        step = LAST_QUESTION[phone]["index"]
        key = LAST_QUESTION[phone]["key"]

        # strict: non-numeric = 0
        try:
            USER_ANSWERS[phone][key] = int(user_msg)
        except:
            USER_ANSWERS[phone][key] = 0

        # move next
        step += 1

        if step < len(EGG_QUESTIONS):
            LAST_QUESTION[phone] = {
                "index": step,
                "key": EGG_QUESTIONS[step][0]
            }
            send_msg91_text_message(phone, EGG_QUESTIONS[step][1])
            return {"status": "egg_next"}

        # Final DB insert
        shed_id = USER_SHED[phone]

        with engine.begin() as conn:
            farm_name, shed_number = conn.execute(text("""
                SELECT f.farm_name, s.shed_number
                FROM Farms f
                JOIN Sheds s ON f.farm_id = s.farm_id
                WHERE s.shed_id = :sid
            """), {"sid": shed_id}).fetchone()

        batch = f"{farm_name.replace(' ','')}_{shed_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        with engine.begin() as conn:

            batch_id = get_active_batch_id(conn, shed_id)

            rec = conn.execute(text("""
                INSERT INTO EggDailyRecords (
                    farm_id, 
                    shed_id, 
                    batch_no,
                    batch_id,
                    good_eggs, 
                    floor_eggs, 
                    broken_cracked_eggs, 
                    mishapped_eggs
                )
                VALUES (
                    (SELECT farm_id FROM Sheds WHERE shed_id = :sid),
                    :sid,
                    :batch_no,
                    :batch_id,
                    :good, 
                    :floor, 
                    :broken, 
                    :mish
                )
                RETURNING egg_id
            """), {
                "sid": shed_id,
                "batch_no": batch,     # your original string batch
                "batch_id": batch_id,  # 🔥 correct flock batch_id
                "good": USER_ANSWERS[phone]["good_eggs"],
                "floor": USER_ANSWERS[phone]["floor_eggs"],
                "broken": USER_ANSWERS[phone]["broken_eggs"],
                "mish": USER_ANSWERS[phone]["mishapped_eggs"]
            }).mappings().fetchone()

        USER_ANSWERS[phone]["egg_id"] = rec["egg_id"]
        USER_ANSWERS[phone]["images"] = []

        LAST_FLOW[phone] = "egg_images"
        LAST_QUESTION.pop(phone, None)

        send_msg91_text_message(phone, "📸 Upload egg images. Type *done* when finished.")
        return {"status": "egg_collect_images"}

    # EGG IMAGES
    if LAST_FLOW.get(phone) == "egg_images":

        if content_type == "image":
            url = payload.get("url")
            if url:
                USER_ANSWERS[phone]["images"].append(url)
                send_msg91_text_message(phone, "📸 Image saved. Send more or type *done*.")
                return {"status": "egg_img_saved"}

        if user_msg_lower == "done":
            imgs = USER_ANSWERS[phone]["images"]
            egg_id = USER_ANSWERS[phone]["egg_id"]

            pdf = merge_images_into_pdf_msg91(imgs, egg_id)
            with engine.begin() as conn:
                conn.execute(text(
                    "UPDATE EggDailyRecords SET proof_pdf=:p WHERE egg_id=:id"
                ), {"p": pdf, "id": egg_id})

            send_msg91_text_message(phone, "🥚 Egg collection recorded!")
            send_close_session_button_msg91(phone)
            LAST_FLOW[phone] = "session_close"
            return {"status": "egg_done"}
    

    if LAST_FLOW.get(phone) == "weekly_images":

        if content_type == "image":
            url = payload.get("url")
            if url:
                USER_ANSWERS[phone]["images"].append(url)
                send_msg91_text_message(phone, "📸 Image saved. Send more or type *done*.")
                return {"status": "weekly_img_saved"}

        if user_msg_lower == "done":
            weekly_id = USER_ANSWERS[phone]["weekly_id"]
            imgs = USER_ANSWERS[phone]["images"]

            pdf = merge_images_into_pdf_msg91(imgs, weekly_id)

            with engine.begin() as conn:
                conn.execute(text("""
                    UPDATE WeeklyEntries SET proof_pdf=:p WHERE weekly_id=:id
                """), {"p": pdf, "id": weekly_id})

            send_msg91_text_message(phone, "📅 Weekly entry completed!")
            send_close_session_button_msg91(phone)

            LAST_FLOW[phone] = "session_close"
            return {"status": "weekly_done"}


    # ============================================================
    # ======================  WEEKLY FLOW  ========================
    # ============================================================
    if LAST_FLOW.get(phone) == "weekly":

        step = LAST_QUESTION[phone]["index"]
        key = LAST_QUESTION[phone]["key"]

        # Store answer
        USER_ANSWERS[phone][key] = user_msg

        # Move next
        step += 1

        # If more questions remain
        if step < len(WEEKLY_QUESTIONS):
            LAST_QUESTION[phone] = {"index": step, "key": WEEKLY_QUESTIONS[step][0]}
            send_msg91_text_message(phone, WEEKLY_QUESTIONS[step][1])
            return {"status": "weekly_next"}

        # All questions answered → Insert DB
        with engine.begin() as conn:

            batch_id = get_active_batch_id(conn, USER_SHED[phone])

            row = conn.execute(text("""
                INSERT INTO WeeklyEntries (
                    farm_id, shed_id, batch_id,
                    entry_date,
                    ammonia_level, avg_bird_weight, weekly_notes
                )
                VALUES (
                    (SELECT farm_id FROM Sheds WHERE shed_id = :sid),
                    :sid, :batch_id,
                    CURRENT_DATE,
                    :ammonia, :weight, :notes
                )
                RETURNING weekly_id
            """), {
                "sid": USER_SHED[phone],
                "batch_id": batch_id,
                "ammonia": USER_ANSWERS[phone]["ammonia_level"],
                "weight": USER_ANSWERS[phone]["avg_bird_weight"],
                "notes": USER_ANSWERS[phone]["weekly_notes"]
            }).mappings().fetchone()

        USER_ANSWERS[phone]["weekly_id"] = row["weekly_id"]
        USER_ANSWERS[phone]["images"] = []

        LAST_FLOW[phone] = "weekly_images"

        send_msg91_text_message(phone, "📸 Upload weekly proof images. Type *done*.")
        return {"status": "weekly_collect_images"}
    


    # ============================================================
    # ===================  DISPATCH GOOD  ========================
    # ============================================================
    if LAST_FLOW.get(phone) == "egg_dispatch_good":
        try:
            USER_ANSWERS[phone]["dispatched_good"] = int(user_msg)
        except:
            USER_ANSWERS[phone]["dispatched_good"] = 0

        LAST_FLOW[phone] = "egg_dispatch_floor"
        send_msg91_text_message(phone, "Enter *dispatched floor/mishapped eggs*:")
        return {"status": "dispatch_floor_req"}

    
    # ============================================================
    # ==================  DISPATCH FLOOR  ========================
    # ============================================================
    if LAST_FLOW.get(phone) == "egg_dispatch_floor":
        try:
            USER_ANSWERS[phone]["dispatched_floor"] = int(user_msg)
        except:
            USER_ANSWERS[phone]["dispatched_floor"] = 0

        shed_id = USER_SHED[phone]

        good_o = USER_ANSWERS[phone]["opening_good"]
        floor_o = USER_ANSWERS[phone]["opening_floor"]

        good_d = USER_ANSWERS[phone]["dispatched_good"]
        floor_d = USER_ANSWERS[phone]["dispatched_floor"]

        closing_good = good_o - good_d
        closing_floor = floor_o - floor_d

        # Save DB (shed-level + active batch), same logic as website/import path
        try:
            with engine.begin() as conn:
                save_egg_dispatch_entry_website(
                    shed_id=shed_id,
                    answers={
                        "dispatched_good_eggs": good_d,
                        "dispatched_floor_mis_eggs": floor_d,
                    },
                    entry_date=date.today(),
                    conn=conn,
                )
        except HTTPException as e:
            send_msg91_text_message(phone, f"⚠️ Dispatch not saved: {e.detail}")
            return {"status": "dispatch_error"}

        summary = (
            "📦 *Dispatch Summary*\n\n"
            f"Shed: {USER_ANSWERS[phone].get('shed_number', USER_SHED.get(phone, '-'))}\n"
            f"Good Eggs → Opening {good_o} | Dispatched {good_d} | Closing {closing_good}\n"
            f"Floor + Mishapped → Opening {floor_o} | Dispatched {floor_d} | Closing {closing_floor}"
        )

        send_msg91_text_message(phone, summary)
        send_close_session_button_msg91(phone)

        LAST_FLOW[phone] = "session_close"
        return {"status": "dispatch_done"}


    # ============================================================
    # =====================  DAILY FLOW  =========================
    # ============================================================
    if LAST_FLOW.get(phone) == "daily":

        step = LAST_QUESTION[phone]["index"]
        key = LAST_QUESTION[phone]["key"]

        # strict numeric except yes/no
        if key == "medical_yes_no":
            USER_ANSWERS[phone][key] = user_msg_lower
        else:
            USER_ANSWERS[phone][key] = int(user_msg) if user_msg.isdigit() else 0

        # mortality reason
        if key == "mortality" and USER_ANSWERS[phone][key] > 0:
            LAST_FLOW[phone] = "daily_mortality_reason"
            send_msg91_text_message(phone, "📝 Enter mortality reason:")
            return {"status": "mortality_reason_req"}

        # culling reason
        if key == "culling" and USER_ANSWERS[phone][key] > 0:
            LAST_FLOW[phone] = "daily_culling_reason"
            send_msg91_text_message(phone, "📝 Enter culling reason:")
            return {"status": "culling_reason_req"}

        # move next
        step += 1

        if step < len(DAILY_QUESTIONS):
            next_key, next_q = DAILY_QUESTIONS[step]

            LAST_QUESTION[phone] = {"index": step, "key": next_key}

            if next_key == "medical_yes_no":
                send_yes_no_buttons_msg91(phone, next_q)
            else:
                send_msg91_text_message(phone, next_q)

            return {"status": "daily_next"}

        # If fully done (only possible after medical_no)
        if key == "medical_yes_no" and user_msg_lower == "no":
            entry_id = save_daily_entry(USER_SHED[phone], USER_ANSWERS[phone])
            USER_ANSWERS[phone]["entry_id"] = entry_id
            USER_ANSWERS[phone]["images"] = []
            LAST_FLOW[phone] = "daily_images"

            send_msg91_text_message(phone, "📸 Upload proof images. Type *done*.")
            return {"status": "daily_collect_images"}

    # Mortality reason
    if LAST_FLOW.get(phone) == "daily_mortality_reason":
        USER_ANSWERS[phone]["mortality_reason"] = user_msg

        # continue from culling
        idx = DAILY_QUESTIONS.index(("culling", "2️⃣ Enter *Culling Count*:"))
        LAST_FLOW[phone] = "daily"
        LAST_QUESTION[phone] = {"index": idx, "key": "culling"}

        send_msg91_text_message(phone, DAILY_QUESTIONS[idx][1])
        return {"status": "mortality_reason_done"}

    # Culling reason
    if LAST_FLOW.get(phone) == "daily_culling_reason":
        USER_ANSWERS[phone]["culling_reason"] = user_msg

        idx = DAILY_QUESTIONS.index(("feed", "3️⃣ Enter *Feed Consumed (kg)*:"))
        LAST_FLOW[phone] = "daily"
        LAST_QUESTION[phone] = {"index": idx, "key": "feed"}

        send_msg91_text_message(phone, DAILY_QUESTIONS[idx][1])
        return {"status": "culling_reason_done"}

    # MEDICAL YES/NO BUTTONS
    if interactive and interactive.get("type") == "button_reply":
        btn = interactive["button_reply"]["id"]

        if btn == "yes":
            USER_ANSWERS[phone]["medical_attention"] = True
            LAST_FLOW[phone] = "daily_medical_details"
            send_msg91_text_message(phone, "Enter medical details:")
            return {"status": "medical_details_req"}

        if btn == "no":
            USER_ANSWERS[phone]["medical_attention"] = False

            entry_id = save_daily_entry(USER_SHED[phone], USER_ANSWERS[phone])
            USER_ANSWERS[phone]["entry_id"] = entry_id
            USER_ANSWERS[phone]["images"] = []

            LAST_FLOW[phone] = "daily_images"
            send_msg91_text_message(phone, "📸 Upload proof images.")
            return {"status": "daily_collect_images"}

    # Medical details
    if LAST_FLOW.get(phone) == "daily_medical_details":
        USER_ANSWERS[phone]["medical_notes"] = user_msg

        entry_id = save_daily_entry(USER_SHED[phone], USER_ANSWERS[phone])
        USER_ANSWERS[phone]["entry_id"] = entry_id

        USER_ANSWERS[phone]["images"] = []
        LAST_FLOW[phone] = "daily_images"

        send_msg91_text_message(phone, "📸 Upload proof images.")
        return {"status": "daily_collect_images"}

    # DAILY images
    if LAST_FLOW.get(phone) == "daily_images":

        if content_type == "image":
            url = payload.get("url")
            if url:
                USER_ANSWERS[phone]["images"].append(url)
                send_msg91_text_message(phone, "📸 Image saved. Send more or type *done*.")
                return {"status": "daily_img_saved"}

        if user_msg_lower == "done":
            entry_id = USER_ANSWERS[phone]["entry_id"]
            imgs = USER_ANSWERS[phone]["images"]

            pdf = merge_images_into_pdf_msg91(imgs, entry_id)

            with engine.begin() as conn:
                conn.execute(text("""
                    UPDATE DailyEntries SET proof_pdf=:p WHERE entry_id=:id
                """), {"p": pdf, "id": entry_id})

            send_msg91_text_message(phone, "✅ Daily entry completed!")
            send_close_session_button_msg91(phone)

            LAST_FLOW[phone] = "session_close"
            return {"status": "daily_done"}

    return {"status": "ignored"}


@app.post("/api/admin/deplete_batch")
def deplete_batch(
    payload: dict,
    admin_id: int = Depends(get_current_admin)
):
    shed_id = payload.get("shed_id")

    if not shed_id:
        raise HTTPException(status_code=400, detail="shed_id is required")

    today = date.today()

    try:
        with engine.begin() as conn:

            # 🔐 1️⃣ VERIFY SHED BELONGS TO THIS ADMIN
            ownership = conn.execute(text("""
                SELECT s.shed_id
                FROM Sheds s
                JOIN Farms f ON f.farm_id = s.farm_id
                WHERE s.shed_id = :sid
                  AND f.admin_id = :aid
            """), {
                "sid": shed_id,
                "aid": admin_id
            }).fetchone()

            if not ownership:
                raise HTTPException(
                    status_code=403,
                    detail="Not authorized to deplete this shed"
                )

            # 2️⃣ Fetch active batch
            batch = conn.execute(text("""
                SELECT batch_id
                FROM Batches
                WHERE shed_id = :sid 
                  AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 1
            """), {"sid": shed_id}).mappings().fetchone()

            if not batch:
                raise HTTPException(
                    status_code=400,
                    detail="No active batch found for this shed"
                )

            batch_id = batch["batch_id"]

            # 3️⃣ Fetch latest closing birds
            latest = conn.execute(text("""
                SELECT birds_closing
                FROM BirdStockHistory
                WHERE shed_id = :sid
                ORDER BY entry_date DESC, id DESC
                LIMIT 1
            """), {"sid": shed_id}).mappings().fetchone()

            final_closing = latest["birds_closing"] if latest else 0

            # 4️⃣ Mark batch as depleted
            conn.execute(text("""
                UPDATE Batches
                SET 
                    status = 'depleted',
                    depletion_date = :d,
                    final_bird_count = :final
                WHERE batch_id = :bid
            """), {
                "d": today,
                "final": final_closing,
                "bid": batch_id
            })

            # 5️⃣ Reset shed initial count
            conn.execute(text("""
                UPDATE Sheds
                SET initial_bird_count = 0
                WHERE shed_id = :sid
            """), {"sid": shed_id})

            # 6️⃣ Insert reset stock row
            conn.execute(text("""
                INSERT INTO BirdStockHistory (
                    shed_id,
                    entry_date,
                    birds_opening,
                    birds_closing,
                    created_at
                ) VALUES (
                    :sid,
                    NOW(),
                    0,
                    0,
                    NOW()
                )
            """), {"sid": shed_id})

        return {
            "status": True,
            "message": "Batch depleted and shed reset successfully.",
            "batch_id": batch_id,
            "final_closing": final_closing
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Error depleting batch:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/transfer_birds")
def transfer_birds_between_sheds(
    payload: dict,
    admin_id: int = Depends(get_current_admin)
):
    from_shed_id = payload.get("from_shed_id")
    to_shed_id = payload.get("to_shed_id")
    bird_count = payload.get("bird_count")

    if not from_shed_id or not to_shed_id:
        raise HTTPException(status_code=400, detail="from_shed_id and to_shed_id are required")
    if from_shed_id == to_shed_id:
        raise HTTPException(status_code=400, detail="Source and destination sheds must be different")
    try:
        transfer_count = int(bird_count)
    except Exception:
        raise HTTPException(status_code=400, detail="bird_count must be a number")
    if transfer_count <= 0:
        raise HTTPException(status_code=400, detail="bird_count must be greater than 0")

    try:
        with engine.begin() as conn:
            shed_rows = conn.execute(text("""
                SELECT s.shed_id, s.shed_number, s.farm_id
                FROM Sheds s
                JOIN Farms f ON f.farm_id = s.farm_id
                WHERE s.shed_id IN (:from_sid, :to_sid)
                  AND f.admin_id = :aid
            """), {
                "from_sid": from_shed_id,
                "to_sid": to_shed_id,
                "aid": admin_id
            }).mappings().fetchall()

            if len(shed_rows) != 2:
                raise HTTPException(status_code=403, detail="Not authorized for one or both sheds")

            by_id = {row["shed_id"]: row for row in shed_rows}
            from_shed = by_id.get(from_shed_id)
            to_shed = by_id.get(to_shed_id)

            if not from_shed or not to_shed:
                raise HTTPException(status_code=404, detail="Shed not found")
            if from_shed["farm_id"] != to_shed["farm_id"]:
                raise HTTPException(status_code=400, detail="Transfers are allowed only within the same farm")

            farm_id = from_shed["farm_id"]

            src_latest = conn.execute(text("""
                SELECT birds_closing
                FROM BirdStockHistory
                WHERE shed_id = :sid
                ORDER BY entry_date DESC, id DESC
                LIMIT 1
            """), {"sid": from_shed_id}).mappings().fetchone()
            src_initial = conn.execute(text("""
                SELECT initial_bird_count
                FROM Sheds
                WHERE shed_id = :sid
            """), {"sid": from_shed_id}).mappings().fetchone()
            src_current = int((src_latest or {}).get("birds_closing", (src_initial or {}).get("initial_bird_count", 0)) or 0)

            if transfer_count > src_current:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot transfer {transfer_count}. Only {src_current} birds are available in source shed."
                )

            dst_latest = conn.execute(text("""
                SELECT birds_closing
                FROM BirdStockHistory
                WHERE shed_id = :sid
                ORDER BY entry_date DESC, id DESC
                LIMIT 1
            """), {"sid": to_shed_id}).mappings().fetchone()
            dst_initial = conn.execute(text("""
                SELECT initial_bird_count
                FROM Sheds
                WHERE shed_id = :sid
            """), {"sid": to_shed_id}).mappings().fetchone()
            dst_current = int((dst_latest or {}).get("birds_closing", (dst_initial or {}).get("initial_bird_count", 0)) or 0)

            src_new = src_current - transfer_count
            dst_new = dst_current + transfer_count

            conn.execute(text("""
                INSERT INTO BirdStockHistory (
                    shed_id, entry_date, mortality, culling,
                    birds_opening, birds_closing, created_at, updated_at
                ) VALUES (
                    :sid, CURRENT_DATE, 0, 0,
                    :opening, :closing, NOW(), NOW()
                )
            """), {
                "sid": from_shed_id,
                "opening": src_current,
                "closing": src_new
            })

            conn.execute(text("""
                INSERT INTO BirdStockHistory (
                    shed_id, entry_date, mortality, culling,
                    birds_opening, birds_closing, created_at, updated_at
                ) VALUES (
                    :sid, CURRENT_DATE, 0, 0,
                    :opening, :closing, NOW(), NOW()
                )
            """), {
                "sid": to_shed_id,
                "opening": dst_current,
                "closing": dst_new
            })

            transfer_row = conn.execute(text("""
                INSERT INTO BirdTransfers (
                    farm_id, from_shed_id, to_shed_id, bird_count, transferred_at
                ) VALUES (
                    :farm_id, :from_sid, :to_sid, :cnt, NOW()
                )
                RETURNING transfer_id, transferred_at
            """), {
                "farm_id": farm_id,
                "from_sid": from_shed_id,
                "to_sid": to_shed_id,
                "cnt": transfer_count
            }).mappings().fetchone()

        return {
            "status": "success",
            "message": "Bird transfer completed successfully",
            "data": {
                "transfer_id": transfer_row["transfer_id"],
                "farm_id": farm_id,
                "from_shed_id": from_shed_id,
                "from_shed_number": from_shed["shed_number"],
                "to_shed_id": to_shed_id,
                "to_shed_number": to_shed["shed_number"],
                "bird_count": transfer_count,
                "source_new_birds": src_new,
                "destination_new_birds": dst_new,
                "transferred_at": transfer_row["transferred_at"].isoformat() if transfer_row["transferred_at"] else None
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        print("❌ Error in transfer_birds_between_sheds:", e)
        raise HTTPException(status_code=500, detail="Failed to transfer birds")


@app.get("/api/batches/completed")
def get_completed_batches(
    admin_id: int = Depends(get_current_admin)
):
    print("🔥 get_completed_batches() called")
    print(f"🔐 Authenticated admin_id: {admin_id}")

    try:
        with engine.begin() as conn:
            print("📡 Executing SQL query...")

            rows = conn.execute(text("""
                SELECT 
                    b.batch_id,
                    b.placement_date,
                    b.depletion_date,
                    b.bird_category,
                    b.bird_breed,
                    b.initial_bird_count,
                    b.final_bird_count,
                    b.status,
                    b.notes,

                    f.farm_name,
                    s.shed_number

                FROM Batches b
                JOIN Farms f ON f.farm_id = b.farm_id
                JOIN Sheds s ON s.shed_id = b.shed_id

                WHERE f.admin_id = :aid
                  AND b.status = 'depleted'
                  AND b.depletion_date IS NOT NULL

                ORDER BY b.depletion_date DESC
            """), {"aid": admin_id}).mappings().all()

            print(f"✅ Query executed. Rows returned: {len(rows)}")

        batch_list = [dict(row) for row in rows]

        print("📦 Batch data prepared for return:")
        for b in batch_list:
            print(
                f"   • Batch #{b['batch_id']} | "
                f"Shed {b['shed_number']} | "
                f"Farm {b['farm_name']}"
            )

        print("🚀 Returning response now...\n")

        return {
            "status": "success",
            "batches": batch_list
        }

    except Exception as e:
        print("❌ Error fetching completed batches:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


from fastapi import Depends, HTTPException
from sqlalchemy import text
from typing import Dict

@app.get("/api/batches/details")
def get_batch_details(
    batch_id: int,
    current_admin: int = Depends(get_current_admin)
):

    with engine.begin() as conn:

        # 1️⃣ Fetch batch WITH admin ownership validation
        batch = conn.execute(text("""
            SELECT 
                b.*,
                f.farm_name,
                s.shed_number
            FROM Batches b
            JOIN Farms f ON f.farm_id = b.farm_id
            JOIN Sheds s ON s.shed_id = b.shed_id
            WHERE b.batch_id = :bid
              AND f.admin_id = :admin_id
        """), {
            "bid": batch_id,
            "admin_id": current_admin
        }).mappings().first()

        if not batch:
            raise HTTPException(
                status_code=404,
                detail="Batch not found or access denied"
            )

        # ---------------------------------
        # 2️⃣ DAILY ENTRIES
        # ---------------------------------
        daily_entries = conn.execute(text("""
            SELECT 
                entry_id,
                entry_date,
                mortality,
                mortality_reason,
                culling,
                culling_reason,
                feed_consumption_kg,
                temperature,
                water_consumed_ltrs,
                lighting_hours,
                medical_attention,
                medical_notes,
                proof_pdf
            FROM DailyEntries
            WHERE batch_id = :bid
            ORDER BY entry_date ASC
        """), {"bid": batch_id}).mappings().all()

        # ---------------------------------
        # 3️⃣ EGG COLLECTION
        # ---------------------------------
        egg_records = conn.execute(text("""
            SELECT 
                egg_id,
                collection_date,
                good_eggs,
                floor_eggs,
                broken_cracked_eggs,
                mishapped_eggs,
                wastage,
                proof_pdf
            FROM EggDailyRecords
            WHERE batch_id = :bid
            ORDER BY collection_date ASC
        """), {"bid": batch_id}).mappings().all()

        # ---------------------------------
        # 4️⃣ WEEKLY ENTRIES
        # ---------------------------------
        weekly_entries = conn.execute(text("""
            SELECT 
                weekly_id,
                entry_date,
                ammonia_level,
                avg_bird_weight,
                weekly_notes,
                proof_pdf
            FROM WeeklyEntries
            WHERE batch_id = :bid
            ORDER BY entry_date ASC
        """), {"bid": batch_id}).mappings().all()

    return {
        "status": "success",
        "batch": dict(batch),
        "daily_entries": [dict(row) for row in daily_entries],
        "egg_records": [dict(row) for row in egg_records],
        "weekly_entries": [dict(row) for row in weekly_entries]
    }

@app.delete("/api/sheds/delete")
def delete_shed(
    shed_id: int,
    admin_id: int = Depends(get_current_admin)
):

    with engine.begin() as conn:

        # 🔐 1️⃣ Verify shed belongs to this admin
        ownership = conn.execute(text("""
            SELECT s.shed_id
            FROM Sheds s
            JOIN Farms f ON f.farm_id = s.farm_id
            WHERE s.shed_id = :sid
              AND f.admin_id = :aid
        """), {
            "sid": shed_id,
            "aid": admin_id
        }).fetchone()

        if not ownership:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to delete this shed"
            )

        # 2️⃣ Delete shed (cascade handles children)
        conn.execute(text("""
            DELETE FROM Sheds
            WHERE shed_id = :sid
        """), {"sid": shed_id})

    return {
        "status": "success",
        "message": "Shed deleted permanently along with all related entries."
    }




# ======================================================
# 🔷 BULK DATA ENTRY APIs  (replaces Excel import)
# ======================================================

class BulkDailyRow(BaseModel):
    entry_date: str
    mortality: int = 0
    culling: int = 0
    culling_reason: Optional[str] = None
    mortality_reason: Optional[str] = None
    feed_consumption_kg: Optional[float] = None
    water_consumed_ltrs: Optional[float] = None
    lighting_hours: Optional[float] = None
    temperature: Optional[float] = None
    medical_attention: bool = False
    medical_notes: Optional[str] = None

class BulkDailyRequest(BaseModel):
    farm_id: int
    shed_id: int
    rows: List[BulkDailyRow]

class BulkEggRow(BaseModel):
    entry_date: str
    good_eggs: int = 0
    floor_eggs: int = 0
    broken_cracked_eggs: int = 0
    mishapped_eggs: int = 0

class BulkEggRequest(BaseModel):
    farm_id: int
    shed_id: int
    rows: List[BulkEggRow]

class BulkDispatchRow(BaseModel):
    dispatch_date: str
    dispatched_good_eggs: int = 0
    dispatched_floor_mis_eggs: int = 0

class BulkDispatchRequest(BaseModel):
    farm_id: int
    shed_id: int
    rows: List[BulkDispatchRow]

class BulkWeeklyRow(BaseModel):
    entry_date: str
    ammonia_level: Optional[float] = None
    avg_bird_weight: Optional[float] = None
    weekly_notes: Optional[str] = None

class BulkWeeklyRequest(BaseModel):
    farm_id: int
    shed_id: int
    rows: List[BulkWeeklyRow]


@app.get("/api/admin/shed/active-batch")
def shed_active_batch(shed_id: int, current_admin: int = Depends(get_current_admin)):
    try:
        with engine.begin() as conn:
            batch = conn.execute(text("""
                SELECT b.batch_id, b.placement_date::text AS placement_date,
                       b.initial_bird_count, b.status,
                       s.shed_number, f.farm_id, f.farm_name
                FROM Batches b
                JOIN Sheds s ON s.shed_id = b.shed_id
                JOIN Farms f ON f.farm_id = s.farm_id
                WHERE b.shed_id = :sid AND b.status = 'active' AND f.admin_id = :aid
                ORDER BY b.created_at DESC
                LIMIT 1
            """), {"sid": shed_id, "aid": current_admin}).mappings().fetchone()

            if not batch:
                raise HTTPException(status_code=404, detail="No active batch found for this shed")

            return {"status": True, "data": dict(batch)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/shed/daily-entries")
def get_shed_daily_entries(shed_id: int, current_admin: int = Depends(get_current_admin)):
    try:
        with engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT d.entry_id, d.entry_date::text, d.batch_id,
                       d.mortality, d.culling, d.culling_reason, d.mortality_reason,
                       d.feed_consumption_kg, d.water_consumed_ltrs, d.lighting_hours,
                       d.temperature, d.medical_attention, d.medical_notes
                FROM DailyEntries d
                JOIN Sheds s ON s.shed_id = d.shed_id
                JOIN Farms f ON f.farm_id = s.farm_id
                WHERE d.shed_id = :sid AND f.admin_id = :aid
                ORDER BY d.entry_date ASC
            """), {"sid": shed_id, "aid": current_admin}).mappings().fetchall()
            return {"status": True, "data": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/daily-entry/bulk")
def bulk_daily_entry(data: BulkDailyRequest, current_admin: int = Depends(get_current_admin)):
    try:
        with engine.begin() as conn:
            _assert_admin_farm_shed(conn, current_admin, data.farm_id, data.shed_id)

            batch = conn.execute(text("""
                SELECT batch_id, placement_date FROM Batches
                WHERE shed_id = :sid AND status = 'active'
                ORDER BY created_at DESC LIMIT 1
            """), {"sid": data.shed_id}).mappings().fetchone()

            if not batch:
                raise HTTPException(status_code=400, detail="No active batch for this shed")

            batch_id = batch["batch_id"]
            inserted = updated = 0
            earliest_date = None

            for row in data.rows:
                try:
                    entry_date = date.fromisoformat(row.entry_date)
                except ValueError:
                    continue

                if earliest_date is None or entry_date < earliest_date:
                    earliest_date = entry_date

                existing = conn.execute(text("""
                    SELECT entry_id FROM DailyEntries
                    WHERE shed_id = :sid AND entry_date = :ed AND batch_id = :bid
                    LIMIT 1
                """), {"sid": data.shed_id, "ed": entry_date, "bid": batch_id}).fetchone()

                params = {
                    "sid": data.shed_id, "bid": batch_id, "ed": entry_date,
                    "mortality": int(row.mortality or 0),
                    "culling": int(row.culling or 0),
                    "culling_reason": row.culling_reason or None,
                    "mortality_reason": row.mortality_reason or None,
                    "feed": row.feed_consumption_kg,
                    "water": row.water_consumed_ltrs,
                    "lighting": row.lighting_hours,
                    "temp": row.temperature,
                    "medical": bool(row.medical_attention),
                    "medical_notes": row.medical_notes or None,
                }

                if existing:
                    conn.execute(text("""
                        UPDATE DailyEntries
                        SET mortality=:mortality, culling=:culling,
                            culling_reason=:culling_reason, mortality_reason=:mortality_reason,
                            feed_consumption_kg=:feed, water_consumed_ltrs=:water,
                            lighting_hours=:lighting, temperature=:temp,
                            medical_attention=:medical, medical_notes=:medical_notes,
                            updated_at=NOW()
                        WHERE entry_id=:eid
                    """), {**params, "eid": existing[0]})
                    updated += 1
                else:
                    conn.execute(text("""
                        INSERT INTO DailyEntries
                            (shed_id, batch_id, entry_date, mortality, culling, culling_reason,
                             mortality_reason, feed_consumption_kg, water_consumed_ltrs,
                             lighting_hours, temperature, medical_attention, medical_notes)
                        VALUES
                            (:sid, :bid, :ed, :mortality, :culling, :culling_reason,
                             :mortality_reason, :feed, :water, :lighting, :temp, :medical, :medical_notes)
                    """), params)
                    inserted += 1

            if earliest_date:
                rebuild_bird_stock_from_date(conn, data.shed_id, batch_id, earliest_date)

            _update_last_entry_at(conn, current_admin)
            return {"status": True, "inserted": inserted, "updated": updated, "total": inserted + updated}

    except HTTPException:
        raise
    except Exception as e:
        print("bulk_daily_entry error:", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/shed/egg-entries")
def get_shed_egg_entries(shed_id: int, current_admin: int = Depends(get_current_admin)):
    try:
        with engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT e.egg_id,
                       e.collection_date::text AS entry_date,
                       e.batch_id,
                       e.good_eggs, e.floor_eggs, e.broken_cracked_eggs, e.mishapped_eggs
                FROM EggDailyRecords e
                JOIN Sheds s ON s.shed_id = e.shed_id
                JOIN Farms f ON f.farm_id = s.farm_id
                WHERE e.shed_id = :sid AND f.admin_id = :aid
                ORDER BY e.collection_date ASC
            """), {"sid": shed_id, "aid": current_admin}).mappings().fetchall()
            return {"status": True, "data": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/egg-entry/bulk")
def bulk_egg_entry(data: BulkEggRequest, current_admin: int = Depends(get_current_admin)):
    try:
        with engine.begin() as conn:
            _assert_admin_farm_shed(conn, current_admin, data.farm_id, data.shed_id)

            shed_row = conn.execute(text("""
                SELECT s.shed_number, f.farm_name
                FROM Sheds s JOIN Farms f ON f.farm_id = s.farm_id
                WHERE s.shed_id = :sid LIMIT 1
            """), {"sid": data.shed_id}).mappings().fetchone()

            batch = conn.execute(text("""
                SELECT batch_id FROM Batches
                WHERE shed_id = :sid AND status = 'active'
                ORDER BY created_at DESC LIMIT 1
            """), {"sid": data.shed_id}).mappings().fetchone()

            if not batch:
                raise HTTPException(status_code=400, detail="No active batch for this shed")

            batch_id = batch["batch_id"]
            farm_name = shed_row["farm_name"] if shed_row else "Farm"
            shed_number = shed_row["shed_number"] if shed_row else "1"
            inserted = updated = 0

            for row in data.rows:
                try:
                    entry_date = date.fromisoformat(row.entry_date)
                except ValueError:
                    continue

                existing = conn.execute(text("""
                    SELECT egg_id FROM EggDailyRecords
                    WHERE shed_id = :sid AND batch_id = :bid AND collection_date = :cd
                    LIMIT 1
                """), {"sid": data.shed_id, "bid": batch_id, "cd": entry_date}).fetchone()

                params = {
                    "sid": data.shed_id, "bid": batch_id, "fid": data.farm_id,
                    "cd": entry_date,
                    "good": max(0, int(row.good_eggs or 0)),
                    "floor": max(0, int(row.floor_eggs or 0)),
                    "broken": max(0, int(row.broken_cracked_eggs or 0)),
                    "mishapped": max(0, int(row.mishapped_eggs or 0)),
                    "batch_no": f"{farm_name.replace(' ', '')}_{shed_number}_{entry_date.strftime('%Y%m%d')}",
                }

                if existing:
                    conn.execute(text("""
                        UPDATE EggDailyRecords
                        SET good_eggs=:good, floor_eggs=:floor,
                            broken_cracked_eggs=:broken, mishapped_eggs=:mishapped,
                            updated_at=NOW()
                        WHERE egg_id=:eid
                    """), {**params, "eid": existing[0]})
                    updated += 1
                else:
                    conn.execute(text("""
                        INSERT INTO EggDailyRecords
                            (farm_id, shed_id, batch_no, batch_id, collection_date,
                             good_eggs, floor_eggs, broken_cracked_eggs, mishapped_eggs)
                        VALUES
                            (:fid, :sid, :batch_no, :bid, :cd,
                             :good, :floor, :broken, :mishapped)
                    """), params)
                    inserted += 1

            _update_last_entry_at(conn, current_admin)
            return {"status": True, "inserted": inserted, "updated": updated, "total": inserted + updated}

    except HTTPException:
        raise
    except Exception as e:
        print("bulk_egg_entry error:", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/shed/dispatch-entries")
def get_shed_dispatch_entries(shed_id: int, current_admin: int = Depends(get_current_admin)):
    try:
        with engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT d.dispatch_id,
                       d.dispatch_date::text AS entry_date,
                       d.batch_id,
                       d.dispatched_good_eggs, d.dispatched_floor_mis_eggs, d.status
                FROM EggDispatchRecords d
                JOIN Sheds s ON s.shed_id = d.shed_id
                JOIN Farms f ON f.farm_id = s.farm_id
                WHERE d.shed_id = :sid AND f.admin_id = :aid
                ORDER BY d.dispatch_date ASC
            """), {"sid": shed_id, "aid": current_admin}).mappings().fetchall()
            return {"status": True, "data": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/egg-dispatch/bulk")
def bulk_egg_dispatch(data: BulkDispatchRequest, current_admin: int = Depends(get_current_admin)):
    try:
        with engine.begin() as conn:
            _assert_admin_farm_shed(conn, current_admin, data.farm_id, data.shed_id)

            batch = conn.execute(text("""
                SELECT batch_id FROM Batches
                WHERE shed_id = :sid AND status = 'active'
                ORDER BY created_at DESC LIMIT 1
            """), {"sid": data.shed_id}).mappings().fetchone()

            if not batch:
                raise HTTPException(status_code=400, detail="No active batch for this shed")

            batch_id = batch["batch_id"]
            inserted = updated = 0

            for row in data.rows:
                try:
                    dispatch_date = date.fromisoformat(row.dispatch_date)
                except ValueError:
                    continue

                good = max(0, int(row.dispatched_good_eggs or 0))
                floor_mis = max(0, int(row.dispatched_floor_mis_eggs or 0))

                if good + floor_mis == 0:
                    continue  # skip empty rows

                existing = conn.execute(text("""
                    SELECT dispatch_id FROM EggDispatchRecords
                    WHERE shed_id = :sid AND batch_id = :bid AND dispatch_date = :dd
                    LIMIT 1
                """), {"sid": data.shed_id, "bid": batch_id, "dd": dispatch_date}).fetchone()

                if existing:
                    conn.execute(text("""
                        UPDATE EggDispatchRecords
                        SET dispatched_good_eggs=:good, dispatched_floor_mis_eggs=:floor_mis
                        WHERE dispatch_id=:did
                    """), {"good": good, "floor_mis": floor_mis, "did": existing[0]})
                    updated += 1
                else:
                    conn.execute(text("""
                        INSERT INTO EggDispatchRecords
                            (farm_id, shed_id, batch_id, dispatched_good_eggs,
                             dispatched_floor_mis_eggs, dispatch_date, status)
                        VALUES (:fid, :sid, :bid, :good, :floor_mis, :dd, 'pending')
                    """), {
                        "fid": data.farm_id, "sid": data.shed_id, "bid": batch_id,
                        "good": good, "floor_mis": floor_mis, "dd": dispatch_date,
                    })
                    inserted += 1

            _update_last_entry_at(conn, current_admin)
            return {"status": True, "inserted": inserted, "updated": updated, "total": inserted + updated}

    except HTTPException:
        raise
    except Exception as e:
        print("bulk_egg_dispatch error:", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/shed/weekly-entries")
def get_shed_weekly_entries(shed_id: int, current_admin: int = Depends(get_current_admin)):
    try:
        with engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT w.weekly_id, w.entry_date::text, w.batch_id,
                       w.ammonia_level, w.avg_bird_weight, w.weekly_notes
                FROM WeeklyEntries w
                JOIN Sheds s ON s.shed_id = w.shed_id
                JOIN Farms f ON f.farm_id = s.farm_id
                WHERE w.shed_id = :sid AND f.admin_id = :aid
                ORDER BY w.entry_date ASC
            """), {"sid": shed_id, "aid": current_admin}).mappings().fetchall()
            return {"status": True, "data": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/weekly-entry/bulk")
def bulk_weekly_entry(data: BulkWeeklyRequest, current_admin: int = Depends(get_current_admin)):
    try:
        with engine.begin() as conn:
            _assert_admin_farm_shed(conn, current_admin, data.farm_id, data.shed_id)

            batch = conn.execute(text("""
                SELECT batch_id FROM Batches
                WHERE shed_id = :sid AND status = 'active'
                ORDER BY created_at DESC LIMIT 1
            """), {"sid": data.shed_id}).mappings().fetchone()

            if not batch:
                raise HTTPException(status_code=400, detail="No active batch for this shed")

            batch_id = batch["batch_id"]
            inserted = updated = 0

            for row in data.rows:
                try:
                    entry_date = date.fromisoformat(row.entry_date)
                except ValueError:
                    continue

                existing = conn.execute(text("""
                    SELECT weekly_id FROM WeeklyEntries
                    WHERE shed_id = :sid AND batch_id = :bid AND entry_date = :ed
                    LIMIT 1
                """), {"sid": data.shed_id, "bid": batch_id, "ed": entry_date}).fetchone()

                params = {
                    "fid": data.farm_id, "sid": data.shed_id, "bid": batch_id,
                    "ed": entry_date,
                    "ammonia": row.ammonia_level,
                    "weight": row.avg_bird_weight,
                    "notes": row.weekly_notes or None,
                }

                if existing:
                    conn.execute(text("""
                        UPDATE WeeklyEntries
                        SET ammonia_level=:ammonia, avg_bird_weight=:weight, weekly_notes=:notes
                        WHERE weekly_id=:wid
                    """), {**params, "wid": existing[0]})
                    updated += 1
                else:
                    conn.execute(text("""
                        INSERT INTO WeeklyEntries
                            (farm_id, shed_id, batch_id, entry_date,
                             ammonia_level, avg_bird_weight, weekly_notes)
                        VALUES
                            (:fid, :sid, :bid, :ed, :ammonia, :weight, :notes)
                    """), params)
                    inserted += 1

            _update_last_entry_at(conn, current_admin)
            return {"status": True, "inserted": inserted, "updated": updated, "total": inserted + updated}

    except HTTPException:
        raise
    except Exception as e:
        print("bulk_weekly_entry error:", e)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

