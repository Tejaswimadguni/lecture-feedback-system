try:
    from .database import get_connection
except ImportError:
    from database import get_connection


def save_student(roll_number):
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO students (student_identifier)
                VALUES (%s)
                ON CONFLICT (student_identifier)
                DO UPDATE SET
                    student_identifier = EXCLUDED.student_identifier
                RETURNING student_id;
                """,
                (str(roll_number),)
            )

            student_id = cursor.fetchone()[0]

        conn.commit()
        return student_id

    finally:
        conn.close()


def save_submission(student_id, lecture_id, feedback_text):
    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT submission_id
                FROM feedback_submissions
                WHERE student_id = %s
                  AND lecture_id = %s
                LIMIT 1;
                """,
                (student_id, lecture_id)
            )

            existing = cursor.fetchone()

            if existing:
                submission_id = existing[0]

                cursor.execute(
                    """
                    UPDATE feedback_submissions
                    SET feedback_text = %s
                    WHERE submission_id = %s;
                    """,
                    (feedback_text, submission_id)
                )

            else:
                cursor.execute(
                    """
                    INSERT INTO feedback_submissions
                    (
                        student_id,
                        lecture_id,
                        feedback_text
                    )
                    VALUES (%s, %s, %s)
                    RETURNING submission_id;
                    """,
                    (
                        student_id,
                        lecture_id,
                        feedback_text
                    )
                )

                submission_id = cursor.fetchone()[0]

        conn.commit()
        return submission_id

    finally:
        conn.close()


def save_claim(submission_id, claim):
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT claim_id
                FROM claims
                WHERE submission_id = %s
                  AND claim_number = %s
                LIMIT 1;
                """,
                (
                    submission_id,
                    claim.get("claim_id")
                )
            )

            existing = cursor.fetchone()

            if existing:
                claim_db_id = existing[0]

                cursor.execute(
                    """
                    UPDATE claims
                    SET claim_text = %s
                    WHERE claim_id = %s;
                    """,
                    (
                        claim.get(
                            "claim",
                            claim.get("text", "")
                        ),
                        claim_db_id
                    )
                )

            else:
                cursor.execute(
                    """
                    INSERT INTO claims
                    (
                        submission_id,
                        claim_number,
                        claim_text
                    )
                    VALUES (%s, %s, %s)
                    RETURNING claim_id;
                    """,
                    (
                        submission_id,
                        claim.get("claim_id"),
                        claim.get(
                            "claim",
                            claim.get("text", "")
                        )
                    )
                )

                claim_db_id = cursor.fetchone()[0]

        conn.commit()
        return claim_db_id

    finally:
        conn.close()


def save_evidence(claim_db_id, evidence):
    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            # Check whether this exact evidence already exists
            cursor.execute(
                """
                SELECT evidence_id
                FROM claim_evidence
                WHERE claim_id = %s
                  AND chunk_id = %s
                LIMIT 1;
                """,
                (
                    claim_db_id,
                    evidence.get("chunk_id")
                )
            )

            existing = cursor.fetchone()

            if existing:
                evidence_id = existing[0]

                cursor.execute(
                    """
                    UPDATE claim_evidence
                    SET
                        source_type = %s,
                        source_file = %s,
                        page_number = %s,
                        similarity = %s,
                        evidence_text = %s
                    WHERE evidence_id = %s;
                    """,
                    (
                        evidence.get("source_type"),
                        evidence.get("source_file"),
                        evidence.get("page"),
                        evidence.get("score"),
                        evidence.get("text"),
                        evidence_id
                    )
                )

            else:
                cursor.execute(
                    """
                    INSERT INTO claim_evidence
                    (
                        claim_id,
                        chunk_id,
                        source_type,
                        source_file,
                        page_number,
                        similarity,
                        evidence_text
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING evidence_id;
                    """,
                    (
                        claim_db_id,
                        evidence.get("chunk_id"),
                        evidence.get("source_type"),
                        evidence.get("source_file"),
                        evidence.get("page"),
                        evidence.get("score"),
                        evidence.get("text")
                    )
                )

                evidence_id = cursor.fetchone()[0]

        conn.commit()
        return evidence_id

    finally:
        conn.close()


def save_evaluation(
    claim_db_id,
    status,
    reasoning,
    evidence_strength=None
):
    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            # Check whether an evaluation already exists
            cursor.execute(
                """
                SELECT evaluation_id
                FROM claim_evaluations
                WHERE claim_id = %s
                LIMIT 1;
                """,
                (claim_db_id,)
            )

            existing = cursor.fetchone()

            if existing:
                evaluation_id = existing[0]

                cursor.execute(
                    """
                    UPDATE claim_evaluations
                    SET
                        status = %s,
                        reasoning = %s,
                        evidence_strength = %s
                    WHERE evaluation_id = %s;
                    """,
                    (
                        status,
                        reasoning,
                        evidence_strength,
                        evaluation_id
                    )
                )

            else:
                cursor.execute(
                    """
                    INSERT INTO claim_evaluations
                    (
                        claim_id,
                        status,
                        reasoning,
                        evidence_strength
                    )
                    VALUES (%s, %s, %s, %s)
                    RETURNING evaluation_id;
                    """,
                    (
                        claim_db_id,
                        status,
                        reasoning,
                        evidence_strength
                    )
                )

                evaluation_id = cursor.fetchone()[0]

        conn.commit()
        return evaluation_id

    finally:
        conn.close()

def save_score(
    submission_id,
    factual_accuracy,
    lecture_coverage,
    understanding_quality,
    total_score
):
    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT score_id
                FROM scores
                WHERE submission_id = %s
                LIMIT 1;
                """,
                (submission_id,)
            )

            existing = cursor.fetchone()

            if existing:
                score_id = existing[0]

                cursor.execute(
                    """
                    UPDATE scores
                    SET
                        factual_accuracy = %s,
                        lecture_coverage = %s,
                        understanding_quality = %s,
                        total_score = %s
                    WHERE score_id = %s;
                    """,
                    (
                        factual_accuracy,
                        lecture_coverage,
                        understanding_quality,
                        total_score,
                        score_id
                    )
                )

            else:
                cursor.execute(
                    """
                    INSERT INTO scores
                    (
                        submission_id,
                        factual_accuracy,
                        lecture_coverage,
                        understanding_quality,
                        total_score
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING score_id;
                    """,
                    (
                        submission_id,
                        factual_accuracy,
                        lecture_coverage,
                        understanding_quality,
                        total_score
                    )
                )

                score_id = cursor.fetchone()[0]

        conn.commit()
        return score_id

    finally:
        conn.close()