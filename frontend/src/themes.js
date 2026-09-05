// 双皮肤定义：人文（暗色星梦 · 考古策展/数字人文）与分析（亮色精锐 · 尽职调查/情报分析）。
// copy 驱动界面文案，canvas 驱动 TreeCanvas 的调色板；CSS 侧由 styles.css 的
// :root[data-theme="..."] 变量负责。

export const THEMES = {
  humanities: {
    id: "humanities",
    label: "人文",
    copy: {
      eyebrow: "INVESTIGATION HISTORY",
      panelTitle: "调查记录",
      streamHeading: "故事脉络",
      inputLabel: "输入地名、古人或传说",
      placeholder: "例如：曹操",
      captionLeft: "向上 · 向过去",
      emptyHistory: "尚无调查记录",
      emptyStory: "证据到达后，事件会按历史时间组成脉络。",
      thinking: "顾问阅读问题中……首次响应可能需要十几秒，请稍候",
      networkCaption: "中心=问题 · 内环=判断 · 外环=证据",
      legend: {
        fact_genomic: "古基因组事实",
        fact_archaeology: "考古事实",
        view_model: "研究模型",
        gap: "证据空白",
      },
    },
    canvas: {
      stars: true,
      glow: true,
      font: '15px "Songti SC", "STSong", serif',
      bgGlow0: "rgba(126, 106, 224, 0.12)",
      bgGlow1: "rgba(34, 72, 92, 0.10)",
      axis: "rgba(178, 172, 214, 0.18)",
      axisText: "rgba(190, 186, 224, 0.55)",
      undatedText: "rgba(190, 186, 224, 0.42)",
      trunk: "rgba(216, 186, 110, 0.52)",
      rootGlow: "rgba(240, 210, 132, 0.85)",
      root: "#f2d282",
      rootLabel: "rgba(236, 227, 200, 0.75)",
      claimBranch: "216, 186, 110",
      claimBoxBg: "rgba(20, 22, 44, 0.92)",
      claimBoxStroke: "rgba(217, 183, 106, 0.38)",
      claimText: "rgba(242, 234, 210, 0.92)",
      leafBranchAttached: "216, 186, 110",
      leafBranch: "192, 160, 96",
      leafBoxBg: "rgba(15, 17, 36, 0.86)",
      leafBoxStroke: "rgba(188, 182, 228, 0.16)",
      leafText: "rgba(238, 233, 214, 0.85)",
      gapDash: "rgba(150, 156, 184, 0.26)",
      gapDot: "rgba(152, 158, 182, 0.38)",
      colors: {
        fact_genomic: "#e3c37b",
        fact_archaeology: "#e59a6e",
        view_model: "#93a2e4",
        unknown: "#9aa3b5",
      },
      relations: {
        supports: { stroke: "rgba(227, 195, 123, 0.75)", dash: [] },
        derived_from: { stroke: "rgba(227, 195, 123, 0.55)", dash: [] },
        contradicts: { stroke: "rgba(226, 116, 100, 0.8)", dash: [6, 6] },
        kin: { stroke: "rgba(147, 162, 228, 0.75)", dash: [] },
        same_site: { stroke: "rgba(147, 162, 228, 0.6)", dash: [3, 4] },
        contemporaneous: { stroke: "rgba(147, 162, 228, 0.6)", dash: [3, 4] },
        part_of: { stroke: "rgba(154, 163, 181, 0.65)", dash: [] },
      },
    },
  },
  analyst: {
    id: "analyst",
    label: "分析",
    copy: {
      eyebrow: "CASE DOCKET",
      panelTitle: "调查档案",
      streamHeading: "证据链 · 时间线",
      inputLabel: "输入靶点、药物或机构",
      placeholder: "例如：PD-L1",
      captionLeft: "向上 · 追溯时间线",
      emptyHistory: "尚无调查档案",
      emptyStory: "证据到达后，将按时间线自动编排。",
      thinking: "分析师阅读问题中……首次响应可能需要十几秒，请稍候",
      networkCaption: "中心=问题 · 内环=判断 · 外环=未归属证据",
      legend: {
        fact_genomic: "数据事实",
        fact_archaeology: "事件事实",
        view_model: "研究观点",
        gap: "证据空白",
      },
    },
    canvas: {
      stars: false,
      glow: false,
      font: '15px Inter, "PingFang SC", system-ui, sans-serif',
      bgGlow0: "rgba(29, 78, 216, 0.05)",
      bgGlow1: "rgba(15, 118, 110, 0.04)",
      axis: "rgba(27, 36, 50, 0.2)",
      axisText: "rgba(27, 36, 50, 0.55)",
      undatedText: "rgba(27, 36, 50, 0.42)",
      trunk: "rgba(15, 61, 145, 0.55)",
      rootGlow: "rgba(15, 61, 145, 0)",
      root: "#0f3d91",
      rootLabel: "rgba(27, 36, 50, 0.78)",
      claimBranch: "15, 61, 145",
      claimBoxBg: "rgba(255, 255, 255, 0.96)",
      claimBoxStroke: "rgba(15, 61, 145, 0.4)",
      claimText: "rgba(27, 36, 50, 0.94)",
      leafBranchAttached: "15, 61, 145",
      leafBranch: "100, 116, 139",
      leafBoxBg: "rgba(255, 255, 255, 0.92)",
      leafBoxStroke: "rgba(27, 36, 50, 0.16)",
      leafText: "rgba(27, 36, 50, 0.85)",
      gapDash: "rgba(100, 116, 139, 0.4)",
      gapDot: "rgba(100, 116, 139, 0.5)",
      colors: {
        fact_genomic: "#b7791f",
        fact_archaeology: "#c05621",
        view_model: "#2b6cb0",
        unknown: "#718096",
      },
      relations: {
        supports: { stroke: "rgba(15, 61, 145, 0.7)", dash: [] },
        derived_from: { stroke: "rgba(15, 61, 145, 0.45)", dash: [] },
        contradicts: { stroke: "rgba(192, 57, 43, 0.8)", dash: [6, 6] },
        kin: { stroke: "rgba(15, 118, 110, 0.7)", dash: [] },
        same_site: { stroke: "rgba(15, 118, 110, 0.5)", dash: [3, 4] },
        contemporaneous: { stroke: "rgba(15, 118, 110, 0.5)", dash: [3, 4] },
        part_of: { stroke: "rgba(113, 128, 150, 0.6)", dash: [] },
      },
    },
  },
};

export const DEFAULT_THEME = "humanities";

export function readStoredTheme() {
  if (typeof window === "undefined") return DEFAULT_THEME;
  // 无界面切换器：路演用 ?skin=analyst / ?skin=humanities 直接指定皮肤
  const param = new URLSearchParams(window.location.search).get("skin");
  if (param && THEMES[param]) return param;
  const stored = window.localStorage.getItem("lc-theme");
  return stored && THEMES[stored] ? stored : DEFAULT_THEME;
}
