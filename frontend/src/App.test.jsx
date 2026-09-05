import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import App, { buildInvestigationLog, buildStoryline } from "./App.jsx";
import { formatHistoricalYear, historicalYearFor } from "./TreeCanvas.jsx";

describe("M4 application shell", () => {
  it("renders the investigation tree, evidence legend, log and input", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain("logo-slot");
    expect(html).toContain("古基因组事实");
    expect(html).toContain("证据空白");
    expect(html).toContain("调查记录");
    expect(html).toContain("开始新调查");
    expect(html).toContain("沿本次继续");
    expect(html).toContain("故事脉络");
    expect(html).toContain("查看调查过程");
    expect(html).not.toContain("启动本地保底重放");
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
});
