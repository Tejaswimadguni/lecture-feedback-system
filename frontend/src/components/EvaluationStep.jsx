import React, { useState } from "react";
import {
  ShieldCheck,
  Play,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  BarChart3,
} from "lucide-react";
import { ConfirmModal } from "./Modals";

const EVAL_STEPS = [
  { num: 1, label: "Student Claim Extraction -> claims.json" },
  { num: 2, label: "Isolated FAISS Lecture Evidence Retrieval -> evidence.json" },
  { num: 3, label: "Claim Support Verification -> evaluated.json" },
  { num: 4, label: "Dynamic 10-Mark Rubric & Coverage Scoring -> score.json" },
];

export function EvaluationStep({
  subject,
  chapter,
  onStartEvaluation,
  onOpenResults,
  onGoToProcessing,
  onGoToFeedback,
}) {
  const [topK, setTopK] = useState(5);
  const [submitting, setSubmitting] = useState(false);
  const [confirmOverwrite, setConfirmOverwrite] = useState(false);

  if (!subject || !chapter) return null;

  const pStatus = chapter.processing?.status || "not_started";
  const kbReady = pStatus === "completed" || pStatus === "outdated";
  const csvMeta = chapter.files?.feedback_csv;
  const csvValid = Boolean(csvMeta?.is_valid);

  const evState = chapter.evaluation || {};
  const evStatus = evState.status || "not_started";
  const isRunning = evStatus === "evaluating" || evStatus === "queued";
  const hasExistingResults = evStatus === "completed";

  const triggerRun = async (overwrite = true) => {
    setSubmitting(true);
    try {
      await onStartEvaluation(subject.subject_id, chapter.lecture_id, {
        student_id_column: csvMeta?.student_id_column || null,
        feedback_column: csvMeta?.feedback_column || null,
        top_k: Number(topK),
        overwrite_existing: overwrite,
        strict_llm: false,
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleClickStart = () => {
    if (hasExistingResults) {
      setConfirmOverwrite(true);
    } else {
      triggerRun(true);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <div className="section-header">
        <div>
          <h1 className="section-title">
            7. Student Feedback Verification & Evaluation — {chapter.title}{" "}
            <span className="code-chip">{chapter.lecture_id}</span>
          </h1>
          <p className="section-subtitle">
            Verifies every student claim exclusively against{" "}
            <span className="code-chip">
              backend/data/lectures/{subject.subject_id}/{chapter.lecture_id}/knowledge_base/
            </span>{" "}
            and writes auditable results under{" "}
            <span className="code-chip">
              backend/data/results/{subject.subject_id}/{chapter.lecture_id}/
            </span>
            .
          </p>
        </div>

        {evStatus === "completed" && (
          <button type="button" className="btn btn-primary" onClick={onOpenResults}>
            <BarChart3 size={15} /> Open Verification Results
          </button>
        )}
      </div>

      {/* Readiness Checklist */}
      <div className="grid-2">
        <div className="card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <div>
            <div className="stat-label">1. Selected Lecture Knowledge Base</div>
            <div style={{ fontWeight: 700, marginTop: 4 }}>
              {kbReady
                ? `${subject.subject_id}/${chapter.lecture_id} (${chapter.processing?.total_chunks || 0} indexed chunks)`
                : "Knowledge base not built yet"}
            </div>
          </div>
          {kbReady ? (
            <span className="badge badge-completed">Ready</span>
          ) : (
            <button type="button" className="btn btn-secondary btn-sm" onClick={onGoToProcessing}>
              Process Lecture
            </button>
          )}
        </div>

        <div className="card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <div>
            <div className="stat-label">2. Student Feedback CSV</div>
            <div style={{ fontWeight: 700, marginTop: 4 }}>
              {csvMeta
                ? `${csvMeta.filename} (${csvMeta.total_rows} rows • ID: ${csvMeta.student_id_column}, Text: ${csvMeta.feedback_column})`
                : "No feedback CSV uploaded"}
            </div>
          </div>
          {csvValid ? (
            <span className="badge badge-completed">Validated</span>
          ) : (
            <button type="button" className="btn btn-secondary btn-sm" onClick={onGoToFeedback}>
              Upload / Fix CSV
            </button>
          )}
        </div>
      </div>

      {evState.warnings?.length > 0 && (
        <div className="banner banner-warning">
          <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
            <AlertTriangle size={16} style={{ marginTop: 2, flexShrink: 0 }} />
            <div>
              {evState.warnings.map((w, i) => (
                <div key={i}>{w}</div>
              ))}
            </div>
          </div>
        </div>
      )}

      {evStatus === "failed" && (
        <div className="banner banner-error">
          <div>
            <strong>Evaluation Failed:</strong> {evState.error || "Pipeline execution failed."}
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={!kbReady || !csvValid || isRunning || submitting}
            onClick={() => triggerRun(true)}
          >
            <RefreshCw size={13} /> Retry Evaluation
          </button>
        </div>
      )}

      {/* Run Controls */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <ShieldCheck size={19} style={{ color: "var(--primary)" }} />
          <h3 style={{ margin: 0, fontSize: 16 }}>
            Rubric & Verification Parameters (Factual Accuracy: 5 • Coverage: 3 • Understanding: 2 = 10 Marks)
          </h3>
        </div>

        <div className="form-row">
          <div className="field" style={{ maxWidth: 280 }}>
            <label htmlFor="topk-select">Top-K Lecture Evidence Chunks per Claim</label>
            <select
              id="topk-select"
              className="select"
              value={topK}
              disabled={isRunning}
              onChange={(e) => setTopK(Number(e.target.value))}
            >
              <option value={3}>Top 3 chunks</option>
              <option value={5}>Top 5 chunks (Default)</option>
              <option value={8}>Top 8 chunks</option>
              <option value={10}>Top 10 chunks</option>
            </select>
          </div>

          <button
            type="button"
            className="btn btn-primary"
            disabled={!kbReady || !csvValid || isRunning || submitting}
            onClick={handleClickStart}
          >
            {isRunning ? (
              <>
                <Loader2 size={15} className="spin" /> Evaluating Students...
              </>
            ) : hasExistingResults ? (
              <>
                <RefreshCw size={15} /> Re-Evaluate Student Feedback
              </>
            ) : (
              <>
                <Play size={15} /> Run Verification & Scoring
              </>
            )}
          </button>
        </div>
      </div>

      {/* Live 4-Step Verification Progress */}
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 16 }}>Verification Pipeline Progress</h3>
            <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 2 }}>
              {evState.message || evState.stage || "Ready to evaluate student claims."}
              {evState.current && evState.total
                ? ` — Student ${evState.current} of ${evState.total}`
                : ""}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {evState.elapsed_seconds !== undefined && evState.elapsed_seconds !== null && (
              <span className="code-chip">Elapsed: {evState.elapsed_seconds}s</span>
            )}
            <span
              className={`badge badge-${
                evStatus === "completed"
                  ? "completed"
                  : evStatus === "evaluating"
                  ? "evaluating"
                  : evStatus === "failed"
                  ? "failed"
                  : "neutral"
              }`}
            >
              {evStatus.toUpperCase()}
            </span>
          </div>
        </div>

        <div className="stage-list">
          {EVAL_STEPS.map((st) => {
            const curIdx = Number(evState.stage_index || 0);
            const isDone = evStatus === "completed" || (isRunning && curIdx > st.num);
            const isActive = isRunning && curIdx === st.num;
            return (
              <div
                key={st.num}
                className={`stage-item ${isDone ? "done" : ""} ${isActive ? "active" : ""}`}
              >
                {isDone ? (
                  <CheckCircle2 size={16} style={{ color: "var(--success)", flexShrink: 0 }} />
                ) : isActive ? (
                  <Loader2 size={16} className="spin" style={{ color: "var(--primary)", flexShrink: 0 }} />
                ) : (
                  <span className="code-chip">{st.num}/4</span>
                )}
                <span>
                  Step {st.num}: {st.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <ConfirmModal
        open={confirmOverwrite}
        title="Re-Evaluate Student Feedback?"
        description={`Existing evaluation results for '${subject.subject_id}/${chapter.lecture_id}' (${
          evState.total_students || 0
        } students) will be replaced with fresh verification outputs. Other lectures are unaffected.`}
        confirmLabel="Re-Evaluate & Replace"
        onCancel={() => setConfirmOverwrite(false)}
        onConfirm={() => {
          setConfirmOverwrite(false);
          triggerRun(true);
        }}
      />
    </div>
  );
}

