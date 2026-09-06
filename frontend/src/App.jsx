import React, { useEffect, useMemo, useRef, useState } from "react";
import CurationMap from "./CurationMap.jsx";
import InvestigationReport from "./InvestigationReport.jsx";
import LifeTree from "./LifeTree.jsx";
import Timeline, { formatYear } from "./Timeline.jsx";
import { formatHistoricalYear, historicalYearFor } from "./TreeCanvas.jsx";
import { localizeField, localizePlace, localizePreferredPlace } from "./displayText.js";

const TYPES = ["investigation.started", "investigation.redirected", "investigation.stopped", "agent.status", "agent.motivation", "tool.called", "tool.result", "evidence.added", "claim.added", "claim.updated", "relation.added", "plan.updated", "curation.event_added", "curation.event_updated", "research.dispatched", "research.returned", "research.no_data", "research.rejected", "narration", "investigation.continue_required", "investigation.completed", "investigation.failed"];
const STATES = { idle: "待命", connecting: "连接", running: "调查", planning: "规划", investigating: "查证", researching: "补证", synthesizing: "策展", completed: "完成", stopped: "停止", failed: "中断" };
const SOURCE_NAMES = { primary_chronicle: "史传", collected_works: "作品集", local_gazetteer: "方志", rare_book: "善本", memoir: "回忆录", ancient_genome_dataset: "古基因组", peer_reviewed_article: "论文", excavation_report: "发掘报告", official_database: "数据库", museum_catalog: "馆藏" };
const STOP = new Set(["停止", "停止调查", "终止", "终止调查", "停下", "stop"]);

function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 100 90" aria-hidden="true">
      <g fill="none" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M5 9H94" />
        <path d="M9 9L87 81" />
        <path d="M49 10V47" />
        <path d="M9 81H95" />
      </g>
      <path d="M5 9h10l-5 6zM42 9h14c-3 1-4 8-7 8s-4-7-7-8zM43 47h12l-6-6zM81 81h13l-6.5 6z" fill="currentColor" />
    </svg>
  );
}

export function apiErrorMessage(payload, status) {
  if (typeof payload?.detail === "string") return payload.detail;
  if (typeof payload?.detail?.message === "string") return payload.detail.message;
  return `请求失败（${status}）`;
}

function itemName(item) { return item.title || item.claim || item.summary || item.site || item.topic || "证据"; }
function period(item) {
  const a = item.event_year_start == null ? null : Number(item.event_year_start);
  const b = item.event_year_end == null ? null : Number(item.event_year_end);
  if (a != null && b != null && a !== b) return `${formatHistoricalYear(a)}—${formatHistoricalYear(b)}`;
  if (a != null || b != null) return formatHistoricalYear(a ?? b);
  return item.date_text || "年代待定";
}

function terminalPlace(value) {
  if (!value) return null;
  const parts = String(value).split(/[／/→、]/).map((part) => part.trim()).filter(Boolean);
  return parts.at(-1) || null;
}

export function isVisualCurationCandidate(item) {
  if (!item || item.timeline_eligible === false || item.curation_role === "context") return false;
  if (["context", "gap", "debate"].includes(item.narrative_role) || item.record_type === "evidence_gap") return false;
  if (item.source_kind === "ancient_genome_dataset" && item.curation_role !== "event" && !item.subject_ids?.length) return false;
  const text = `${item.title || ""} ${item.summary || item.text || item.claim || ""} ${item.relation_to_question || ""}`;
  return !/(深时|区域)(背景|基线)|比较基线|比较框架|古基因组.{0,20}基线|底色.{0,20}基线|背景而非直接|不能直接|不直接等同|没有任何古个体被直接|尚未与.+直接对应|阴性证据/.test(text);
}

