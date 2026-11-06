import React, { useState } from "react";
import {
  FolderPlus,
  FolderOpen,
  Edit3,
  Trash2,
  Layers,
  Database,
  Award,
} from "lucide-react";
import { ConfirmModal, RenameModal } from "./Modals";

export function SubjectManagementView({
  selectedTeacher,
  subjects,
  showAllTeachers,
  onToggleShowAll,
  selectedSubjectId,
  onOpenSubject,
  onCreateSubject,
  onRenameSubject,
  onDeleteSubject,
}) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [creating, setCreating] = useState(false);

  const [renameTarget, setRenameTarget] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [modalBusy, setModalBusy] = useState(false);

  const visibleSubjects = showAllTeachers
    ? subjects
    : subjects.filter((s) => s.teacher_id === selectedTeacher?.teacher_id);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!name.trim() || !selectedTeacher) return;
    setCreating(true);
    try {
      await onCreateSubject({
        name: name.trim(),
        code: code.trim() || null,
        teacher_id: selectedTeacher.teacher_id,
      });
      setName("");
      setCode("");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <div className="section-header">
        <div>
          <h1 className="section-title">2. Subject Management</h1>
          <p className="section-subtitle">
            Create and manage subjects for <strong>{selectedTeacher?.name || "Selected Teacher"}</strong>.
            Every subject stores its lectures in an isolated filesystem namespace under{" "}
            <span className="code-chip">backend/data/lectures/&#123;subject_id&#125;/</span>.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            type="button"
            className={`btn btn-sm ${!showAllTeachers ? "btn-primary" : "btn-secondary"}`}
            onClick={() => onToggleShowAll(false)}
          >
            {selectedTeacher?.name || "My"} Subjects
          </button>
          <button
            type="button"
            className={`btn btn-sm ${showAllTeachers ? "btn-primary" : "btn-secondary"}`}
            onClick={() => onToggleShowAll(true)}
          >
            All Workspace Subjects ({subjects.length})
          </button>
        </div>
      </div>

      <div className="card">
        <h3 style={{ margin: "0 0 12px", fontSize: 16, display: "flex", alignItems: "center", gap: 8 }}>
          <FolderPlus size={18} /> Create New Subject
        </h3>
        <form className="form-row" onSubmit={handleCreate}>
          <div className="field" style={{ flex: 2 }}>
            <label htmlFor="subject-name">Subject Name *</label>
            <input
              id="subject-name"
              className="input"
              placeholder="e.g., Database Management Systems or Operating Systems"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="subject-code">Subject ID / Short Code (Optional)</label>
            <input
              id="subject-code"
              className="input"
              placeholder="e.g., DBMS or OS (auto-generated if blank)"
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          </div>
          <button type="submit" className="btn btn-primary" disabled={creating || !name.trim()}>
            <FolderPlus size={15} />
            {creating ? "Creating..." : "Create Subject"}
          </button>
        </form>
      </div>

      {visibleSubjects.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "38px 20px" }}>
          <p style={{ margin: 0, fontWeight: 600, fontSize: 15 }}>
            No subjects found for {selectedTeacher?.name || "this teacher"}.
          </p>
          <p style={{ margin: "6px 0 16px", fontSize: 13.5, color: "var(--text-secondary)" }}>
            Create your first subject above, or switch to All Workspace Subjects to view imported CLI lectures.
          </p>
          {!showAllTeachers && subjects.length > 0 && (
            <button type="button" className="btn btn-secondary" onClick={() => onToggleShowAll(true)}>
              Show All Workspace Subjects ({subjects.length})
            </button>
          )}
        </div>
      ) : (
        <div className="grid-3">
          {visibleSubjects.map((subj) => {
            const isSelected = subj.subject_id === selectedSubjectId;
            return (
              <div
                key={subj.subject_id}
                className={`selectable-card ${isSelected ? "selected" : ""}`}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
                  <div>
                    <span className="code-chip">{subj.subject_id}</span>
                    <h3 style={{ margin: "8px 0 0", fontSize: 17 }}>{subj.name}</h3>
                  </div>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      title="Rename subject"
                      onClick={() => setRenameTarget(subj)}
                    >
                      <Edit3 size={13} />
                    </button>
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      title="Delete subject"
                      onClick={() => setDeleteTarget(subj)}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>

                <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 12.5, color: "var(--text-secondary)" }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                    <Layers size={14} /> {subj.chapter_count} Chapter(s)
                  </span>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                    <Database size={14} /> {subj.processed_chapter_count} Indexed KB
                  </span>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                    <Award size={14} /> {subj.evaluated_chapter_count} Evaluated
                  </span>
                </div>

                <div
                  style={{
                    marginTop: "auto",
                    paddingTop: 12,
                    borderTop: "1px solid var(--border)",
                    display: "flex",
                    justifyContent: "flex-end",
                  }}
                >
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    onClick={() => onOpenSubject(subj.subject_id)}
                  >
                    <FolderOpen size={14} /> Open Chapters
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <RenameModal
        open={Boolean(renameTarget)}
        title={`Rename Subject (${renameTarget?.subject_id || ""})`}
        label="Subject Display Name"
        initialValue={renameTarget?.name || ""}
        busy={modalBusy}
        onCancel={() => setRenameTarget(null)}
        onSave={async (newName) => {
          setModalBusy(true);
          try {
            await onRenameSubject(renameTarget.subject_id, newName);
            setRenameTarget(null);
          } finally {
            setModalBusy(false);
          }
        }}
      />

      <ConfirmModal
        open={Boolean(deleteTarget)}
        title={`Delete Subject '${deleteTarget?.name || ""}'?`}
        description={`This permanently removes subject '${deleteTarget?.subject_id}' along with all ${
          deleteTarget?.chapter_count || 0
        } chapter(s), raw files, FAISS knowledge bases, and student evaluation results for this subject only.`}
        confirmLabel="Delete Subject"
        danger
        busy={modalBusy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={async () => {
          setModalBusy(true);
          try {
            await onDeleteSubject(deleteTarget.subject_id);
            setDeleteTarget(null);
          } finally {
            setModalBusy(false);
          }
        }}
      />
    </div>
  );
}

