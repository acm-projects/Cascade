"""The AI Editor "beats" pipeline (see MASTER_PROMPT.md in this folder).

upload -> transcribe (word timestamps) -> director (LLM) -> plan.json -> critic loop
       -> assets -> render (Remotion) ; chat message -> revise (LLM) -> patched plan.json

The beat plan JSON is the source of truth. Only the planning steps call a model; transcription,
validation and rendering are deterministic. Selected with CASCADE_EDIT_ENGINE=beats; the Cinema
engine (../cinema) stays the default and the fallback.
"""
