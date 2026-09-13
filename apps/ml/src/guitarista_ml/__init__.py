"""Guitarista ML sidecar: audio separation (Demucs) and transcription (basic-pitch).

Exposed as the ``guitarista-ml`` CLI. Every command prints exactly one JSON
object on the last line of stdout; progress goes to stderr as JSON lines.
"""

__version__ = "0.1.0"
