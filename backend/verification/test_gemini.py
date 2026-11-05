import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.verification.llm_client import LLMAPIError, call_llm_json, redact_secrets


def main() -> None:
    print("\n===================================")
    print("LLM API CONNECTIVITY TEST")
    print("===================================")
    prompt = 'Return ONLY valid JSON: {"status": "ok", "message": "API connectivity verified."}'
    try:
        res = call_llm_json(prompt=prompt, max_tokens=100, strict_llm=True)
        print("\nAPI Response:")
        print(res)
    except LLMAPIError as exc:
        print(f"LLM API check failed: {redact_secrets(exc)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
