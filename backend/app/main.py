from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from .evidence_tools import TOOL_DEFINITIONS, EvidenceTools, ToolCall, ToolResult
from .investigation import (
    ClaimStore,
    InvestigationCreated,
    InvestigationManager,
    InvestigationRequest,
    InvestigationSummary,
    RedirectAccepted,
    RedirectRequest,
    StopAccepted,
    encode_sse,
)
from .providers import MockLLM, provider_from_environment
from .research_agent import (
    ResearchAgent,
    ResearchStagingStore,
    research_provider_from_environment,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = Path(os.getenv("LIGHTCONE_CATALOG_PATH", os.getenv("JIALUO_CATALOG_PATH", PROJECT_ROOT / "artifacts/catalog.sqlite")))
NUMERIC_DIR = Path(os.getenv("LIGHTCONE_NUMERIC_DIR", os.getenv("JIALUO_NUMERIC_DIR", PROJECT_ROOT / "artifacts/numeric")))
FIXTURE_PATH = Path(
    os.getenv(
        "LIGHTCONE_MOCK_FIXTURE",
        os.getenv("JIALUO_MOCK_FIXTURE", PROJECT_ROOT / "fixtures/investigations/mock_v1.json"),
    )
)
RESEARCH_CORPUS_PATH = Path(
    os.getenv(
        "LIGHTCONE_RESEARCH_CORPUS",
        os.getenv("JIALUO_RESEARCH_CORPUS", PROJECT_ROOT / "fixtures/research/mock_corpus_v1.json"),
    )
)
RESEARCH_STAGING_PATH = Path(
    os.getenv(
        "LIGHTCONE_RESEARCH_STAGING",
        os.getenv("JIALUO_RESEARCH_STAGING", PROJECT_ROOT / "artifacts/research_staging.sqlite"),
    )
)
CLAIM_STORE_PATH = Path(
    os.getenv(
        "LIGHTCONE_CLAIM_STORE",
        PROJECT_ROOT / "artifacts/investigations.sqlite",
    )
)
ALIASES_PATH = Path(
    os.getenv(
        "LIGHTCONE_ALIASES",
        PROJECT_ROOT / "data/aliases.json",
    )
)

app = FastAPI(title="光锥之内 API", version="0.5.0")
evidence_tools = EvidenceTools(CATALOG_PATH, NUMERIC_DIR, RESEARCH_STAGING_PATH, ALIASES_PATH)
research_provider = research_provider_from_environment(RESEARCH_CORPUS_PATH)
research_agent = ResearchAgent(
    research_provider,
    ResearchStagingStore(RESEARCH_STAGING_PATH),
)
claim_store = ClaimStore(CLAIM_STORE_PATH)
runtime_provider = provider_from_environment(FIXTURE_PATH, TOOL_DEFINITIONS)
investigations = InvestigationManager(runtime_provider, evidence_tools, research_agent, claim_store=claim_store)
replays = InvestigationManager(MockLLM(FIXTURE_PATH), evidence_tools, research_agent, claim_store=claim_store)


def manager_for(investigation_id: str) -> InvestigationManager | None:
    if investigations.get(investigation_id) is not None:
        return investigations
    if replays.get(investigation_id) is not None:
        return replays
    return None


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "catalog": CATALOG_PATH.exists(),
        "numeric": evidence_tools.numeric.available,
        "provider": runtime_provider.name,
        "replay_provider": replays.provider.name,
        "research_provider": research_provider.name,
        "research_corpus": RESEARCH_CORPUS_PATH.exists(),
        "research_staging": RESEARCH_STAGING_PATH.exists(),
    }


@app.get("/api/tools")
def list_tools() -> list[dict[str, object]]:
    return TOOL_DEFINITIONS


@app.post("/api/tools/{tool_name}", response_model=ToolResult)
def call_tool(tool_name: str, call: ToolCall) -> ToolResult:
    return evidence_tools.execute(tool_name, call.arguments)


@app.post("/api/investigations", response_model=InvestigationCreated)
async def create_investigation(request: InvestigationRequest) -> InvestigationCreated:
    if investigations.is_stop_command(request.question):
        raise HTTPException(status_code=422, detail="当前没有可停止的调查")
    session = await investigations.create(request.question)
    return InvestigationCreated(
        investigation_id=session.id,
        provider=session.provider,
    )


@app.get("/api/investigations", response_model=list[InvestigationSummary])
def list_investigations() -> list[InvestigationSummary]:
    return investigations.list_sessions()


@app.post("/api/replays", response_model=InvestigationCreated)
async def create_replay(request: InvestigationRequest) -> InvestigationCreated:
    session = await replays.create(request.question)
    return InvestigationCreated(
        investigation_id=session.id,
        provider=session.provider,
    )


@app.post(
    "/api/investigations/{investigation_id}/redirect",
    response_model=RedirectAccepted,
)
async def redirect_investigation(
    investigation_id: str,
    request: RedirectRequest,
) -> RedirectAccepted:
    manager = manager_for(investigation_id)
    if manager is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    accepted = await manager.redirect(investigation_id, request.direction)
    if accepted is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    if accepted.mode == "ignored":
        raise HTTPException(status_code=422, detail="direction is empty")
    return accepted


@app.post(
    "/api/investigations/{investigation_id}/stop",
    response_model=StopAccepted,
)
async def stop_investigation(investigation_id: str) -> StopAccepted:
    manager = manager_for(investigation_id)
    if manager is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    stopped = await manager.stop(investigation_id)
    if stopped is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    return stopped


@app.get("/api/investigations/{investigation_id}/events")
async def stream_investigation(investigation_id: str, after: int = 0) -> StreamingResponse:
    manager = manager_for(investigation_id)
    session = manager.get(investigation_id) if manager else None
    if session is None:
        raise HTTPException(status_code=404, detail="investigation not found")

    async def event_stream():
        async for event in session.stream(after):
            yield encode_sse(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
