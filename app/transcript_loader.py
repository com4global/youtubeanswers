from youtube_transcript_api import YouTubeTranscriptApi
import xml.etree.ElementTree as ET


def get_transcript(video_id: str):
    """
    Best-effort transcript fetch.
    Tries multiple language fallbacks.
    Never crashes.
    """
    try:
        return YouTubeTranscriptApi.get_transcript(
            video_id,
            languages=[
                "en", "en-US", "en-GB",
                "auto", "en-IN"
            ]
        )
    except ET.ParseError:
        return None
    except Exception:
        return None
