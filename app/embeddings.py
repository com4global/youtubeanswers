from app.openai_client import get_openai_client


def embed(texts: list[str]):
    """
    Takes a list of strings and returns embedding objects
    """
    client = get_openai_client()
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts
    )
    return response.data
