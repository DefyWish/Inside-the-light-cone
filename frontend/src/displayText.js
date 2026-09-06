const PLACE_NAMES = {
  zhongyuan: "中原",
  "central plains": "中原",
  meishan: "眉州",
  meizhou: "梅州",
  bianliang: "汴梁",
  kaifeng: "开封",
  fengxiang: "凤翔",
  hangzhou: "杭州",
  mizhou: "密州",
  xuzhou: "徐州",
  huzhou: "湖州",
  huangzhou: "黄州",
  dengzhou: "登州",
  yangzhou: "扬州",
  dingzhou: "定州",
  huizhou: "惠州",
  danzhou: "儋州",
  changzhou: "常州",
  tingzhou: "汀州",
  jiayingzhou: "嘉应州",
  ganzhou: "赣州",
  longyan: "龙岩",
  meixian: "梅县",
  fujian: "福建",
  guangdong: "广东",
  jiangxi: "江西",
  henan: "河南",
  sichuan: "四川",
  hainan: "海南",
  jiangsu: "江苏",
  zhejiang: "浙江",
  shandong: "山东",
  hubei: "湖北",
};

const FIELD_NAMES = {
  event: "事件",
  evidence: "证据",
  claim: "判断",
  fact: "史实",
  view: "观点",
  disputed: "争议",
  gap: "证据缺口",
  migration: "迁徙",
  movement: "迁徙",
  appointment: "任职",
  office: "任职",
  work: "作品",
  literature: "作品",
  thought: "思想",
  war: "战争",
  kinship: "亲缘",
  archaeology: "考古",
  documentary: "文献",
  influence: "影响",
  legacy: "后世影响",
  debate: "争议",
  context: "历史背景",
  research: "研究",
  other: "其他",
};

export function hasChinese(value) {
  return /[\u3400-\u9fff]/.test(String(value || ""));
}

export function preferChinese(...values) {
  const present = values.filter((value) => value != null && String(value).trim());
  return present.find(hasChinese) || present[0] || "";
}

export function localizePlace(value) {
  const raw = String(value || "").trim();
  if (!raw) return raw;
  const terminal = raw.split(/[／/→、;；|—]/).map((part) => part.trim()).filter(Boolean).at(-1) || raw;
  if (hasChinese(terminal)) return terminal;
  const place = terminal.split(/\s*,\s*/)[0].trim();
  return PLACE_NAMES[place.toLowerCase()] || "地点待考";
}

export function localizePreferredPlace(...values) {
  const present = values.filter((value) => value != null && String(value).trim());
  for (const value of present) {
    const localized = localizePlace(value);
    if (localized && localized !== "地点待考") return localized;
  }
  return present.length ? "地点待考" : "";
}

export function localizeField(value, fallback = "事件") {
  const raw = String(value || "").trim();
  if (!raw) return fallback;
  if (hasChinese(raw)) return raw;
  const normalized = raw.toLowerCase().replace(/[_-]+/g, " ").trim();
  return FIELD_NAMES[normalized] || FIELD_NAMES[normalized.split(/\s+/).at(-1)] || fallback;
}