export function buildStoryline(evidence, claims = []) {
  const rows = [
    ...claims.map((node) => ({ key: `claim:${node.data.claim_id}`, year: historicalYearFor(node.data), timeLabel: period(node.data), role: "判断", claim: node.data.text, relation: node.data.motivation || "", evidence: { record_type: "claim", ...node.data }, isClaim: true, status: node.data.status || "open" })),
    ...evidence.map((node) => { const item = node.data || node; return { key: `${historicalYearFor(item) ?? "x"}:${itemName(item)}`, year: historicalYearFor(item), timeLabel: period(item), sourceTimeLabel: item.publication_year ? `证据发表于 ${item.publication_year} 年` : "", role: item.narrative_role || "证据", claim: item.claim || item.summary || itemName(item), relation: item.relation_to_question || "", evidence: item }; }),
  ];
  return rows.sort((a, b) => (a.year ?? Infinity) - (b.year ?? Infinity));
}

export function buildInvestigationLog(events) {
  const completed = events.some((event) => event.type === "investigation.completed");
  const rows = [];
  events.forEach((event) => {
    if (event.type === "tool.called") rows.push({ kind: "tool", sequence: event.sequence, title: event.data.tool, detail: "" });
    if (event.type === "claim.added") rows.push({ kind: "claim", sequence: event.sequence, title: "形成判断", detail: event.data.claim?.text });
    if (event.type === "curation.event_added") rows.push({ kind: "curation", sequence: event.sequence, title: "生成节点", detail: event.data.event?.title });
    if (event.type === "narration" && !completed) {
      const old = rows.find((row) => row.kind === "narration");
      if (old) Object.assign(old, { sequence: event.sequence, detail: event.data.text });
      else rows.push({ kind: "narration", sequence: event.sequence, title: "阶段叙述", detail: event.data.text });
    }
    if (event.type === "investigation.completed") rows.push({ kind: "completed", sequence: event.sequence, title: "调查结论", detail: event.data.summary });
  });
  return rows;
}

function normalize(item, id) {
  const year = item.event_year_start ?? historicalYearFor(item);
  const destination = item.movement?.to;
  const destinationLatitude = destination?.latitude ?? destination?.lat;
  const destinationLongitude = destination?.longitude ?? destination?.lon;
  const latitude = destinationLatitude ?? item.latitude ?? null;
  const longitude = destinationLongitude ?? item.longitude ?? null;
  const coordinateBound = latitude != null && longitude != null;
  const rawHistoricalPlace = item.historical_place || item.place || item.site || item.political_entity || null;
  const destinationPlace = destination?.name || null;
  const historicalPlace = localizePreferredPlace(destinationPlace, coordinateBound ? terminalPlace(rawHistoricalPlace) : rawHistoricalPlace, item.modern_place);
  const modernPlace = localizePlace(coordinateBound ? terminalPlace(item.modern_place) : item.modern_place);
  const rawBranch = item.branch || SOURCE_NAMES[item.source_kind] || item.narrative_role || "证据线";
  const rawEventType = item.event_type || item.narrative_role || item.record_type || "事件";
  const movement = item.movement ? {
    ...item.movement,
    from: item.movement.from ? { ...item.movement.from, raw_name: item.movement.from.name, name: localizePlace(item.movement.from.name) } : item.movement.from,
    to: item.movement.to ? { ...item.movement.to, raw_name: item.movement.to.name, name: localizePreferredPlace(item.movement.to.name, rawHistoricalPlace, item.modern_place) } : item.movement.to,
  } : item.movement;
  return { ...item, raw_historical_place: rawHistoricalPlace, raw_branch: rawBranch, raw_event_type: rawEventType, event_id: item.event_id || id, title: item.title || item.claim || item.summary || "节点", summary: item.summary || item.claim || item.note || item.title || "", branch: localizeField(rawBranch, "证据线"), event_type: localizeField(rawEventType, "事件"), event_year_start: year, event_year_end: item.event_year_end ?? year, historical_place: historicalPlace || null, modern_place: modernPlace || null, latitude, longitude, movement, epistemic_status: item.epistemic_status || (item.evidence_level === "view_model" ? "view" : "fact"), source_ids: item.source_ids || (item.source_id ? [item.source_id] : []), claim_ids: item.claim_ids || [], evidence_ids: item.evidence_ids || (item.evidence_id ? [item.evidence_id] : []) };
}

