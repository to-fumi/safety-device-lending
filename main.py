from contextlib import asynccontextmanager
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import engine
import models
from routers import devices, loans

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    raise ValueError(
        "ADMIN_PASSWORD 環境変数が設定されていません。管理者認証機能を使用するために必要です。"
    )


def ensure_loan_schema() -> None:
    required_columns = {
        "lent_type": "TEXT NOT NULL DEFAULT 'full_set'",
        "is_smartphone_out": "BOOLEAN NOT NULL DEFAULT 1",
        "is_dock_out": "BOOLEAN NOT NULL DEFAULT 1",
        "is_cable_out": "BOOLEAN NOT NULL DEFAULT 1",
        "smartphone_relent_at": "DATETIME",
        "smartphone_returned_at": "DATETIME",
        "dock_returned_at": "DATETIME",
        "cable_returned_at": "DATETIME",
        "cable_weight_g": "REAL",
        "cable_weight_ok": "BOOLEAN",
        "broken_note": "TEXT",
        "broken_reported_by": "TEXT",
        "broken_at": "DATETIME",
    }

    with engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(loans)").fetchall()
        existing = {r[1] for r in rows}
        for name, ddl in required_columns.items():
            if name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE loans ADD COLUMN {name} {ddl}")

        conn.exec_driver_sql(
            """
            UPDATE loans
            SET is_smartphone_out = 0,
                is_dock_out = 0,
                is_cable_out = 0,
            WHERE returned_at IS NOT NULL
            """
        )

        dev_rows = conn.exec_driver_sql("PRAGMA table_info(devices)").fetchall()
        dev_existing = {r[1] for r in dev_rows}
        if "broken_note" not in dev_existing:
            conn.exec_driver_sql("ALTER TABLE devices ADD COLUMN broken_note TEXT")
        if "broken_reported_by" not in dev_existing:
            conn.exec_driver_sql("ALTER TABLE devices ADD COLUMN brokne_reported_by TEXT")
        if "broken_at" not in dev_existing:
            conn.exec_driver_sql("ALTER TABLE devices ADD COLUMN broken_at DATETIME")
        if "recovered_at" not in dev_existing:
            conn.exec_driver_sql("ALTER TABLE devices ADD COLUMN recovered_at DATETIME")
        if "retired_at" not in dev_existing:
            conn.exec_driver_sql("ALTER TABLE devices ADD COLUMN retired_at DATETIME")
        if "deleted_at" not in dev_existing:
            conn.exec_driver_sql("ALTER TABLE devices ADD COLUMN deleted_at DATETIME")

        sp_rows = conn.exec_driver_sql("PRAGMA table_info(smartphone_loans)").fetchall()
        sp_existing = {r[1] for r in sp_rows}
        if "test_course_rule_confirmed" not in sp_existing:
            conn.exec_driver_sql(
                "ALTER TABLE smartphone_loans ADD COLUMN test_course_rule_confirmed BOOLEAN NOT NULL DEFAULT 0"
            )

        dev_rows = conn.exec_driver_sql("PRAGMA table_info(devices)").fetchall()
        dev_info = {r[1]: r for r in dev_rows}
        no_notnull = dev_info.get("no", [None, None, None, 0])[3] == 1
        code_notnull = dev_info.get("device_id_code", [None, None, None, 0])[3] == 1
        needs_rebuild = (not no_notnull) or code_notnull

        if needs_rebuild:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            conn.exec_driver_sql(
                """
                CREATE TABLE devices_new(
                    id INTEGER NOT NULL PRIMARY KEY,
                    no VARCHAR(50) NOT NULL,
                    device_id_code VARCHAR(50),
                    memo VARCHAR(200),
                    is_active BOOLEAN NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    broken_note TEXT,
                    broken_reported_by TEXT,
                    broken_at DATETIME,
                    recovered_at DATETIME,
                    retired_at DATETIME,
                    deleted_at DATETIME
                )
                """
            )

            conn.exec_driver_sql(
                """
                INSERT INTO devices_new(
                    id, no, device_id_code, memo, is_active, status,
                    broken_note, broken_reported_by, broken_at, recovered_at, retired_at, deleted_at
                )
                SELECT
                    d.id,
                    CASE
                        WHEN d.no IS NULL OR TRIM(d.no) = '' THEN 'NO-' || d.id
                        WHEN (
                            SELECT COUNT(*)
                            FROM devices d2
                            WHERE TRIM(COALESCE(d2.no, '')) = TRIM(d.no)
                                AND d2.id < d.id
                        ) > 0 THEN TRIM(d.no) || '-' || d.id
                        ELSE TRIM(d.no)
                    END AS normalized_no,
                    NULLIF(TRIM(COALESCE(d.device_id_code, '')), '') AS normalized_device_id_code,
                    d.memo,
                    d.is_active,
                    COALESCE(d.status, 'active') AS status,
                    d.broken_note,
                    d.broken_reported_by,
                    d.broken_at,
                    d.recovered_at,
                    d.retired_at,
                    d.deleted_at
                FROM devices d
                ORDER BY d.id
                """
            )

            conn.exec_driver_sql("DROP TABLE devices")
            conn.exec_driver_sql("ALTER TABLE devices_new RENAME TO devices")
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")

        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_devices_id ON devices (id)")
        conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS ix_devices_no ON devices (no)")
        conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS ix_devices_device_id_code ON devices (device_id_code)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    ensure_loan_schema()
    yield


app = FastAPI(
    title="端末貸出管理 API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(devices.router)
app.include_router(loans.router)


class AdminAuthRequest(BaseModel):
    password: str

@app.post("/admin/auth")
async def admin_auth(req: AdminAuthRequest):
    if req.password == ADMIN_PASSWORD:
        return {"success": True}
    return {"success": False}

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
async def root():
    from fastapi.responses import FileResponse
    return FileResponse("static/index.html")
