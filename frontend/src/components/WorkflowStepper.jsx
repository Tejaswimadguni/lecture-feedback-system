import React from "react";
import {
  GraduationCap,
  Check,
  Download,
  Upload,
  RefreshCw,
} from "lucide-react";

export const WORKFLOW_STEPS = [
  { key: "teachers", label: "Teacher Selection", num: 1, requiresSubject: false, requiresChapter: false },
  { key: "subjects", label: "Subject Management", num: 2, requiresSubject: false, requiresChapter: false },
  { key: "chapters", label: "Chapter Management", num: 3, requiresSubject: true, requiresChapter: false },
  { key: "upload", label: "Lecture Upload", num: 4, requiresSubject: true, requiresChapter: true },
  { key: "processing", label: "Lecture Processing", num: 5, requiresSubject: true, requiresChapter: true },
  { key: "feedback", label: "Student Feedback CSV", num: 6, requiresSubject: true, requiresChapter: true },
  { key: "evaluation", label: "Evaluation Run", num: 7, requiresSubject: true, requiresChapter: true },
  { key: "results", label: "Verification Results", num: 8, requiresSubject: true, requiresChapter: true },
];

export function WorkflowSidebar({
  activeStep,
  onSelectStep,
  selectedTeacher,
  selectedSubject,
  selectedChapter,
  onSync,
  syncing,
  onExportBackup,
  onRestoreBackupFile,
}) {
  const isStepDone = (key) => {
    if (key === "teachers") return Boolean(selectedTeacher);
    if (key === "subjects") return Boolean(selectedSubject);
    if (key === "chapters") return Boolean(selectedChapter);
    if (!selectedChapter) return false;
    if (key === "upload") {
      return Boolean(selectedChapter.files?.audio || selectedChapter.files?.document);
    }
    if (key === "processing") {
      return selectedChapter.processing?.status === "completed";
    }
    if (key === "feedback") {
      return Boolean(selectedChapter.files?.feedback_csv);
    }
    if (key === "evaluation" || key === "results") {
      return selectedChapter.evaluation?.status === "completed";
    }
    return false;
  };

  return (
    <aside className="sidebar">
      <div className="brand-box">
        <div className="brand-icon">
          <GraduationCap size={22} />
        </div>
        <div>
          <div className="brand-title">LectureVerify Studio</div>
          <div className="brand-subtitle">Isolated FAISS + IndexedDB</div>
        </div>
      </div>

      <div className="context-card">
        <div className="context-row">
          <span className="context-label">Teacher</span>
          <span className="context-val" title={selectedTeacher?.name || "Not selected"}>
            {selectedTeacher?.name || "Select teacher"}
          </span>
        </div>
        <div className="context-row">
          <span className="context-label">Subject</span>
          <span className="context-val" title={selectedSubject?.name || "None"}>
            {selectedSubject ? `${selectedSubject.name} (${selectedSubject.subject_id})` : "None"}
          </span>
        </div>
        <div className="context-row">
          <span className="context-label">Lecture ID</span>
          <span className="context-val mono" title={selectedChapter?.lecture_id || "None"}>
            {selectedChapter ? selectedChapter.lecture_id : "None"}
          </span>
        </div>
      </div>

      <nav className="step-nav" aria-label="Workflow navigation">
        {WORKFLOW_STEPS.map((st) => {
          const disabled =
            (st.requiresSubject && !selectedSubject) ||
            (st.requiresChapter && !selectedChapter);
          const done = isStepDone(st.key);
          const active = activeStep === st.key;
          return (
            <button
              key={st.key}
              type="button"
              disabled={disabled}
              onClick={() => onSelectStep(st.key)}
              className={`step-btn ${active ? "active" : ""} ${done && !active ? "done" : ""}`}
            >
              <span className="step-num">{done && !active ? <Check size={12} /> : st.num}</span>
              <span>{st.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <button type="button" className="btn btn-ghost btn-sm" onClick={onSync} disabled={syncing}>
          <RefreshCw size={14} className={syncing ? "spin" : ""} />
          {syncing ? "Syncing Disk..." : "Sync Local Storage"}
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onExportBackup}>
          <Download size={14} />
          Export Backup (.zip)
        </button>
        <label className="btn btn-ghost btn-sm" style={{ cursor: "pointer" }}>
          <Upload size={14} />
          Restore Backup (.zip)
          <input
            type="file"
            accept=".zip"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onRestoreBackupFile(f);
              e.target.value = "";
            }}
          />
        </label>
      </div>
    </aside>
  );
}

