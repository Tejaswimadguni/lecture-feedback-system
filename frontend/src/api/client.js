const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

async function requestJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    let errMsg = `Request failed (${response.status})`;
    try {
      const errBody = await response.json();
      if (errBody?.detail) {
        errMsg =
          typeof errBody.detail === "string"
            ? errBody.detail
            : JSON.stringify(errBody.detail);
      }
    } catch {
      const txt = await response.text().catch(() => "");
      if (txt) errMsg = txt;
    }
    const err = new Error(errMsg);
    err.status = response.status;
    throw err;
  }

  return response.json();
}

export const apiClient = {
  health: () => requestJson("/api/health"),

  syncWorkspace: (teacherId = "all") =>
    requestJson(`/api/sync${teacherId && teacherId !== "all" ? `?teacher_id=${encodeURIComponent(teacherId)}` : ""}`),

  // Teachers
  listTeachers: () => requestJson("/api/teachers"),
  createTeacher: (name, department) =>
    requestJson("/api/teachers", {
      method: "POST",
      body: JSON.stringify({ name, department }),
    }),

  // Subjects
  listSubjects: (teacherId = "all") =>
    requestJson(`/api/subjects${teacherId && teacherId !== "all" ? `?teacher_id=${encodeURIComponent(teacherId)}` : ""}`),
  createSubject: ({ name, code, teacher_id }) =>
    requestJson("/api/subjects", {
      method: "POST",
      body: JSON.stringify({ name, code: code || null, teacher_id }),
    }),
  renameSubject: (subjectId, name) =>
    requestJson(`/api/subjects/${encodeURIComponent(subjectId)}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),
  deleteSubject: (subjectId) =>
    requestJson(`/api/subjects/${encodeURIComponent(subjectId)}?confirm=true`, {
      method: "DELETE",
    }),

  // Chapters / Lectures
  createChapter: (subjectId, title) =>
    requestJson(`/api/subjects/${encodeURIComponent(subjectId)}/chapters`, {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  getChapter: (subjectId, lectureId) =>
    requestJson(
      `/api/subjects/${encodeURIComponent(subjectId)}/chapters/${encodeURIComponent(lectureId)}`
    ),
  renameChapter: (subjectId, lectureId, title) =>
    requestJson(
      `/api/subjects/${encodeURIComponent(subjectId)}/chapters/${encodeURIComponent(lectureId)}`,
      {
        method: "PATCH",
        body: JSON.stringify({ title }),
      }
    ),
  deleteChapter: (subjectId, lectureId) =>
    requestJson(
      `/api/subjects/${encodeURIComponent(subjectId)}/chapters/${encodeURIComponent(lectureId)}?confirm=true`,
      { method: "DELETE" }
    ),

  // Lecture Media Uploads
  uploadAudio: (subjectId, lectureId, file) => {
    const form = new FormData();
    form.append("file", file);
    return requestJson(
      `/api/subjects/${encodeURIComponent(subjectId)}/chapters/${encodeURIComponent(lectureId)}/upload/audio`,
      { method: "POST", body: form }
    );
  },
  uploadDocument: (subjectId, lectureId, file) => {
    const form = new FormData();
    form.append("file", file);
    return requestJson(
      `/api/subjects/${encodeURIComponent(subjectId)}/chapters/${encodeURIComponent(lectureId)}/upload/document`,
      { method: "POST", body: form }
    );
  },
  removeFile: (subjectId, lectureId, fileKind) =>
    requestJson(
      `/api/subjects/${encodeURIComponent(subjectId)}/chapters/${encodeURIComponent(lectureId)}/files/${encodeURIComponent(fileKind)}`,
      { method: "DELETE" }
    ),

  // Processing & Knowledge Base
  startProcessing: (subjectId, lectureId, options) =>
    requestJson(
      `/api/subjects/${encodeURIComponent(subjectId)}/chapters/${encodeURIComponent(lectureId)}/process`,
      {
        method: "POST",
        body: JSON.stringify(options),
      }
    ),
  getProcessingStatus: (subjectId, lectureId) =>
    requestJson(
      `/api/subjects/${encodeURIComponent(subjectId)}/chapters/${encodeURIComponent(lectureId)}/process/status`
    ),
  getLectureMetadata: (subjectId, lectureId) =>
    requestJson(
      `/api/subjects/${encodeURIComponent(subjectId)}/chapters/${encodeURIComponent(lectureId)}/metadata`
    ),

  // Feedback CSV Upload & Validation
  uploadFeedbackCsv: (subjectId, lectureId, file) => {
    const form = new FormData();
    form.append("file", file);
    return requestJson(
      `/api/subjects/${encodeURIComponent(subjectId)}/chapters/${encodeURIComponent(lectureId)}/feedback/upload`,
      { method: "POST", body: form }
    );
  },
  previewFeedbackCsv: (subjectId, lectureId, studentIdCol, feedbackCol) => {
    const params = new URLSearchParams();
    if (studentIdCol) params.set("student_id_column", studentIdCol);
    if (feedbackCol) params.set("feedback_column", feedbackCol);
    const qs = params.toString() ? `?${params.toString()}` : "";
    return requestJson(
      `/api/subjects/${encodeURIComponent(subjectId)}/chapters/${encodeURIComponent(lectureId)}/feedback/preview${qs}`
    );
  },
  confirmFeedbackColumns: (subjectId, lectureId, studentIdCol, feedbackCol) =>
    requestJson(
      `/api/subjects/${encodeURIComponent(subjectId)}/chapters/${encodeURIComponent(lectureId)}/feedback/confirm`,
      {
        method: "POST",
        body: JSON.stringify({
          student_id_column: studentIdCol,
          feedback_column: feedbackCol,
        }),
      }
    ),

  // Evaluation
  startEvaluation: (subjectId, lectureId, options) =>
    requestJson(
      `/api/subjects/${encodeURIComponent(subjectId)}/chapters/${encodeURIComponent(lectureId)}/evaluate`,
      {
        method: "POST",
        body: JSON.stringify(options),
      }
    ),
  getEvaluationStatus: (subjectId, lectureId) =>
    requestJson(
      `/api/subjects/${encodeURIComponent(subjectId)}/chapters/${encodeURIComponent(lectureId)}/evaluate/status`
    ),

  // Results & Student Detail
  getResults: (subjectId, lectureId) =>
    requestJson(
      `/api/subjects/${encodeURIComponent(subjectId)}/chapters/${encodeURIComponent(lectureId)}/results`
    ),
  getStudentResult: (subjectId, lectureId, studentId) =>
    requestJson(
      `/api/subjects/${encodeURIComponent(subjectId)}/chapters/${encodeURIComponent(lectureId)}/results/${encodeURIComponent(studentId)}`
    ),

  // Download Reports & Backup
  getExportUrl: (subjectId, lectureId, format = "csv", studentId = null) => {
    const params = new URLSearchParams({ format });
    if (studentId) params.set("student_id", studentId);
    return `${API_BASE}/api/subjects/${encodeURIComponent(subjectId)}/chapters/${encodeURIComponent(lectureId)}/results/export?${params.toString()}`;
  },
  getBackupExportUrl: (includeKb = false) =>
    `${API_BASE}/api/backup/export?include_knowledge_base=${includeKb ? "true" : "false"}`,
  restoreBackupZip: (file) => {
    const form = new FormData();
    form.append("file", file);
    return requestJson("/api/backup/restore", { method: "POST", body: form });
  },
};

export function formatBytes(bytes) {
  if (bytes === null || bytes === undefined || Number.isNaN(Number(bytes))) return "—";
  const n = Number(bytes);
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

export function formatDateTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

