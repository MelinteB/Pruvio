import os

from dotenv import load_dotenv
from openai import OpenAI


def main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_RECEIPT_MODEL", "gpt-6-luna")
    if not api_key:
        raise SystemExit(
            "OPENAI_API_KEY is not set. Put it in your local environment/.env, "
            "not inside this script."
        )

    client = OpenAI(
        api_key=api_key,
        timeout=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60")),
    )
    response = client.responses.create(
        model=model,
        reasoning={"effort": "none"},
        input="Reply with exactly: PRUVS_OPENAI_OK",
        max_output_tokens=30,
        store=False,
    )
    print("OpenAI API connection: OK")
    print(f"Model: {model}")
    print(f"Response: {response.output_text.strip()}")
    usage = getattr(response, "usage", None)
    if usage:
        print(
            "Usage: "
            f"input={getattr(usage, 'input_tokens', None)}, "
            f"output={getattr(usage, 'output_tokens', None)}, "
            f"total={getattr(usage, 'total_tokens', None)}"
        )


if __name__ == "__main__":
    main()
