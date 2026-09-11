import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

sys.path.append(
    str(PROJECT_ROOT / "backend" / "retrival")
)

from search import search
# --------------------------------------------------
# Project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CLAIMS_FILE = (
    PROJECT_ROOT
    / "data"
    / "results"
    / "student_01_claims.json"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "results"
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "student_01_evidence.json"
)


# --------------------------------------------------
# Load claims
# --------------------------------------------------

def load_claims(file_path):

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(file)

    return data


# --------------------------------------------------
# Retrieve evidence for each claim
# --------------------------------------------------

def retrieve_evidence(
    claims,
    top_k=5
):

    results = []

    for claim in claims:

        claim_id = claim["claim_id"]
        claim_text = claim["text"]

        print("\n-----------------------------------")
        print(f"Claim: {claim_id}")
        print("-----------------------------------")

        print(claim_text)

        print("\nSearching lecture evidence...")

        search_results = search(
            claim_text,
            top_k=top_k
        )

        evidence = []

        for result in search_results:

            evidence.append({
                "score": result["score"],
                "chunk_id": result["chunk_id"],
                "source_type": result["source_type"],
                "source_file": result["source_file"],
                "page": result["page"],
                "start_time": result["start_time"],
                "end_time": result["end_time"],
                "text": result["text"]
            })

        results.append({
            "claim_id": claim_id,
            "claim": claim_text,
            "evidence": evidence
        })

        if evidence:

            print(
                f"\nTop evidence "
                f"(similarity: {evidence[0]['score']:.4f})"
            )

            print(
                f"Source: {evidence[0]['source_type']}"
            )

            if evidence[0]["page"] is not None:

                print(
                    f"Page: {evidence[0]['page']}"
                )

            if evidence[0]["start_time"] is not None:

                print(
                    f"Time: "
                    f"{evidence[0]['start_time']:.2f}"
                    f" - "
                    f"{evidence[0]['end_time']:.2f}"
                )

            safe_text = evidence[0]['text'].replace('\uf0a7', '-').encode('ascii', errors='backslashreplace').decode('ascii')
            print(
                f"Text: {safe_text[:120]}..."
            )

    return results


# --------------------------------------------------
# Main
# --------------------------------------------------

def main(target_roll_number=None):
    print("\n===================================")
    print("CLAIM -> EVIDENCE RETRIEVAL")
    print("===================================")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if target_roll_number is not None:
        claim_files = [OUTPUT_DIR / f"student_{int(target_roll_number):02d}_claims.json"]
    else:
        claim_files = sorted(list(OUTPUT_DIR.glob("student_*_claims.json")))

    if not claim_files and CLAIMS_FILE.exists():
        claim_files = [CLAIMS_FILE]

    print(f"\nFound {len(claim_files)} claim files to process...")

    for c_file in claim_files:
        if not c_file.exists():
            continue

        data = load_claims(c_file)
        roll_number = data.get("roll_number", 1)
        claims = data.get("claims", [])

        print(f"\nRetrieving evidence for Roll No. {roll_number} ({len(claims)} claims)...")
        results = retrieve_evidence(claims, top_k=5)

        output = {
            "roll_number": roll_number,
            "total_claims": len(claims),
            "claims": results
        }

        out_file = OUTPUT_DIR / f"student_{roll_number:02d}_evidence.json"
        with open(out_file, "w", encoding="utf-8") as file:
            json.dump(output, file, indent=2, ensure_ascii=False)

        if roll_number == 1:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
                json.dump(output, file, indent=2, ensure_ascii=False)

    print("\n===================================")
    print("EVIDENCE RETRIEVAL COMPLETE")
    print(f"Processed {len(claim_files)} students. Saved to {OUTPUT_DIR}")
    print("===================================")


if __name__ == "__main__":
    main()