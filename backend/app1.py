import json
import requests
from datetime import timedelta
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from pydantic import BaseModel, EmailStr, conint
from sqlalchemy import create_engine, text, bindparam
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Query
from typing import Optional
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



UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)



# ======================================================
# 🔷 FASTAPI INIT
# ======================================================
app = FastAPI()


app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL not found in environment variables")

engine = create_engine(DATABASE_URL, future=True)

FRONTEND_URL = os.getenv("FRONTEND_URL")

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

if not FRONTEND_URL:
    raise ValueError("❌ FRONTEND_URL not found in environment variables")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],  # secure
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ======================================================
# 🔷 DB INITIALIZATION FUNCTION
# ======================================================
def init_db(engine):
    print("🛠️ Initializing database...")

    with engine.begin() as conn:

        # -------------------------------
        # ADMIN USERS
        # -------------------------------
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS AdminUsers (
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

        # -------------------------------
        # FARMS
        # -------------------------------
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS Farms (
                farm_id SERIAL PRIMARY KEY,
                admin_id INTEGER NOT NULL REFERENCES AdminUsers(admin_id) ON DELETE CASCADE,

                farm_name TEXT NOT NULL,
                supervisor_name TEXT NOT NULL,
                supervisor_phone TEXT NOT NULL,
                farm_location TEXT NOT NULL,

                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

        conn.execute(text("""
            ALTER TABLE Farms
            ADD COLUMN IF NOT EXISTS farm_owner_name TEXT,
            ADD COLUMN IF NOT EXISTS farm_owner_phone TEXT,
            ADD COLUMN IF NOT EXISTS farm_owner_email TEXT;
        """))


        # -------------------------------
        # SHEDS
        # -------------------------------
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS Sheds (
                shed_id SERIAL PRIMARY KEY,

                farm_id INTEGER NOT NULL
                    REFERENCES Farms(farm_id)
                    ON DELETE CASCADE,

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

        conn.execute(text("""ALTER TABLE Sheds ADD COLUMN IF NOT EXISTS no_of_feeders INTEGER;"""))
        conn.execute(text("""ALTER TABLE Sheds ADD COLUMN IF NOT EXISTS no_of_water_nipples INTEGER;"""))
        conn.execute(text("""ALTER TABLE Sheds ADD COLUMN IF NOT EXISTS perch_angle INTEGER;"""))
        conn.execute(text("""ALTER TABLE Sheds ADD COLUMN IF NOT EXISTS perch_length_value NUMERIC;"""))
        conn.execute(text("""ALTER TABLE Sheds ADD COLUMN IF NOT EXISTS perch_length_unit TEXT DEFAULT 'ft';"""))
        conn.execute(text("""ALTER TABLE Sheds ADD COLUMN IF NOT EXISTS shed_type TEXT DEFAULT 'free_range';"""))
        conn.execute(text("""
            ALTER TABLE Sheds 
            ADD COLUMN IF NOT EXISTS open_area_value NUMERIC;
        """))

        conn.execute(text("""
            ALTER TABLE Sheds 
            ADD COLUMN IF NOT EXISTS open_area_unit TEXT DEFAULT 'sqft';
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS Batches (
                batch_id SERIAL PRIMARY KEY,

                shed_id INTEGER NOT NULL 
                    REFERENCES Sheds(shed_id) 
                    ON DELETE CASCADE,

                farm_id INTEGER NOT NULL
                    REFERENCES Farms(farm_id)
                    ON DELETE CASCADE,

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
        



        # -------------------------------
        # SUPERVISORS
        # -------------------------------
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS Supervisors (
                supervisor_id SERIAL PRIMARY KEY,
                admin_id INTEGER NOT NULL REFERENCES AdminUsers(admin_id) ON DELETE CASCADE,
                farm_id INTEGER NOT NULL REFERENCES Farms(farm_id) ON DELETE CASCADE,
                supervisor_name TEXT NOT NULL,
                supervisor_phone TEXT NOT NULL,
                supervisor_email TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

        # -------------------------------
        # DAILY ENTRIES (BIRD)
        # -------------------------------
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS DailyEntries (
                entry_id SERIAL PRIMARY KEY,
                shed_id INTEGER NOT NULL REFERENCES Sheds(shed_id) ON DELETE CASCADE,

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
            ALTER TABLE DailyEntries
                DROP COLUMN IF EXISTS ammonia_level,
                ADD COLUMN IF NOT EXISTS water_consumed_ltrs NUMERIC,
                ADD COLUMN IF NOT EXISTS lighting_hours NUMERIC;
        """))   
        conn.execute(text("""
            ALTER TABLE DailyEntries
                ADD COLUMN IF NOT EXISTS mortality_reason TEXT;
        """))   

        conn.execute(text("""
            ALTER TABLE DailyEntries
            ADD COLUMN IF NOT EXISTS batch_id INTEGER REFERENCES Batches(batch_id);
        """))



        # -------------------------------
        # EGG DAILY RECORDS (PER SHED BATCH)
        # -------------------------------
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS EggDailyRecords (
                egg_id SERIAL PRIMARY KEY,

                farm_id INTEGER NOT NULL REFERENCES Farms(farm_id) ON DELETE CASCADE,
                shed_id INTEGER NOT NULL REFERENCES Sheds(shed_id) ON DELETE CASCADE,

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

        # -------------------------------
        # EGG DISPATCH RECORDS
        # -------------------------------
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS EggDispatchRecords (
                dispatch_id SERIAL PRIMARY KEY,

                farm_id INTEGER NOT NULL REFERENCES Farms(farm_id) ON DELETE CASCADE,

                dispatched_good_eggs INTEGER NOT NULL DEFAULT 0,
                dispatched_floor_mis_eggs INTEGER NOT NULL DEFAULT 0,

                dispatch_date DATE NOT NULL DEFAULT CURRENT_DATE,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))
        conn.execute(text("""
            ALTER TABLE EggDispatchRecords
            ADD COLUMN IF NOT EXISTS dispatched_good_eggs INTEGER NOT NULL DEFAULT 0;
        """))
    
        conn.execute(text("""
            ALTER TABLE EggDispatchRecords
            ADD COLUMN IF NOT EXISTS dispatched_floor_mis_eggs INTEGER NOT NULL DEFAULT 0;
        """))

        conn.execute(text("""
            ALTER TABLE EggDispatchRecords
            DROP COLUMN IF EXISTS dispatched_qty;
        """))


        # -------------------------------
        # FARM-LEVEL EGG STOCK HISTORY
        # -------------------------------
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS EggFarmStockHistory (
                id SERIAL PRIMARY KEY,

                farm_id INTEGER NOT NULL REFERENCES Farms(farm_id) ON DELETE CASCADE,

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

        # -------------------------------
        # BIRD STOCK HISTORY
        # -------------------------------
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS BirdStockHistory (
                id SERIAL PRIMARY KEY,
                shed_id INTEGER NOT NULL REFERENCES Sheds(shed_id) ON DELETE CASCADE,
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
            CREATE TABLE IF NOT EXISTS WeeklyEntries (
                weekly_id SERIAL PRIMARY KEY,

                farm_id INT NOT NULL REFERENCES Farms(farm_id) ON DELETE CASCADE,
                shed_id INT NOT NULL REFERENCES Sheds(shed_id) ON DELETE CASCADE,

                entry_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),

                ammonia_level FLOAT,
                avg_bird_weight FLOAT,
                weekly_notes TEXT,

                proof_pdf TEXT
            );
        """))
        conn.execute(text("""
            ALTER TABLE WeeklyEntries
            ADD COLUMN IF NOT EXISTS batch_id INTEGER REFERENCES Batches(batch_id);
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS SuperAdmins (
                super_admin_id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))
        print("SuperAdmins Created")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS AllowedUsers (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))
        print("AllowedUser Table")

        conn.execute(text("""
            ALTER TABLE BirdStockHistory
            ADD COLUMN IF NOT EXISTS batch_id INTEGER
                REFERENCES Batches(batch_id)
                ON DELETE CASCADE;
        """))

        conn.execute(text("""
            ALTER TABLE EggDailyRecords
            ADD COLUMN IF NOT EXISTS batch_id INTEGER REFERENCES Batches(batch_id);
        """))




    print("✅ Database initialized!")



# Run DB setup on startup
init_db(engine)



class SuperAdminLoginModel(BaseModel):
    email: EmailStr
    name: str | None = None  # Google name or any name you pass


@app.post("/api/super_admin_login")
async def super_admin_login(data: SuperAdminLoginModel):
    print("🔸 Super admin login attempt:", data.email)

    # ALLOWED EMAILS (add more if needed)
    ALLOWED_SUPER_ADMINS = {
        "darshthakkar09@gmail.com"
    }

    # ❌ Block if email is not the super admin
    if data.email not in ALLOWED_SUPER_ADMINS:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized as a Super Admin."
        )

    try:
        with engine.begin() as conn:

            # 1️⃣ Check if super admin already exists
            super_admin = conn.execute(
                text("SELECT * FROM SuperAdmins WHERE email = :email"),
                {"email": data.email}
            ).mappings().fetchone()

            if super_admin:
                print("✅ Super Admin exists:", super_admin["super_admin_id"])

                token = create_access_token(
                    {"sub": str(super_admin["super_admin_id"]), "role": "super_admin"},
                    timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
                )

                return {
                    "status": True,
                    "message": "Super Admin Login Successful",
                    "access_token": token,
                    "data": super_admin
                }

            # 2️⃣ Create a new Super Admin
            print("🆕 Creating new Super Admin:", data.email)

            new_superadmin = conn.execute(
                text("""
                    INSERT INTO SuperAdmins (email, name)
                    VALUES (:email, :name)
                    RETURNING super_admin_id, email, name, created_at
                """),
                {
                    "email": data.email,
                    "name": data.name or "Super Admin"
                }
            ).mappings().fetchone()

            print("✅ New Super Admin registered:", new_superadmin["super_admin_id"])

            token = create_access_token(
                {"sub": str(new_superadmin["super_admin_id"]), "role": "super_admin"},
                timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            )

            return {
                "status": True,
                "message": "Super Admin Registered",
                "access_token": token,
                "data": new_superadmin
            }

    except Exception as e:
        print("❌ Super Admin Login Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))





oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_admin(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        admin_id: str = payload.get("sub")

        if admin_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

        return int(admin_id)

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )

# ======================================================
# 🔷 GOOGLE ADMIN LOGIN MODELS
# ======================================================
class AdminLoginModel(BaseModel):
    email: EmailStr
    name: str
    farm_name: str | None = None
    owner_name: str | None = None
    phone_number: str | None = None
    address: str | None = None



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


@app.post("/api/admin_login")
async def admin_login(data: AdminLoginModel):
    print("🔹 Admin login attempt:", data.email)

    try:
        with engine.begin() as conn:

            # STEP 1 — Check if email is allowed
            allowed = conn.execute(
                text("SELECT * FROM AllowedUsers WHERE email = :email"),
                {"email": data.email}
            ).mappings().fetchone()

            if not allowed:
                print("❌ Not allowed:", data.email)
                raise HTTPException(
                    status_code=403,
                    detail="You are not allowed to access this system."
                )

            # STEP 2 — Check if AdminUser already exists
            admin = conn.execute(
                text("SELECT * FROM AdminUsers WHERE email = :email"),
                {"email": data.email}
            ).mappings().fetchone()

            if admin:
                print("✅ Admin exists:", admin["admin_id"])
            else:
                # STEP 3 — Create AdminUser automatically
                print("🆕 Creating new AdminUser:", data.email)

                admin = conn.execute(
                    text("""
                        INSERT INTO AdminUsers (email, name)
                        VALUES (:email, :name)
                        RETURNING admin_id, email, name, farm_name, owner_name, phone_number, address
                    """),
                    {"email": data.email, "name": allowed["name"] or data.name}
                ).mappings().fetchone()

                print("✅ Registered AdminUser:", admin["admin_id"])

            # STEP 4 — Return token
            token = create_access_token(
                {"sub": str(admin["admin_id"]), "role": "admin"},
                timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            )

            return {
                "status": True,
                "message": "Login Successful",
                "access_token": token,
                "data": admin,
            }

    except Exception as e:
        print("❌ Admin login error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


class AdminFarmUpdate(BaseModel):
    farm_name: str
    owner_name: str
    phone_number: str
    address: str

@app.post("/api/admin_update_details")
async def admin_update_details(admin_id: int, data: AdminFarmUpdate):
    print(f"🔄 Updating admin profile for ID: {admin_id}")

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
    print(f"➕ Adding new farm for admin {admin_id}")

    try:
        with engine.begin() as conn:

            # 1️⃣ Create the farm (admin_id comes from JWT)
            new_farm = conn.execute(
                text("""
                    INSERT INTO Farms (
                        admin_id,
                        farm_name,

                        farm_owner_name,
                        farm_owner_phone,
                        farm_owner_email,

                        supervisor_name,
                        supervisor_phone,
                        farm_location
                    )
                    VALUES (
                        :admin_id,
                        :farm_name,

                        :farm_owner_name,
                        :farm_owner_phone,
                        :farm_owner_email,

                        :supervisor_name,
                        :supervisor_phone,
                        :farm_location
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
    print(f"📥 Fetching farms for admin {admin_id}")

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
    print(f"✏️ Updating farm {farm_id} by admin {admin_id}")

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
    print(f"🗑️ Deleting farm {farm_id} by admin {admin_id}")

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
    print(f"➕ Adding new shed for admin {current_admin}")

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

            # 2️⃣ CREATE SHED
            new_shed = conn.execute(
                text("""
                    INSERT INTO Sheds (
                        farm_id, shed_number, shed_type,
                        bird_category, bird_breed,
                        initial_bird_count,

                        area_value, area_unit,
                        open_area_value, open_area_unit,

                        placement_date, shed_status, notes,

                        no_of_feeders, no_of_water_nipples,
                        perch_angle, perch_length_value, perch_length_unit
                    )
                    VALUES (
                        :farm_id, :shed_number, :shed_type,
                        :bird_category, :bird_breed,
                        :initial_bird_count,

                        :area_value, :area_unit,
                        :open_area_value, :open_area_unit,

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

        # Outside transaction
        stock_map = {row["shed_id"]: row for row in stock}

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
    print(f"✏️ Updating shed {shed_id} by admin {admin_id}")

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
    print(f"🗑️ Deleting shed {shed_id}")

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

        print(f"✅ Shed {shed_id} deleted")

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
    print(f"📥 Fetching farms for admin {current_admin}")

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
        raise HTTPException(status_code=500, detail="Internal Server Error")

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
        raise HTTPException(status_code=500, detail="Internal Server Error")

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
        raise HTTPException(status_code=500, detail="Internal Server Error")


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
                    SELECT DISTINCT shed_id
                    FROM DailyEntries
                    WHERE entry_date = :today
                """),
                {"today": today}
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
        raise HTTPException(status_code=500, detail="Internal Server Error")




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
        raise HTTPException(status_code=500, detail="Internal Server Error")

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
        raise HTTPException(status_code=500, detail="Internal Server Error")


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
        raise HTTPException(status_code=500, detail="Internal Server Error")

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
        raise HTTPException(status_code=500, detail="Internal Server Error")
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
        raise HTTPException(status_code=500, detail="Internal Server Error")
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
        raise HTTPException(status_code=500, detail="Internal Server Error")

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
        raise HTTPException(status_code=500, detail="Internal Server Error")

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
        raise HTTPException(status_code=500, detail="Internal Server Error")

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
        raise HTTPException(status_code=500, detail="Internal Server Error")


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
            """), {"shed_ids": list(active_sheds.keys())}).mappings().fetchall()

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
            key = (r["shed_id"], str(r["entry_date"]))
            grouped.setdefault(key, []).append(r)

        # 5️⃣ BUILD FINAL SUMMARY LIST
        final_summary = []
        for (shed_id, entry_date), entry_rows in grouped.items():

            summary = summarize_daily_entries(entry_rows)

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

            print("\n================ GLOBAL SUMMARY CARDS ================")
            print(f"📌 admin_id = {current_admin}")

            # 1️⃣ Fetch all farms for this admin
            farms = conn.execute(text("""
                SELECT farm_id 
                FROM Farms
                WHERE admin_id = :aid
            """), {"aid": current_admin}).fetchall()

            if not farms:
                print("❗ No farms found for this admin.\n")
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
            print(f"➡️ Total Birds = {total_closing_birds}")

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

            print("================ END GLOBAL SUMMARY ================\n")

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
        raise HTTPException(status_code=500, detail="Internal Server Error")


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
        raise HTTPException(status_code=500, detail="Internal Server Error")

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
        raise HTTPException(status_code=500, detail="Internal Server Error")


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
        raise HTTPException(status_code=500, detail="Internal Server Error")


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
        raise HTTPException(status_code=500, detail="Internal Server Error")

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
        raise HTTPException(status_code=500, detail="Internal Server Error")


SUPER_ADMIN_EMAIL = "darshthakkar09@gmail.com"

def extract_email_from_token(token: str):
    # TEMP: Replace with real JWT decode later
    # For now, always treat token as valid and belonging to super admin
    return SUPER_ADMIN_EMAIL


@app.get("/api/super_admin/allowed_users")
def list_allowed_users(authorization: str = Header(None)):

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing token")

    token = authorization.replace("Bearer ", "")
    email = extract_email_from_token(token)

    if email != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Not authorized")

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
    authorization: str = Header(None)
):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing token")

    token = authorization.replace("Bearer ", "")
    email = extract_email_from_token(token)

    if email != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Not authorized")

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
    authorization: str = Header(None)
):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing token")

    token = authorization.replace("Bearer ", "")
    email = extract_email_from_token(token)

    if email != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Not authorized")

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM AllowedUsers WHERE email = :email"),
            {"email": data.email}
        )

    return {"status": True, "message": "User removed from allowed list"}

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
        raise HTTPException(status_code=500, detail="Internal Server Error")



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
        raise HTTPException(status_code=500, detail="Internal Server Error")

MSG91_API = "https://control.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/"
AUTH_KEY = os.getenv("AUTH_KEY")
INTEGRATED_NUMBER = os.getenv("INTEGRATED_NUMBER")

print("INTEGRATED_NUMBER", INTEGRATED_NUMBER)

if not AUTH_KEY or not INTEGRATED_NUMBER:
    raise ValueError("MSG91 credentials missing from environment variables")


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




########################
#  CHECK REGISTRATION  #
########################
def is_registered_user(phone):
    normalized = normalize_phone(phone)
    print("Normalized Phone:", normalized)

    with engine.begin() as conn:
        row = conn.execute(
            text("""
                SELECT farm_name, supervisor_name
                FROM Farms
                WHERE supervisor_phone = :p
            """),
            {"p": normalized}
        ).mappings().fetchone()

    print(row)

    return row  # None if not registered


############################################
#  MSG91 SEND — TEXT MESSAGE (simple text) #
############################################
def send_msg91_text_message(to_number: str, text: str):
    print("to_number", to_number)
    to_number = "91" + to_number
    print("final",to_number)
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



############################################
#  MSG91 SEND — LIST MESSAGE               #
############################################
def send_msg91_list_message(to_number, header, body, footer, sections):
    to_number = "91"+to_number
    print("to_number", to_number)
    print("body", body)
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

    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT 
                    f.farm_name,
                    f.supervisor_name,
                    s.shed_id,
                    s.shed_number
                FROM Farms f
                JOIN Sheds s ON s.farm_id = f.farm_id
                WHERE f.supervisor_phone = :phone
            """),
            {"phone": normalized},
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
    payload = {
        "recipient_number": "91" + phone,
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
    payload = {
        "recipient_number": "91" + phone,
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
    
    TARGET_NUMBER = "918097197639"
    incoming_integrated_number = payload.get("integratedNumber")

    if incoming_integrated_number != TARGET_NUMBER:
        print("not the number to be activated")
        return {"status": "ignored_wrong_integrated_number"}

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

    # Check registration
    user = is_registered_user(phone)
    if not user:
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
            f"Please type your shed name (example: A1, Shed 3, B12)."
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

        # Shed matched successfully
        USER_SHED[phone] = shed["shed_id"]
        LAST_FLOW[phone] = None
        USER_ANSWERS[phone] = {}

        # Continue to entry options
        send_entry_type_buttons_msg91(phone, shed["shed_number"])
        return {"status": "shed_selected_nlp"}



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
            return {"status": "ignored_list_during_flow"}

    # ------------------------------------------
    # LIST: SHED SELECT / ENTRY OPTIONS
    # ------------------------------------------
    if interactive and interactive.get("type") == "list_reply":
        reply = interactive["list_reply"]
        list_id = reply["id"]
        title = reply["title"]

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
        # Find farm_id of selected shed
            with engine.begin() as conn:
                farm_id = conn.execute(
                    text("SELECT farm_id FROM Sheds WHERE shed_id=:sid"),
                    {"sid": USER_SHED[phone]}
                ).scalar()

            # Fetch opening stock
            opening_good, opening_floor = get_farm_stock(farm_id)

            USER_ANSWERS[phone] = {
                "farm_id": farm_id,
                "opening_good": opening_good,
                "opening_floor": opening_floor
            }

            LAST_FLOW[phone] = "egg_dispatch_good"

            msg_text = (
                f"🐣 *Egg Dispatch - Farm {farm_id}*\n\n"
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

        farm_id = USER_ANSWERS[phone]["farm_id"]

        good_o = USER_ANSWERS[phone]["opening_good"]
        floor_o = USER_ANSWERS[phone]["opening_floor"]

        good_d = USER_ANSWERS[phone]["dispatched_good"]
        floor_d = USER_ANSWERS[phone]["dispatched_floor"]

        closing_good = good_o - good_d
        closing_floor = floor_o - floor_d

        # Save DB
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO EggDispatchRecords (
                    farm_id, dispatched_good_eggs, dispatched_floor_mis_eggs
                )
                VALUES (:fid, :good, :floor)
            """), {"fid": farm_id, "good": good_d, "floor": floor_d})

        summary = (
            "📦 *Dispatch Summary*\n\n"
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

