from __future__ import annotations

import asyncio
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .db import get_conn, init_db
from .simulator import CB2TSimulator

app = FastAPI(title="CB2T MVP")
Path("data").mkdir(exist_ok=True)
init_db()

simulator = CB2TSimulator()
active_runs: dict[int, dict[str, Any]] = {}

BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")


class ProjectCreate(BaseModel):
    name: str
    dut_profile: str = "reference-dut"
    trays: int = Field(default=1, ge=1, le=8)
    bports_per_tray: int = Field(default=4, ge=1, le=16)
    lanes_per_bport: int = Field(default=4, ge=1, le=8)


class TestStart(BaseModel):
    project_id: int
    dut_serial: str
    prbs_type: str = "PRBS31"
    duration_sec: int = Field(default=12, ge=3, le=180)
    ber_threshold: float = 1e-10
    notes: str = ""


class ProjectTopologyUpdate(BaseModel):
    trays: int = Field(ge=1, le=64)
    bports_per_tray: int = Field(ge=1, le=32)
    lanes_per_bport: int = Field(ge=1, le=16)


def _to_int(value: Any, key: str, minimum: int, maximum: int) -> int:
    try:
        ivalue = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {key}: {value}") from exc
    if ivalue < minimum or ivalue > maximum:
        raise HTTPException(
            status_code=400,
            detail=f"{key} must be between {minimum} and {maximum}, got {ivalue}",
        )
    return ivalue


def _extract_topology_from_json(data: dict[str, Any]) -> ProjectTopologyUpdate:
    aliases = {
        "trays": ["trays", "tray_count", "num_trays"],
        "bports_per_tray": ["bports_per_tray", "bportsPerTray", "bports", "ports_per_tray"],
        "lanes_per_bport": ["lanes_per_bport", "lanesPerBport", "lanes", "lanes_per_port"],
    }

    extracted: dict[str, Any] = {}
    for target_key, keys in aliases.items():
        for k in keys:
            if k in data:
                extracted[target_key] = data[k]
                break

    if len(extracted) != 3:
        raise HTTPException(
            status_code=400,
            detail=(
                "Topology JSON must include trays, bports_per_tray, lanes_per_bport "
                "(or known aliases)"
            ),
        )

    return ProjectTopologyUpdate(
        trays=_to_int(extracted["trays"], "trays", 1, 64),
        bports_per_tray=_to_int(extracted["bports_per_tray"], "bports_per_tray", 1, 32),
        lanes_per_bport=_to_int(extracted["lanes_per_bport"], "lanes_per_bport", 1, 16),
    )


def _extract_topology_from_csv(raw_text: str) -> ProjectTopologyUpdate:
    reader = csv.DictReader(io.StringIO(raw_text))
    rows = list(reader)
    if rows:
        first = rows[0]
        return ProjectTopologyUpdate(
            trays=_to_int(first.get("trays"), "trays", 1, 64),
            bports_per_tray=_to_int(first.get("bports_per_tray"), "bports_per_tray", 1, 32),
            lanes_per_bport=_to_int(first.get("lanes_per_bport"), "lanes_per_bport", 1, 16),
        )

    kv: dict[str, str] = {}
    for line in raw_text.splitlines():
        line = line.strip()
        if not line or "," not in line:
            continue
        key, value = line.split(",", 1)
        kv[key.strip()] = value.strip()

    if {"trays", "bports_per_tray", "lanes_per_bport"} <= set(kv.keys()):
        return ProjectTopologyUpdate(
            trays=_to_int(kv["trays"], "trays", 1, 64),
            bports_per_tray=_to_int(kv["bports_per_tray"], "bports_per_tray", 1, 32),
            lanes_per_bport=_to_int(kv["lanes_per_bport"], "lanes_per_bport", 1, 16),
        )

    raise HTTPException(
        status_code=400,
        detail=(
            "Topology CSV not recognized. Use header trays,bports_per_tray,lanes_per_bport "
            "or key,value lines."
        ),
    )


def _prepare_run(payload: TestStart) -> tuple[int, Any, list[dict[str, Any]]]:
    with get_conn() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id = ?", (payload.project_id,)).fetchone()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

    run_started = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO test_runs (project_id, dut_serial, prbs_type, duration_sec, status, started_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.project_id,
                payload.dut_serial,
                payload.prbs_type,
                payload.duration_sec,
                "running",
                run_started,
                payload.notes,
            ),
        )
        run_id = cur.lastrowid

    lanes = simulator.discover(
        trays=project["trays"],
        bports_per_tray=project["bports_per_tray"],
        lanes_per_bport=project["lanes_per_bport"],
    )
    lane_dicts = [l.__dict__ for l in lanes]
    active_runs[run_id] = {
        "id": run_id,
        "project_id": payload.project_id,
        "status": "running",
        "progress": 0,
        "lanes": lane_dicts,
    }
    return run_id, project, lane_dicts


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/projects")
def list_projects() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


