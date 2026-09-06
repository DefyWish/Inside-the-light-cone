import React from "react";
import { localizePlace, localizePreferredPlace } from "./displayText.js";

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

function isCoordinate(value) {
  return value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
}

export function hasPoint(value) {
  return isCoordinate(value?.longitude) && isCoordinate(value?.latitude);
}

function movementPoint(value) {
  if (!value) return null;
  const longitude = value.longitude ?? value.lon;
  const latitude = value.latitude ?? value.lat;
  if (!isCoordinate(longitude) || !isCoordinate(latitude)) return null;
  return projectChinaPoint(longitude, latitude);
}

function displayPlace(event) {
  return localizePreferredPlace(event.movement?.to?.name, event.historical_place, event.modern_place) || event.title;
}

const LABEL_OFFSETS = [
  { x: 22, y: -17, anchor: "start" },
  { x: 22, y: 31, anchor: "start" },
  { x: -22, y: -17, anchor: "end" },
  { x: -22, y: 31, anchor: "end" },
  { x: 22, y: -49, anchor: "start" },
  { x: -22, y: -49, anchor: "end" },
  { x: 22, y: 61, anchor: "start" },
  { x: -22, y: 61, anchor: "end" },
  { x: 22, y: -81, anchor: "start" },
  { x: -22, y: -81, anchor: "end" },
  { x: 22, y: 93, anchor: "start" },
  { x: -22, y: 93, anchor: "end" },
  { x: 22, y: -113, anchor: "start" },
  { x: -22, y: -113, anchor: "end" },
  { x: 22, y: 125, anchor: "start" },
  { x: -22, y: 125, anchor: "end" },
  { x: 22, y: -145, anchor: "start" },
  { x: -22, y: -145, anchor: "end" },
  { x: 22, y: 157, anchor: "start" },
  { x: -22, y: 157, anchor: "end" },
];

function labelBox(label, offset) {
  const width = Math.min(330, Math.max(42, [...label.name].reduce(
    (sum, character) => sum + (/^[\u3400-\u9fff]$/.test(character) ? 21 : 11),
    0,
  )));
  const endX = label.x + offset.x;
  return {
    x1: offset.anchor === "end" ? endX - width : endX,
    x2: offset.anchor === "end" ? endX : endX + width,
    y1: label.y + offset.y - 22,
    y2: label.y + offset.y + 6,
  };
}

function boxesOverlap(a, b) {
  return a.x1 < b.x2 + 8 && a.x2 + 8 > b.x1 && a.y1 < b.y2 + 5 && a.y2 + 5 > b.y1;
}

export function buildMapLabels(points, routes, selectedId) {
  const candidates = [
    ...points.map((event) => {
      const point = projectChinaPoint(event.longitude, event.latitude);
      return { ...point, name: displayPlace(event), eventId: event.event_id, active: event.event_id === selectedId, priority: 2 };
    }),
    ...routes.flatMap(({ event, start, end, progress, startName, endName }) => [
      { ...start, name: startName, eventId: event.event_id, active: false, priority: 1 },
      progress >= 1 ? { ...end, name: endName, eventId: event.event_id, active: event.event_id === selectedId, priority: 2 } : null,
    ].filter(Boolean)),
  ].filter((label) => label.name);

  const unique = [];
  candidates.forEach((candidate) => {
    const index = unique.findIndex((label) => Math.hypot(label.x - candidate.x, label.y - candidate.y) < 12);
    if (index < 0) unique.push(candidate);
    else if (candidate.active || candidate.priority > unique[index].priority) unique[index] = candidate;
  });

  const occupied = [];
  const laidOut = unique
    .sort((a, b) => Number(b.active) - Number(a.active))
    .map((label) => {
      const offset = LABEL_OFFSETS.find((candidate) => {
        const box = labelBox(label, candidate);
        const inside = box.x1 >= 8 && box.x2 <= WIDTH - 8 && box.y1 >= 8 && box.y2 <= HEIGHT - 8;
        return inside && !occupied.some((placed) => boxesOverlap(box, placed));
      }) || LABEL_OFFSETS[0];
      occupied.push(labelBox(label, offset));
      return { ...label, offset };
    });
  return laidOut.sort((a, b) => Number(a.active) - Number(b.active));
}

