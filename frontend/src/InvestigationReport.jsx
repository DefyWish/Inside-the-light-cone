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
          <div className="report-meta"><span>{report.overview}</span></div>
          <article className={`report-essay ${audience === "public" ? "public" : "professional"}`}>
            {(report.narrative || []).map((paragraph, index) => <p key={`report:p:${index}`}>{paragraph}</p>)}
          </article>
          {report.sources.length > 0 && (
            <details className="report-sources">
              <summary>{audience === "professional" ? "展开资料来源" : "延伸阅读"}<span>{report.sources.length}</span></summary>
              <div>{report.sources.map((source, index) => (
                <a key={`${source.source_id}:${index}`} href={source.url} target="_blank" rel="noreferrer">
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <b>{source.title}</b>
                  <small>{source.source_label}{source.publication_year ? ` · ${source.publication_year}` : ""}</small>
                </a>
              ))}</div>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
