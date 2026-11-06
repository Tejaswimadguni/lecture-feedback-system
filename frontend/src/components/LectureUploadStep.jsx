import React, { useRef, useState } from "react";
import {
  FileAudio,
  FileText,
  UploadCloud,
  Trash2,
  RefreshCw,
  ArrowRight,
  HardDrive,
  AlertTriangle,
} from "lucide-react";
import { formatBytes, formatDateTime } from "../api/client";
import { ConfirmModal } from "./Modals";

const AUDIO_EXTS = [".mp3", ".wav", ".m4a", ".mp4", ".flac", ".ogg", ".mkv", ".webm"];
const DOC_EXTS = [".pdf", ".pptx"];

export function LectureUploadStep({
  subject,
  chapter,
  localIdbFiles,
  onUploadMedia,
  onRemoveMedia,
  onContinueToProcessing,
}) {
  const audioInputRef = useRef(null);
  const docInputRef = useRef(null);

  const [uploadingKind, setUploadingKind] = useState(null);
  const [localError, setLocalError] = useState(null);
  const [removeTarget, setRemoveTarget] = useState(null);

  if (!subject || !chapter) return null;

  const audioFile = chapter.files?.audio;
  const docFile = chapter.files?.document;
  const pStatus = chapter.processing?.status || "not_started";

  const validateAndSend = async (kind, file) => {
    setLocalError(null);
    if (!file) return;
    const lower = file.name.toLowerCase();
    const allowed = kind === "audio" ? AUDIO_EXTS : DOC_EXTS;
    const matches = allowed.some((ext) => lower.endsWith(ext));
    if (!matches) {
      setLocalError(
        `Unsupported ${kind === "audio" ? "audio/video" : "document"} format for '${
          file.name
        }'. Supported: ${allowed.join(", ")}`
      );
      return;
    }
    if (file.size === 0) {
      setLocalError(`Selected file '${file.name}' is empty (0 bytes).`);
      return;
    }
    const maxBytes = (kind === "audio" ? 500 : 150) * 1024 * 1024;
    if (file.size > maxBytes) {
      setLocalError(
        `File '${file.name}' exceeds maximum size of ${kind === "audio" ? "500 MB" : "150 MB"}.`
      );
      return;
    }

    setUploadingKind(kind);
    try {
      await onUploadMedia(subject.subject_id, chapter.lecture_id, kind, file);
    } catch (err) {
      setLocalError(err.message || "File upload failed.");
    } finally {
      setUploadingKind(null);
    }
  };

  const renderMediaCard = ({
    kind,
    title,
    subtitle,
    accept,
    icon,
    fileMeta,
    inputRef,
    localRec,
  }) => {
    const isBusy = uploadingKind === kind;
    return (
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {icon}
            <div>
              <h3 style={{ margin: 0, fontSize: 16 }}>{title}</h3>
              <div style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>{subtitle}</div>
            </div>
          </div>
          {fileMeta ? (
            <span className="badge badge-completed">Uploaded</span>
          ) : (
            <span className="badge badge-neutral">Awaiting File</span>
          )}
        </div>

        <input
          ref={inputRef}
          type="file"
          accept={accept}
          style={{ display: "none" }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) validateAndSend(kind, f);
            e.target.value = "";
          }}
        />

        {!fileMeta ? (
          <div
            className="upload-zone"
            onClick={() => !isBusy && inputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && !isBusy && inputRef.current?.click()}
          >
            <UploadCloud size={28} style={{ color: "var(--primary)", marginBottom: 6 }} />
            <div style={{ fontWeight: 600, fontSize: 14 }}>
              {isBusy ? "Uploading & Saving to Disk + IndexedDB..." : `Click to Choose ${title}`}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }}>
              Arbitrary original filenames supported — stored in{" "}
              <span className="mono">
                lectures/{subject.subject_id}/{chapter.lecture_id}/raw/
              </span>
            </div>
          </div>
        ) : (
          <>
            <div className="file-meta-list">
              <div>
                <div style={{ color: "var(--text-muted)", fontSize: 11 }}>Uploaded Filename</div>
                <div style={{ fontWeight: 600, wordBreak: "break-all" }}>{fileMeta.filename}</div>
              </div>
              <div>
                <div style={{ color: "var(--text-muted)", fontSize: 11 }}>File Size</div>
                <div style={{ fontWeight: 600 }}>{formatBytes(fileMeta.size_bytes)}</div>
              </div>
              <div>
                <div style={{ color: "var(--text-muted)", fontSize: 11 }}>Upload Date</div>
                <div style={{ fontWeight: 500 }}>{formatDateTime(fileMeta.uploaded_at)}</div>
              </div>
              <div>
                <div style={{ color: "var(--text-muted)", fontSize: 11 }}>Processing Status</div>
                <div style={{ fontWeight: 600, textTransform: "capitalize" }}>
                  {pStatus.replace("_", " ")}
                </div>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
              <span style={{ fontSize: 12, color: "var(--text-secondary)", display: "inline-flex", alignItems: "center", gap: 5 }}>
                <HardDrive size={13} />
                {localRec?.has_local_blob
                  ? "Persisted in Backend Disk + Browser IndexedDB"
                  : "Authoritative on Backend Local Disk"}
              </span>

              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={isBusy}
                  onClick={() => inputRef.current?.click()}
                >
                  <RefreshCw size={13} className={isBusy ? "spin" : ""} />
                  {isBusy ? "Replacing..." : "Replace"}
                </button>
                <button
                  type="button"
                  className="btn btn-danger btn-sm"
                  disabled={isBusy}
                  onClick={() => setRemoveTarget({ kind, filename: fileMeta.filename })}
                >
                  <Trash2 size={13} /> Remove
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <div className="section-header">
        <div>
          <h1 className="section-title">
            4. Lecture File Upload — {chapter.title}{" "}
            <span className="code-chip">{chapter.lecture_id}</span>
          </h1>
          <p className="section-subtitle">
            Upload the lecture audio/video and slide deck (PDF or PPTX) for{" "}
            <strong>
              {subject.name} / {chapter.lecture_id}
            </strong>
            . Files are never shared with any other chapter.
          </p>
        </div>

        <button
          type="button"
          className="btn btn-primary"
          disabled={!audioFile && !docFile}
          onClick={onContinueToProcessing}
        >
          Continue to Lecture Processing <ArrowRight size={15} />
        </button>
      </div>

      {localError && (
        <div className="banner banner-error">
          <span>{localError}</span>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setLocalError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {pStatus === "outdated" && (
        <div className="banner banner-warning">
          <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <AlertTriangle size={16} />
            {chapter.processing?.outdated_reason ||
              "Lecture files changed since the knowledge base was built. Reprocess on the next step."}
          </span>
          <button type="button" className="btn btn-primary btn-sm" onClick={onContinueToProcessing}>
            Reprocess Now
          </button>
        </div>
      )}

      <div className="grid-2">
        {renderMediaCard({
          kind: "audio",
          title: "Lecture Audio / Video",
          subtitle: "Supported: MP3, WAV, M4A, MP4, FLAC, OGG, MKV, WEBM (up to 500 MB)",
          accept: AUDIO_EXTS.join(","),
          icon: <FileAudio size={24} style={{ color: "var(--primary)" }} />,
          fileMeta: audioFile,
          inputRef: audioInputRef,
          localRec: localIdbFiles?.audio,
        })}

        {renderMediaCard({
          kind: "document",
          title: "Lecture Slides / Notes (PDF or PPTX)",
          subtitle: "Supported: PDF (.pdf) and PowerPoint (.pptx) (up to 150 MB)",
          accept: DOC_EXTS.join(","),
          icon: <FileText size={24} style={{ color: "#4f46e5" }} />,
          fileMeta: docFile,
          inputRef: docInputRef,
          localRec: localIdbFiles?.document,
        })}
      </div>

      <ConfirmModal
        open={Boolean(removeTarget)}
        title={`Remove '${removeTarget?.filename || ""}'?`}
        description="This removes the raw file from this chapter's local directory and IndexedDB record. If a knowledge base already exists, it will be marked outdated until reprocessed."
        confirmLabel="Remove File"
        danger
        onCancel={() => setRemoveTarget(null)}
        onConfirm={async () => {
          const target = removeTarget;
          setRemoveTarget(null);
          await onRemoveMedia(subject.subject_id, chapter.lecture_id, target.kind);
        }}
      />
    </div>
  );
}