export function projectCurationEvents(events) {
  const projected = new Map();
  events.forEach((stream) => {
    if (stream.type === "evidence.added" && stream.data.evidence?.record_type !== "evidence_gap") {
      const item = stream.data.evidence;
      if (isVisualCurationCandidate(item) && (historicalYearFor(item) != null || item.latitude != null)) {
        const event = { ...normalize(item, item.evidence_id || `evidence:${stream.sequence}`), projection_kind: "evidence" };
        projected.set(event.event_id, { ...(projected.get(event.event_id) || {}), ...event });
      }
    }
    if (stream.type === "claim.added" && isVisualCurationCandidate(stream.data.claim) && historicalYearFor(stream.data.claim) != null) {
      const claim = stream.data.claim;
      const event = { ...normalize({ ...claim, title: claim.text, branch: claim.line, claim_ids: [claim.claim_id] }, `claim:${claim.claim_id}`), projection_kind: "claim" };
      projected.set(event.event_id, { ...(projected.get(event.event_id) || {}), ...event });
    }
  });
  const formal = new Map();
  events.forEach((stream) => {
    if (!["curation.event_added", "curation.event_updated"].includes(stream.type) || !stream.data.event) return;
    if (stream.data.event.epistemic_status === "gap") return;
    const event = { ...normalize(stream.data.event, `event:${stream.sequence}`), projection_kind: "curation" };
    formal.set(event.event_id, { ...(formal.get(event.event_id) || {}), ...event });
  });
  formal.forEach((event, eventId) => {
    projected.set(eventId, { ...(projected.get(eventId) || {}), ...event });
  });
  return [...projected.values()].sort((a, b) => (a.event_year_start ?? Infinity) - (b.event_year_start ?? Infinity));
}

export function InvestigationHistory({ history, activeId, onOpen, onDelete }) {
  return <details className="history-menu"><summary>检索历史 · {history.length}</summary><div>{history.map((item) => <div key={item.investigation_id} className={`history-entry ${item.investigation_id === activeId ? "active" : ""}`}><button type="button" className="history-open" onClick={() => onOpen(item)}><b>{item.question}</b><small>{STATES[item.status] || item.status} · {item.event_count}</small></button><button type="button" className="history-delete" title="删除这条检索" aria-label={`删除 ${item.question}`} onClick={(event) => { event.preventDefault(); event.stopPropagation(); onDelete(item); }}>×</button></div>)}</div></details>;
}

