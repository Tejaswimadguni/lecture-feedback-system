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

def main():

    print("\n===================================")
    print("CLAIM -> EVIDENCE RETRIEVAL")
    print("===================================")

    print("\nLoading claims...")

    data = load_claims(
        CLAIMS_FILE
    )

    roll_number = data["roll_number"]
    claims = data["claims"]

    print(
        f"Roll number: {roll_number}"
    )

    print(
        f"Total claims: {len(claims)}"
    )

    print("\nRetrieving evidence...")

    results = retrieve_evidence(
        claims,
        top_k=5
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    output = {
        "roll_number": roll_number,
        "total_claims": len(claims),
        "claims": results
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            output,
            file,
            indent=2,
            ensure_ascii=False
        )

    print("\n===================================")
    print("EVIDENCE RETRIEVAL COMPLETE")
    print("===================================")

    print(
        f"\nEvidence saved to:"
    )

    print(
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()