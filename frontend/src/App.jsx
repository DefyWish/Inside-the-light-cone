import { useEffect, useMemo, useRef, useState } from "react";

import TreeCanvas, { formatHistoricalYear, historicalYearFor, labelFor, targetMatchesLabel } from "./TreeCanvas.jsx";
import NetworkCanvas from "./NetworkCanvas.jsx";
import { THEMES, readStoredTheme } from "./themes.js";

const EVENT_TYPES = [
  "investigation.started",
  "investigation.redirected",
  "investigation.stopped",
  "investigation.continue_required",
  "agent.motivation",
  "tool.called",
  "tool.result",
  "evidence.added",
  "claim.added",
  "claim.updated",
  "relation.added",
  "plan.updated",
  "research.dispatched",
  "research.returned",
  "research.no_data",
  "research.rejected",
  "narration",
  "investigation.completed",
  "investigation.failed",
];

const STATUS_LABELS = {
  idle: "等待提问",
  connecting: "连接调查",
  running: "调查进行中",
  completed: "调查完成",
  stopped: "调查已停止",
  failed: "调查中断",
};

const EVIDENCE_LABELS = {
  fact_genomic: "古基因组事实",
  fact_archaeology: "考古事实",
  view_model: "研究模型",
};

const SOURCE_KIND_LABELS = {
  peer_reviewed_article: "同行评议论文",
  excavation_report: "考古发掘报告",
  academic_monograph: "学术专著",
  thesis: "学位论文",
  official_database: "权威学术数据库",
  institutional_repository: "大学／科研机构仓储",
  museum_catalog: "博物馆藏品目录",
};

const CLAIM_STATUS_LABELS = {
  open: "暗线·待证",
  strengthened: "明线",
  challenged: "遇反证",
  dropped: "已证伪",
};

const NARRATIVE_ROLE_LABELS = {
  context: "历史背景",
  event: "关键事件",
  evidence: "证据落点",
  debate: "争议转折",
  gap: "证据缺口",
  legacy: "后续影响",
};

const TOOL_LABELS = {
  search_ancient_samples: "查古样本",
  search_genetic_relations: "查遗传关系",
  search_archaeological_sites: "查考古遗址",
  search_place_history: "查地名沿革",
  search_literature: "查文献",
  mark_evidence_gap: "标注证据空白",
};

const ARGUMENT_LABELS = {
  individual: "个体",
  place: "地点",
  query: "关键词",
  topic: "主题",
  reason: "原因",
  min_bp: "最早界限 BP",
  max_bp: "最晚界限 BP",
  time_scope: "时间范围",
  limit: "上限",
};

const STOP_COMMANDS = new Set(["停止", "停止调查", "终止", "终止调查", "停下", "stop", "stop investigation"]);

function evidenceName(item) {
  return item.claim
    || item.individual_id
    || item.genetic_id
    || item.site
    || item.title
    || item.abbreviation
    || item.topic
    || item.record_type
    || "证据";
}

function evidencePeriod(item) {
  const start = item.event_year_start === null || item.event_year_start === undefined
    ? null
    : Number(item.event_year_start);
  const end = item.event_year_end === null || item.event_year_end === undefined
    ? null
    : Number(item.event_year_end);
  if (start !== null && end !== null && start !== end) {
    return `${formatHistoricalYear(start)}—${formatHistoricalYear(end)}`;
  }
  if (start !== null || end !== null) return formatHistoricalYear(start ?? end);
  if (item.mean_bp) return `距今约 ${Math.round(item.mean_bp).toLocaleString()} 年`;
  return item.date_text;
}