export default function App() {
  const [draft, setDraft] = useState("");
  const [question, setQuestion] = useState("");
  const [status, setStatus] = useState("idle");
  const [events, setEvents] = useState([]);
  const [history, setHistory] = useState([]);
  const [notice, setNotice] = useState("");
  const [id, setId] = useState(null);
  const [selected, setSelected] = useState(null);
  const [cursorYear, setCursorYear] = useState(0);
  const [reportAudience, setReportAudience] = useState("professional");
  const [report, setReport] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);
  const sourceRef = useRef(null);
  const lastRef = useRef(0);
  const historyRestoredRef = useRef(false);
  const curated = useMemo(() => projectCurationEvents(events), [events]);
  const evidence = useMemo(() => [...new Map(events.filter((event) => event.type === "evidence.added").map((event) => [event.data.evidence.evidence_id || event.sequence, event.data.evidence])).values()], [events]);
  const timelineEvents = useMemo(() => curated.filter((event) => event.projection_kind !== "claim"), [curated]);
  const lines = useMemo(() => ([...events].reverse().find((event) => event.type === "plan.updated")?.data.lines || []).map((line) => ({ ...line, line: localizeField(line.line, "调查主线") })), [events]);
  const agent = useMemo(() => [...events].reverse().find((event) => event.type === "agent.status")?.data, [events]);
  const latestYear = timelineEvents.map((event) => event.event_year_start).filter((year) => year != null).at(-1);
  const active = curated.find((event) => event.event_id === selected) || timelineEvents.filter((event) => event.event_year_start == null || event.event_year_start <= cursorYear).at(-1);
  const exactSources = active ? evidence.filter((item) => active.evidence_ids.includes(item.evidence_id)) : [];
  const sourceCandidates = exactSources.length > 0 ? exactSources : (active ? evidence.filter((item) => active.source_ids.includes(item.source_id)) : []);
  const sources = [...new Map(sourceCandidates.map((item) => [item.evidence_id || `${item.source_url}:${item.title}`, item])).values()];

  useEffect(() => { if (latestYear != null) setCursorYear(latestYear); }, [latestYear]);
  useEffect(() => { if (timelineEvents.length) setSelected((value) => curated.some((event) => event.event_id === value) ? value : timelineEvents.at(-1).event_id); }, [curated, timelineEvents]);
  useEffect(() => { setReport(null); }, [id]);
  useEffect(() => {
    if (!id || status !== "completed") return undefined;
    const controller = new AbortController();
    setReportLoading(true);
    fetch(`/api/investigations/${id}/report?audience=${reportAudience}`, { signal: controller.signal })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("报告生成失败")))
      .then(setReport)
      .catch((error) => { if (error.name !== "AbortError") setNotice(error.message); })
      .finally(() => setReportLoading(false));
    return () => controller.abort();
  }, [id, status, reportAudience]);
  async function refreshHistory() {
    try {
      const response = await fetch("/api/investigations");
      if (response.ok) {
        const items = await response.json();
        setHistory(items);
        if (!historyRestoredRef.current && !id && items.length > 0) {
          historyRestoredRef.current = true;
          openHistory(items[0]);
        }
      }
    } catch {
      return;
    }
  }

  useEffect(() => {
    refreshHistory();
    const timer = window.setInterval(refreshHistory, 4000);
    return () => { window.clearInterval(timer); sourceRef.current?.close(); };
  }, []);

  function connect(nextId, after = 0, reset = false) {
    sourceRef.current?.close(); setStatus("connecting"); setNotice("");
    if (reset) { setEvents([]); setSelected(null); lastRef.current = 0; }
    const source = new EventSource(`/api/investigations/${nextId}/events${after ? `?after=${after}` : ""}`); sourceRef.current = source;
    source.onopen = () => setStatus("running");
    TYPES.forEach((type) => source.addEventListener(type, (message) => {
      const parsed = JSON.parse(message.data); lastRef.current = Math.max(lastRef.current, parsed.sequence); setEvents((old) => [...old, parsed]);
      if (type === "investigation.started") setQuestion(parsed.data.question);
      if (type === "investigation.completed") { setStatus("completed"); source.close(); refreshHistory(); }
      if (type === "investigation.stopped") { setStatus("stopped"); source.close(); refreshHistory(); }
      if (type === "investigation.failed") { setStatus("failed"); setNotice(parsed.data.message || "调查中断"); source.close(); refreshHistory(); }
    }));
  }

  async function create(nextQuestion) {
    historyRestoredRef.current = true;
    const response = await fetch("/api/investigations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: nextQuestion }) });
    if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(apiErrorMessage(error, response.status)); }
    const body = await response.json(); setEvents([]); setSelected(null); setQuestion(nextQuestion); setStatus("connecting"); lastRef.current = 0; setId(body.investigation_id); setDraft(""); connect(body.investigation_id); refreshHistory();
  }

  async function stop() { if (id) await fetch(`/api/investigations/${id}/stop`, { method: "POST" }); }
  async function submit(event) {
    event.preventDefault(); const text = draft.trim(); if (!text) return;
    try { setNotice(""); if (STOP.has(text.toLowerCase())) await stop(); else await create(text); } catch (error) { setNotice(error.message); }
  }
  async function follow() {
    const direction = draft.trim(); if (!direction || !id) return;
    if (STOP.has(direction.toLowerCase())) { await stop(); return; }
    const terminal = ["completed", "stopped", "failed"].includes(status);
    const response = await fetch(`/api/investigations/${id}/redirect`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ direction }) });
    if (!response.ok) { const error = await response.json().catch(() => ({})); setNotice(apiErrorMessage(error, response.status)); return; }
    setNotice(""); setDraft(""); if (terminal) connect(id, lastRef.current); refreshHistory();
  }

  function openHistory(item) {
    historyRestoredRef.current = true;
    setId(item.investigation_id); setQuestion(item.question); connect(item.investigation_id, 0, true);
  }

  async function deleteHistory(item) {
    try {
      const response = await fetch(`/api/investigations/${item.investigation_id}`, { method: "DELETE" });
      if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(apiErrorMessage(error, response.status)); }
      const remaining = history.filter((entry) => entry.investigation_id !== item.investigation_id);
      setHistory(remaining); setNotice("");
      if (item.investigation_id !== id) return;
      sourceRef.current?.close(); setEvents([]); setSelected(null); setReport(null); lastRef.current = 0;
      if (remaining.length > 0) openHistory(remaining[0]);
      else { setId(null); setQuestion(""); setStatus("idle"); }
    } catch (error) {
      setNotice(error.message);
    }
  }

  function changeTimeline(year) {
    setCursorYear(year);
    const nearest = timelineEvents.filter((event) => event.event_year_start == null || event.event_year_start <= year).at(-1);
    setSelected(nearest?.event_id || null);
  }

  return <main className="curation-shell">
    <header><div className="brand-lockup"><BrandMark /><strong>光锥之内</strong></div><InvestigationHistory history={history} activeId={id} onOpen={openHistory} onDelete={deleteHistory} /><i>{STATES[status]}</i></header>
    <form className="curation-query" onSubmit={submit}><input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="问一个人物、家族、族群或遗址" aria-label="调查问题" /><button>新调查</button>{id && <button type="button" onClick={follow}>继续追问</button>}{status === "running" && <button type="button" onClick={stop}>停止</button>}</form>
    <section className="agent-ribbon"><b>{STATES[agent?.state] || STATES[status]}</b><span>{agent?.message || "Agent 将自行规划来源与主题枝"}</span>{agent?.active_line && <em>{agent.active_line}</em>}</section>
    {notice && <div className="query-notice">{notice}</div>}
    <section className="curation-grid"><article className="map-panel"><div className="panel-title"><h1>{question || "历史对象"}</h1><span>{curated.length} 节点</span></div><CurationMap events={timelineEvents} cursorYear={cursorYear} selectedId={active?.event_id} onSelect={setSelected} /></article><aside className="tree-panel"><div className="panel-title"><h2>生命树</h2><span>{lines.length} 主线</span></div><LifeTree events={curated} lines={lines} cursorYear={cursorYear} selectedId={active?.event_id} onSelect={setSelected} /></aside></section>
    <Timeline events={timelineEvents} cursorYear={cursorYear} onChange={changeTimeline} selectedId={active?.event_id} onSelect={setSelected} />
    {active && <article className="story-card"><div><span>{formatYear(active.event_year_start)}</span><span>{active.branch}</span><span>{active.event_type}</span></div><h2>{active.title}</h2><p>{active.summary}</p>{(active.historical_place || active.modern_place) && <small>{[active.historical_place, active.modern_place].filter(Boolean).join(" · ")}</small>}{sources.slice(0, 3).map((source) => source.source_url && <a key={source.evidence_id} href={source.source_url} target="_blank" rel="noreferrer">{SOURCE_NAMES[source.source_kind] || "来源"} · {itemName(source)}</a>)}</article>}
    {lines.length > 0 && <div className="plan-strip">{lines.map((line) => <span key={line.line} className={`line-${line.status}`}>{line.line}</span>)}</div>}
    <details className="agent-trace"><summary>调查过程 · {buildInvestigationLog(events).length}</summary>{buildInvestigationLog(events).map((row) => <p key={`${row.sequence}:${row.kind}`}><b>{row.title}</b>{row.detail && ` · ${row.detail}`}</p>)}</details>
    {id && status === "completed" && <InvestigationReport report={report} audience={reportAudience} loading={reportLoading} onAudienceChange={setReportAudience} />}
  </main>;
}
