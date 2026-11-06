import React, { useState, useEffect } from "react";

export function ConfirmModal({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}) {
  if (!open) return null;
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal-card">
        <div>
          <h3 style={{ margin: 0, fontSize: 18 }}>{title}</h3>
          <p style={{ margin: "8px 0 0", fontSize: 13.5, color: "var(--text-secondary)" }}>
            {description}
          </p>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className={`btn ${danger ? "btn-danger" : "btn-primary"}`}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? "Working..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export function RenameModal({
  open,
  title,
  label,
  initialValue = "",
  busy = false,
  onSave,
  onCancel,
}) {
  const [value, setValue] = useState(initialValue);

  useEffect(() => {
    if (open) setValue(initialValue || "");
  }, [open, initialValue]);

  if (!open) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!value.trim()) return;
    onSave(value.trim());
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <form className="modal-card" onSubmit={handleSubmit}>
        <h3 style={{ margin: 0, fontSize: 18 }}>{title}</h3>
        <div className="field">
          <label>{label}</label>
          <input
            className="input"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            autoFocus
            required
          />
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy || !value.trim()}>
            {busy ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </form>
    </div>
  );
}

