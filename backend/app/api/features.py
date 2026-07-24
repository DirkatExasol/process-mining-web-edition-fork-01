"""Notes, sampling, simulation, AI documentation, settings and backup endpoints."""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from .. import log_events as logx
from ..config import DEFAULT_LLM_PROMPT
from ..db.manager import db
from ..models import (
    FilterSpec,
    HappyPath,
    ProcessGraph,
    ProcessNote,
    SampleSet,
    SamplingMethod,
    SimulationConfig,
    SimulationResult,
    StepInfo,
    TransitionMetric,
)
from ..services import backup as backup_service
from ..services import docgen, llm as llm_service, simulation
from ..services.analytics import (
    happy_path_conformance,
    path_diverse_sample,
    random_sample,
    temporal_stratified_sample,
)
from ..store.settings import store
from .projects import repo, require_connection

router = APIRouter(prefix="/api", tags=["features"])


# ── Notes ────────────────────────────────────────────────────────────────────


@router.get("/projects/{project_id}/notes", response_model=list[ProcessNote])
async def list_notes(project_id: str) -> list[ProcessNote]:
    require_connection()
    r = repo()
    await r.ensure_notes_table()
    return await r.load_notes(project_id, db.username)


@router.put("/projects/{project_id}/notes", response_model=ProcessNote)
async def save_note(project_id: str, note: ProcessNote) -> ProcessNote:
    require_connection()
    r = repo()
    await r.ensure_notes_table()

    current_user = db.username
    existing = next(
        (n for n in await r.load_notes(project_id, current_user) if n.id == note.id),
        None,
    )
    if existing is not None:
        # Editing preserves the original author and records who made this edit.
        note.username = existing.username
        note.lastEditedBy = current_user
        note.editedAt = datetime.now()
    else:
        note.username = current_user
        note.lastEditedBy = ""

    await r.upsert_note(note, project_id)
    return note


@router.delete("/projects/{project_id}/notes/{note_id}")
async def delete_note(project_id: str, note_id: str) -> dict[str, bool]:
    require_connection()
    await repo().delete_note(note_id, project_id)
    return {"ok": True}


# ── Sampling ─────────────────────────────────────────────────────────────────


class CreateSampleRequest(BaseModel):
    sampleSet: SampleSet
    count: int
    method: SamplingMethod


@router.get("/projects/{project_id}/samples")
async def sample_counts(project_id: str) -> dict[str, object]:
    require_connection()
    r = repo()
    await r.ensure_sample_set_column()
    counts = await r.load_sample_journey_counts(project_id)
    methods = {
        s.value: store.get(f"sampling.method.{s.value}.{project_id}")
        for s in (SampleSet.sample1, SampleSet.sample2, SampleSet.sample3)
    }
    return {"counts": counts, "methods": {k: v for k, v in methods.items() if v}}


@router.post("/projects/{project_id}/samples")
async def create_sample(project_id: str, request: CreateSampleRequest) -> dict[str, object]:
    require_connection()
    if request.sampleSet.is_original:
        raise HTTPException(status_code=400, detail="Cannot overwrite the original data.")

    r = repo()
    await r.ensure_sample_set_column()
    await r.delete_sample(project_id, request.sampleSet)

    if request.method is SamplingMethod.random:
        ids = await r.load_all_event_ids_for_sampling(project_id)
        selected = random_sample(ids, request.count)
    elif request.method is SamplingMethod.temporal:
        pairs = await r.load_event_ids_with_start_times(project_id)
        selected = temporal_stratified_sample(pairs, request.count)
    else:
        pairs = await r.load_event_ids_with_paths(project_id)
        selected = path_diverse_sample(pairs, request.count)

    if not selected:
        raise HTTPException(
            status_code=404, detail="No journeys found in the original data."
        )

    await r.insert_sample_journeys(project_id, selected, request.sampleSet)
    store.set(
        f"sampling.method.{request.sampleSet.value}.{project_id}", request.method.value
    )
    counts = await r.load_sample_journey_counts(project_id)
    return {"counts": counts, "created": len(selected)}


