import React, { useEffect, useMemo, useState } from "react";

export function formatYear(year) {
  if (year == null || Number.isNaN(Number(year))) return "年代待定";
  return Number(year) < 0 ? `公元前${Math.abs(Number(year))}年` : `${Number(year)}年`;
}

export default function Timeline({ events, cursorYear, onChange, selectedId, onSelect }) {
  const [playing, setPlaying] = useState(false);
  const years = useMemo(
    () => [...new Set(events.map((event) => event.event_year_start).filter((year) => year != null))].sort((a, b) => a - b),
    [events],
  );
  const min = years[0] ?? 0;
  const last = years.at(-1) ?? 1;
  const max = Math.max(last, min + 1);

  useEffect(() => {
    if (!playing || years.length === 0) return undefined;
    const timer = window.setInterval(() => {
      const next = years.find((year) => year > cursorYear);
      if (next == null) {
        setPlaying(false);
      } else {
        onChange(next);
      }
    }, 850);
    return () => window.clearInterval(timer);
  }, [playing, years, cursorYear, onChange]);

  const cursorPercent = ((Math.min(Math.max(cursorYear, min), max) - min) / (max - min)) * 100;

  return (
    <section className="timeline-panel" aria-label="策展时间轴">
      <div className="timeline-topline">
        <button
          type="button"
          className="play-button"
          disabled={years.length < 2}
          onClick={() => {
            if (!playing && cursorYear >= last) onChange(min);
            setPlaying((value) => !value);
          }}
          aria-label={playing ? "暂停时间轴" : "播放时间轴"}
        >
          {playing ? "Ⅱ" : "▶"}
        </button>
        <strong>{formatYear(cursorYear)}</strong>
        <span>{years.length ? `${formatYear(min)} — ${formatYear(last)}` : "等待年代证据"}</span>
      </div>
      <div className="timeline-track-wrap">
        <div className="timeline-progress" style={{ width: `${cursorPercent}%` }} />
        {events.map((event) => {
          if (event.event_year_start == null || years.length === 0) return null;
          const left = ((event.event_year_start - min) / (max - min)) * 100;
          return (
            <button
              type="button"
              key={event.event_id}
              className={event.event_id === selectedId ? "timeline-tick timeline-tick-active" : "timeline-tick"}
              style={{ left: `${left}%` }}
              onClick={() => {
                onChange(event.event_year_start);
                onSelect(event.event_id);
              }}
              aria-label={`${formatYear(event.event_year_start)} ${event.title}`}
              title={`${formatYear(event.event_year_start)} · ${event.title}`}
            />
          );
        })}
        <input
          type="range"
          min={min}
          max={max}
          step="1"
          value={Math.min(Math.max(cursorYear, min), max)}
          disabled={years.length === 0}
          onChange={(event) => onChange(Number(event.target.value))}
          aria-label="拖动年代"
        />
      </div>
      {events.some((event) => event.event_year_start == null) && (
        <div className="undated-count">另有 {events.filter((event) => event.event_year_start == null).length} 个年代待考节点</div>
      )}
    </section>
  );
}
