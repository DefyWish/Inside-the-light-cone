import React, { useEffect, useMemo, useRef, useState } from "react";
import CurationMap from "./CurationMap.jsx";
import LifeTree from "./LifeTree.jsx";
import Timeline, { formatYear } from "./Timeline.jsx";
import { formatHistoricalYear, historicalYearFor } from "./TreeCanvas.jsx";

const TYPES = ["investigation.started", "investigation.redirected", "investigation.stopped", "agent.status", "agent.motivation", "tool.called", "tool.result", "evidence.added", "claim.added", "claim.updated", "relation.added", "plan.updated", "curation.event_added", "curation.event_updated", "research.dispatched", "research.returned", "research.no_data", "research.rejected", "narration", "investigation.continue_required", "investigation.completed", "investigation.failed"];
const STATES = { idle: "待命", connecting: "连接", running: "调查", planning: "规划", investigating: "查证", researching: "补证", synthesizing: "策展", completed: "完成", stopped: "停止", failed: "中断" };
const SOURCE_NAMES = { primary_chronicle: "史传", collected_works: "作品集", local_gazetteer: "方志", rare_book: "善本", memoir: "回忆录", ancient_genome_dataset: "古基因组", peer_reviewed_article: "论文", excavation_report: "发掘报告", official_database: "数据库", museum_catalog: "馆藏" };
const STOP = new Set(["停止", "停止调查", "终止", "终止调查", "停下", "stop"]);

function itemName(item) { return item.title || item.claim || item.summary || item.site || item.topic || "证据"; }
function period(item) {
  const a = item.event_year_start == null ? null : Number(item.event_year_start);
  const b = item.event_year_end == null ? null : Number(item.event_year_end);
  if (a != null && b != null && a !== b) return `${formatHistoricalYear(a)}—${formatHistoricalYear(b)}`;
  if (a != null || b != null) return formatHistoricalYear(a ?? b);
  return item.date_text || "年代待定";
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
  return { ...item, event_id: item.event_id || id, title: item.title || item.claim || item.summary || "节点", summary: item.summary || item.claim || item.note || item.title || "", branch: item.branch || SOURCE_NAMES[item.source_kind] || item.narrative_role || "证据线", event_type: item.event_type || item.narrative_role || item.record_type || "事件", event_year_start: year, event_year_end: item.event_year_end ?? year, historical_place: item.historical_place || item.place || item.site || item.political_entity || null, modern_place: item.modern_place || null, latitude: item.latitude ?? null, longitude: item.longitude ?? null, epistemic_status: item.epistemic_status || (item.evidence_level === "view_model" ? "view" : "fact"), source_ids: item.source_ids || (item.source_id ? [item.source_id] : []), claim_ids: item.claim_ids || [], evidence_ids: item.evidence_ids || (item.evidence_id ? [item.evidence_id] : []) };
}

export function projectCurationEvents(events) {
  const formal = new Map();
  events.forEach((stream) => {
    if (!["curation.event_added", "curation.event_updated"].includes(stream.type) || !stream.data.event) return;
    const event = normalize(stream.data.event, `event:${stream.sequence}`);
    formal.set(event.event_id, { ...(formal.get(event.event_id) || {}), ...event });
  });
  if (formal.size) return [...formal.values()].sort((a, b) => (a.event_year_start ?? Infinity) - (b.event_year_start ?? Infinity));
  return events.flatMap((stream) => {
    if (stream.type === "evidence.added" && stream.data.evidence?.record_type !== "evidence_gap") {
      const item = stream.data.evidence;
      if (historicalYearFor(item) != null || item.latitude != null) return [normalize(item, item.evidence_id || `evidence:${stream.sequence}`)];
    }
    if (stream.type === "claim.added" && historicalYearFor(stream.data.claim) != null) return [normalize({ ...stream.data.claim, title: stream.data.claim.text, branch: stream.data.claim.line, claim_ids: [stream.data.claim.claim_id] }, `claim:${stream.data.claim.claim_id}`)];
    return [];
  }).sort((a, b) => (a.event_year_start ?? Infinity) - (b.event_year_start ?? Infinity));
}

