/**
 * Browser-side persistence layer built on native IndexedDB (NO localStorage for files).
 * Stores navigation context, synchronized teacher/subject/chapter records,
 * uploaded File/Blob handles, and cached evaluation results so the application
 * survives page reloads and restores active workflows seamlessly.
 */

const DB_NAME = "LectureFeedbackSystemIDB";
const DB_VERSION = 1;

const STORES = {
  NAVIGATION: "navigation",
  TEACHERS: "teachers",
  SUBJECTS: "subjects",
  UPLOADED_FILES: "uploaded_files",
  RESULTS_CACHE: "results_cache",
};

function openDatabase() {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB is not supported in this browser environment."));
      return;
    }
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains(STORES.NAVIGATION)) {
        db.createObjectStore(STORES.NAVIGATION, { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains(STORES.TEACHERS)) {
        db.createObjectStore(STORES.TEACHERS, { keyPath: "teacher_id" });
      }
      if (!db.objectStoreNames.contains(STORES.SUBJECTS)) {
        db.createObjectStore(STORES.SUBJECTS, { keyPath: "subject_id" });
      }
      if (!db.objectStoreNames.contains(STORES.UPLOADED_FILES)) {
        const fileStore = db.createObjectStore(STORES.UPLOADED_FILES, { keyPath: "record_key" });
        fileStore.createIndex("by_subject", "subject_id", { unique: false });
        fileStore.createIndex("by_lecture", ["subject_id", "lecture_id"], { unique: false });
      }
      if (!db.objectStoreNames.contains(STORES.RESULTS_CACHE)) {
        db.createObjectStore(STORES.RESULTS_CACHE, { keyPath: "cache_key" });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Failed to open IndexedDB."));
  });
}

async function runTx(storeNames, mode, callback) {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const names = Array.isArray(storeNames) ? storeNames : [storeNames];
    const tx = db.transaction(names, mode);
    let result;
    try {
      result = callback(tx);
    } catch (err) {
      db.close();
      reject(err);
      return;
    }
    tx.oncomplete = async () => {
      db.close();
      try {
        resolve(await result);
      } catch (err) {
        reject(err);
      }
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error || new Error("IndexedDB transaction failed."));
    };
  });
}

