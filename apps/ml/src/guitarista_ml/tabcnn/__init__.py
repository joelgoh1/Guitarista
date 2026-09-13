"""TabCNN: frame-level string/fret classification from a CQT (Wiggins & Kim, ISMIR 2019).

Layout: ``features`` (CQT frames, shared by training and inference), ``labels`` (GuitarSet
JAMS → per-frame classes), ``model``/``train``/``export`` (torch; ``train`` extra only),
``infer`` (onnxruntime; part of the base install), ``metrics`` and ``evaluate``.

Only ``infer`` and ``features`` may be imported by the transcription path: the sidecar must
never import torch for a plain ``transcribe`` (see CLAUDE.md).
"""
