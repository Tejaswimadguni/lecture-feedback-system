import React, { useState } from "react";
import { UserPlus, ArrowRight, CheckCircle2, BookOpen } from "lucide-react";

export function TeacherSelectionView({
  teachers,
  selectedTeacherId,
  onSelectTeacher,
  onCreateTeacher,
}) {
  const [name, setName] = useState("");
  const [department, setDepartment] = useState("");
  const [creating, setCreating] = useState(false);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    try {
      await onCreateTeacher(name.trim(), department.trim() || "Computer Science & Engineering");
      setName("");
      setDepartment("");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <div className="section-header">
        <div>
          <h1 className="section-title">1. Teacher Profile Selection</h1>
          <p className="section-subtitle">
            Select a faculty profile to organize subjects and chapters locally (no login required).
            Existing CLI lectures are automatically available under Workspace Faculty.
          </p>
        </div>
      </div>

      <div className="grid-3">
        {teachers.map((t) => {
          const isSelected = t.teacher_id === selectedTeacherId;
          return (
            <div
              key={t.teacher_id}
              className={`selectable-card ${isSelected ? "selected" : ""}`}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div
                    style={{
                      width: 44,
                      height: 44,
                      borderRadius: 12,
                      background: isSelected ? "var(--primary)" : "#e2e8f0",
                      color: isSelected ? "#fff" : "#1e293b",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontWeight: 700,
                      fontSize: 15,
                    }}
                  >
                    {t.avatar_initials || "TC"}
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 15.5 }}>{t.name}</div>
                    <div style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>
                      {t.department}
                    </div>
                  </div>
                </div>
                {isSelected && (
                  <span className="badge badge-completed">
                    <CheckCircle2 size={13} /> Active
                  </span>
                )}
              </div>

              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  paddingTop: 10,
                  borderTop: "1px solid var(--border)",
                  marginTop: "auto",
                }}
              >
                <span style={{ fontSize: 12.5, color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 6 }}>
                  <BookOpen size={14} /> {t.subject_count || 0} Subject(s)
                </span>
                <button
                  type="button"
                  className={`btn btn-sm ${isSelected ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => onSelectTeacher(t.teacher_id, true)}
                >
                  {isSelected ? "Continue to Subjects" : "Select Profile"}
                  <ArrowRight size={14} />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="card">
        <h3 style={{ margin: "0 0 12px", fontSize: 16, display: "flex", alignItems: "center", gap: 8 }}>
          <UserPlus size={18} /> Add Faculty Profile
        </h3>
        <form className="form-row" onSubmit={handleCreate}>
          <div className="field">
            <label htmlFor="teacher-name">Faculty Name *</label>
            <input
              id="teacher-name"
              className="input"
              placeholder="e.g., Dr. Meera Krishnan"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="teacher-dept">Department / Specialization</label>
            <input
              id="teacher-dept"
              className="input"
              placeholder="e.g., Artificial Intelligence & ML"
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
            />
          </div>
          <button type="submit" className="btn btn-primary" disabled={creating || !name.trim()}>
            <UserPlus size={15} />
            {creating ? "Creating..." : "Create Profile"}
          </button>
        </form>
      </div>
    </div>
  );
}

