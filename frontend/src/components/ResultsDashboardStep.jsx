import React, { useEffect, useMemo, useState } from "react";
import {
  Download,
  Search,
  Eye,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  FileText,
  RefreshCw,
} from "lucide-react";
import { apiClient } from "../api/client";
import {
  cacheLectureResults,
  cacheStudentDetail,
  getCachedLectureResults,
  getCachedStudentDetail,
} from "../storage/indexedDb";

function claimBadge(status) {
  if (status === "SUPPORTED") {
    return (
      <span className="badge badge-supported">
        <CheckCircle2 size={12} /> SUPPORTED
      </span>
    );
  }
  if (status === "PARTIALLY_SUPPORTED") {
    return (
      <span className="badge badge-partial">
        <AlertTriangle size={12} /> PARTIALLY SUPPORTED
      </span>
    );
  }
  return (
    <span className="badge badge-unsupported">
      <XCircle size={12} /> NOT SUPPORTED
    </span>
  );
}

export function ResultsDashboardStep({
  subject,
  chapter,
  selectedStudentId,
  onSelectStudentId,
  onGoToEvaluation,
}) {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [query, setQuery] = useState("");
  const [sortBy, setSortBy] = useState("total_desc");

  const [studentDetail, setStudentDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const loadSummary = async () => {
    if (!subject || !chapter) return;
    setLoading(true);
    setError(null);

    const cached = await getCachedLectureResults(subject.subject_id, chapter.lecture_id);
    if (cached) setResults(cached);

    try {
      const fresh = await apiClient.getResults(subject.subject_id, chapter.lecture_id);
      setResults(fresh);
      await cacheLectureResults(subject.subject_id, chapter.lecture_id, fresh);
      if (!selectedStudentId && fresh.students?.length > 0) {
        onSelectStudentId(fresh.students[0].student_id);
      }
    } catch (err) {
      if (!cached) setError(err.message || "No evaluation results available.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setResults(null);
    setStudentDetail(null);
    loadSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subject?.subject_id, chapter?.lecture_id, chapter?.evaluation?.last_evaluated_at]);

  useEffect(() => {
    let cancelled = false;
    const fetchStudent = async () => {
      if (!subject || !chapter || !selectedStudentId) {
        setStudentDetail(null);
        return;
      }
      setLoadingDetail(true);
      const cached = await getCachedStudentDetail(
        subject.subject_id,
        chapter.lecture_id,
        selectedStudentId
      );
      if (cached && !cancelled) setStudentDetail(cached);

      try {
        const fresh = await apiClient.getStudentResult(
          subject.subject_id,
          chapter.lecture_id,
          selectedStudentId
        );
        if (!cancelled) {
          setStudentDetail(fresh);
          await cacheStudentDetail(
            subject.subject_id,
            chapter.lecture_id,
            selectedStudentId,
            fresh
          );
        }
      } catch {
        // Ignore if student doesn't exist in this lecture
      } finally {
        if (!cancelled) setLoadingDetail(false);
      }
    };
    fetchStudent();
    return () => {
      cancelled = true;
    };
  }, [subject?.subject_id, chapter?.lecture_id, selectedStudentId, results?.total_students]);

  const filteredStudents = useMemo(() => {
    const list = [...(results?.students || [])];
    const q = query.trim().toLowerCase();
    const filtered = q
      ? list.filter(
          (s) =>
            String(s.student_id).toLowerCase().includes(q) ||
            String(s.grade || "").toLowerCase().includes(q)
        )
      : list;

    filtered.sort((a, b) => {
      if (sortBy === "total_desc") return b.total_score - a.total_score;
      if (sortBy === "total_asc") return a.total_score - b.total_score;
      if (sortBy === "accuracy_desc") return b.accuracy_score - a.accuracy_score;
      if (sortBy === "coverage_desc") return b.coverage_score - a.coverage_score;
      return String(a.student_id).localeCompare(String(b.student_id), undefined, { numeric: true });
    });
    return filtered;
  }, [results, query, sortBy]);

  if (!subject || !chapter) return null;

  if (loading && !results) {
    return (
      <div className="card" style={{ textAlign: "center", padding: 40 }}>
        Loading lecture verification results...
      </div>
    );
  }

  if (error && !results) {
    return (
      <div className="card" style={{ textAlign: "center", padding: 40 }}>
        <h3 style={{ margin: "0 0 8px" }}>No Verification Results Yet</h3>
        <p style={{ color: "var(--text-secondary)", marginBottom: 18 }}>{error}</p>
        <button type="button" className="btn btn-primary" onClick={onGoToEvaluation}>
          Go to Step 7: Run Evaluation
        </button>
      </div>
    );
  }

  if (!results) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <div className="section-header">
        <div>
          <h1 className="section-title">
            8. Verification Results — {results.lecture_title}{" "}
            <span className="code-chip">
              {results.subject_id} / {results.lecture_id}
            </span>
          </h1>
          <p className="section-subtitle">
            Auditable 10-mark rubric scores stored locally at{" "}
            <span className="mono">{results.results_dir}</span>
          </p>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" className="btn btn-secondary btn-sm" onClick={loadSummary}>
            <RefreshCw size={14} /> Refresh
          </button>
          <a
            className="btn btn-secondary btn-sm"
            href={apiClient.getExportUrl(subject.subject_id, chapter.lecture_id, "csv")}
            download
          >
            <Download size={14} /> Export CSV Report
          </a>
          <a
            className="btn btn-primary btn-sm"
            href={apiClient.getExportUrl(subject.subject_id, chapter.lecture_id, "json")}
            download
          >
            <Download size={14} /> Export JSON Report
          </a>
        </div>
      </div>

      {(chapter.evaluation?.outdated || chapter.processing?.status === "outdated") && (
        <div className="banner banner-warning">
          <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <AlertTriangle size={16} />
            Lecture files or knowledge base were updated after these results were generated. Re-run
            evaluation on Step 7 when ready.
          </span>
          <button type="button" className="btn btn-primary btn-sm" onClick={onGoToEvaluation}>
            Re-Evaluate
          </button>
        </div>
      )}

      {chapter.evaluation?.warnings?.length > 0 && (
        <div className="banner banner-info">
          <span>{chapter.evaluation.warnings[0]}</span>
        </div>
      )}

      {/* Class Summary Cards */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Evaluated Students</div>
          <div className="stat-value">{results.total_students}</div>
          <div className="stat-sub">Isolated per-student directories</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Class Mean Total</div>
          <div className="stat-value">
            {results.averages?.total_score} <span style={{ fontSize: 15, fontWeight: 600 }}>/ 10</span>
          </div>
          <div className="stat-sub">Mean Grade: {results.averages?.average_grade}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Mean Factual Accuracy</div>
          <div className="stat-value">
            {results.averages?.accuracy_score} <span style={{ fontSize: 15, fontWeight: 600 }}>/ 5</span>
          </div>
          <div className="stat-sub">Claim verification accuracy</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Mean Lecture Coverage</div>
          <div className="stat-value">
            {results.averages?.coverage_score} <span style={{ fontSize: 15, fontWeight: 600 }}>/ 3</span>
          </div>
          <div className="stat-sub">
            Across {results.lecture_concepts?.length || 0} lecture units
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Mean Understanding</div>
          <div className="stat-value">
            {results.averages?.understanding_score}{" "}
            <span style={{ fontSize: 15, fontWeight: 600 }}>/ 2</span>
          </div>
          <div className="stat-sub">Depth & synthesis quality</div>
        </div>
      </div>

      {/* Grade Distribution */}
      <div className="card" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div style={{ fontWeight: 600, fontSize: 13.5 }}>Grade Distribution:</div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {Object.entries(results.grade_distribution || {}).map(([grade, count]) => (
            <span key={grade} className="badge badge-neutral" style={{ fontSize: 12.5 }}>
              <strong>{grade}:</strong> {count}
            </span>
          ))}
        </div>
      </div>

      {/* Student Summary Table */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
          <h3 style={{ margin: 0, fontSize: 16 }}>Student Evaluation Leaderboard</h3>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <div style={{ position: "relative" }}>
              <Search
                size={14}
                style={{ position: "absolute", left: 10, top: 11, color: "var(--text-muted)" }}
              />
              <input
                className="input"
                style={{ paddingLeft: 30, minWidth: 210 }}
                placeholder="Search student ID or grade..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <select
              className="select"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
            >
              <option value="total_desc">Sort: Highest Total Score</option>
              <option value="total_asc">Sort: Lowest Total Score</option>
              <option value="accuracy_desc">Sort: Highest Accuracy (/5)</option>
              <option value="coverage_desc">Sort: Highest Coverage (/3)</option>
              <option value="student_id">Sort: Student ID (A–Z)</option>
            </select>
          </div>
        </div>

        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Student ID</th>
                <th>Total (/10)</th>
                <th>Grade</th>
                <th>Factual Accuracy (/5)</th>
                <th>Lecture Coverage (/3)</th>
                <th>Understanding (/2)</th>
                <th>Claims (S / P / N)</th>
                <th>Inspect</th>
              </tr>
            </thead>
            <tbody>
              {filteredStudents.map((stu) => {
                const isSelected = stu.student_id === selectedStudentId;
                return (
                  <tr
                    key={stu.sanitized_student_id}
                    className={isSelected ? "row-selected" : ""}
                    style={{ cursor: "pointer" }}
                    onClick={() => onSelectStudentId(stu.student_id)}
                  >
                    <td style={{ fontWeight: 700 }}>{stu.student_id}</td>
                    <td>
                      <span style={{ fontWeight: 800, fontSize: 14 }}>{stu.total_score}</span> / 10
                    </td>
                    <td>
                      <span
                        className={`badge ${
                          stu.total_score >= 7
                            ? "badge-completed"
                            : stu.total_score >= 5
                            ? "badge-outdated"
                            : "badge-failed"
                        }`}
                      >
                        {stu.grade}
                      </span>
                    </td>
                    <td>{stu.accuracy_score} / 5</td>
                    <td>{stu.coverage_score} / 3</td>
                    <td>{stu.understanding_score} / 2</td>
                    <td className="mono">
                      {stu.supported}S / {stu.partially_supported}P / {stu.not_supported}N
                    </td>
                    <td>
                      <button
                        type="button"
                        className={`btn btn-sm ${isSelected ? "btn-primary" : "btn-secondary"}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectStudentId(stu.student_id);
                        }}
                      >
                        <Eye size={13} /> Inspect
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detailed Student Verification View */}
      {selectedStudentId && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          {loadingDetail && !studentDetail ? (
            <div style={{ padding: 20, textAlign: "center" }}>
              Loading student verification details...
            </div>
          ) : studentDetail ? (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <h2 style={{ margin: 0, fontSize: 19 }}>
                      Student Detail: {studentDetail.student_id}
                    </h2>
                    <span className="badge badge-completed" style={{ fontSize: 13 }}>
                      Grade {studentDetail.grade} •{" "}
                      {studentDetail.scores?.total?.score} / 10
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }}>
                    Directory: <span className="mono">{studentDetail.files?.score_json}</span>
                  </div>
                </div>

                <div style={{ display: "flex", gap: 8 }}>
                  <a
                    className="btn btn-secondary btn-sm"
                    href={apiClient.getExportUrl(
                      subject.subject_id,
                      chapter.lecture_id,
                      "csv",
                      studentDetail.student_id
                    )}
                    download
                  >
                    <Download size={13} /> Student CSV
                  </a>
                  <a
                    className="btn btn-secondary btn-sm"
                    href={apiClient.getExportUrl(
                      subject.subject_id,
                      chapter.lecture_id,
                      "json",
                      studentDetail.student_id
                    )}
                    download
                  >
                    <Download size={13} /> Student JSON
                  </a>
                </div>
              </div>

              {/* Rubric Score Progress Bars */}
              <div className="grid-3">
                {[
                  {
                    label: "Factual Accuracy",
                    score: studentDetail.scores?.factual_accuracy?.score ?? 0,
                    max: 5,
                  },
                  {
                    label: "Lecture Coverage",
                    score: studentDetail.scores?.lecture_coverage?.score ?? 0,
                    max: 3,
                  },
                  {
                    label: "Understanding Quality",
                    score: studentDetail.scores?.understanding_quality?.score ?? 0,
                    max: 2,
                  },
                ].map((item) => (
                  <div
                    key={item.label}
                    style={{
                      padding: 12,
                      borderRadius: 8,
                      border: "1px solid var(--border)",
                      background: "var(--bg-subtle)",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                      <span>{item.label}</span>
                      <span>
                        {item.score} / {item.max}
                      </span>
                    </div>
                    <div className="score-bar-track">
                      <div
                        className="score-bar-fill"
                        style={{ width: `${Math.min(100, (item.score / item.max) * 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>

              {/* Original Student Feedback */}
              {studentDetail.original_feedback && (
                <div style={{ background: "var(--bg-subtle)", border: "1px solid var(--border)", borderRadius: 8, padding: 14 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", marginBottom: 4 }}>
                    Submitted Student Feedback
                  </div>
                  <div style={{ fontSize: 13.5, whiteSpace: "pre-wrap" }}>
                    {studentDetail.original_feedback}
                  </div>
                </div>
              )}

              {/* Lecture Coverage Breakdown */}
              <div className="grid-2">
                <div style={{ border: "1px solid var(--success-border)", background: "var(--success-soft)", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontWeight: 700, fontSize: 13, color: "var(--success)", marginBottom: 6 }}>
                    Covered Lecture Units (
                    {studentDetail.coverage_details?.covered_lecture_units || 0} /{" "}
                    {studentDetail.coverage_details?.total_lecture_units || 0})
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {(studentDetail.coverage_details?.covered_units || []).length === 0 ? (
                      <span style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>
                        No lecture concept units covered by supported claims.
                      </span>
                    ) : (
                      studentDetail.coverage_details.covered_units.map((u) => (
                        <span key={u.unit_id} className="badge badge-supported">
                          {u.unit_id}: {u.label}
                        </span>
                      ))
                    )}
                  </div>
                </div>

                <div style={{ border: "1px solid var(--border)", background: "var(--bg-subtle)", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontWeight: 700, fontSize: 13, color: "var(--text-secondary)", marginBottom: 6 }}>
                    Uncovered Lecture Units (
                    {(studentDetail.coverage_details?.uncovered_units || []).length})
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {(studentDetail.coverage_details?.uncovered_units || []).map((u) => (
                      <span key={u.unit_id} className="badge badge-neutral">
                        {u.unit_id}: {u.label}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              {/* Extracted Claims & Lecture Evidence */}
              <div>
                <h3 style={{ margin: "0 0 12px", fontSize: 16 }}>
                  Extracted Claims & Supporting Lecture Evidence (
                  {studentDetail.evaluated_claims?.length || 0})
                </h3>
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {(studentDetail.evaluated_claims || []).map((cl, idx) => (
                    <div key={idx} className="claim-card">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
                        <div style={{ fontWeight: 600, fontSize: 14, flex: 1 }}>
                          <span className="code-chip" style={{ marginRight: 8 }}>
                            Claim #{idx + 1}
                          </span>
                          {cl.claim}
                        </div>
                        {claimBadge(cl.status)}
                      </div>

                      {cl.explanation && (
                        <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                          <strong>Verification Reasoning:</strong> {cl.explanation}
                        </div>
                      )}

                      {(cl.evidence || []).length > 0 && (
                        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 4 }}>
                          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)" }}>
                            Top Supporting Evidence from {results.subject_id}/{results.lecture_id}:
                          </div>
                          {cl.evidence.slice(0, 2).map((ev, evIdx) => (
                            <div key={evIdx} className="evidence-box">
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                                  <span className="code-chip">{ev.chunk_id}</span>
                                  {ev.timestamp_range && (
                                    <span className="badge badge-processing">
                                      <Clock size={11} /> Audio {ev.timestamp_range}
                                    </span>
                                  )}
                                  {ev.page_number !== null && ev.page_number !== undefined && (
                                    <span className="badge badge-neutral">
                                      <FileText size={11} /> Slide / Page {ev.page_number}
                                    </span>
                                  )}
                                </div>
                                {ev.similarity_score !== undefined && (
                                  <span className="mono" style={{ color: "var(--text-muted)" }}>
                                    Similarity: {Number(ev.similarity_score).toFixed(3)}
                                  </span>
                                )}
                              </div>
                              <div style={{ color: "var(--text-primary)" }}>{ev.text}</div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}