export default function CurationMap({ events, cursorYear, selectedId, onSelect }) {
  const visible = events.filter((event) => (
    event.event_year_start == null || event.event_year_start <= cursorYear
  )).sort((a, b) => (a.event_year_start ?? Infinity) - (b.event_year_start ?? Infinity));
  const routes = visible.flatMap((event) => {
    const start = movementPoint(event.movement?.from);
    const end = movementPoint(event.movement?.to);
    if (!start || !end || (Math.abs(start.x - end.x) < 1 && Math.abs(start.y - end.y) < 1)) return [];
    const startYear = Number(event.event_year_start);
    const endYear = Number(event.event_year_end);
    const progress = Number.isFinite(startYear) && Number.isFinite(endYear) && endYear > startYear
      ? Math.min(1, Math.max(0.015, (cursorYear - startYear) / (endYear - startYear)))
      : 1;
    return [{
      event,
      start,
      end,
      progress,
      startName: localizePlace(event.movement?.from?.name) || "起点",
      endName: localizePreferredPlace(event.movement?.to?.name, event.historical_place, event.modern_place) || displayPlace(event),
    }];
  });
  const movingIds = new Set(routes.filter(({ progress }) => progress < 1).map(({ event }) => event.event_id));
  const points = visible.filter((event) => hasPoint(event) && !movingIds.has(event.event_id));
  const labels = buildMapLabels(points, routes, selectedId);

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
          {routes.map(({ event, start, end, progress }) => {
            const bend = Math.max(18, Math.abs(end.x - start.x) * 0.12);
            const path = `M ${start.x} ${start.y} Q ${(start.x + end.x) / 2} ${Math.min(start.y, end.y) - bend} ${end.x} ${end.y}`;
            return (
              <path
                key={`route:${event.event_id}`}
                d={path}
                className={event.event_id === selectedId ? "route route-active" : "route"}
                pathLength="100"
                style={{ strokeDasharray: `${progress * 100} 100` }}
                markerEnd={progress >= 1 ? "url(#route-arrow)" : undefined}
              />
            );
          })}
        </g>
        <g className="route-anchor-layer">
          {routes.flatMap(({ event, start, end, progress, startName, endName }) => [
            <g key={`anchor:start:${event.event_id}`} transform={`translate(${start.x} ${start.y})`}>
              <circle className="route-anchor" r="10" />
              <circle className="route-anchor-core" r="4" />
              <title>{startName}</title>
            </g>,
            progress >= 1 ? (
              <g key={`anchor:end:${event.event_id}`} transform={`translate(${end.x} ${end.y})`}>
                <circle className="route-anchor" r="10" />
                <circle className="route-anchor-core" r="4" />
                <title>{endName}</title>
              </g>
            ) : null,
          ])}
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
                <title>{event.title}</title>
              </g>
            );
          })}
        </g>
        <g className="map-label-layer">
          {labels.map((label) => (
            <g
              key={`label:${label.eventId}:${label.name}:${Math.round(label.x)}:${Math.round(label.y)}`}
              className={label.active ? "map-place-label map-place-label-active" : "map-place-label"}
              role="button"
              tabIndex="0"
              onClick={() => onSelect(label.eventId)}
              onKeyDown={(keyboardEvent) => keyboardEvent.key === "Enter" && onSelect(label.eventId)}
            >
              <line x1={label.x} y1={label.y} x2={label.x + label.offset.x * 0.72} y2={label.y + label.offset.y * 0.72} />
              <text x={label.x + label.offset.x} y={label.y + label.offset.y} textAnchor={label.offset.anchor}>{label.name}</text>
            </g>
          ))}
        </g>
      </svg>
      {points.length === 0 && <div className="map-empty">等待带地点的证据</div>}
    </div>
  );
}
