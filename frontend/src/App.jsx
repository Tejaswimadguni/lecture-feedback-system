import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronRight, HardDrive, WifiOff, RefreshCw, X } from "lucide-react";
import { apiClient } from "./api/client";
import {
  getLectureLocalFiles,
  loadCachedWorkspaceSnapshot,
  loadNavigationState,
  persistWorkspaceSnapshot,
  removeLectureRecordsFromIdb,
  removeSubjectRecordsFromIdb,
  removeUploadedFileRecord,
  saveNavigationState,
  saveUploadedFileBlob,
} from "./storage/indexedDb";
import { WORKFLOW_STEPS, WorkflowSidebar } from "./components/WorkflowStepper";
import { TeacherSelectionView } from "./components/TeacherSelectionView";
import { SubjectManagementView } from "./components/SubjectManagementView";
import { ChapterManagementView } from "./components/ChapterManagementView";
import { LectureUploadStep } from "./components/LectureUploadStep";
import { LectureProcessingStep } from "./components/LectureProcessingStep";
import { FeedbackUploadStep } from "./components/FeedbackUploadStep";
import { EvaluationStep } from "./components/EvaluationStep";
import { ResultsDashboardStep } from "./components/ResultsDashboardStep";

export default function App() {
  const [teachers, setTeachers] = useState([]);
  const [subjects, setSubjects] = useState([]);

  const [selectedTeacherId, setSelectedTeacherId] = useState("t_workspace");
  const [selectedSubjectId, setSelectedSubjectId] = useState(null);
  const [selectedLectureId, setSelectedLectureId] = useState(null);
  const [activeStep, setActiveStep] = useState("teachers");
  const [selectedStudentId, setSelectedStudentId] = useState(null);
  const [showAllTeachers, setShowAllTeachers] = useState(true);

  const [localIdbFiles, setLocalIdbFiles] = useState({});
  const [hydrated, setHydrated] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [backendError, setBackendError] = useState(null);
  const [toasts, setToasts] = useState([]);

  const pushToast = useCallback((message, type = "info") => {
    const id = `${Date.now()}_${Math.random()}`;
    setToasts((prev) => [...prev.slice(-3), { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4500);
  }, []);

  const syncFromBackend = useCallback(
    async (silent = false) => {
      if (!silent) setSyncing(true);
      try {
        const snap = await apiClient.syncWorkspace("all");
        setTeachers(snap.teachers || []);
        setSubjects(snap.subjects || []);
        setBackendError(null);
        await persistWorkspaceSnapshot({
          teachers: snap.teachers || [],
          subjects: snap.subjects || [],
        });
        return snap;
      } catch (err) {
        setBackendError(
          err.message ||
            "Cannot reach FastAPI backend at http://127.0.0.1:8000. Start backend server and click Retry."
        );
        return null;
      } finally {
        if (!silent) setSyncing(false);
      }
    },
    []
  );

  // Initial IndexedDB hydration + authoritative backend filesystem sync
  useEffect(() => {
    let mounted = true;
    (async () => {
      const [nav, cached] = await Promise.all([
        loadNavigationState(),
        loadCachedWorkspaceSnapshot(),
      ]);

      if (!mounted) return;
      if (cached.teachers.length > 0) setTeachers(cached.teachers);
      if (cached.subjects.length > 0) setSubjects(cached.subjects);

      if (nav) {
        if (nav.selectedTeacherId) setSelectedTeacherId(nav.selectedTeacherId);
        if (nav.selectedSubjectId) setSelectedSubjectId(nav.selectedSubjectId);
        if (nav.selectedLectureId) setSelectedLectureId(nav.selectedLectureId);
        if (nav.activeStep) setActiveStep(nav.activeStep);
        if (nav.selectedStudentId) setSelectedStudentId(nav.selectedStudentId);
        if (typeof nav.showAllTeachers === "boolean") setShowAllTeachers(nav.showAllTeachers);
      }

      const fresh = await syncFromBackend(false);
      if (!mounted) return;

      if (fresh) {
        const validTids = new Set((fresh.teachers || []).map((t) => t.teacher_id));
        const curTid = nav?.selectedTeacherId;
        if (!curTid || !validTids.has(curTid)) {
          const fallbackTid = fresh.teachers?.[0]?.teacher_id || "t_workspace";
          setSelectedTeacherId(fallbackTid);
        }

        const subjMap = new Map((fresh.subjects || []).map((s) => [s.subject_id, s]));
        const curSid = nav?.selectedSubjectId;
        if (curSid && !subjMap.has(curSid)) {
          setSelectedSubjectId(null);
          setSelectedLectureId(null);
          setActiveStep("subjects");
        } else if (curSid && nav?.selectedLectureId) {
          const subj = subjMap.get(curSid);
          const hasCh = (subj?.chapters || []).some(
            (c) => c.lecture_id === nav.selectedLectureId
          );
          if (!hasCh) {
            setSelectedLectureId(null);
            setActiveStep("chapters");
          }
        }
      }
      setHydrated(true);
    })();
    return () => {
      mounted = false;
    };
  }, [syncFromBackend]);

  // Persist navigation context in IndexedDB whenever it changes
  useEffect(() => {
    if (!hydrated) return;
    saveNavigationState({
      selectedTeacherId,
      selectedSubjectId,
      selectedLectureId,
      activeStep,
      selectedStudentId,
      showAllTeachers,
    }).catch(() => {});
  }, [
    hydrated,
    selectedTeacherId,
    selectedSubjectId,
    selectedLectureId,
    activeStep,
    selectedStudentId,
    showAllTeachers,
  ]);

  const selectedTeacher = useMemo(
    () => teachers.find((t) => t.teacher_id === selectedTeacherId) || teachers[0] || null,
    [teachers, selectedTeacherId]
  );

  const selectedSubject = useMemo(
    () => subjects.find((s) => s.subject_id === selectedSubjectId) || null,
    [subjects, selectedSubjectId]
  );

  const selectedChapter = useMemo(() => {
    if (!selectedSubject || !selectedLectureId) return null;
    return (
      (selectedSubject.chapters || []).find((c) => c.lecture_id === selectedLectureId) || null
    );
  }, [selectedSubject, selectedLectureId]);

  // Load IndexedDB file blob metadata for active chapter
  const refreshLocalFiles = useCallback(async (sid, lid) => {
    if (!sid || !lid) {
      setLocalIdbFiles({});
      return;
    }
    const recs = await getLectureLocalFiles(sid, lid);
    setLocalIdbFiles(recs);
  }, []);

  useEffect(() => {
    refreshLocalFiles(selectedSubjectId, selectedLectureId);
  }, [selectedSubjectId, selectedLectureId, refreshLocalFiles]);

  // Poll backend whenever any lecture has an active processing or evaluation job
  const hasActiveJob = useMemo(() => {
    return subjects.some((s) =>
      (s.chapters || []).some(
        (c) =>
          ["queued", "processing"].includes(c.processing?.status) ||
          ["queued", "evaluating"].includes(c.evaluation?.status)
      )
    );
  }, [subjects]);

  useEffect(() => {
    if (!hasActiveJob) return undefined;
    const timer = setInterval(() => {
      syncFromBackend(true);
    }, 1500);
    return () => clearInterval(timer);
  }, [hasActiveJob, syncFromBackend]);

  // =========================================================================
  // Action Handlers
  // =========================================================================

  const handleSelectTeacher = (teacherId, navigateNext = false) => {
    setSelectedTeacherId(teacherId);
    if (navigateNext) setActiveStep("subjects");
  };

  const handleCreateTeacher = async (name, department) => {
    try {
      const res = await apiClient.createTeacher(name, department);
      await syncFromBackend(true);
      setSelectedTeacherId(res.teacher.teacher_id);
      setShowAllTeachers(false);
      pushToast(`Created teacher profile '${res.teacher.name}'.`, "success");
    } catch (err) {
      pushToast(err.message, "error");
      throw err;
    }
  };

  const handleCreateSubject = async ({ name, code, teacher_id }) => {
    try {
      const res = await apiClient.createSubject({ name, code, teacher_id });
      await syncFromBackend(true);
      setSelectedSubjectId(res.subject.subject_id);
      setSelectedLectureId(null);
      setActiveStep("chapters");
      pushToast(
        `Created subject '${res.subject.name}' (${res.subject.subject_id}).`,
        "success"
      );
    } catch (err) {
      pushToast(err.message, "error");
      throw err;
    }
  };

  const handleRenameSubject = async (subjectId, newName) => {
    try {
      await apiClient.renameSubject(subjectId, newName);
      await syncFromBackend(true);
      pushToast(`Renamed subject '${subjectId}' to '${newName}'.`, "success");
    } catch (err) {
      pushToast(err.message, "error");
      throw err;
    }
  };

  const handleDeleteSubject = async (subjectId) => {
    try {
      await apiClient.deleteSubject(subjectId);
      await removeSubjectRecordsFromIdb(subjectId);
      if (selectedSubjectId === subjectId) {
        setSelectedSubjectId(null);
        setSelectedLectureId(null);
        setSelectedStudentId(null);
        setActiveStep("subjects");
      }
      await syncFromBackend(true);
      pushToast(`Deleted subject '${subjectId}' and its isolated files.`, "success");
    } catch (err) {
      pushToast(err.message, "error");
      throw err;
    }
  };

  const handleOpenSubject = (subjectId) => {
    setSelectedSubjectId(subjectId);
    setSelectedLectureId(null);
    setSelectedStudentId(null);
    setActiveStep("chapters");
  };

  const handleCreateChapter = async (subjectId, title) => {
    try {
      const res = await apiClient.createChapter(subjectId, title);
      await syncFromBackend(true);
      setSelectedLectureId(res.chapter.lecture_id);
      setSelectedStudentId(null);
      setActiveStep("upload");
      pushToast(
        `Created chapter '${res.chapter.title}' with ID '${res.chapter.lecture_id}'.`,
        "success"
      );
    } catch (err) {
      pushToast(err.message, "error");
      throw err;
    }
  };

  const handleRenameChapter = async (subjectId, lectureId, newTitle) => {
    try {
      await apiClient.renameChapter(subjectId, lectureId, newTitle);
      await syncFromBackend(true);
      pushToast(`Renamed chapter '${lectureId}' to '${newTitle}'.`, "success");
    } catch (err) {
      pushToast(err.message, "error");
      throw err;
    }
  };

  const handleDeleteChapter = async (subjectId, lectureId) => {
    try {
      await apiClient.deleteChapter(subjectId, lectureId);
      await removeLectureRecordsFromIdb(subjectId, lectureId);
      if (selectedLectureId === lectureId) {
        setSelectedLectureId(null);
        setSelectedStudentId(null);
        setActiveStep("chapters");
      }
      await syncFromBackend(true);
      pushToast(`Deleted chapter '${lectureId}'.`, "success");
    } catch (err) {
      pushToast(err.message, "error");
      throw err;
    }
  };

  const handleOpenChapterStep = (lectureId, stepKey) => {
    setSelectedLectureId(lectureId);
    setSelectedStudentId(null);
    setActiveStep(stepKey);
  };

  const handleUploadMedia = async (subjectId, lectureId, kind, file) => {
    const res =
      kind === "audio"
        ? await apiClient.uploadAudio(subjectId, lectureId, file)
        : await apiClient.uploadDocument(subjectId, lectureId, file);
    const serverMeta = res.chapter?.files?.[kind] || {};
    await saveUploadedFileBlob(subjectId, lectureId, kind, file, serverMeta);
    await refreshLocalFiles(subjectId, lectureId);
    await syncFromBackend(true);
    pushToast(`Uploaded '${file.name}' to ${subjectId}/${lectureId}.`, "success");
    return res;
  };

  const handleRemoveFile = async (subjectId, lectureId, kind) => {
    try {
      await apiClient.removeFile(subjectId, lectureId, kind);
      await removeUploadedFileRecord(subjectId, lectureId, kind);
      await refreshLocalFiles(subjectId, lectureId);
      await syncFromBackend(true);
      pushToast(`Removed ${kind} file from ${subjectId}/${lectureId}.`, "info");
    } catch (err) {
      pushToast(err.message, "error");
    }
  };

  const handleStartProcessing = async (subjectId, lectureId, options) => {
    try {
      await apiClient.startProcessing(subjectId, lectureId, options);
      await syncFromBackend(true);
      pushToast(`Started lecture processing for ${subjectId}/${lectureId}.`, "info");
    } catch (err) {
      pushToast(err.message, "error");
    }
  };

  const handleUploadCsv = async (subjectId, lectureId, file) => {
    const res = await apiClient.uploadFeedbackCsv(subjectId, lectureId, file);
    await saveUploadedFileBlob(
      subjectId,
      lectureId,
      "feedback_csv",
      file,
      res.chapter?.files?.feedback_csv || {}
    );
    await refreshLocalFiles(subjectId, lectureId);
    await syncFromBackend(true);
    pushToast(`Uploaded feedback CSV '${file.name}'.`, "success");
    return res;
  };

  const handleConfirmColumns = async (subjectId, lectureId, idCol, fbCol) => {
    const res = await apiClient.confirmFeedbackColumns(subjectId, lectureId, idCol, fbCol);
    await syncFromBackend(true);
    pushToast(`Confirmed columns: '${idCol}' & '${fbCol}'.`, "success");
    return res;
  };

  const handleStartEvaluation = async (subjectId, lectureId, options) => {
    try {
      await apiClient.startEvaluation(subjectId, lectureId, options);
      await syncFromBackend(true);
      pushToast(`Started verification & scoring for ${subjectId}/${lectureId}.`, "info");
    } catch (err) {
      pushToast(err.message, "error");
    }
  };

  const handleExportBackup = () => {
    window.location.href = apiClient.getBackupExportUrl(false);
    pushToast("Downloading workspace backup archive (.zip)...", "info");
  };

  const handleRestoreBackup = async (file) => {
    try {
      const res = await apiClient.restoreBackupZip(file);
      await syncFromBackend(false);
      pushToast(
        `Restored ${res.restored_files} files across ${res.subject_count} subjects.`,
        "success"
      );
    } catch (err) {
      pushToast(err.message || "Backup restore failed.", "error");
    }
  };

  const activeStepObj =
    WORKFLOW_STEPS.find((s) => s.key === activeStep) || WORKFLOW_STEPS[0];

  return (
    <div className="app-shell">
      <WorkflowSidebar
        activeStep={activeStep}
        onSelectStep={setActiveStep}
        selectedTeacher={selectedTeacher}
        selectedSubject={selectedSubject}
        selectedChapter={selectedChapter}
        onSync={() => syncFromBackend(false)}
        syncing={syncing}
        onExportBackup={handleExportBackup}
        onRestoreBackupFile={handleRestoreBackup}
      />

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              type="button"
              className="crumb-btn"
              onClick={() => setActiveStep("teachers")}
            >
              {selectedTeacher?.name || "Teachers"}
            </button>
            <ChevronRight size={14} />
            <button
              type="button"
              className="crumb-btn"
              onClick={() => setActiveStep("subjects")}
            >
              {selectedSubject ? selectedSubject.name : "Subjects"}
            </button>
            {selectedSubject && (
              <>
                <ChevronRight size={14} />
                <button
                  type="button"
                  className="crumb-btn"
                  onClick={() => setActiveStep("chapters")}
                >
                  {selectedChapter
                    ? `${selectedChapter.lecture_id} (${selectedChapter.title})`
                    : "Chapters"}
                </button>
              </>
            )}
            <ChevronRight size={14} />
            <span className="crumb-active">{activeStepObj.label}</span>
          </div>

          <div className="topbar-actions">
            <span className="badge badge-neutral" title="No SQL/NoSQL database; pure IndexedDB + Local Disk">
              <HardDrive size={13} /> Local Disk + IndexedDB Active
            </span>
          </div>
        </header>

        <div className="page-content">
          {backendError && (
            <div className="banner banner-error">
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <WifiOff size={16} />
                {backendError}
              </span>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => syncFromBackend(false)}
              >
                <RefreshCw size={13} /> Retry Connection
              </button>
            </div>
          )}

          {activeStep === "teachers" && (
            <TeacherSelectionView
              teachers={teachers}
              selectedTeacherId={selectedTeacher?.teacher_id}
              onSelectTeacher={handleSelectTeacher}
              onCreateTeacher={handleCreateTeacher}
            />
          )}

          {activeStep === "subjects" && (
            <SubjectManagementView
              selectedTeacher={selectedTeacher}
              subjects={subjects}
              showAllTeachers={showAllTeachers}
              onToggleShowAll={setShowAllTeachers}
              selectedSubjectId={selectedSubjectId}
              onOpenSubject={handleOpenSubject}
              onCreateSubject={handleCreateSubject}
              onRenameSubject={handleRenameSubject}
              onDeleteSubject={handleDeleteSubject}
            />
          )}

          {activeStep === "chapters" && (
            <ChapterManagementView
              subject={selectedSubject}
              selectedLectureId={selectedLectureId}
              onCreateChapter={handleCreateChapter}
              onOpenChapterStep={handleOpenChapterStep}
              onRenameChapter={handleRenameChapter}
              onDeleteChapter={handleDeleteChapter}
            />
          )}

          {activeStep === "upload" && (
            <LectureUploadStep
              subject={selectedSubject}
              chapter={selectedChapter}
              localIdbFiles={localIdbFiles}
              onUploadMedia={handleUploadMedia}
              onRemoveMedia={handleRemoveFile}
              onContinueToProcessing={() => setActiveStep("processing")}
            />
          )}

          {activeStep === "processing" && (
            <LectureProcessingStep
              subject={selectedSubject}
              chapter={selectedChapter}
              onStartProcessing={handleStartProcessing}
              onContinueToFeedback={() => setActiveStep("feedback")}
            />
          )}

          {activeStep === "feedback" && (
            <FeedbackUploadStep
              subject={selectedSubject}
              chapter={selectedChapter}
              onUploadCsv={handleUploadCsv}
              onConfirmColumns={handleConfirmColumns}
              onRemoveCsv={handleRemoveFile}
              onContinueToEvaluation={() => setActiveStep("evaluation")}
            />
          )}

          {activeStep === "evaluation" && (
            <EvaluationStep
              subject={selectedSubject}
              chapter={selectedChapter}
              onStartEvaluation={handleStartEvaluation}
              onOpenResults={() => setActiveStep("results")}
              onGoToProcessing={() => setActiveStep("processing")}
              onGoToFeedback={() => setActiveStep("feedback")}
            />
          )}

          {activeStep === "results" && (
            <ResultsDashboardStep
              subject={selectedSubject}
              chapter={selectedChapter}
              selectedStudentId={selectedStudentId}
              onSelectStudentId={setSelectedStudentId}
              onGoToEvaluation={() => setActiveStep("evaluation")}
            />
          )}
        </div>
      </main>

      {toasts.length > 0 && (
        <div className="toast-stack" role="status" aria-live="polite">
          {toasts.map((t) => (
            <div key={t.id} className={`toast ${t.type}`}>
              <span>{t.message}</span>
              <button
                type="button"
                style={{
                  background: "none",
                  border: "none",
                  color: "inherit",
                  cursor: "pointer",
                  padding: 2,
                }}
                onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