export function buildStoryline(evidence, claims = []) {
  const seen = new Set();
  const beats = [];
  const push = (beat) => {
    const dedupKey = `${beat.year ?? "x"}:${(beat.claim || "").slice(0, 18).toLowerCase()}`;
    if (seen.has(dedupKey)) return;
    seen.add(dedupKey);
    beats.push(beat);
  };
  for (const node of claims) {
    const item = node.data;
    push({
      key: `claim:${item.claim_id}`,
      year: historicalYearFor(item),
      timeLabel: evidencePeriod(item) || "年代待定",
      role: "判断",
      claim: item.text,
      relation: item.motivation || "",
      evidence: { record_type: "claim", ...item },
      isClaim: true,
      status: item.status || "open",
    });
  }
  for (const node of evidence) {
    const item = node.data || node;
    push({
      key: `${historicalYearFor(item) ?? "undated"}:${item.claim || evidenceName(item)}`,
      year: historicalYearFor(item),
      timeLabel: evidencePeriod(item) || "年代待定",
      sourceTimeLabel: item.publication_year ? `证据发表于 ${item.publication_year} 年` : "",
      role: NARRATIVE_ROLE_LABELS[item.narrative_role] || "证据落点",
      claim: item.claim || item.summary || evidenceName(item),
      relation: item.relation_to_question || item.scope_note || "",
      evidence: item,
    });
  }
  const noYear = Number.POSITIVE_INFINITY;
  return beats.sort((a, b) => (a.year ?? noYear) - (b.year ?? noYear));
}

function formatArguments(argumentsValue = {}) {
  return Object.entries(argumentsValue)
    .map(([key, value]) => `${ARGUMENT_LABELS[key] || key}：${String(value)}`)
    .join(" · ");
}

function resultSummary(result) {
  if (!result) return "等待结果";
  if (result.status !== "ok") return result.message || result.status;
  const names = (result.items || []).slice(0, 3).map(evidenceName);
  const suffix = names.length ? `：${names.join("、")}` : "";
  return `取得 ${(result.items || []).length} 条结果${suffix}`;
}

export function buildInvestigationLog(events) {
  const entries = [];
  const hasCompleted = events.some((event) => event.type === "investigation.completed");
  let motivation = "";
  for (const event of events) {
    if (event.type === "agent.motivation") {
      motivation = event.data.text || "";
      continue;
    }
    if (event.type === "tool.called") {
      entries.push({
        kind: "tool",
        sequence: event.sequence,
        title: TOOL_LABELS[event.data.tool] || event.data.tool,
        motivation,
        detail: formatArguments(event.data.arguments),
        tool: event.data.tool,
        result: null,
      });
      motivation = "";
      continue;
    }
    if (event.type === "tool.result") {
      const target = [...entries].reverse().find((entry) => entry.kind === "tool" && entry.tool === event.data.tool && !entry.result);
      if (target) target.result = event.data;
      continue;
    }
    if (event.type === "research.dispatched") {
      entries.push({
        kind: "research",
        sequence: event.sequence,
        title: "联网研究",
        detail: event.data.query,
        resultText: "正在检索带原文引文的公开来源",
      });
      continue;
    }
    if (["research.returned", "research.no_data", "research.rejected"].includes(event.type)) {
      entries.push({
        kind: event.type === "research.returned" ? "research-ok" : "research-empty",
        sequence: event.sequence,
        title: event.type === "research.returned" ? "联网研究返回" : "联网研究未命中",
        detail: event.data.message,
      });
      continue;
    }
    if (event.type === "investigation.redirected") {
      entries.push({ kind: "direction", sequence: event.sequence, title: "继续追问", detail: event.data.direction });
      continue;
    }
    if (event.type === "claim.added") {
      entries.push({
        kind: "claim",
        sequence: event.sequence,
        title: "形成判断",
        detail: event.data.claim?.text,
      });
      continue;
    }
    if (event.type === "relation.added") {
      const relation = event.data.relation || {};
      entries.push({
        kind: "relation",
        sequence: event.sequence,
        title: "关系连接",
        detail: `${relation.subject_id} —${relation.predicate}→ ${relation.object_id}${relation.note ? `（${relation.note}）` : ""}`,
      });
      continue;
    }
    if (event.type === "investigation.continue_required") {
      entries.push({ kind: "system", sequence: event.sequence, title: "收束被驳回", detail: event.data.message });
      continue;
    }
    if (event.type === "narration") {
      if (hasCompleted) continue;
      const previousNarration = [...entries].reverse().find((entry) => entry.kind === "narration");
      if (previousNarration) {
        previousNarration.sequence = event.sequence;
        previousNarration.detail = event.data.text;
      } else {
        entries.push({ kind: "narration", sequence: event.sequence, title: "阶段叙述", detail: event.data.text });
      }
      continue;
    }
    if (event.type === "investigation.completed") {
      entries.push({ kind: "completed", sequence: event.sequence, title: "调查结论", detail: event.data.summary });
      continue;
    }
    if (event.type === "investigation.stopped") {
      entries.push({ kind: "stopped", sequence: event.sequence, title: "调查已停止", detail: event.data.message });
      continue;
    }
    if (event.type === "investigation.failed") {
      entries.push({ kind: "failed", sequence: event.sequence, title: "调查中断", detail: event.data.message });
    }
  }
  return entries;
}

