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
  ]).slice(0, 8);

  return (
    <div className="life-tree-wrap">
      <svg className="life-tree" viewBox="0 0 520 620" role="img" aria-label="随时间展开的生命树">
        <defs>
          <linearGradient id="trunk-gradient" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0" stopColor="#805f38" />
            <stop offset="1" stopColor="#b78a4e" />
          </linearGradient>
        </defs>
        <path className="tree-trunk-shadow" d="M 248 592 C 253 500 250 403 260 310 C 267 405 275 497 273 592 Z" />
        <path className="tree-trunk" d="M 248 592 C 253 500 250 403 260 310 C 267 405 275 497 273 592 Z" />
        {branches.map((branch, branchIndex) => {
          const geometry = branchGeometry(branchIndex, branches.length);
          const branchEvents = events.filter((event) => event.branch === branch);
          const lineState = lines.find((line) => line.line === branch)?.status || "open";
          const branchPath = `M 260 350 C 260 ${geometry.y + 100}, ${geometry.x * 0.72 + 72} ${geometry.y + 38}, ${geometry.x} ${geometry.y}`;
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
                const progress = 0.42 + ((eventIndex + 1) / (branchEvents.length + 1)) * 0.53;
                const x = 260 + (geometry.x - 260) * progress;
                const y = 350 + (geometry.y - 350) * progress;
                if (!revealed) {
                  return <circle key={event.event_id} cx={x} cy={y} r="3.5" className="future-bud"><title>{event.title}</title></circle>;
                }
                const active = event.event_id === selectedId;
                const rotation = (geometry.angle * 180) / Math.PI + 90;
                return (
                  <g
                    key={event.event_id}
                    transform={`translate(${x} ${y}) rotate(${rotation})`}
                    className={active ? "story-leaf story-leaf-active" : `story-leaf story-leaf-${event.epistemic_status || "fact"}`}
                    role="button"
                    tabIndex="0"
                    onClick={() => onSelect(event.event_id)}
                    onKeyDown={(keyboardEvent) => keyboardEvent.key === "Enter" && onSelect(event.event_id)}
                  >
                    <path d="M 0 0 C -22 -19 -39 -12 -42 2 C -22 17 -7 14 0 0 C 22 19 39 12 42 -2 C 22 -17 7 -14 0 0 Z" />
                    <circle r={active ? 5 : 3} />
                    <title>{event.title}</title>
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
