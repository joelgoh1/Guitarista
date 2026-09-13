"""torch checkpoint → ONNX, with an onnxruntime parity check."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from guitarista_ml.tabcnn.features import N_BINS


def export_onnx(weights: Path, out: Path, opset: int = 17) -> dict[str, object]:
    import onnxruntime as ort
    import torch

    from guitarista_ml.tabcnn.train import load_checkpoint

    model, cfg = load_checkpoint(weights, device="cpu")
    model.eval()
    dummy = torch.zeros(1, 1, N_BINS, cfg.context)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model,
        dummy,
        str(out),
        input_names=["cqt"],
        output_names=["logits"],
        dynamic_axes={"cqt": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=opset,
        dynamo=False,
    )
    x = torch.randn(7, 1, N_BINS, cfg.context)
    with torch.no_grad():
        ref = model(x).numpy()
    sess = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    (got,) = sess.run(None, {"cqt": x.numpy()})
    max_abs = float(np.abs(got - ref).max())
    if max_abs > 1e-3:
        raise RuntimeError(f"ONNX output differs from torch by {max_abs:.2e}")
    return {"out": str(out), "config": cfg.name, "context": cfg.context, "max_abs_diff": max_abs, "bytes": out.stat().st_size}