@router.delete("/projects/{project_id}/samples/{sample_set}")
async def delete_sample(project_id: str, sample_set: SampleSet) -> dict[str, object]:
    require_connection()
    r = repo()
    await r.delete_sample(project_id, sample_set)
    store.delete(f"sampling.method.{sample_set.value}.{project_id}")
    return {"counts": await r.load_sample_journey_counts(project_id)}


# ── Simulation ───────────────────────────────────────────────────────────────


class SimulateRequest(BaseModel):
    graph: ProcessGraph
    stepInfos: dict[str, StepInfo] = {}
    config: SimulationConfig = SimulationConfig()


# A run beyond this exhausts memory / crashes the process, so it is refused up
# front rather than attempted (the user reported ~200k journeys killing the app).
_MAX_SIM_JOURNEYS = 100_000
# Wall-clock ceiling for a single run — a slower run is abandoned (and logged)
# instead of hanging the request indefinitely.
_SIM_TIMEOUT_SECS = 120.0


@router.post("/simulate", response_model=SimulationResult)
async def simulate(request: SimulateRequest) -> SimulationResult:
    step_infos = request.stepInfos or request.graph.steps
    count = request.config.journeyCount
    # Guard against an oversized run that would otherwise exhaust memory / crash.
    if count > _MAX_SIM_JOURNEYS:
        logx.warn(
            f"Simulation rejected: {count} journeys exceeds the {_MAX_SIM_JOURNEYS} limit",
            operation="simulation",
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"Too many journeys to simulate ({count:,}). "
                f"The maximum is {_MAX_SIM_JOURNEYS:,}."
            ),
        )
    # Run the CPU-bound simulation off the event loop, bounded by a timeout so a
    # pathological run surfaces as a logged error rather than a frozen request.
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                simulation.simulate, request.graph, step_infos, request.config
            ),
            timeout=_SIM_TIMEOUT_SECS,
        )
    except (asyncio.TimeoutError, TimeoutError):
        logx.error(
            f"Simulation timed out after {_SIM_TIMEOUT_SECS:g}s ({count} journeys)",
            operation="simulation",
        )
        raise HTTPException(
            status_code=504,
            detail=(
                f"Simulation timed out ({count:,} journeys). Try fewer journeys."
            ),
        ) from None
    except MemoryError:
        logx.error(
            f"Simulation ran out of memory ({count} journeys)",
            operation="simulation",
        )
        raise HTTPException(
            status_code=500,
            detail=(
                f"Simulation ran out of memory ({count:,} journeys). "
                "Try fewer journeys."
            ),
        ) from None
    except Exception as exc:  # noqa: BLE001
        logx.error(
            f"Simulation failed ({count} journeys): {exc.__class__.__name__}: {exc}",
            operation="simulation",
        )
        raise HTTPException(status_code=500, detail=f"Simulation failed: {exc}") from exc


# ── Happy-path conformance ───────────────────────────────────────────────────


class ConformanceRequest(BaseModel):
    filter: FilterSpec = FilterSpec()
    happyPaths: list[HappyPath] = []
    limit: int = 500


@router.post("/projects/{project_id}/conformance")
async def conformance(
    project_id: str, request: ConformanceRequest
) -> dict[str, float | None]:
    require_connection()
    r = repo(request.filter.sampleSet)
    try:
        variants = await r.load_journey_paths(project_id, request.filter, request.limit)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    return {p.id: happy_path_conformance(p, variants) for p in request.happyPaths}


# ── AI supported documentation ───────────────────────────────────────────────


class DocumentationRequest(BaseModel):
    projectTitle: str
    filter: FilterSpec = FilterSpec()
    graph: ProcessGraph
    promptTemplate: str = DEFAULT_LLM_PROMPT
    targetNorms: dict[str, dict[str, float]] = {}
    targetMetric: TransitionMetric = TransitionMetric.count
    happyPaths: list[HappyPath] = []