function ClaimDetail({ claim, allEvidence, relations, onSelect, onClose }) {
  const attach = relations.filter(
    (relation) => relation.subject_id === claim.claim_id && ["supports", "derived_from"].includes(relation.predicate),
  );
  const supported = allEvidence.filter((node) =>
    attach.some((relation) => targetMatchesLabel(relation.object_id, String(labelFor(node.data)))),
  );
  const rows = [
    ["状态", CLAIM_STATUS_LABELS[claim.status] || claim.status],
    ["所属线索", claim.line],
    ["事件年代", evidencePeriod(claim)],
    ["形成动机", claim.motivation],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "");

  return (
    <aside className="evidence-drawer">
      <button className="icon-button" onClick={onClose} aria-label="关闭判断详情">×</button>
      <div className="eyebrow">JUDGMENT · 判断</div>
      <h2>{claim.text}</h2>
      <dl>
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{String(value)}</dd>
          </div>
        ))}
      </dl>
      <div className="stream-heading">支撑证据 · {supported.length}</div>
      <div className="support-list">
        {supported.length === 0 && <p>尚无证据挂到这条判断上。</p>}
        {supported.map((node) => (
          <button type="button" key={node.sequence} onClick={() => onSelect(node.data)}>
            {evidenceName(node.data)}
          </button>
        ))}
      </div>
      <details>
        <summary>查看原始字段</summary>
        <pre>{JSON.stringify(claim, null, 2)}</pre>
      </details>
    </aside>
  );
}

function EvidenceDetail({ evidence, allEvidence = [], relations = [], onSelect, onClose, legend }) {
  if (!evidence) return null;
  if (evidence.record_type === "claim") {
    return <ClaimDetail claim={evidence} allEvidence={allEvidence} relations={relations} onSelect={onSelect} onClose={onClose} />;
  }
  const levelLabels = { ...(legend || {}) };
  const rows = [
    ["证据层级", levelLabels[evidence.evidence_level] || EVIDENCE_LABELS[evidence.evidence_level] || evidence.evidence_level],
    ["资料类型", SOURCE_KIND_LABELS[evidence.source_kind] || evidence.source_kind],
    ["叙事位置", NARRATIVE_ROLE_LABELS[evidence.narrative_role] || evidence.narrative_role],
    ["来源", evidence.source_id],
    ["作者", evidence.authors?.join("、")],
    ["刊物／报告", evidence.publication_title],
    ["发表年份", evidence.publication_year],
    ["DOI", evidence.doi],
    ["审阅状态", evidence.review_status === "temporary" ? "临时入库 · 待人工转正" : evidence.review_status],
    ["方法", evidence.method],
    ["分析面板", evidence.panel],
    ["重叠 SNP", evidence.overlap_snp_count?.toLocaleString?.()],
    ["事件年代", evidencePeriod(evidence)],
    ["地点", [evidence.site, evidence.political_entity].filter(Boolean).join(" · ")],
    ["个体 ID", evidence.individual_id || evidence.genetic_id],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "");

  return (
    <aside className="evidence-drawer">
      <button className="icon-button" onClick={onClose} aria-label="关闭证据详情">×</button>
      <div className="eyebrow">EVIDENCE LEAF</div>
      <h2>{evidenceName(evidence)}</h2>
      <dl>
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{String(value)}</dd>
          </div>
        ))}
        {evidence.source_url && (
          <div>
            <dt>来源地址</dt>
            <dd><a href={evidence.source_url} target="_blank" rel="noreferrer">打开原始来源</a></dd>
          </div>
        )}
      </dl>
      {evidence.quote && <blockquote>“{evidence.quote}”</blockquote>}
      {evidence.reported_text && <blockquote>{evidence.reported_text}</blockquote>}
      {evidence.summary && <p>{evidence.summary}</p>}
      {evidence.scope_note && <p>{evidence.scope_note}</p>}
      <details>
        <summary>查看原始字段</summary>
        <pre>{JSON.stringify(evidence, null, 2)}</pre>
      </details>
    </aside>
  );
}

