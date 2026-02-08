from openai import OpenAI

client = OpenAI()


def embed(texts: list[str]):
    """
    Takes a list of strings and returns embedding objects
    """
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts
    )
    return response.data