export default function App() {
  const [draft, setDraft] = useState("");
  const [question, setQuestion] = useState("");
  const [status, setStatus] = useState("idle");
  const [events, setEvents] = useState([]);
  const [id, setId] = useState(null);
  const [selected, setSelected] = useState(null);
  const [cursorYear, setCursorYear] = useState(0);
  const sourceRef = useRef(null);
  const lastRef = useRef(0);
  const curated = useMemo(() => projectCurationEvents(events), [events]);
  const evidence = useMemo(() => events.filter((event) => event.type === "evidence.added").map((event) => event.data.evidence), [events]);
  const lines = useMemo(() => [...events].reverse().find((event) => event.type === "plan.updated")?.data.lines || [], [events]);
  const agent = useMemo(() => [...events].reverse().find((event) => event.type === "agent.status")?.data, [events]);
  const latestYear = curated.map((event) => event.event_year_start).filter((year) => year != null).at(-1);
  const active = curated.find((event) => event.event_id === selected) || curated.filter((event) => event.event_year_start == null || event.event_year_start <= cursorYear).at(-1);
  const sources = active ? evidence.filter((item) => active.evidence_ids.includes(item.evidence_id) || active.source_ids.includes(item.source_id)) : [];

  useEffect(() => { if (latestYear != null) setCursorYear(latestYear); }, [latestYear]);
  useEffect(() => { if (curated.length) setSelected((value) => curated.some((event) => event.event_id === value) ? value : curated.at(-1).event_id); }, [curated]);
  useEffect(() => () => sourceRef.current?.close(), []);

  function connect(nextId, after = 0) {
    sourceRef.current?.close(); setStatus("connecting");
    const source = new EventSource(`/api/investigations/${nextId}/events${after ? `?after=${after}` : ""}`); sourceRef.current = source;
    source.onopen = () => setStatus("running");
    TYPES.forEach((type) => source.addEventListener(type, (message) => {
      const parsed = JSON.parse(message.data); lastRef.current = Math.max(lastRef.current, parsed.sequence); setEvents((old) => [...old, parsed]);
      if (type === "investigation.started") setQuestion(parsed.data.question);
      if (type === "investigation.completed") { setStatus("completed"); source.close(); }
      if (type === "investigation.stopped") { setStatus("stopped"); source.close(); }
      if (type === "investigation.failed") { setStatus("failed"); source.close(); }
    }));
  }

  async function create(nextQuestion) {
    setEvents([]); setSelected(null); setQuestion(nextQuestion); setStatus("connecting"); lastRef.current = 0;
    const response = await fetch("/api/investigations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: nextQuestion }) });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const body = await response.json(); setId(body.investigation_id); setDraft(""); connect(body.investigation_id);
  }

  async function stop() { if (id) await fetch(`/api/investigations/${id}/stop`, { method: "POST" }); }
  async function submit(event) {
    event.preventDefault(); const text = draft.trim(); if (!text) return;
    try { if (STOP.has(text.toLowerCase())) await stop(); else await create(text); } catch (error) { setStatus("failed"); setEvents([{ type: "investigation.failed", sequence: 0, data: { message: error.message } }]); }
  }
  async function follow() {
    const direction = draft.trim(); if (!direction || !id) return;
    if (STOP.has(direction.toLowerCase())) { await stop(); return; }
    const terminal = ["completed", "stopped", "failed"].includes(status);
    const response = await fetch(`/api/investigations/${id}/redirect`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ direction }) });
    if (response.ok) { setDraft(""); if (terminal) connect(id, lastRef.current); }
  }

  return <main className="curation-shell">
    <header><strong>光锥之内</strong><span>历史策展 Agent</span><i>{STATES[status]}</i></header>
    <form className="curation-query" onSubmit={submit}><input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="问一个人物、家族、族群或遗址" aria-label="调查问题" /><button>新调查</button>{id && <button type="button" onClick={follow}>继续追问</button>}{status === "running" && <button type="button" onClick={stop}>停止</button>}</form>
    <section className="agent-ribbon"><b>{STATES[agent?.state] || STATES[status]}</b><span>{agent?.message || "Agent 将自行规划来源与主题枝"}</span>{agent?.active_line && <em>{agent.active_line}</em>}</section>
    <section className="curation-grid"><article className="map-panel"><div className="panel-title"><h1>{question || "历史对象"}</h1><span>{curated.length} 节点</span></div><CurationMap events={curated} cursorYear={cursorYear} selectedId={active?.event_id} onSelect={setSelected} /></article><aside className="tree-panel"><div className="panel-title"><h2>生命树</h2><span>{lines.length} 主线</span></div><LifeTree events={curated} lines={lines} cursorYear={cursorYear} selectedId={active?.event_id} onSelect={setSelected} /></aside></section>
    <Timeline events={curated} cursorYear={cursorYear} onChange={setCursorYear} selectedId={active?.event_id} onSelect={setSelected} />
    {active && <article className="story-card"><div><span>{formatYear(active.event_year_start)}</span><span>{active.branch}</span><span>{active.event_type}</span></div><h2>{active.title}</h2><p>{active.summary}</p>{(active.historical_place || active.modern_place) && <small>{[active.historical_place, active.modern_place].filter(Boolean).join(" · ")}</small>}{sources.slice(0, 3).map((source) => source.source_url && <a key={source.evidence_id} href={source.source_url} target="_blank" rel="noreferrer">{SOURCE_NAMES[source.source_kind] || "来源"} · {itemName(source)}</a>)}</article>}
    {lines.length > 0 && <div className="plan-strip">{lines.map((line) => <span key={line.line} className={`line-${line.status}`}>{line.line}</span>)}</div>}
    <details className="agent-trace"><summary>调查过程 · {buildInvestigationLog(events).length}</summary>{buildInvestigationLog(events).map((row) => <p key={`${row.sequence}:${row.kind}`}><b>{row.title}</b>{row.detail && ` · ${row.detail}`}</p>)}</details>
  </main>;
}