export default function App() {
  const [draft, setDraft] = useState("");
  const [question, setQuestion] = useState("");
  const [status, setStatus] = useState("idle");
  const [events, setEvents] = useState([]);
  const [history, setHistory] = useState([]);
  const [investigationId, setInvestigationId] = useState(null);
  const [selectedEvidence, setSelectedEvidence] = useState(null);
  const [theme, setTheme] = useState(readStoredTheme);
  const [view, setView] = useState("network");
  const sourceRef = useRef(null);
  const lastSequenceRef = useRef(0);

  const skin = THEMES[theme];
  const copy = skin.copy;

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("lc-theme", theme);
  }, [theme]);

  const evidence = useMemo(
    () => events
      .filter((event) => event.type === "evidence.added" && event.data.evidence.record_type !== "evidence_gap")
      .map((event) => ({ sequence: event.sequence, bornAt: event.receivedAt, data: event.data.evidence })),
    [events],
  );

  const gaps = useMemo(
    () => events.filter(
      (event) => event.type === "evidence.added" && event.data.evidence.record_type === "evidence_gap",
    ),
    [events],
  );

  const claims = useMemo(() => {
    const byId = new Map();
    const order = [];
    for (const event of events) {
      if (event.type === "claim.added") {
        const node = { sequence: event.sequence, bornAt: event.receivedAt, data: event.data.claim };
        byId.set(node.data.claim_id, node);
        order.push(node.data.claim_id);
      } else if (event.type === "claim.updated") {
        const existing = byId.get(event.data.claim.claim_id);
        if (existing) existing.data = { ...existing.data, ...event.data.claim };
      }
    }
    return order.map((id) => byId.get(id));
  }, [events]);

  const relations = useMemo(
    () => events
      .filter((event) => event.type === "relation.added")
      .map((event) => event.data.relation),
    [events],
  );

  const lines = useMemo(() => {
    for (let index = events.length - 1; index >= 0; index -= 1) {
      if (events[index].type === "plan.updated") return events[index].data.lines || [];
    }
    return [];
  }, [events]);

  const log = useMemo(() => buildInvestigationLog(events), [events]);
  const storyline = useMemo(() => buildStoryline(evidence, claims), [evidence, claims]);
  const thinking = status === "running" && !events.some((event) =>
    ["tool.called", "claim.added", "narration", "investigation.completed", "investigation.failed", "investigation.stopped"].includes(event.type),
  );

  async function refreshHistory() {
    try {
      const response = await fetch("/api/investigations");
      if (response.ok) setHistory(await response.json());
    } catch {
      // 页面仍可使用当前会话；下次轮询会再次读取。
    }
  }

  useEffect(() => {
    refreshHistory();
    const timer = window.setInterval(refreshHistory, 3000);
    return () => {
      window.clearInterval(timer);
      sourceRef.current?.close();
    };
  }, []);

  function connectStream(id, { after = 0, reset = false } = {}) {
    sourceRef.current?.close();
    if (reset) {
      setEvents([]);
      setSelectedEvidence(null);
      lastSequenceRef.current = 0;
    }
    setStatus("connecting");
    const suffix = after > 0 ? `?after=${after}` : "";
    const source = new EventSource(`/api/investigations/${id}/events${suffix}`);
    sourceRef.current = source;
    source.onopen = () => setStatus("running");
    EVENT_TYPES.forEach((type) => {
      source.addEventListener(type, (message) => {
        const parsed = JSON.parse(message.data);
        lastSequenceRef.current = Math.max(lastSequenceRef.current, parsed.sequence);
        setEvents((current) => [...current, { ...parsed, receivedAt: performance.now() }]);
        if (type === "investigation.started") setQuestion(parsed.data.question);
        if (type === "investigation.completed") {
          setStatus("completed");
          source.close();
          refreshHistory();
        }
        if (type === "investigation.stopped") {
          setStatus("stopped");
          source.close();
          refreshHistory();
        }
        if (type === "investigation.failed") {
          setStatus("failed");
          source.close();
          refreshHistory();
        }
      });
    });
    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) return;
      setStatus("failed");
      source.close();
    };
  }

  async function createSession(nextQuestion) {
    sourceRef.current?.close();
    setQuestion(nextQuestion);
    setEvents([]);
    setSelectedEvidence(null);
    lastSequenceRef.current = 0;
    setStatus("connecting");
    const response = await fetch("/api/investigations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: nextQuestion }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const created = await response.json();
    setInvestigationId(created.investigation_id);
    setDraft("");
    await refreshHistory();
    connectStream(created.investigation_id);
  }

  async function stopCurrent() {
    if (!investigationId || status !== "running") return;
    const response = await fetch(`/api/investigations/${investigationId}/stop`, { method: "POST" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    setDraft("");
  }

  async function startNewInvestigation(event) {
    event?.preventDefault();
    const nextQuestion = draft.trim();
    if (!nextQuestion || status === "connecting") return;
    try {
      if (STOP_COMMANDS.has(nextQuestion.toLocaleLowerCase())) {
        await stopCurrent();
        return;
      }
      await createSession(nextQuestion);
    } catch (error) {
      setStatus("failed");
      setEvents([{ type: "investigation.failed", sequence: 0, data: { message: error.message } }]);
    }
  }

  async function continueInvestigation() {
    const direction = draft.trim();
    if (!direction || !investigationId || status === "connecting") return;
    try {
      if (STOP_COMMANDS.has(direction.toLocaleLowerCase())) {
        await stopCurrent();
        return;
      }
      const terminal = ["completed", "stopped", "failed"].includes(status);
      if (terminal) setStatus("connecting");
      const response = await fetch(`/api/investigations/${investigationId}/redirect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ direction }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setDraft("");
      if (terminal) connectStream(investigationId, { after: lastSequenceRef.current });
      refreshHistory();
    } catch (error) {
      setStatus("failed");
      setEvents((current) => [...current, { type: "investigation.failed", sequence: 0, data: { message: error.message } }]);
    }
  }

  function selectHistory(item) {
    setInvestigationId(item.investigation_id);
    setQuestion(item.question);
    connectStream(item.investigation_id, { reset: true });
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        {/* 品牌 logo 位：正式 logo 图（矩形，约 176×48）产出后放这里 */}
        <div className="logo-slot" aria-hidden="true" />
        <div className="topbar-right">
          {/* 临时皮肤切换，路演期用，后续会换成正式的入口 */}
          <div className="theme-switch" role="group" aria-label="切换皮肤">
            {Object.values(THEMES).map((item) => (
              <button
                key={item.id}
                type="button"
                className={item.id === theme ? "active" : ""}
                onClick={() => setTheme(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className={`status-chip status-${status}`}>
            <span />{STATUS_LABELS[status]}
          </div>
        </div>
      </header>

      <section className="workspace">
        <div className="tree-stage">
          <div className="stage-caption">
            <span>{theme === "analyst" && view === "network" ? copy.networkCaption : copy.captionLeft}</span>
            <strong>{claims.length} 个判断 · {evidence.length} 片证据叶 · {gaps.length} 条暗枝</strong>
          </div>
          {theme === "analyst" && (
            <div className="view-switch" role="group" aria-label="切换视图">
              <button type="button" className={view === "network" ? "active" : ""} onClick={() => setView("network")}>情报网</button>
              <button type="button" className={view === "timeline" ? "active" : ""} onClick={() => setView("timeline")}>时间轴</button>
            </div>
          )}
          {theme === "analyst" && view === "network" ? (
            <NetworkCanvas question={question} evidence={evidence} gaps={gaps} claims={claims} relations={relations} palette={skin.canvas} onSelect={setSelectedEvidence} />
          ) : (
            <TreeCanvas question={question} evidence={evidence} gaps={gaps} claims={claims} relations={relations} palette={skin.canvas} onSelect={setSelectedEvidence} />
          )}
          {theme === "analyst" && view === "network" && (
            <div className="stage-hint">滚轮缩放 · 拖拽平移 · 点击节点查看证据</div>
          )}
          <div className="legend">
            <span><i className="legend-genomic" />{copy.legend.fact_genomic}</span>
            <span><i className="legend-archaeology" />{copy.legend.fact_archaeology}</span>
            <span><i className="legend-model" />{copy.legend.view_model}</span>
            <span><i className="legend-gap" />{copy.legend.gap}</span>
          </div>
        </div>

        <aside className="agent-panel">
          <div className="panel-header">
            <div className="eyebrow">{copy.eyebrow}</div>
            <h2>{copy.panelTitle}</h2>
          </div>
          <div className="history-list">
            {history.length === 0 && <p>{copy.emptyHistory}</p>}
            {history.map((item, index) => (
              <button
                type="button"
                key={item.investigation_id}
                className={item.investigation_id === investigationId ? "active" : ""}
                onClick={() => selectHistory(item)}
              >
                <span>{String(history.length - index).padStart(2, "0")}</span>
                <strong>{item.question}</strong>
                <small>{STATUS_LABELS[item.status] || item.status}</small>
              </button>
            ))}
          </div>
          <div className="stream-heading">{copy.streamHeading}</div>
          {lines.length > 0 && (
            <div className="plan-lines">
              {lines.map((line) => (
                <span key={line.line} className={`plan-line plan-line-${line.status}`}>
                  {line.line}
                  {line.status === "covered" && " ✓"}
                  {line.status === "gap" && " ◌"}
                </span>
              ))}
            </div>
          )}
          {thinking && <p className="thinking-pulse">{copy.thinking}</p>}
          <div className="storyline" aria-live="polite">
            {storyline.length === 0 && <p className="storyline-empty">{copy.emptyStory}</p>}
            {storyline.map((beat, index) => (
              <button type="button" key={beat.key} className={beat.isClaim ? "story-beat story-claim" : "story-beat"} onClick={() => setSelectedEvidence(beat.evidence)}>
                <span className="story-index">{String(index + 1).padStart(2, "0")}</span>
                <span className="story-copy">
                  <small>{beat.timeLabel} · {beat.role}{beat.isClaim ? ` · ${CLAIM_STATUS_LABELS[beat.status] || beat.status}` : (beat.sourceTimeLabel && ` · ${beat.sourceTimeLabel}`)}</small>
                  <strong>{beat.claim}</strong>
                  {beat.relation && <em>{beat.relation}</em>}
                </span>
              </button>
            ))}
          </div>
          <details className="investigation-trace">
            <summary>查看调查过程 · {log.length} 步</summary>
            <div className="log-stream">
              {log.length === 0 && <div className="empty-log"><p>{thinking ? "顾问思考中……" : "尚无调查动作。"}</p></div>}
              {log.map((item) => (
                <article key={`${item.sequence}-${item.kind}`} className={`log-card log-${item.kind}`}>
                  <div className="log-card-title">
                    <span>{String(item.sequence).padStart(2, "0")}</span>
                    <strong>{item.title}</strong>
                  </div>
                  {item.motivation && <p className="log-motivation">{item.motivation}</p>}
                  {item.detail && <p>{item.detail}</p>}
                  {item.kind === "tool" && <p className={`log-result result-${item.result?.status || "pending"}`}>{resultSummary(item.result)}</p>}
                  {item.resultText && <p className="log-result result-pending">{item.resultText}</p>}
                </article>
              ))}
            </div>
          </details>
          <form className="question-form" onSubmit={startNewInvestigation}>
            <label htmlFor="question">{copy.inputLabel}</label>
            <input
              id="question"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={copy.placeholder}
              autoComplete="off"
            />
            <div className="form-actions">
              <button type="submit" disabled={!draft.trim() || status === "connecting"}>开始新调查</button>
              <button type="button" onClick={continueInvestigation} disabled={!draft.trim() || !investigationId || status === "connecting"}>沿本次继续</button>
              {status === "running" && <button type="button" className="stop-button" onClick={stopCurrent}>停止</button>}
            </div>
          </form>
        </aside>
      </section>
      <EvidenceDetail
        evidence={selectedEvidence}
        allEvidence={evidence}
        relations={relations}
        legend={copy.legend}
        onSelect={setSelectedEvidence}
        onClose={() => setSelectedEvidence(null)}
      />
    </main>
  );
}
