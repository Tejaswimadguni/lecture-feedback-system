import React, { useState } from "react";
import {
  PlusCircle,
  UploadCloud,
  Cpu,
  BarChart3,
  Edit3,
  Trash2,
  AlertTriangle,
  CheckCircle2,
  Clock,
} from "lucide-react";
import { ConfirmModal, RenameModal } from "./Modals";

function statusBadge(status, labelOverride) {
  const map = {
    completed: { cls: "badge-completed", text: labelOverride || "Completed" },
    processing: { cls: "badge-processing", text: labelOverride || "Processing..." },
    evaluating: { cls: "badge-evaluating", text: labelOverride || "Evaluating..." },
    outdated: { cls: "badge-outdated", text: labelOverride || "Outdated KB" },
    failed: { cls: "badge-failed", text: labelOverride || "Failed" },
    not_started: { cls: "badge-neutral", text: labelOverride || "Not Started" },
  };
  const cfg = map[status] || map.not_started;
  return <span className={`badge ${cfg.cls}`}>{cfg.text}</span>;
}

export function ChapterManagementView({
  subject,
  selectedLectureId,
  onCreateChapter,
  onOpenChapterStep,
  onRenameChapter,
  onDeleteChapter,
}) {
  const [title, setTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [renameTarget, setRenameTarget] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [modalBusy, setModalBusy] = useState(false);

  if (!subject) return null;
  const chapters = subject.chapters || [];

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!title.trim()) return;
    setCreating(true);
    try {
      await onCreateChapter(subject.subject_id, title.trim());
      setTitle("");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <div className="section-header">
        <div>
          <h1 className="section-title">
            3. Chapters & Lectures — {subject.name}{" "}
            <span className="code-chip">{subject.subject_id}</span>
          </h1>
          <p className="section-subtitle">
            Each chapter generates a unique lecture ID (e.g.,{" "}
            <span className="code-chip">{subject.subject_id}_lect1</span>) and maintains a strictly
            independent FAISS knowledge base and results directory.
          </p>
        </div>
      </div>

      <div className="card">
        <h3 style={{ margin: "0 0 12px", fontSize: 16, display: "flex", alignItems: "center", gap: 8 }}>
          <PlusCircle size={18} /> Add Chapter / Lecture
        </h3>
        <form className="form-row" onSubmit={handleCreate}>
          <div className="field" style={{ flex: 2 }}>
            <label htmlFor="chapter-title">Chapter / Lecture Title *</label>
            <input
              id="chapter-title"
              className="input"
              placeholder="e.g., Normalization (1NF, 2NF, 3NF, BCNF) or SQL Joins"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
            />
          </div>
          <button type="submit" className="btn btn-primary" disabled={creating || !title.trim()}>
            <PlusCircle size={15} />
            {creating ? "Creating..." : "Create Chapter"}
          </button>
        </form>
      </div>

      {chapters.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "38px 20px" }}>
          <p style={{ margin: 0, fontWeight: 600, fontSize: 15 }}>
            No chapters created inside {subject.name} yet.
          </p>
          <p style={{ margin: "6px 0 0", fontSize: 13.5, color: "var(--text-secondary)" }}>
            Enter a lecture title above to automatically generate{" "}
            <span className="code-chip">{subject.subject_id}_lect1</span>.
          </p>
        </div>
      ) : (
        <div className="grid-2">
          {chapters.map((ch) => {
            const isSelected = ch.lecture_id === selectedLectureId;
            const pStatus = ch.processing?.status || "not_started";
            const eStatus = ch.evaluation?.status || "not_started";
            const hasAudio = Boolean(ch.files?.audio);
            const hasDoc = Boolean(ch.files?.document);

            return (
              <div
                key={ch.lecture_id}
                className={`selectable-card ${isSelected ? "selected" : ""}`}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <span className="code-chip">{ch.lecture_id}</span>
                      {statusBadge(
                        pStatus,
                        pStatus === "completed"
                          ? `KB Ready (${ch.processing?.total_chunks || 0} chunks)`
                          : undefined
                      )}
                      {eStatus === "completed" && (
                        <span className="badge badge-completed">
                          <CheckCircle2 size={12} /> {ch.evaluation?.total_students || 0} Students Evaluated
                        </span>
                      )}
                    </div>
                    <h3 style={{ margin: "10px 0 0", fontSize: 17 }}>{ch.title}</h3>
                  </div>

                  <div style={{ display: "flex", gap: 6 }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      title="Rename chapter"
                      onClick={() => setRenameTarget(ch)}
                    >
                      <Edit3 size={13} />
                    </button>
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      title="Delete chapter"
                      onClick={() => setDeleteTarget(ch)}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>

                {pStatus === "outdated" && (
                  <div className="banner banner-warning" style={{ padding: "8px 12px", fontSize: 12 }}>
                    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <AlertTriangle size={14} />
                      {ch.processing?.outdated_reason || "Source files changed — reprocess KB."}
                    </span>
                  </div>
                )}

                <div style={{ fontSize: 12.5, color: "var(--text-secondary)", display: "grid", gap: 4 }}>
                  <div>
                    <strong>Audio:</strong>{" "}
                    {hasAudio ? ch.files.audio.filename : <span style={{ color: "var(--text-muted)" }}>Not uploaded</span>}
                  </div>
                  <div>
                    <strong>Slides/PDF:</strong>{" "}
                    {hasDoc ? ch.files.document.filename : <span style={{ color: "var(--text-muted)" }}>Not uploaded</span>}
                  </div>
                  <div>
                    <strong>Isolated Path:</strong>{" "}
                    <span className="mono">
                      backend/data/lectures/{subject.subject_id}/{ch.lecture_id}/
                    </span>
                  </div>
                </div>

                <div
                  style={{
                    marginTop: "auto",
                    paddingTop: 12,
                    borderTop: "1px solid var(--border)",
                    display: "flex",
                    gap: 8,
                    flexWrap: "wrap",
                    justifyContent: "flex-end",
                  }}
                >
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => onOpenChapterStep(ch.lecture_id, "upload")}
                  >
                    <UploadCloud size={14} /> Upload Files
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => onOpenChapterStep(ch.lecture_id, "processing")}
                  >
                    <Cpu size={14} /> Process KB
                  </button>
                  {eStatus === "completed" ? (
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      onClick={() => onOpenChapterStep(ch.lecture_id, "results")}
                    >
                      <BarChart3 size={14} /> View Results
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      onClick={() =>
                        onOpenChapterStep(
                          ch.lecture_id,
                          pStatus === "completed" ? "feedback" : "upload"
                        )
                      }
                    >
                      <Clock size={14} /> Open Workflow
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <RenameModal
        open={Boolean(renameTarget)}
        title={`Rename Chapter (${renameTarget?.lecture_id || ""})`}
        label="Chapter / Lecture Title"
        initialValue={renameTarget?.title || ""}
        busy={modalBusy}
        onCancel={() => setRenameTarget(null)}
        onSave={async (newTitle) => {
          setModalBusy(true);
          try {
            await onRenameChapter(subject.subject_id, renameTarget.lecture_id, newTitle);
            setRenameTarget(null);
          } finally {
            setModalBusy(false);
          }
        }}
      />

      <ConfirmModal
        open={Boolean(deleteTarget)}
        title={`Delete Chapter '${deleteTarget?.title || ""}'?`}
        description={`This deletes ONLY '${subject.subject_id}/${deleteTarget?.lecture_id}' (its raw files, FAISS index, and student evaluation results). All other lectures in '${subject.name}' remain untouched.`}
        confirmLabel="Delete Chapter"
        danger
        busy={modalBusy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={async () => {
          setModalBusy(true);
          try {
            await onDeleteChapter(subject.subject_id, deleteTarget.lecture_id);
            setDeleteTarget(null);
          } finally {
            setModalBusy(false);
          }
        }}
      />
    </div>
  );
}

