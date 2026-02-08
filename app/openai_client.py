import os
from openai import OpenAI

_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    """
    Lazily create the OpenAI client so imports don't crash in serverless
    when OPENAI_API_KEY is missing. The error will surface on first use.
    """
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Configure it in your environment."
            )
        _client = OpenAI(api_key=api_key)
    return _client
