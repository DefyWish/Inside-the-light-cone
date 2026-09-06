import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import App, { apiErrorMessage, buildInvestigationLog, buildStoryline, InvestigationHistory, isVisualCurationCandidate, projectCurationEvents } from "./App.jsx";
import CurationMap, { buildMapLabels, hasPoint } from "./CurationMap.jsx";
import InvestigationReport from "./InvestigationReport.jsx";
import Timeline from "./Timeline.jsx";
import { formatHistoricalYear, historicalYearFor } from "./TreeCanvas.jsx";

describe("history curation application shell", () => {
  it("renders the map, life tree, history and investigation controls", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain("光锥之内");
    expect(html).toContain("brand-mark");
    expect(html).not.toContain("历史策展 Agent");
    expect(html).toContain("检索历史");
    expect(html).toContain("china-standard-outline.svg");
    expect(html).toContain("生命树");
    expect(html).toContain("新调查");
    expect(html).toContain("调查过程");
    expect(html).not.toContain("药物");
    expect(html).not.toContain("BD");
  });

  it("keeps early evidence leaves after formal curation events arrive", () => {
    const events = projectCurationEvents([
      { sequence: 1, type: "evidence.added", data: { evidence: { evidence_id: "e1", title: "早期证据一", event_year_start: 100 } } },
      { sequence: 2, type: "evidence.added", data: { evidence: { evidence_id: "e2", title: "早期证据二", event_year_start: 200 } } },
      { sequence: 3, type: "curation.event_added", data: { event: { event_id: "final-1", title: "收束节点", event_year_start: 300 } } },
    ]);

    expect(events.map((event) => event.event_id)).toEqual(["e1", "e2", "final-1"]);
  });

  it("uses one destination per point and draws a timed migration route", () => {
    const [event] = projectCurationEvents([
      { sequence: 1, type: "evidence.added", data: { evidence: {
        evidence_id: "move-1",
        title: "由湖州贬往黄州",
        event_year_start: 1079,
        historical_place: "湖州／黄州",
        modern_place: "浙江湖州／湖北黄冈",
        latitude: 30.453,
        longitude: 114.873,
        movement: {
          from: { name: "湖州", latitude: 30.894, longitude: 120.088 },
          to: { name: "黄州", latitude: 30.453, longitude: 114.873 },
        },
      } } },
    ]);
    const html = renderToStaticMarkup(<CurationMap events={[event]} cursorYear={1079} selectedId="move-1" onSelect={() => {}} />);

    expect(event.historical_place).toBe("黄州");
    expect(event.latitude).toBe(30.453);
    expect(html).toContain("route route-active");
    expect(html.match(/route-anchor/g)?.length).toBeGreaterThanOrEqual(2);
    expect(html).toContain(">黄州</text>");
    expect(html).not.toContain("湖州／黄州");
  });

  it("keeps labels for every reached map point while the timeline advances", () => {
    const events = [
      { event_id: "meishan", title: "出生", event_year_start: 1037, historical_place: "眉州", latitude: 30.05, longitude: 103.84 },
      { event_id: "huangzhou", title: "谪居", event_year_start: 1080, historical_place: "黄州", latitude: 30.45, longitude: 114.87 },
      { event_id: "huizhou", title: "再贬", event_year_start: 1094, historical_place: "惠州", latitude: 23.11, longitude: 114.42 },
    ];
    const html = renderToStaticMarkup(<CurationMap events={events} cursorYear={1080} selectedId="huangzhou" onSelect={() => {}} />);
    const labels = buildMapLabels(events.slice(0, 2), [], "huangzhou");

    expect(labels.map((label) => label.name)).toEqual(expect.arrayContaining(["眉州", "黄州"]));
    expect(html).toContain(">眉州</text>");
    expect(html).toContain(">黄州</text>");
    expect(html).not.toContain(">惠州</text>");
  });

  it("uses the coordinate-bound end of a compound place label", () => {
    const html = renderToStaticMarkup(<CurationMap events={[{
      event_id: "compound-place",
      title: "迁徙节点",
      event_year_start: 1200,
      historical_place: "Tingzhou, Fujian; Jiayingzhou, Guangdong",
      latitude: 24.3,
      longitude: 116.1,
    }]} cursorYear={1200} selectedId="compound-place" onSelect={() => {}} />);

    expect(html).toContain(">嘉应州</text>");
    expect(html).not.toContain("Jiayingzhou");
  });

  it("keeps deep-time background and negative evidence out of visual chronology", () => {
    const background = {
      claim: "华南古基因组提供深时区域背景而非直接证据，没有任何古个体被直接标识为客家人。",
      event_year_start: -9798,
    };
    expect(isVisualCurationCandidate(background)).toBe(false);
    expect(projectCurationEvents([
      { sequence: 1, type: "claim.added", data: { claim: { claim_id: "c4", ...background } } },
      { sequence: 2, type: "evidence.added", data: { evidence: { evidence_id: "context-1", curation_role: "context", title: "区域样本", event_year_start: -9000 } } },
      { sequence: 3, type: "evidence.added", data: { evidence: { evidence_id: "ancient-context", source_kind: "ancient_genome_dataset", title: "未策展古样本", event_year_start: -2600 } } },
      { sequence: 4, type: "evidence.added", data: { evidence: { evidence_id: "event-1", title: "1175年方言边界", event_year_start: 1175 } } },
    ]).map((event) => event.event_id)).toEqual(["event-1"]);
  });

  it("renders a draggable timeline control", () => {
    const html = renderToStaticMarkup(<Timeline events={[{ event_id: "e1", title: "节点", event_year_start: 100 }]} cursorYear={100} onChange={() => {}} onSelect={() => {}} />);
    expect(html).toContain('type="range"');
    expect(html).toContain('aria-label="拖动年代"');
  });

  it("renders professional and public report switches", () => {
    const report = { title: "客家调查报告", subtitle: "专业历史文博版", overview: "摘要", narrative: ["这是一篇完整的综合论述。"], sources: [] };
    const html = renderToStaticMarkup(<InvestigationReport report={report} audience="professional" loading={false} onAudienceChange={() => {}} />);
    expect(html).toContain("专业版");
    expect(html).toContain("科普版");
    expect(html).toContain("客家调查报告");
    expect(html).toContain("这是一篇完整的综合论述");
    expect(html).not.toContain("report-findings");
  });

  it("renders an independent delete control for every history entry", () => {
    const history = [{ investigation_id: "i1", question: "测试调查", status: "completed", event_count: 12 }];
    const html = renderToStaticMarkup(<InvestigationHistory history={history} activeId="i1" onOpen={() => {}} onDelete={() => {}} />);
    expect(html).toContain("删除 测试调查");
    expect(html).toContain("history-delete");
    expect(html).toContain("测试调查");
  });

  it("rejects missing coordinates instead of projecting them to zero", () => {
    expect(hasPoint({ latitude: null, longitude: null })).toBe(false);
    expect(hasPoint({ latitude: "", longitude: "" })).toBe(false);
    expect(hasPoint({ latitude: 30.453, longitude: 114.873 })).toBe(true);
  });

  it("keeps one live narration and only the final conclusion after completion", () => {
    const running = buildInvestigationLog([
      { sequence: 1, type: "narration", data: { text: "第一版" } },
      { sequence: 2, type: "narration", data: { text: "第二版" } },
    ]);
    expect(running).toEqual([
      { kind: "narration", sequence: 2, title: "阶段叙述", detail: "第二版" },
    ]);

    const completed = buildInvestigationLog([
      { sequence: 1, type: "narration", data: { text: "第一版" } },
      { sequence: 2, type: "narration", data: { text: "第二版" } },
      { sequence: 3, type: "investigation.completed", data: { summary: "最终结论" } },
    ]);
    expect(completed).toEqual([
      { kind: "completed", sequence: 3, title: "调查结论", detail: "最终结论" },
    ]);
  });

  it("sorts the storyline by historical year and shows complete historical ranges", () => {
    const storyline = buildStoryline([
      {
        data: {
          claim: "高陵得到考古确认",
          event_year_start: 2009,
          narrative_role: "legacy",
          relation_to_question: "解释现代证据链。",
        },
      },
      {
        data: {
          claim: "曹操去世",
          event_year_start: 220,
          narrative_role: "event",
          relation_to_question: "形成历史起点。",
        },
      },
      { data: { claim: "年代仍待确认", narrative_role: "gap" } },
    ]);

    expect(storyline.map((beat) => beat.claim)).toEqual([
      "曹操去世",
      "高陵得到考古确认",
      "年代仍待确认",
    ]);
    expect(storyline[0].timeLabel).toBe("公元220年");
    expect(storyline[1].timeLabel).toBe("公元2009年");
    expect(storyline[2].timeLabel).toBe("年代待定");
  });

  it("shows a historical range separately from the source publication year", () => {
    const [beat] = buildStoryline([
      {
        data: {
          claim: "曹操家族父系研究",
          event_year_start: 155,
          event_year_end: 220,
          publication_year: 2012,
        },
      },
    ]);

    expect(beat.timeLabel).toBe("公元155年—公元220年");
    expect(beat.sourceTimeLabel).toBe("证据发表于 2012 年");
  });

  it("maps scientific BP ages and explicit event years onto one calendar", () => {
    expect(historicalYearFor({ mean_bp: 1730 })).toBe(220);
    expect(historicalYearFor({ event_year_start: 2008, event_year_end: 2010 })).toBe(2008);
    expect(historicalYearFor({ date_text: "东汉晚期" })).toBeNull();
    expect(formatHistoricalYear(-221)).toBe("公元前221年");
  });

  it("shows structured query-filter messages", () => {
    expect(apiErrorMessage({ detail: { code: "out_of_scope", message: "请改问历史问题。" } }, 422)).toBe("请改问历史问题。");
  });
});