function reqToPromise(req) {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

// ============================================================================
// Navigation & Active Session State
// ============================================================================

export async function saveNavigationState(state) {
  return runTx(STORES.NAVIGATION, "readwrite", (tx) => {
    const store = tx.objectStore(STORES.NAVIGATION);
    store.put({
      id: "active_session",
      ...state,
      updated_at: new Date().toISOString(),
    });
  });
}

export async function loadNavigationState() {
  try {
    return await runTx(STORES.NAVIGATION, "readonly", (tx) =>
      reqToPromise(tx.objectStore(STORES.NAVIGATION).get("active_session"))
    );
  } catch {
    return null;
  }
}

// ============================================================================
// Workspace Sync Persistence (Teachers & Subjects)
// ============================================================================

export async function persistWorkspaceSnapshot({ teachers = [], subjects = [] }) {
  return runTx([STORES.TEACHERS, STORES.SUBJECTS], "readwrite", (tx) => {
    const tStore = tx.objectStore(STORES.TEACHERS);
    const sStore = tx.objectStore(STORES.SUBJECTS);
    tStore.clear();
    sStore.clear();
    for (const t of teachers) {
      tStore.put(t);
    }
    for (const s of subjects) {
      sStore.put(s);
    }
  });
}

export async function loadCachedWorkspaceSnapshot() {
  try {
    return await runTx([STORES.TEACHERS, STORES.SUBJECTS], "readonly", async (tx) => {
      const teachers = await reqToPromise(tx.objectStore(STORES.TEACHERS).getAll());
      const subjects = await reqToPromise(tx.objectStore(STORES.SUBJECTS).getAll());
      return { teachers: teachers || [], subjects: subjects || [] };
    });
  } catch {
    return { teachers: [], subjects: [] };
  }
}

// ============================================================================
// Uploaded File Blob Records (Audio, PDF/PPTX, Feedback CSV)
// ============================================================================

export function makeFileKey(subjectId, lectureId, kind) {
  return `${subjectId}::${lectureId}::${kind}`;
}

export async function saveUploadedFileBlob(subjectId, lectureId, kind, fileObj, serverMeta = {}) {
  const recordKey = makeFileKey(subjectId, lectureId, kind);
  const blobCopy = fileObj instanceof Blob ? fileObj : null;
  const record = {
    record_key: recordKey,
    subject_id: subjectId,
    lecture_id: lectureId,
    kind,
    filename: fileObj?.name || serverMeta?.filename || "uploaded_file",
    size_bytes: fileObj?.size ?? serverMeta?.size_bytes ?? 0,
    mime_type: fileObj?.type || "application/octet-stream",
    uploaded_at: serverMeta?.uploaded_at || new Date().toISOString(),
    sha256: serverMeta?.sha256 || null,
    blob: blobCopy,
  };
  return runTx(STORES.UPLOADED_FILES, "readwrite", (tx) => {
    tx.objectStore(STORES.UPLOADED_FILES).put(record);
  });
}

export async function getUploadedFileRecord(subjectId, lectureId, kind) {
  try {
    const recordKey = makeFileKey(subjectId, lectureId, kind);
    return await runTx(STORES.UPLOADED_FILES, "readonly", (tx) =>
      reqToPromise(tx.objectStore(STORES.UPLOADED_FILES).get(recordKey))
    );
  } catch {
    return null;
  }
}

export async function getLectureLocalFiles(subjectId, lectureId) {
  const kinds = ["audio", "document", "feedback_csv"];
  const map = {};
  for (const k of kinds) {
    const rec = await getUploadedFileRecord(subjectId, lectureId, k);
    if (rec) {
      map[k] = {
        filename: rec.filename,
        size_bytes: rec.size_bytes,
        mime_type: rec.mime_type,
        uploaded_at: rec.uploaded_at,
        has_local_blob: Boolean(rec.blob),
      };
    }
  }
  return map;
}

export async function removeUploadedFileRecord(subjectId, lectureId, kind) {
  const recordKey = makeFileKey(subjectId, lectureId, kind);
  return runTx(STORES.UPLOADED_FILES, "readwrite", (tx) => {
    tx.objectStore(STORES.UPLOADED_FILES).delete(recordKey);
  });
}

export async function removeLectureRecordsFromIdb(subjectId, lectureId) {
  return runTx([STORES.UPLOADED_FILES, STORES.RESULTS_CACHE], "readwrite", async (tx) => {
    const fStore = tx.objectStore(STORES.UPLOADED_FILES);
    for (const kind of ["audio", "document", "feedback_csv"]) {
      fStore.delete(makeFileKey(subjectId, lectureId, kind));
    }
    const rStore = tx.objectStore(STORES.RESULTS_CACHE);
    const allKeys = await reqToPromise(rStore.getAllKeys());
    const prefix = `${subjectId}::${lectureId}`;
    for (const key of allKeys || []) {
      if (String(key).startsWith(prefix)) {
        rStore.delete(key);
      }
    }
  });
}

export async function removeSubjectRecordsFromIdb(subjectId) {
  return runTx([STORES.SUBJECTS, STORES.UPLOADED_FILES, STORES.RESULTS_CACHE], "readwrite", async (tx) => {
    tx.objectStore(STORES.SUBJECTS).delete(subjectId);
    const fStore = tx.objectStore(STORES.UPLOADED_FILES);
    const fKeys = await reqToPromise(fStore.getAllKeys());
    for (const key of fKeys || []) {
      if (String(key).startsWith(`${subjectId}::`)) {
        fStore.delete(key);
      }
    }
    const rStore = tx.objectStore(STORES.RESULTS_CACHE);
    const rKeys = await reqToPromise(rStore.getAllKeys());
    for (const key of rKeys || []) {
      if (String(key).startsWith(`${subjectId}::`)) {
        rStore.delete(key);
      }
    }
  });
}

// ============================================================================
// Results Cache
// ============================================================================

export async function cacheLectureResults(subjectId, lectureId, resultsPayload) {
  const cacheKey = `${subjectId}::${lectureId}::summary`;
  return runTx(STORES.RESULTS_CACHE, "readwrite", (tx) => {
    tx.objectStore(STORES.RESULTS_CACHE).put({
      cache_key: cacheKey,
      cached_at: new Date().toISOString(),
      payload: resultsPayload,
    });
  });
}

export async function getCachedLectureResults(subjectId, lectureId) {
  try {
    const cacheKey = `${subjectId}::${lectureId}::summary`;
    const rec = await runTx(STORES.RESULTS_CACHE, "readonly", (tx) =>
      reqToPromise(tx.objectStore(STORES.RESULTS_CACHE).get(cacheKey))
    );
    return rec?.payload || null;
  } catch {
    return null;
  }
}

export async function cacheStudentDetail(subjectId, lectureId, studentId, detailPayload) {
  const cacheKey = `${subjectId}::${lectureId}::student::${studentId}`;
  return runTx(STORES.RESULTS_CACHE, "readwrite", (tx) => {
    tx.objectStore(STORES.RESULTS_CACHE).put({
      cache_key: cacheKey,
      cached_at: new Date().toISOString(),
      payload: detailPayload,
    });
  });
}

export async function getCachedStudentDetail(subjectId, lectureId, studentId) {
  try {
    const cacheKey = `${subjectId}::${lectureId}::student::${studentId}`;
    const rec = await runTx(STORES.RESULTS_CACHE, "readonly", (tx) =>
      reqToPromise(tx.objectStore(STORES.RESULTS_CACHE).get(cacheKey))
    );
    return rec?.payload || null;
  } catch {
    return null;
  }
}