@app.get("/api/projects/{project_id}")
def get_project(project_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Project not found")
    return dict(row)


@app.post("/api/projects")
def create_project(payload: ProjectCreate) -> dict[str, Any]:
    try:
        with get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO projects (name, dut_profile, trays, bports_per_tray, lanes_per_bport)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    payload.name,
                    payload.dut_profile,
                    payload.trays,
                    payload.bports_per_tray,
                    payload.lanes_per_bport,
                ),
            )
            project_id = cur.lastrowid
        return {"id": project_id, **payload.model_dump()}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Project creation failed: {exc}") from exc


@app.post("/api/projects/{project_id}/topology")
async def import_topology(project_id: int, file: UploadFile = File(...)) -> dict[str, Any]:
    with get_conn() as conn:
        existing = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Project not found")

    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    suffix = Path(file.filename or "").suffix.lower()

    if suffix == ".json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="Topology JSON must be an object")
        topo = _extract_topology_from_json(parsed)
    elif suffix == ".csv":
        topo = _extract_topology_from_csv(text)
    else:
        # Try JSON first, then CSV.
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                topo = _extract_topology_from_json(parsed)
            else:
                topo = _extract_topology_from_csv(text)
        except Exception:
            topo = _extract_topology_from_csv(text)

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE projects
            SET trays = ?, bports_per_tray = ?, lanes_per_bport = ?
            WHERE id = ?
            """,
            (topo.trays, topo.bports_per_tray, topo.lanes_per_bport, project_id),
        )
        updated = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()

    return {"message": "Topology imported", "project": dict(updated)}


@app.post("/api/connect/{project_id}")
def connect(project_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

    lanes = simulator.discover(
        trays=project["trays"],
        bports_per_tray=project["bports_per_tray"],
        lanes_per_bport=project["lanes_per_bport"],
    )
    connected = sum(1 for l in lanes if l.connected)
    return {
        "project_id": project_id,
        "connected_lanes": connected,
        "total_lanes": len(lanes),
        "lanes": [l.__dict__ for l in lanes],
    }


@app.post("/api/tests/start")
async def start_test(payload: TestStart) -> dict[str, Any]:
    run_id, _, _ = _prepare_run(payload)
    asyncio.create_task(execute_run(run_id, payload.duration_sec, payload.ber_threshold))
    return {"run_id": run_id, "status": "running"}


@app.post("/api/tests/run-now")
async def run_now(payload: TestStart) -> dict[str, Any]:
    run_id, _, _ = _prepare_run(payload)
    await execute_run(run_id, payload.duration_sec, payload.ber_threshold)
    return {"run_id": run_id, "status": active_runs[run_id]["status"], "progress": 100}


async def execute_run(run_id: int, duration_sec: int, ber_threshold: float) -> None:
    for i in range(duration_sec):
        run = active_runs.get(run_id)
        if not run:
            return
        run["progress"] = int((i / duration_sec) * 100)
        await asyncio.sleep(1)

    run = active_runs.get(run_id)
    if not run:
        return

    lane_objects = []
    for l in run["lanes"]:
        lane_objects.append(type("Lane", (), l)())
    tested = simulator.run_prbs(lane_objects, ber_threshold)

    pass_count = 0
    fail_count = 0
    error_count = 0

    with get_conn() as conn:
        for lane in tested:
            if lane.status == "pass":
                pass_count += 1
            elif lane.status == "fail":
                fail_count += 1
            else:
                error_count += 1

            conn.execute(
                """
                INSERT INTO lane_results (test_run_id, tray, bport, lane, ber, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, lane.tray, lane.bport, lane.lane, lane.ber, lane.status),
            )

        final_status = "passed" if fail_count == 0 and error_count == 0 else "failed"
        conn.execute(
            """
            UPDATE test_runs
            SET status = ?, ended_at = ?, pass_count = ?, fail_count = ?, error_count = ?
            WHERE id = ?
            """,
            (
                final_status,
                datetime.now(timezone.utc).isoformat(),
                pass_count,
                fail_count,
                error_count,
                run_id,
            ),
        )

    run["status"] = final_status
    run["progress"] = 100
    run["pass_count"] = pass_count
    run["fail_count"] = fail_count
    run["error_count"] = error_count


@app.get("/api/tests/{run_id}")
def get_run(run_id: int) -> dict[str, Any]:
    if run_id in active_runs:
        return active_runs[run_id]

    with get_conn() as conn:
        run = conn.execute("SELECT * FROM test_runs WHERE id = ?", (run_id,)).fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        lanes = conn.execute(
            "SELECT tray, bport, lane, ber, status FROM lane_results WHERE test_run_id = ?",
            (run_id,),
        ).fetchall()

    data = dict(run)
    data["lanes"] = [dict(l) for l in lanes]
    return data


@app.get("/api/results")
def list_results() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT r.*, p.name AS project_name
            FROM test_runs r
            JOIN projects p ON p.id = r.project_id
            ORDER BY r.id DESC
            LIMIT 50
            """
        ).fetchall()
    return [dict(r) for r in rows]
