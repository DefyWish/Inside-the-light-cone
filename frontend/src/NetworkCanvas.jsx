import { useEffect, useRef } from "react";

import { THEMES } from "./themes.js";
import { labelFor, targetMatchesLabel } from "./TreeCanvas.jsx";

const ATTACH_PREDICATES = new Set(["supports", "derived_from"]);

// 与 TreeCanvas 一致：claim 芽的状态即明暗
const CLAIM_STATUS_STYLE = {
  open: { alpha: 0.6, tint: null },
  strengthened: { alpha: 1.0, tint: null },
  challenged: { alpha: 0.95, tint: "#e27464" },
  dropped: { alpha: 0.25, tint: null },
};

function hash(text) {
  let value = 2166136261;
  for (const char of text) {
    value ^= char.charCodeAt(0);
    value = Math.imul(value, 16777619);
  }
  return value >>> 0;
}

// 确定性环形布局（世界坐标，问题在原点）：
// 中心=问题；内环=claim 判断；每片证据围绕其挂靠的 claim 成簇；
// 无归属证据在外环均布；暗枝在中环虚线圈。
function computeLayout(evidence, gaps, claims, relations) {
  const positions = new Map();

  const claimList = claims.map((node) => node.data);
  const R_CLAIM = 250;
  claimList.forEach((item, index) => {
    const jitter = ((hash(`${item.claim_id}`) % 36) - 18) * (Math.PI / 180);
    const angle = -Math.PI / 2 + (index / Math.max(1, claimList.length)) * Math.PI * 2 + jitter;
    positions.set(`claim:${item.claim_id}`, {
      x: Math.cos(angle) * R_CLAIM,
      y: Math.sin(angle) * R_CLAIM,
      kind: "claim",
      item,
      node: { data: { record_type: "claim", ...item }, bornAt: claims[index].bornAt },
    });
  });

  const anchorOf = new Map();
  evidence.forEach((node) => {
    const label = String(labelFor(node.data));
    const relation = relations.find(
      (candidate) =>
        ATTACH_PREDICATES.has(candidate.predicate) &&
        positions.has(`claim:${candidate.subject_id}`) &&
        targetMatchesLabel(candidate.object_id, label),
    );
    if (relation) anchorOf.set(node.sequence, relation.subject_id);
  });

  const perClaimCount = new Map();
  const outer = evidence.filter((node) => !anchorOf.has(node.sequence));
  let outerIndex = 0;
  evidence.forEach((node) => {
    const claimId = anchorOf.get(node.sequence);
    if (claimId) {
      const index = perClaimCount.get(claimId) || 0;
      perClaimCount.set(claimId, index + 1);
      const anchor = positions.get(`claim:${claimId}`);
      const baseAngle = Math.atan2(anchor.y, anchor.x);
      const angle = baseAngle + (index - 0.5) * 0.55 + ((hash(`a${node.sequence}`) % 30) - 15) * (Math.PI / 180);
      const radius = 110 + (hash(`r${node.sequence}`) % 70);
      positions.set(`leaf:${node.sequence}`, {
        x: anchor.x + Math.cos(angle) * radius,
        y: anchor.y + Math.sin(angle) * radius,
        kind: "leaf",
        item: node.data,
        node,
        anchorKey: `claim:${claimId}`,
      });
    } else {
      const angle = -Math.PI / 2 + (outerIndex / Math.max(1, outer.length)) * Math.PI * 2;
      outerIndex += 1;
      const radius = 430 + (hash(`o${node.sequence}`) % 60);
      positions.set(`leaf:${node.sequence}`, {
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
        kind: "leaf",
        item: node.data,
        node,
        anchorKey: null,
      });
    }
  });

  gaps.forEach((gap, index) => {
    const angle = -Math.PI / 2 + ((index + 0.5) / Math.max(1, gaps.length)) * Math.PI * 2;
    positions.set(`gap:${index}`, {
      x: Math.cos(angle) * 340,
      y: Math.sin(angle) * 340,
      kind: "gap",
      item: gap.data?.evidence || gap.data || {},
      node: gap,
    });
  });

  return { positions, anchorOf };
}

