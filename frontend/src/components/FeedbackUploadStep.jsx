import React, { useEffect, useRef, useState } from "react";
import {
  FileSpreadsheet,
  UploadCloud,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  Trash2,
} from "lucide-react";
import { apiClient, formatBytes, formatDateTime } from "../api/client";

export function FeedbackUploadStep({
  subject,
  chapter,
  onUploadCsv,
  onConfirmColumns,
  onRemoveCsv,
  onContinueToEvaluation,
}) {
  const csvInputRef = useRef(null);
  const [preview, setPreview] = useState(null);
  const [studentIdCol, setStudentIdCol] = useState("");
  const [feedbackCol, setFeedbackCol] = useState("");
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState(null);

  const csvMeta = chapter?.files?.feedback_csv;

  useEffect(() => {
    let cancelled = false;
    if (subject && chapter && csvMeta?.filename) {
      setLoading(true);
      apiClient
        .previewFeedbackCsv(subject.subject_id, chapter.lecture_id)
        .then((res) => {
          if (cancelled) return;
          setPreview(res.preview);
          setStudentIdCol(res.preview.student_id_column || "");
          setFeedbackCol(res.preview.feedback_column || "");
        })
        .catch((err) => {
          if (!cancelled) setError(err.message);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    } else {
      setPreview(null);
      setStudentIdCol("");
      setFeedbackCol("");
    }
    return () => {
      cancelled = true;
    };
  }, [subject?.subject_id, chapter?.lecture_id, csvMeta?.filename, csvMeta?.sha256]);

  if (!subject || !chapter) return null;

  const handleFileChange = async (file) => {
    if (!file) return;
    setError(null);
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setError(`Unsupported format for '${file.name}'. Please upload a .csv file.`);
      return;
    }
    setLoading(true);
    try {
      const res = await onUploadCsv(subject.subject_id, chapter.lecture_id, file);
      if (res?.preview) {
        setPreview(res.preview);
        setStudentIdCol(res.preview.student_id_column || "");
        setFeedbackCol(res.preview.feedback_column || "");
      }
    } catch (err) {
      setError(err.message || "Failed to upload feedback CSV.");
    } finally {
      setLoading(false);
    }
  };

  const handleColumnChange = async (nextIdCol, nextFbCol) => {
    setStudentIdCol(nextIdCol);
    setFeedbackCol(nextFbCol);
    setError(null);
    try {
      const res = await apiClient.previewFeedbackCsv(
        subject.subject_id,
        chapter.lecture_id,
        nextIdCol,
        nextFbCol
      );
      setPreview(res.preview);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleConfirm = async () => {
    setConfirming(true);
    setError(null);
    try {
      const res = await onConfirmColumns(
        subject.subject_id,
        chapter.lecture_id,
        studentIdCol,
        feedbackCol
      );
      if (res?.preview) setPreview(res.preview);
    } catch (err) {
      setError(err.message || "Column confirmation failed.");
    } finally {
      setConfirming(false);
    }
  };

  const isValid = Boolean(preview?.validation?.is_valid);
  const isConfirmed = Boolean(preview?.confirmed);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <div className="section-header">
        <div>
          <h1 className="section-title">
            6. Student Feedback CSV Upload — {chapter.title}{" "}
            <span className="code-chip">{chapter.lecture_id}</span>
          </h1>
          <p className="section-subtitle">
            Upload any student feedback CSV for{" "}
            <strong>
              {subject.name} ({chapter.lecture_id})
            </strong>
            , preview student rows, map columns, and confirm before evaluation.
          </p>
        </div>

        {isValid && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={async () => {
              if (!isConfirmed) {
                await handleConfirm();
              }
              onContinueToEvaluation();
            }}
          >
            Continue to Evaluation <ArrowRight size={15} />
          </button>
        )}
      </div>

      {chapter.processing?.status !== "completed" && (
        <div className="banner banner-warning">
          <span>
            Note: Lecture knowledge base status is{" "}
            <strong>{chapter.processing?.status || "not_started"}</strong>. Make sure lecture processing
            is completed before running evaluation on Step 7.
          </span>
        </div>
      )}

      {error && (
        <div className="banner banner-error">
          <span>{error}</span>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <input
          ref={csvInputRef}
          type="file"
          accept=".csv"
          style={{ display: "none" }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFileChange(f);
            e.target.value = "";
          }}
        />

        {!csvMeta ? (
          <div
            className="upload-zone"
            onClick={() => !loading && csvInputRef.current?.click()}
            role="button"
            tabIndex={0}
          >
            <UploadCloud size={28} style={{ color: "var(--primary)", marginBottom: 6 }} />
            <div style={{ fontWeight: 600, fontSize: 14 }}>
              {loading ? "Uploading & Inspecting CSV..." : "Click to Upload Student Feedback CSV (.csv)"}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }}>
              Supports custom column names (e.g., <span className="mono">roll_number</span>,{" "}
              <span className="mono">student_id</span>, <span className="mono">feedback</span>,{" "}
              <span className="mono">reflection</span>).
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <FileSpreadsheet size={26} style={{ color: "var(--success)" }} />
              <div>
                <div style={{ fontWeight: 700 }}>{csvMeta.filename}</div>
                <div style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>
                  {formatBytes(csvMeta.size_bytes)} • {preview?.total_rows ?? csvMeta.total_rows} rows • Uploaded{" "}
                  {formatDateTime(csvMeta.uploaded_at)}
                </div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => csvInputRef.current?.click()}
                disabled={loading}
              >
                Replace CSV
              </button>
              <button
                type="button"
                className="btn btn-danger btn-sm"
                onClick={() => onRemoveCsv(subject.subject_id, chapter.lecture_id, "feedback_csv")}
                disabled={loading}
              >
                <Trash2 size={13} /> Remove
              </button>
            </div>
          </div>
        )}
      </div>

      {preview && (
        <>
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
              <h3 style={{ margin: 0, fontSize: 16 }}>Column Mapping & CSV Validation</h3>
              {isConfirmed ? (
                <span className="badge badge-completed">
                  <CheckCircle2 size={13} /> Mapping Confirmed ({preview.validation.valid_student_count} Students)
                </span>
              ) : isValid ? (
                <span className="badge badge-processing">Ready to Confirm</span>
              ) : (
                <span className="badge badge-failed">
                  <AlertCircle size={13} /> Validation Issues Found
                </span>
              )}
            </div>

            <div className="form-row">
              <div className="field">
                <label htmlFor="id-col-select">Student Identifier Column *</label>
                <select
                  id="id-col-select"
                  className="select"
                  value={studentIdCol}
                  onChange={(e) => handleColumnChange(e.target.value, feedbackCol)}
                >
                  {preview.headers.map((h) => (
                    <option key={h} value={h}>
                      {h}
                    </option>
                  ))}
                </select>
              </div>

              <div className="field">
                <label htmlFor="fb-col-select">Student Feedback Text Column *</label>
                <select
                  id="fb-col-select"
                  className="select"
                  value={feedbackCol}
                  onChange={(e) => handleColumnChange(studentIdCol, e.target.value)}
                >
                  {preview.headers.map((h) => (
                    <option key={h} value={h}>
                      {h}
                    </option>
                  ))}
                </select>
              </div>

              <button
                type="button"
                className="btn btn-primary"
                disabled={!isValid || confirming || isConfirmed}
                onClick={handleConfirm}
              >
                <CheckCircle2 size={15} />
                {isConfirmed
                  ? "Columns Confirmed"
                  : confirming
                  ? "Confirming..."
                  : "Confirm Column Mapping"}
              </button>
            </div>

            {!isValid && preview.validation?.errors?.length > 0 && (
              <div className="banner banner-error" style={{ flexDirection: "column", alignItems: "stretch" }}>
                <strong>
                  Fix {preview.validation.total_error_count} CSV validation error(s) before running evaluation:
                </strong>
                <ul style={{ margin: "6px 0 0", paddingLeft: 20 }}>
                  {preview.validation.errors.slice(0, 8).map((errStr, i) => (
                    <li key={i}>{errStr}</li>
                  ))}
                </ul>
              </div>
            )}

            {isValid && (
              <div className="banner banner-success">
                <span>
                  Validated <strong>{preview.validation.valid_student_count}</strong> unique student submissions
                  with zero duplicate IDs and zero empty feedback cells.
                </span>
              </div>
            )}
          </div>

          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <h3 style={{ margin: 0, fontSize: 16 }}>
              CSV Data Preview (Showing {preview.preview_rows.length} of {preview.total_rows} rows)
            </h3>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th style={{ width: 65 }}>CSV Row</th>
                    {preview.headers.map((h) => (
                      <th key={h}>
                        {h}{" "}
                        {h === studentIdCol && <span className="badge badge-processing">Student ID</span>}
                        {h === feedbackCol && <span className="badge badge-completed">Feedback</span>}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.preview_rows.map((r) => (
                    <tr key={r.row_number}>
                      <td className="mono">#{r.row_number}</td>
                      {preview.headers.map((h) => (
                        <td key={h} style={{ maxWidth: 460 }}>
                          {r.values[h] || <em style={{ color: "var(--danger)" }}>[Empty]</em>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

