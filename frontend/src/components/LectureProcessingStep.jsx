import React, { useEffect, useState } from "react";
import {
  Play,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Database,
  ArrowRight,
  Loader2,
} from "lucide-react";
import { apiClient, formatDateTime } from "../api/client";

const PIPELINE_STAGES = [
  { num: 1, label: "Audio Ingestion & Whisper Transcription" },
  { num: 2, label: "Transcript Cleaning & Timestamp-Preserving Chunking" },
  { num: 3, label: "PDF / Slide Extraction, Cleaning & Page-Aware Chunking" },
  { num: 4, label: "Chunk Validation & Lecture Concept Metadata" },
  { num: 5, label: "SentenceTransformer Embeddings & Isolated FAISS Indexing" },
];

export function LectureProcessingStep({
  subject,
  chapter,
  onStartProcessing,
  onContinueToFeedback,
}) {
  const hasAudio = Boolean(chapter?.files?.audio);
  const hasDoc = Boolean(chapter?.files?.document);

  const [whisperModel, setWhisperModel] = useState(chapter?.processing?.whisper_model || "base");
  const [mode, setMode] = useState("both");
  const [forceReprocess, setForceReprocess] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [metadataDetail, setMetadataDetail] = useState(null);

  useEffect(() => {
    if (hasAudio && hasDoc) setMode("both");
    else if (hasAudio && !hasDoc) setMode("audio_only");
    else if (!hasAudio && hasDoc) setMode("pdf_only");
  }, [hasAudio, hasDoc, chapter?.lecture_id]);

  const pState = chapter?.processing || {};
  const status = pState.status || "not_started";
  const isRunning = status === "processing" || status === "queued";

  useEffect(() => {
    let cancelled = false;
    if (subject && chapter && (status === "completed" || status === "outdated")) {
      apiClient
        .getLectureMetadata(subject.subject_id, chapter.lecture_id)
        .then((res) => {
          if (!cancelled) setMetadataDetail(res);
        })
        .catch(() => {});
    } else {
      setMetadataDetail(null);
    }
    return () => {
      cancelled = true;
    };
  }, [subject?.subject_id, chapter?.lecture_id, status, pState.total_chunks]);

  if (!subject || !chapter) return null;

  const handleRun = async (forceOverride = null) => {
    setSubmitting(true);
    try {
      await onStartProcessing(subject.subject_id, chapter.lecture_id, {
        whisper_model: whisperModel,
        force_reprocess: forceOverride !== null ? forceOverride : forceReprocess,
        audio_only: mode === "audio_only",
        pdf_only: mode === "pdf_only",
      });
    } finally {
      setSubmitting(false);
    }
  };

  const canRun =
    !isRunning &&
    !submitting &&
    ((mode === "both" && hasAudio && hasDoc) ||
      (mode === "audio_only" && hasAudio) ||
      (mode === "pdf_only" && hasDoc));

  const concepts = metadataDetail?.dataset_metadata?.lecture_concepts || [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <div className="section-header">
        <div>
          <h1 className="section-title">
            5. Lecture Processing & Knowledge Base — {chapter.title}{" "}
            <span className="code-chip">{chapter.lecture_id}</span>
          </h1>
          <p className="section-subtitle">
            Builds a strictly isolated FAISS vector index and chunk mapping inside{" "}
            <span className="code-chip">
              backend/data/lectures/{subject.subject_id}/{chapter.lecture_id}/knowledge_base/
            </span>
            .
          </p>
        </div>

        {status === "completed" && (
          <button type="button" className="btn btn-primary" onClick={onContinueToFeedback}>
            Continue to Student Feedback CSV <ArrowRight size={15} />
          </button>
        )}
      </div>

      {status === "outdated" && (
        <div className="banner banner-warning">
          <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <AlertTriangle size={16} />
            {pState.outdated_reason || "Source lecture files changed. Reprocess to refresh the knowledge base."}
          </span>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={!canRun}
            onClick={() => handleRun(true)}
          >
            Rebuild Knowledge Base
          </button>
        </div>
      )}

      {status === "failed" && (
        <div className="banner banner-error">
          <div>
            <strong>Processing Failed:</strong> {pState.error || "An unexpected error occurred."}
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={!canRun}
            onClick={() => handleRun(true)}
          >
            <RefreshCw size={13} /> Retry Processing
          </button>
        </div>
      )}

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <h3 style={{ margin: 0, fontSize: 16 }}>Pipeline Configuration</h3>
        <div className="form-row">
          <div className="field">
            <label htmlFor="proc-mode">Ingestion Source Mode</label>
            <select
              id="proc-mode"
              className="select"
              value={mode}
              disabled={isRunning}
              onChange={(e) => setMode(e.target.value)}
            >
              <option value="both">Standard: Audio + Slides/PDF (Recommended)</option>
              <option value="audio_only">Audio Only (Whisper Transcript)</option>
              <option value="pdf_only">Slides / PDF Only</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="whisper-model">Whisper Transcription Model</label>
            <select
              id="whisper-model"
              className="select"
              value={whisperModel}
              disabled={isRunning || mode === "pdf_only"}
              onChange={(e) => setWhisperModel(e.target.value)}
            >
              <option value="tiny">tiny (Fastest CPU)</option>
              <option value="base">base (Balanced Default)</option>
              <option value="small">small (Higher Accuracy)</option>
              <option value="medium">medium</option>
              <option value="large">large</option>
            </select>
          </div>

          <div className="field" style={{ justifyContent: "center", minWidth: 190 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginTop: 20 }}>
              <input
                type="checkbox"
                checked={forceReprocess}
                disabled={isRunning}
                onChange={(e) => setForceReprocess(e.target.checked)}
              />
              Force full re-extraction
            </label>
          </div>

          <button type="button" className="btn btn-primary" disabled={!canRun} onClick={() => handleRun()}>
            {isRunning ? (
              <>
                <Loader2 size={15} className="spin" /> Processing...
              </>
            ) : status === "completed" ? (
              <>
                <RefreshCw size={15} /> Reprocess Lecture
              </>
            ) : (
              <>
                <Play size={15} /> Process Lecture & Build KB
              </>
            )}
          </button>
        </div>

        {mode === "both" && (!hasAudio || !hasDoc) && (
          <div style={{ fontSize: 12.5, color: "var(--warning)" }}>
            Standard mode requires both Audio and Slides/PDF to be uploaded on Step 4 (or select Audio-Only / Slides-Only mode above).
          </div>
        )}
      </div>

      {/* Real Stage-Based Progress Tracker */}
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 16 }}>Live Stage Execution Status</h3>
            <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 2 }}>
              {pState.message || pState.stage || "Ready to execute pipeline."}
              {pState.current && pState.total ? ` (${pState.current} of ${pState.total})` : ""}
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {pState.elapsed_seconds !== undefined && pState.elapsed_seconds !== null && (
              <span className="code-chip">Elapsed: {pState.elapsed_seconds}s</span>
            )}
            <span className={`badge badge-${status === "completed" ? "completed" : status === "processing" ? "processing" : status === "failed" ? "failed" : "neutral"}`}>
              {status.toUpperCase()}
            </span>
          </div>
        </div>

        <div className="stage-list">
          {PIPELINE_STAGES.map((st) => {
            const curIdx = Number(pState.stage_index || 0);
            const isDone = status === "completed" || (isRunning && curIdx > st.num);
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
                  <span className="code-chip">{st.num}/5</span>
                )}
                <span>
                  Stage {st.num}: {st.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Knowledge Base Summary Card */}
      {metadataDetail?.kb_ready && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <Database size={20} style={{ color: "var(--success)" }} />
              <div>
                <h3 style={{ margin: 0, fontSize: 16 }}>
                  Isolated Lecture Knowledge Base Verified
                </h3>
                <div style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>
                  Last built: {formatDateTime(pState.last_processed_at)}
                </div>
              </div>
            </div>
            <span className="badge badge-completed">Strict Lecture Isolation Active</span>
          </div>

          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-label">Total FAISS Vectors</div>
              <div className="stat-value">{pState.total_chunks || 0}</div>
              <div className="stat-sub">all-MiniLM-L6-v2 (384-d)</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Audio Transcript Chunks</div>
              <div className="stat-value">{pState.transcript_chunks || 0}</div>
              <div className="stat-sub">Timestamp-preserved</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">PDF / Slide Chunks</div>
              <div className="stat-value">{pState.pdf_chunks || 0}</div>
              <div className="stat-sub">Page-aware chunks</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Derived Concept Units</div>
              <div className="stat-value">{concepts.length}</div>
              <div className="stat-sub">Dynamic coverage rubric</div>
            </div>
          </div>

          <div style={{ fontSize: 12, color: "var(--text-secondary)", display: "grid", gap: 4 }}>
            <div>
              <strong>FAISS Index:</strong>{" "}
              <span className="mono">{metadataDetail.paths?.faiss_index}</span>
            </div>
            <div>
              <strong>Embeddings:</strong>{" "}
              <span className="mono">{metadataDetail.paths?.embeddings}</span>
            </div>
            <div>
              <strong>Chunk Mapping:</strong>{" "}
              <span className="mono">{metadataDetail.paths?.chunk_mapping}</span>
            </div>
          </div>

          {concepts.length > 0 && (
            <div>
              <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 8 }}>
                Derived Lecture Concept Units (Used for Dynamic 3-Mark Coverage Scoring):
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {concepts.map((u) => (
                  <span key={u.unit_id} className="badge badge-neutral">
                    <strong>{u.unit_id}:</strong> {u.label}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

