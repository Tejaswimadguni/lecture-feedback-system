-- ============================================================
-- LECTURE FEEDBACK SYSTEM
-- PostgreSQL Database Schema
-- ============================================================

-- ============================================================
-- 1. LECTURES
-- Master record for each lecture
-- ============================================================

CREATE TABLE IF NOT EXISTS lectures (
    lecture_id VARCHAR(100) PRIMARY KEY,
    lecture_number INTEGER,
    lecture_title TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- 2. LECTURE SOURCES
-- Original files belonging to a lecture:
-- AUDIO / VIDEO / PDF / PPT
-- ============================================================

CREATE TABLE IF NOT EXISTS lecture_sources (
    source_id SERIAL PRIMARY KEY,

    lecture_id VARCHAR(100) NOT NULL,

    source_type VARCHAR(20) NOT NULL,

    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,

    file_size BIGINT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_source_lecture
        FOREIGN KEY (lecture_id)
        REFERENCES lectures(lecture_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_source_type
        CHECK (
            source_type IN ('AUDIO', 'VIDEO', 'PDF', 'PPT')
        )
);


-- ============================================================
-- 3. LECTURE CHUNKS
-- Cleaned/chunked lecture knowledge used by retrieval
-- ============================================================

CREATE TABLE IF NOT EXISTS lecture_chunks (
    chunk_id VARCHAR(150) PRIMARY KEY,

    lecture_id VARCHAR(100) NOT NULL,

    source_id INTEGER,

    chunk_index INTEGER,

    source_type VARCHAR(20) NOT NULL,

    text TEXT NOT NULL,

    page_number INTEGER,

    start_time DOUBLE PRECISION,

    end_time DOUBLE PRECISION,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_chunk_lecture
        FOREIGN KEY (lecture_id)
        REFERENCES lectures(lecture_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_chunk_source
        FOREIGN KEY (source_id)
        REFERENCES lecture_sources(source_id)
        ON DELETE SET NULL,

    CONSTRAINT chk_chunk_source_type
        CHECK (
            source_type IN ('AUDIO', 'VIDEO', 'PDF', 'PPT')
        )
);


-- ============================================================
-- 4. STUDENTS
-- Student master record
-- ============================================================

CREATE TABLE IF NOT EXISTS students (
    student_id SERIAL PRIMARY KEY,

    student_identifier VARCHAR(100) NOT NULL UNIQUE,

    student_name VARCHAR(255),

    email VARCHAR(255),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- 5. FEEDBACK SUBMISSIONS
-- One student's feedback for a lecture
-- ============================================================

CREATE TABLE IF NOT EXISTS feedback_submissions (
    submission_id SERIAL PRIMARY KEY,

    student_id INTEGER NOT NULL,

    lecture_id VARCHAR(100) NOT NULL,

    feedback_text TEXT NOT NULL,

    processing_status VARCHAR(30) DEFAULT 'COMPLETED',

    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_submission_student
        FOREIGN KEY (student_id)
        REFERENCES students(student_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_submission_lecture
        FOREIGN KEY (lecture_id)
        REFERENCES lectures(lecture_id)
        ON DELETE CASCADE,

    CONSTRAINT unique_student_lecture_submission
        UNIQUE (student_id, lecture_id),

    CONSTRAINT chk_processing_status
        CHECK (
            processing_status IN (
                'PENDING',
                'PROCESSING',
                'COMPLETED',
                'FAILED'
            )
        )
);


-- ============================================================
-- 6. CLAIMS
-- Claims extracted from student feedback
-- ============================================================

CREATE TABLE IF NOT EXISTS claims (
    claim_id SERIAL PRIMARY KEY,

    submission_id INTEGER NOT NULL,

    claim_number VARCHAR(50) NOT NULL,

    claim_text TEXT NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_claim_submission
        FOREIGN KEY (submission_id)
        REFERENCES feedback_submissions(submission_id)
        ON DELETE CASCADE,

    CONSTRAINT unique_claim_number_per_submission
        UNIQUE (submission_id, claim_number)
);


-- ============================================================
-- 7. CLAIM EVIDENCE
-- Evidence retrieved from lecture chunks / FAISS
-- ============================================================

CREATE TABLE IF NOT EXISTS claim_evidence (
    evidence_id SERIAL PRIMARY KEY,

    claim_id INTEGER NOT NULL,

    chunk_id VARCHAR(150),

    source_type VARCHAR(20),

    source_file TEXT,

    page_number INTEGER,

    start_time DOUBLE PRECISION,

    end_time DOUBLE PRECISION,

    similarity DOUBLE PRECISION,

    evidence_text TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_evidence_claim
        FOREIGN KEY (claim_id)
        REFERENCES claims(claim_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_evidence_chunk
        FOREIGN KEY (chunk_id)
        REFERENCES lecture_chunks(chunk_id)
        ON DELETE SET NULL
);


-- ============================================================
-- 8. CLAIM EVALUATIONS
-- LLM verification result for each claim
-- ============================================================

CREATE TABLE IF NOT EXISTS claim_evaluations (
    evaluation_id SERIAL PRIMARY KEY,

    claim_id INTEGER NOT NULL,

    status VARCHAR(30) NOT NULL,

    reasoning TEXT,

    evidence_strength DOUBLE PRECISION,

    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_evaluation_claim
        FOREIGN KEY (claim_id)
        REFERENCES claims(claim_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_evaluation_status
        CHECK (
            status IN (
                'SUPPORTED',
                'PARTIALLY_SUPPORTED',
                'NOT_SUPPORTED'
            )
        )
);


-- ============================================================
-- 9. SCORES
-- Final student score
-- ============================================================

CREATE TABLE IF NOT EXISTS scores (
    score_id SERIAL PRIMARY KEY,

    submission_id INTEGER NOT NULL UNIQUE,

    factual_accuracy DOUBLE PRECISION NOT NULL DEFAULT 0,

    lecture_coverage DOUBLE PRECISION NOT NULL DEFAULT 0,

    understanding_quality DOUBLE PRECISION NOT NULL DEFAULT 0,

    total_score DOUBLE PRECISION NOT NULL DEFAULT 0,

    grade VARCHAR(10),

    scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_score_submission
        FOREIGN KEY (submission_id)
        REFERENCES feedback_submissions(submission_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_total_score
        CHECK (total_score >= 0 AND total_score <= 10)
);


-- ============================================================
-- INDEXES
-- Improve common lookup operations
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_lecture_sources_lecture
    ON lecture_sources(lecture_id);

CREATE INDEX IF NOT EXISTS idx_lecture_chunks_lecture
    ON lecture_chunks(lecture_id);

CREATE INDEX IF NOT EXISTS idx_lecture_chunks_source
    ON lecture_chunks(source_id);

CREATE INDEX IF NOT EXISTS idx_feedback_student
    ON feedback_submissions(student_id);

CREATE INDEX IF NOT EXISTS idx_feedback_lecture
    ON feedback_submissions(lecture_id);

CREATE INDEX IF NOT EXISTS idx_claims_submission
    ON claims(submission_id);

CREATE INDEX IF NOT EXISTS idx_evidence_claim
    ON claim_evidence(claim_id);

CREATE INDEX IF NOT EXISTS idx_evidence_chunk
    ON claim_evidence(chunk_id);

CREATE INDEX IF NOT EXISTS idx_evaluation_claim
    ON claim_evaluations(claim_id);


-- ============================================================
-- END OF SCHEMA
-- ============================================================