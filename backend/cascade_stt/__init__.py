"""Speech-to-text shared by every feature: Deepgram, the only transcription path in the project."""

from .transcribe import (  # noqa: F401
    DEEPGRAM_MODEL,
    DEEPGRAM_USD_PER_MINUTE,
    TRANSCRIPT_TAG,
    TranscriptionError,
    transcribe_media,
)
