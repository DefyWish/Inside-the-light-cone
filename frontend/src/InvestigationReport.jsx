import React from "react";

export default function InvestigationReport({ report, audience, loading, onAudienceChange }) {
  return (
    <section className="report-panel" aria-label="调查报告">
      <div className="report-header">
        <div>
          <span>调查报告</span>
          <h2>{report?.title || "正在整理最终生命树"}</h2>
        </div>
        <div className="report-switch" role="group" aria-label="报告版本">
          <button type="button" className={audience === "professional" ? "active" : ""} onClick={() => onAudienceChange("professional")}>专业版</button>
          <button type="button" className={audience === "public" ? "active" : ""} onClick={() => onAudienceChange("public")}>科普版</button>
        </div>
      </div>
      {loading && <p className="report-loading">正在整理证据、判断与策展节点…</p>}
      {report && !loading && (
        <div className="report-body">
          <div className="report-meta"><b>{report.subtitle}</b><span>{report.overview}</span></div>
          {report.sections.map((section) => (
            <section key={section.heading} className="report-section">
              <h3>{section.heading}</h3>
              {section.paragraphs.map((paragraph, index) => <p key={`${section.heading}:p:${index}`}>{paragraph}</p>)}
              {section.items.length > 0 && <div className="report-findings">{section.items.map((item, index) => (
                <article key={`${section.heading}:i:${index}`}>
                  <b>{item.title}</b>
                  <p>{item.text}</p>
                </article>
              ))}</div>}
            </section>
          ))}
          {report.sources.length > 0 && (
            <section className="report-section report-sources">
              <h3>{audience === "professional" ? "来源目录" : "继续了解"}</h3>
              <div>{report.sources.map((source, index) => (
                <a key={`${source.source_id}:${index}`} href={source.url} target="_blank" rel="noreferrer">
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <b>{source.title}</b>
                  <small>{source.source_label}{source.publication_year ? ` · ${source.publication_year}` : ""}</small>
                </a>
              ))}</div>
            </section>
          )}
        </div>
      )}
    </section>
  );
}
