import { useEffect, useRef } from "react";

import { THEMES } from "./themes.js";

const ATTACH_PREDICATES = new Set(["supports", "derived_from"]);

// 明暗线：claim 芽的状态即明暗
const CLAIM_STATUS_STYLE = {
  open: { alpha: 0.55, glow: 8, tint: null },
  strengthened: { alpha: 1.0, glow: 18, tint: null },
  challenged: { alpha: 0.9, glow: 16, tint: "rgba(224, 110, 96, 0.85)" },
  dropped: { alpha: 0.22, glow: 0, tint: null },
};

function hash(text) {
  let value = 2166136261;
  for (const char of text) {
    value ^= char.charCodeAt(0);
    value = Math.imul(value, 16777619);
  }
  return value >>> 0;
}

export function labelFor(evidence) {
  return (
    evidence.claim ||
    evidence.individual_id ||
    evidence.genetic_id ||
    evidence.site ||
    evidence.title ||
    evidence.abbreviation ||
    evidence.topic ||
    evidence.record_type ||
    "证据"
  );
}

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function historicalYearFor(evidence) {
  // 按事件的开始时间定位（220年的事站在220年），不做首尾中点平均；
  // 超出常识范围的年份视为不可信，落入"年代待定"。
  const currentYear = new Date().getFullYear();
  const sane = (value) => {
    const year = finiteNumber(value);
    return year !== null && year <= currentYear + 10 && year >= -200000 ? year : null;
  };
  const start = sane(evidence.event_year_start);
  const end = sane(evidence.event_year_end);
  if (start !== null) return start;
  if (end !== null) return end;
  const meanBP = finiteNumber(evidence.mean_bp);
  return meanBP !== null && meanBP > 0 ? 1950 - meanBP : null;
}

export function formatHistoricalYear(year) {
  if (!Number.isFinite(year)) return "年代待定";
  const rounded = Math.round(year);
  return rounded > 0 ? `公元${rounded}年` : `公元前${Math.abs(rounded)}年`;
}

function roundedRect(context, x, y, width, height, radius) {
  context.beginPath();
  context.roundRect(x, y, width, height, radius);
}

export function targetMatchesLabel(target, label) {
  if (!target || !label) return false;
  return target === label || label.includes(target) || target.includes(label);
}