@router.post("/projects/{project_id}/documentation")
async def documentation(
    project_id: str, request: DocumentationRequest
) -> dict[str, object]:
    require_connection()
    server = db.active_llm_server
    if server is None or not server.serverURL.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "No LLM server configured. Edit your connection to select an LLM "
                "server, or add one in Settings."
            ),
        )

    r = repo(request.filter.sampleSet)
    try:
        paths = await r.load_journey_paths(project_id, request.filter, 200)
    except TimeoutError:
        logx.warn(
            f"AI documentation: journey-paths query timed out (project {project_id})",
            operation="ai-doc",
        )
        paths = []
    paths_html, paths_section = docgen.journey_paths_section(paths)

    conformance_md = docgen.conformance_section(
        request.graph, request.targetNorms, request.targetMetric
    )

    try:
        variants = await r.load_journey_paths(project_id, request.filter, 500)
    except TimeoutError:
        logx.warn(
            f"AI documentation: variants query timed out (project {project_id})",
            operation="ai-doc",
        )
        variants = []
    happy_md = docgen.happy_path_section(request.happyPaths, variants)

    prompt = docgen.build_prompt(
        request.projectTitle, request.promptTemplate, request.graph, paths_html
    )

    try:
        answer = await llm_service.chat(
            server.serverURL, server.apiKey, server.model, prompt
        )
        error = None
    except llm_service.LLMError as exc:
        answer, error = None, str(exc)
        logx.error(
            f"AI documentation LLM call failed (project {project_id}, "
            f"model {server.model or '?'}): {exc}",
            operation="ai-doc",
        )

    return {
        "result": answer,
        "error": error,
        "prompt": prompt,
        "model": server.model or None,
        "generatedAt": datetime.now(),
        "journeyPathsSummary": paths_section,
        "conformanceSummary": conformance_md,
        "happyPathSummary": happy_md,
    }


# ── Settings (the UserDefaults replacement) ──────────────────────────────────


class SettingsPatch(BaseModel):
    values: dict[str, object]


@router.get("/settings")
def get_settings() -> dict[str, object]:
    values = store.all()
    # Secrets are never echoed back through the settings channel.
    return {
        k: v
        for k, v in values.items()
        if not k.startswith("conn_pw_") and not k.startswith("llm_api_key_")
    }


@router.patch("/settings")
def patch_settings(patch: SettingsPatch) -> dict[str, bool]:
    for key, value in patch.values.items():
        if key.startswith("conn_pw_") or key.startswith("llm_api_key_"):
            continue
        if value is None:
            store.delete(key)
        else:
            store.set(key, value)
    return {"ok": True}


# ── Backup / restore ─────────────────────────────────────────────────────────


class ExportRequest(BaseModel):
    includePasswords: bool = False
    includeUsername: bool = True
    includeLlmApiKey: bool = False
    password: str = ""


class InspectRequest(BaseModel):
    content: str  # base64-encoded file bytes
    password: str = ""


class RestoreRequest(InspectRequest):
    options: dict[str, bool] = {}


def _decode_backup(request: InspectRequest) -> dict:
    try:
        raw = base64.b64decode(request.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid file content.") from exc

    if backup_service.is_encrypted(raw):
        if not request.password:
            raise HTTPException(status_code=401, detail="This backup is encrypted.")
        try:
            raw = backup_service.decrypt(raw, request.password)
        except backup_service.BackupError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    import json

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400, detail="The backup file format is invalid or corrupted."
        ) from exc


@router.post("/backup/export")
def export_backup(request: ExportRequest) -> Response:
    payload = backup_service.export_payload(
        db,
        include_passwords=request.includePasswords,
        include_username=request.includeUsername,
        include_llm_api_key=request.includeLlmApiKey,
    )
    data = backup_service.encode(payload)
    if request.password:
        data = backup_service.encrypt(data, request.password)
    stamp = datetime.now().strftime("%Y-%m-%d")
    return Response(
        content=data,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="ProcessMining-Backup-{stamp}.json"'
            )
        },
    )


@router.post("/backup/inspect")
def inspect_backup(request: InspectRequest) -> dict[str, object]:
    return backup_service.summarize(_decode_backup(request))


@router.post("/backup/restore")
def restore_backup(request: RestoreRequest) -> dict[str, bool]:
    backup_service.restore(db, _decode_backup(request), request.options)
    return {"ok": True}
