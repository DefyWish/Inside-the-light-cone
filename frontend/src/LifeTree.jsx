import React from "react";

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function branchGeometry(index, total) {
  const angle = total <= 1 ? -Math.PI / 2 : (-Math.PI * 0.9) + (index / (total - 1)) * Math.PI * 0.8;
  return {
    angle,
    x: 260 + Math.cos(angle) * 205,
    y: 330 + Math.sin(angle) * 215,
  };
}

export default function LifeTree({ events, lines = [], cursorYear, selectedId, onSelect }) {
  const branches = unique([
    ...lines.map((line) => line.line),
    ...events.map((event) => event.branch),
  ]);
  const geometries = branches.map((_, index) => branchGeometry(index, branches.length));

  return (
    <div className="life-tree-wrap">
      <svg className="life-tree" viewBox="0 0 520 620" role="img" aria-label="随时间展开的生命树">
        <defs><filter id="tree-glow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="3" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter></defs>
        <path className="tree-spine tree-spine-ghost" d="M 260 600 C 252 520 269 458 258 390 C 250 342 268 302 260 262" />
        <path className="tree-spine" d="M 260 600 C 252 520 269 458 258 390 C 250 342 268 302 260 262" />
        {geometries.slice(1).map((geometry, index) => {
          const previous = geometries[index];
          return <path key={`network:${index}`} className="canopy-link" d={`M ${previous.x} ${previous.y} Q 260 ${Math.min(previous.y, geometry.y) - 22} ${geometry.x} ${geometry.y}`} />;
        })}
        {branches.map((branch, branchIndex) => {
          const geometry = geometries[branchIndex];
          const branchEvents = events.filter((event) => event.branch === branch);
          const lineState = lines.find((line) => line.line === branch)?.status || "open";
          const joinY = 455 - (branchIndex % 4) * 34;
          const branchPath = `M 260 ${joinY} C ${260 + (geometry.x - 260) * 0.16} ${joinY - 68}, ${260 + (geometry.x - 260) * 0.62} ${geometry.y + 42}, ${geometry.x} ${geometry.y}`;
          return (
            <g key={branch} className={`tree-branch tree-branch-${lineState}`}>
              <path d={branchPath} />
              <text
                x={geometry.x}
                y={geometry.y - 14}
                textAnchor={geometry.x < 260 ? "end" : "start"}
                className="branch-label"
              >
                {branch}
              </text>
              {branchEvents.map((event, eventIndex) => {
                const revealed = event.event_year_start == null || event.event_year_start <= cursorYear;
                const progress = 0.28 + ((eventIndex + 1) / (branchEvents.length + 1)) * 0.68;
                const baseX = 260 + (geometry.x - 260) * progress;
                const baseY = joinY + (geometry.y - joinY) * progress;
                const side = eventIndex % 2 === 0 ? 1 : -1;
                const leafX = baseX + Math.sin(geometry.angle) * 14 * side;
                const leafY = baseY - Math.cos(geometry.angle) * 14 * side;
                if (!revealed) {
                  return <circle key={event.event_id} cx={leafX} cy={leafY} r="2.4" className="future-bud"><title>{event.title}</title></circle>;
                }
                const active = event.event_id === selectedId;
                const rotation = (geometry.angle * 180) / Math.PI + (side > 0 ? 15 : 195);
                return (
                  <g key={event.event_id}>
                    <path className="leaf-stem" d={`M ${baseX} ${baseY} Q ${(baseX + leafX) / 2} ${(baseY + leafY) / 2 - 5} ${leafX} ${leafY}`} />
                    <g
                      transform={`translate(${leafX} ${leafY}) rotate(${rotation})`}
                      className={active ? "story-leaf story-leaf-active" : `story-leaf story-leaf-${event.epistemic_status || "fact"}`}
                      role="button"
                      tabIndex="0"
                      onClick={() => onSelect(event.event_id)}
                      onKeyDown={(keyboardEvent) => keyboardEvent.key === "Enter" && onSelect(event.event_id)}
                    >
                      <path d="M 0 0 C 5 -7 15 -10 23 -5 C 21 4 13 10 0 0 Z M 3 -1 L 19 -5" />
                      <title>{event.title}</title>
                    </g>
                  </g>
                );
              })}
            </g>
          );
        })}
        {branches.length === 0 && <text x="260" y="270" textAnchor="middle" className="tree-empty">等待 Agent 生长主题枝</text>}
      </svg>
    </div>
  );
}