export default function TreeCanvas({ question, evidence, gaps, claims = [], relations = [], palette = THEMES.humanities.canvas, onSelect }) {
  const canvasRef = useRef(null);
  const hitAreasRef = useRef([]);

  useEffect(() => {
    const P = palette;
    const canvas = canvasRef.current;
    const context = canvas.getContext("2d");
    let frame = 0;
    let stopped = false;
    let width = 0;
    let height = 0;

    function resize() {
      const rect = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      width = rect.width;
      height = rect.height;
      canvas.width = Math.max(1, Math.floor(width * ratio));
      canvas.height = Math.max(1, Math.floor(height * ratio));
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
    }

    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();

    function draw(now) {
      if (stopped) return;
      context.clearRect(0, 0, width, height);
      const root = { x: width * 0.5, y: height - 68 };
      const currentYear = new Date().getFullYear();
      // 年代待定的材料进入顶部"待定区"，与时间轴物理隔离——
      // 绝不放在时间轴顶端，否则会被误读为最古老年代的事。
      const undatedTotal = evidence.filter((node) => historicalYearFor(node.data) === null).length
        + claims.filter((node) => historicalYearFor(node.data) === null).length;
      const bandHeight = undatedTotal ? 96 : 0;
      const top = 54 + bandHeight;
      const datedItems = [
        ...evidence.map((node) => historicalYearFor(node.data)),
        ...claims.map((node) => historicalYearFor(node.data)),
      ].filter((year) => year !== null);
      const oldestYear = datedItems.length ? Math.min(...datedItems) : null;
      const timelineSpan = oldestYear === null
        ? 2000
        : Math.max(100, currentYear - oldestYear) * 1.05;
      const axisStartYear = currentYear - timelineSpan;

      // 星空（人文皮肤）：确定性星位 + 缓慢闪烁
      if (P.stars) {
        for (let i = 0; i < 120; i += 1) {
          const sx = ((hash(`star-x-${i}`) % 1000) / 1000) * width;
          const sy = ((hash(`star-y-${i}`) % 1000) / 1000) * height;
          const twinkle = 0.25 + 0.75 * Math.abs(Math.sin(now / 1200 + i * 1.7));
          const radius = 0.4 + ((hash(`star-r-${i}`) % 10) / 10) * 1.1;
          context.fillStyle = `rgba(232, 226, 250, ${0.1 + twinkle * 0.42})`;
          context.beginPath();
          context.arc(sx, sy, radius, 0, Math.PI * 2);
          context.fill();
        }
      }

      const glow = context.createRadialGradient(root.x, root.y, 0, root.x, root.y, width * 0.55);
      glow.addColorStop(0, P.bgGlow0);
      glow.addColorStop(0.45, P.bgGlow1);
      glow.addColorStop(1, "rgba(0, 0, 0, 0)");
      context.fillStyle = glow;
      context.fillRect(0, 0, width, height);

      context.strokeStyle = P.axis;
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(38, top);
      context.lineTo(38, root.y);
      context.stroke();
      context.font = P.font;
      context.textAlign = "left";
      context.fillStyle = P.axisText;
      [1, 0.66, 0.33, 0].forEach((position) => {
        const y = top + (root.y - top) * position;
        context.beginPath();
        context.moveTo(34, y);
        context.lineTo(42, y);
        context.stroke();
        context.fillText(
          position === 1
            ? "今天"
            : formatHistoricalYear(axisStartYear + timelineSpan * position),
          48,
          y + 4,
        );
      });

      if (bandHeight) {
        context.save();
        context.setLineDash([4, 6]);
        context.strokeStyle = P.axis;
        context.beginPath();
        context.moveTo(30, top - 16);
        context.lineTo(width - 30, top - 16);
        context.stroke();
        context.restore();
        context.font = P.font;
        context.textAlign = "left";
        context.fillStyle = P.undatedText;
        context.fillText(`年代待定 × ${undatedTotal} · 不计入时间轴`, 48, 40);
      }

      context.strokeStyle = P.trunk;
      context.lineWidth = 2.2;
      context.beginPath();
      context.moveTo(root.x, root.y);
      context.bezierCurveTo(root.x - 7, height * 0.72, root.x + 5, height * 0.48, root.x, top + 18);
      context.stroke();

      context.save();
      if (P.glow) {
        context.shadowBlur = 22;
        context.shadowColor = P.rootGlow;
      }
      context.fillStyle = P.root;
      context.beginPath();
      context.arc(root.x, root.y, 5.5, 0, Math.PI * 2);
      context.fill();
      context.restore();

      context.font = P.font;
      context.textAlign = "center";
      context.fillStyle = P.rootLabel;
      context.fillText(question || "等待一个问题", root.x, root.y + 28);

      hitAreasRef.current = [];

      // —— 标签防碰撞器：节点位置忠实于时间，标签沿纵向找空位；放不下就放弃该标签 ——
      const placedBoxes = [];
      const overlaps = (a, b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
      const placeBox = (x, y, w, h) => {
        const box = { x, y, w, h };
        for (let attempt = 0; attempt < 40; attempt += 1) {
          if (!placedBoxes.some((b) => overlaps(box, b))) {
            placedBoxes.push(box);
            return box;
          }
          box.y += 9;
          if (box.y + h > root.y - 14) return null;
        }
        return null;
      };
      const drawLeader = (fromX, fromY, box, side, stroke) => {
        context.strokeStyle = stroke;
        context.lineWidth = 1;
        context.beginPath();
        context.moveTo(fromX, fromY);
        context.lineTo(side > 0 ? box.x : box.x + box.w, box.y + box.h / 2);
        context.stroke();
      };

      // —— claim 芽：调查的骨架节点 ——
      const claimPositions = new Map();
      let undatedClaimCount = 0;
      claims.forEach((node) => {
        const item = node.data;
        const nodeHash = hash(`${item.claim_id}:${item.text}`);
        const side = nodeHash % 2 === 0 ? -1 : 1;
        const spread = Math.min(width * 0.3, 150 + (nodeHash % 100));
        const historicalYear = historicalYearFor(item);
        const timeRatio = historicalYear === null
          ? null
          : Math.min(Math.max((currentYear - historicalYear) / timelineSpan, 0.05), 0.92);
        let target;
        if (timeRatio !== null) {
          target = { x: root.x + side * spread, y: root.y - timeRatio * (root.y - top) };
        } else {
          const slot = undatedClaimCount;
          undatedClaimCount += 1;
          target = { x: 96 + (slot * 280) % Math.max(280, width - 192), y: 64 + (slot % 2) * 32 };
        }
        const age = Math.max(0, now - node.bornAt);
        const progress = Math.min(1, age / 820);
        const eased = 1 - Math.pow(1 - progress, 3);
        const bud = {
          x: root.x + (target.x - root.x) * eased,
          y: root.y + (target.y - root.y) * eased,
          progress,
          side,
        };
        claimPositions.set(item.claim_id, bud);

        // 树干到芽的枝条（待定区内的芽不连树干，避免"从根长到1921年"的错觉）
        if (timeRatio !== null) {
          context.strokeStyle = `rgba(${P.claimBranch}, ${0.2 + eased * 0.4})`;
          context.lineWidth = 1.8;
          context.beginPath();
          context.moveTo(root.x, Math.min(root.y, bud.y + 60));
          context.bezierCurveTo(
            root.x + side * spread * 0.15,
            bud.y + 34,
            bud.x - side * 30,
            bud.y + 14,
            bud.x,
            bud.y,
          );
          context.stroke();
        }

        // 芽本体（明暗=状态）
        const color = P.colors[item.evidence_level] || P.colors.unknown;
        const statusStyle = CLAIM_STATUS_STYLE[item.status] || CLAIM_STATUS_STYLE.open;
        context.save();
        context.globalAlpha = statusStyle.alpha;
        context.shadowBlur = P.glow ? statusStyle.glow * eased : 0;
        context.shadowColor = statusStyle.tint || color;
        context.fillStyle = color;
        context.beginPath();
        context.arc(bud.x, bud.y, 6.5 * eased, 0, Math.PI * 2);
        context.fill();
        context.restore();

        if (progress > 0.6) {
          const label = String(item.text || "").slice(0, 26);
          context.font = P.font;
          const labelWidth = Math.min(270, context.measureText(label).width + 22);
          const wantX = side > 0 ? bud.x + 16 : bud.x - 16 - labelWidth;
          const box = placeBox(wantX, bud.y - 17, labelWidth, 34);
          if (box) {
            drawLeader(bud.x, bud.y, box, side, P.claimBoxStroke);
            roundedRect(context, box.x, box.y, box.w, box.h, 9);
            context.fillStyle = P.claimBoxBg;
            context.fill();
            context.strokeStyle = P.claimBoxStroke;
            context.stroke();
            context.fillStyle = P.claimText;
            context.textAlign = "left";
            context.fillText(label, box.x + 11, box.y + 22);
            hitAreasRef.current.push({
              x: box.x, y: box.y, width: box.w, height: box.h,
              node: { data: { record_type: "claim", ...item } },
            });
          }
        }
      });

      // —— relation 枝条：claim 之间的分叉与汇合 ——
      relations.forEach((relation) => {
        const subject = claimPositions.get(relation.subject_id);
        const object = claimPositions.get(relation.object_id);
        if (!subject || !object || subject === object) return;
        if (subject.progress < 0.9 || object.progress < 0.9) return;
        const style = P.relations[relation.predicate] || P.relations.part_of;
        context.save();
        context.setLineDash(style.dash);
        context.strokeStyle = style.stroke;
        context.lineWidth = 1.4;
        context.beginPath();
        context.moveTo(subject.x, subject.y);
        const midX = (subject.x + object.x) / 2;
        const lift = Math.min(60, Math.abs(subject.y - object.y) * 0.5 + 24);
        context.bezierCurveTo(midX, subject.y - lift, midX, object.y - lift, object.x, object.y);
        context.stroke();
        context.restore();
      });

      // —— 证据叶：优先挂到关联的 claim 芽上 ——
      const leafAnchor = new Map();
      evidence.forEach((node) => {
        const label = String(labelFor(node.data));
        const attachment = relations.find(
          (relation) =>
            ATTACH_PREDICATES.has(relation.predicate) &&
            claimPositions.has(relation.subject_id) &&
            targetMatchesLabel(relation.object_id, label),
        );
        if (attachment) leafAnchor.set(node.sequence, claimPositions.get(attachment.subject_id));
      });

      // 标签预算：挂靠 claim 的关键叶子优先显示标签，其余只画点（可点击），
      // 避免上百片叶子的标签互相踩踏成一锅粥。
      const LABEL_BUDGET = 18;
      const labeledSequences = new Set(
        [...evidence]
          .sort((a, b) => (
            (leafAnchor.has(b.sequence) ? 1 : 0) - (leafAnchor.has(a.sequence) ? 1 : 0)
            || a.sequence - b.sequence
          ))
          .slice(0, LABEL_BUDGET)
          .map((node) => node.sequence),
      );
      const crowdAlpha = evidence.length > 40 ? 0.5 : 1;
      const dotScale = evidence.length > 40 ? 0.65 : 1;

      // 待定区网格参数
      const undatedLeafTotal = evidence.filter(
        (node) => !leafAnchor.has(node.sequence) && historicalYearFor(node.data) === null,
      ).length;
      const undatedColumns = Math.max(6, Math.floor((width - 140) / 26));
      const undatedRows = Math.max(1, Math.ceil(undatedLeafTotal / undatedColumns));
      const undatedYStep = undatedRows > 1 ? Math.min(30, 62 / (undatedRows - 1)) : 0;
      let undatedLeafCount = 0;

      evidence.forEach((node) => {
        const item = node.data;
        const label = String(labelFor(item));
        const nodeHash = hash(`${node.sequence}:${label}`);
        const side = nodeHash % 2 === 0 ? -1 : 1;
        const spread = Math.min(width * 0.32, 128 + (nodeHash % 95));
        const historicalYear = historicalYearFor(item);
        const timeRatio = historicalYear === null
          ? null
          : Math.min(Math.max((currentYear - historicalYear) / timelineSpan, 0.02), 0.96);

        const anchorBud = leafAnchor.get(node.sequence) || null;

        let target;
        if (anchorBud) {
          target = { x: anchorBud.x + side * 46, y: anchorBud.y - 20 - (nodeHash % 36) };
        } else if (timeRatio !== null) {
          target = { x: root.x + side * spread, y: root.y - timeRatio * (root.y - top) };
        } else {
          // 年代待定：进顶部待定区网格，不与根连线
          const slot = undatedLeafCount;
          undatedLeafCount += 1;
          target = {
            x: 70 + (slot % undatedColumns) * ((width - 140) / undatedColumns),
            y: 64 + Math.floor(slot / undatedColumns) * undatedYStep,
          };
        }

        const age = Math.max(0, now - node.bornAt);
        const progress = Math.min(1, age / 820);
        const eased = 1 - Math.pow(1 - progress, 3);
        const origin = anchorBud || root;
        const leaf = {
          x: origin.x + (target.x - origin.x) * eased,
          y: origin.y + (target.y - origin.y) * eased,
        };

        // 待定区内的散叶不画枝条；密集调查时枝条自动变淡
        if (anchorBud || timeRatio !== null) {
          context.strokeStyle = anchorBud
            ? `rgba(${P.leafBranchAttached}, ${(0.25 + eased * 0.5) * crowdAlpha})`
            : `rgba(${P.leafBranch}, ${(0.18 + eased * 0.48) * crowdAlpha})`;
          context.lineWidth = 1.3;
          context.beginPath();
          context.moveTo(origin.x, origin.y);
          context.bezierCurveTo(
            origin.x + side * spread * 0.2,
            origin.y - 18,
            target.x - side * 34,
            target.y + 18,
            leaf.x,
            leaf.y,
          );
          context.stroke();
        }

        const color = P.colors[item.evidence_level] || P.colors.unknown;
        context.save();
        context.translate(leaf.x, leaf.y);
        context.rotate(side * -0.34);
        context.shadowBlur = P.glow ? 12 * eased : 0;
        context.shadowColor = color;
        context.fillStyle = color;
        context.beginPath();
        context.ellipse(0, 0, 10 * eased * dotScale, 5.3 * eased * dotScale, 0, 0, Math.PI * 2);
        context.fill();
        context.restore();

        let labeled = false;
        // 待定区散叶只画点；时间轴上的叶子才参与标签预算
        if (progress > 0.72 && labeledSequences.has(node.sequence) && (anchorBud || timeRatio !== null)) {
          const short = label.slice(0, 24);
          context.font = P.font;
          const labelWidth = Math.min(240, context.measureText(short).width + 20);
          const wantX = side > 0 ? leaf.x + 16 : leaf.x - 16 - labelWidth;
          const box = placeBox(wantX, leaf.y - 15, labelWidth, 30);
          if (box) {
            drawLeader(leaf.x, leaf.y, box, side, P.leafBoxStroke);
            roundedRect(context, box.x, box.y, box.w, box.h, 8);
            context.fillStyle = P.leafBoxBg;
            context.fill();
            context.strokeStyle = P.leafBoxStroke;
            context.stroke();
            context.fillStyle = P.leafText;
            context.textAlign = "left";
            context.fillText(short, box.x + 10, box.y + 20);
            hitAreasRef.current.push({ x: box.x, y: box.y, width: box.w, height: box.h, node });
            labeled = true;
          }
        }
        if (!labeled) {
          // 无标签的叶子保留一个小点击圈，仍可打开证据详情
          hitAreasRef.current.push({ x: leaf.x - 9, y: leaf.y - 9, width: 18, height: 18, node });
        }
      });

      gaps.forEach((gap, index) => {
        const side = index % 2 === 0 ? -1 : 1;
        const y = root.y - 100 - index * 44;
        const x = root.x + side * Math.min(width * 0.24, 150);
        context.save();
        context.setLineDash([5, 7]);
        context.strokeStyle = P.gapDash;
        context.beginPath();
        context.moveTo(root.x, y + 48);
        context.quadraticCurveTo(root.x + side * 70, y + 30, x, y);
        context.stroke();
        context.restore();
        context.fillStyle = P.gapDot;
        context.beginPath();
        context.arc(x, y, 3, 0, Math.PI * 2);
        context.fill();
      });

      frame = requestAnimationFrame(draw);
    }

    frame = requestAnimationFrame(draw);
    return () => {
      stopped = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [question, evidence, gaps, claims, relations, palette]);

  function handleClick(event) {
    const rect = canvasRef.current.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const hit = [...hitAreasRef.current]
      .reverse()
      .find((area) => x >= area.x && x <= area.x + area.width && y >= area.y && y <= area.y + area.height);
    if (hit) onSelect(hit.node.data);
  }

  return <canvas ref={canvasRef} className="tree-canvas" onClick={handleClick} />;
}
