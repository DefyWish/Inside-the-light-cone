import React from "react";

const WIDTH = 1600;
const HEIGHT = 1000;

export function projectChinaPoint(longitude, latitude) {
  const east = -3313821.05089796 + ((Number(longitude) - 72) / 68) * 6020641.180897959;
  const north = 1841646.983099264 + ((Number(latitude) - 18) / 36) * 4059657.334200998;
  return {
    x: ((east + 3413821.05089796) / 6220641.180897959) * WIDTH,
    y: ((6001304.317300262 - north) / 4259657.334200998) * HEIGHT,
  };
}

function hasPoint(value) {
  return Number.isFinite(Number(value?.longitude)) && Number.isFinite(Number(value?.latitude));
}

function movementPoint(value) {
  if (!value) return null;
  const longitude = value.longitude ?? value.lon;
  const latitude = value.latitude ?? value.lat;
  if (!Number.isFinite(Number(longitude)) || !Number.isFinite(Number(latitude))) return null;
  return projectChinaPoint(longitude, latitude);
}

export default function CurationMap({ events, cursorYear, selectedId, onSelect }) {
  const visible = events.filter((event) => (
    event.event_year_start == null || event.event_year_start <= cursorYear
  ));
  const points = visible.filter(hasPoint);

  return (
    <div className="map-wrap">
      <svg className="curation-map" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="历史事件地图">
        <defs>
          <marker id="route-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" />
          </marker>
          <filter id="point-glow" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="7" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <image href="/maps/china-standard-outline.svg" width={WIDTH} height={HEIGHT} preserveAspectRatio="xMidYMid meet" className="map-outline" />
        <g className="route-layer">
          {visible.map((event) => {
            const start = movementPoint(event.movement?.from);
            const end = movementPoint(event.movement?.to);
            if (!start || !end) return null;
            const bend = Math.max(18, Math.abs(end.x - start.x) * 0.12);
            const path = `M ${start.x} ${start.y} Q ${(start.x + end.x) / 2} ${Math.min(start.y, end.y) - bend} ${end.x} ${end.y}`;
            return (
              <path
                key={`route:${event.event_id}`}
                d={path}
                className={event.event_id === selectedId ? "route route-active" : "route"}
                markerEnd="url(#route-arrow)"
              />
            );
          })}
        </g>
        <g className="point-layer">
          {points.map((event) => {
            const point = projectChinaPoint(event.longitude, event.latitude);
            const active = event.event_id === selectedId;
            return (
              <g
                key={event.event_id}
                className={active ? "map-point map-point-active" : "map-point"}
                transform={`translate(${point.x} ${point.y})`}
                role="button"
                tabIndex="0"
                onClick={() => onSelect(event.event_id)}
                onKeyDown={(keyboardEvent) => keyboardEvent.key === "Enter" && onSelect(event.event_id)}
              >
                <circle className="map-point-ring" r={active ? 24 : 16} filter={active ? "url(#point-glow)" : undefined} />
                <circle className="map-point-core" r={active ? 9 : 7} />
                {active && (
                  <text x="20" y="-18" className="map-point-label">
                    {event.historical_place || event.modern_place || event.title}
                  </text>
                )}
                <title>{event.title}</title>
              </g>
            );
          })}
        </g>
      </svg>
      {points.length === 0 && <div className="map-empty">等待带地点的证据</div>}
    </div>
  );
}