export default function NetworkCanvas({ question, evidence, gaps, claims = [], relations = [], palette = THEMES.analyst.canvas, onSelect }) {
  const canvasRef = useRef(null);
  const hitAreasRef = useRef([]);
  const viewRef = useRef({ x: 0, y: 0, k: 1, ready: false });
  const dragRef = useRef(null);
  const suppressClickRef = useRef(false);

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
      if (!viewRef.current.ready && width > 0) {
        viewRef.current = {
          x: width / 2,
          y: height / 2,
          k: Math.min(1.1, Math.max(0.45, Math.min(width, height) / 1000)),
          ready: true,
        };
      }
    }

    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();

    function onWheel(event) {
      event.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mx = event.clientX - rect.left;
      const my = event.clientY - rect.top;
      const view = viewRef.current;
      const factor = Math.exp(-event.deltaY * 0.0012);
      const k = Math.min(3.2, Math.max(0.3, view.k * factor));
      // 以鼠标位置为锚点缩放
      view.x = mx - (mx - view.x) * (k / view.k);
      view.y = my - (my - view.y) * (k / view.k);
      view.k = k;
    }

    function onMouseDown(event) {
      dragRef.current = { x: event.clientX, y: event.clientY, moved: false };
      canvas.style.cursor = "grabbing";
    }
    function onMouseMove(event) {
      const drag = dragRef.current;
      if (!drag) return;
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
      viewRef.current.x += dx;
      viewRef.current.y += dy;
      drag.x = event.clientX;
      drag.y = event.clientY;
    }
    function onMouseUp() {
      if (dragRef.current?.moved) suppressClickRef.current = true;
      dragRef.current = null;
      canvas.style.cursor = "grab";
    }

    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("mousedown", onMouseDown);
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);

    function draw(now) {
      if (stopped) return;
      const ratio = window.devicePixelRatio || 1;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      const view = viewRef.current;

      const { positions } = computeLayout(evidence, gaps, claims, relations);

      context.save();
      context.translate(view.x, view.y);
      context.scale(view.k, view.k);

      // 雷达式同心环，给网络一个"坐标系"；环顶标注每一圈是什么
      context.strokeStyle = P.axis;
      context.lineWidth = 1 / view.k;
      [250, 340, 460].forEach((radius) => {
        context.beginPath();
        context.arc(0, 0, radius, 0, Math.PI * 2);
        context.stroke();
      });
      context.font = P.font.replace(/^\d+px/, "12px");
      context.textAlign = "left";
      context.fillStyle = P.undatedText;
      context.fillText("内环 · 判断", 8, -246);
      context.fillText("中环 · 证据空白", 8, -336);
      context.fillText("外环 · 未归属证据", 8, -456);

      // —— 边 ——
      positions.forEach((pos) => {
        if (pos.kind === "claim") {
          context.strokeStyle = `rgba(${P.claimBranch}, 0.5)`;
          context.lineWidth = 1.6;
          context.beginPath();
          context.moveTo(0, 0);
          context.lineTo(pos.x, pos.y);
          context.stroke();
        }
      });
      positions.forEach((pos) => {
        if (pos.kind !== "leaf") return;
        const anchor = pos.anchorKey ? positions.get(pos.anchorKey) : null;
        context.strokeStyle = anchor
          ? `rgba(${P.leafBranchAttached}, 0.45)`
          : `rgba(${P.leafBranch}, 0.16)`;
        context.lineWidth = 1;
        context.beginPath();
        if (anchor) {
          context.moveTo(anchor.x, anchor.y);
          context.lineTo(pos.x, pos.y);
        } else {
          context.moveTo(pos.x * 0.12, pos.y * 0.12);
          context.lineTo(pos.x, pos.y);
        }
        context.stroke();
      });
      relations.forEach((relation) => {
        const subject = positions.get(`claim:${relation.subject_id}`);
        const object = positions.get(`claim:${relation.object_id}`);
        if (!subject || !object) return;
        const style = P.relations[relation.predicate] || P.relations.part_of;
        context.save();
        context.setLineDash(style.dash);
        context.strokeStyle = style.stroke;
        context.lineWidth = 1.4;
        const midX = (subject.x + object.x) / 2;
        const midY = (subject.y + object.y) / 2;
        context.beginPath();
        context.moveTo(subject.x, subject.y);
        context.quadraticCurveTo(midX * 1.25, midY * 1.25, object.x, object.y);
        context.stroke();
        context.restore();
        if (view.k >= 1.1) {
          context.font = P.font;
          context.textAlign = "center";
          context.fillStyle = P.undatedText;
          context.fillText(relation.predicate, midX * 1.12, midY * 1.12 - 6);
        }
      });

      // —— 中心问题节点 ——
      context.save();
      if (P.glow) {
        context.shadowBlur = 24;
        context.shadowColor = P.rootGlow;
      }
      context.fillStyle = P.root;
      context.beginPath();
      context.arc(0, 0, 11, 0, Math.PI * 2);
      context.fill();
      context.restore();
      context.font = P.font;
      context.textAlign = "center";
      context.fillStyle = P.rootLabel;
      context.fillText(String(question || "等待一个问题").slice(0, 34), 0, 34);

      hitAreasRef.current = [];
      // 点击热区随缩放补偿：缩得再小也点得到
      const hitHalf = Math.max(10, 12 / view.k);

      // —— 节点 ——
      positions.forEach((pos, key) => {
        const bornAt = pos.node?.bornAt ?? 0;
        const progress = bornAt ? Math.min(1, Math.max(0, now - bornAt) / 700) : 1;
        const eased = 1 - Math.pow(1 - progress, 3);
        const color = P.colors[pos.item?.evidence_level] || P.colors.unknown;

        if (pos.kind === "claim") {
          const statusStyle = CLAIM_STATUS_STYLE[pos.item.status] || CLAIM_STATUS_STYLE.open;
          context.save();
          context.globalAlpha = statusStyle.alpha;
          if (P.glow) {
            context.shadowBlur = 16 * eased;
            context.shadowColor = statusStyle.tint || color;
          }
          context.fillStyle = statusStyle.tint || color;
          context.beginPath();
          context.arc(pos.x, pos.y, 9 * eased, 0, Math.PI * 2);
          context.fill();
          context.restore();

          // claim 始终带标签，沿径向朝外放
          const label = String(pos.item.text || "").slice(0, 24);
          context.font = P.font;
          const labelWidth = context.measureText(label).width + 18;
          const outward = pos.x >= 0 ? 1 : -1;
          const boxX = outward > 0 ? pos.x + 14 : pos.x - 14 - labelWidth;
          const boxY = pos.y - 14;
          context.beginPath();
          context.roundRect(boxX, boxY, labelWidth, 28, 7);
          context.fillStyle = P.claimBoxBg;
          context.fill();
          context.strokeStyle = P.claimBoxStroke;
          context.lineWidth = 1 / view.k;
          context.stroke();
          context.fillStyle = P.claimText;
          context.textAlign = "left";
          context.fillText(label, boxX + 9, boxY + 19);
          hitAreasRef.current.push({ x: boxX, y: boxY, w: labelWidth, h: 28, node: pos.node });
          hitAreasRef.current.push({ x: pos.x - hitHalf, y: pos.y - hitHalf, w: hitHalf * 2, h: hitHalf * 2, node: pos.node });
        } else if (pos.kind === "gap") {
          context.save();
          context.setLineDash([3, 4]);
          context.strokeStyle = P.gapDot;
          context.lineWidth = 1.2;
          context.beginPath();
          context.arc(pos.x, pos.y, 6, 0, Math.PI * 2);
          context.stroke();
          context.restore();
          hitAreasRef.current.push({ x: pos.x - hitHalf, y: pos.y - hitHalf, w: hitHalf * 2, h: hitHalf * 2, node: pos.node });
        } else {
          context.save();
          if (P.glow) {
            context.shadowBlur = 10 * eased;
            context.shadowColor = color;
          }
          context.fillStyle = color;
          context.beginPath();
          context.arc(pos.x, pos.y, 6 * eased, 0, Math.PI * 2);
          context.fill();
          context.restore();

          // 证据标签：放大到一定程度才显示，避免缩略全景时糊成一片
          if (view.k >= 1.25 && progress > 0.7) {
            const label = String(labelFor(pos.item)).slice(0, 22);
            context.font = P.font;
            const labelWidth = context.measureText(label).width + 14;
            const boxX = pos.x + 10;
            const boxY = pos.y - 11;
            context.beginPath();
            context.roundRect(boxX, boxY, labelWidth, 22, 6);
            context.fillStyle = P.leafBoxBg;
            context.fill();
            context.strokeStyle = P.leafBoxStroke;
            context.lineWidth = 1 / view.k;
            context.stroke();
            context.fillStyle = P.leafText;
            context.textAlign = "left";
            context.fillText(label, boxX + 7, boxY + 15);
          }
          hitAreasRef.current.push({ x: pos.x - hitHalf, y: pos.y - hitHalf, w: hitHalf * 2, h: hitHalf * 2, node: pos.node });
        }
        void key;
      });

      context.restore();
      frame = requestAnimationFrame(draw);
    }

    frame = requestAnimationFrame(draw);
    return () => {
      stopped = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("mousedown", onMouseDown);
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [question, evidence, gaps, claims, relations, palette]);

  function handleClick(event) {
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      return;
    }
    const rect = canvasRef.current.getBoundingClientRect();
    const view = viewRef.current;
    const wx = (event.clientX - rect.left - view.x) / view.k;
    const wy = (event.clientY - rect.top - view.y) / view.k;
    const hit = [...hitAreasRef.current]
      .reverse()
      .find((area) => wx >= area.x && wx <= area.x + area.w && wy >= area.y && wy <= area.y + area.h);
    if (hit) onSelect(hit.node.data);
  }

  return <canvas ref={canvasRef} className="tree-canvas network-canvas" onClick={handleClick} />;
}
