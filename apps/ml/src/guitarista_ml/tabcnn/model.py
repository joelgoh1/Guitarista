"""TabCNN in PyTorch. Imported only by ``train``/``export`` (the ``train`` extra)."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import torch
from torch import nn

from guitarista_ml.tabcnn.features import N_BINS, N_CLASSES, N_STRINGS


@dataclass(frozen=True, slots=True)
class TabCNNConfig:
    name: str
    context: int = 9
    """Frames per input window (odd)."""
    batchnorm: bool = False
    extra_conv: bool = False
    """Fourth conv + second max-pool; keeps the dense layer small with wide context windows."""
    hidden: int = 128
    dropout_conv: float = 0.25
    dropout_dense: float = 0.5

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


CONFIGS: dict[str, TabCNNConfig] = {
    # Wiggins & Kim 2019 as published (bar the log-CQT input, see features.py).
    "baseline": TabCNNConfig("baseline"),
    # Wider context, BatchNorm and a second pooling stage; trained with Adam + early stopping.
    "improved": TabCNNConfig("improved", context=25, batchnorm=True, extra_conv=True),
}


def _conv(cin: int, cout: int, batchnorm: bool) -> list[nn.Module]:
    layers: list[nn.Module] = [nn.Conv2d(cin, cout, kernel_size=3)]
    if batchnorm:
        layers.append(nn.BatchNorm2d(cout))
    layers.append(nn.ReLU(inplace=True))
    return layers


class TabCNN(nn.Module):
    """``(B, 1, N_BINS, context)`` → ``(B, N_STRINGS, N_CLASSES)`` logits (softmax per string)."""

    def __init__(self, cfg: TabCNNConfig) -> None:
        super().__init__()
        self.cfg = cfg
        feats: list[nn.Module] = [
            *_conv(1, 32, cfg.batchnorm),
            *_conv(32, 64, cfg.batchnorm),
            *_conv(64, 64, cfg.batchnorm),
            nn.MaxPool2d(2),
            nn.Dropout(cfg.dropout_conv),
        ]
        if cfg.extra_conv:
            feats += [*_conv(64, 64, cfg.batchnorm), nn.MaxPool2d(2), nn.Dropout(cfg.dropout_conv)]
        self.features = nn.Sequential(*feats)
        with torch.no_grad():
            flat = self.features(torch.zeros(1, 1, N_BINS, cfg.context)).numel()
        self.head = nn.Sequential(
            nn.Flatten(),
            nn.Linear(flat, cfg.hidden),
            nn.ReLU(inplace=True),
            nn.Dropout(cfg.dropout_dense),
            nn.Linear(cfg.hidden, N_STRINGS * N_CLASSES),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.features(x)).view(-1, N_STRINGS, N_CLASSES)


def string_cross_entropy(logits: torch.Tensor, target: torch.Tensor, label_smoothing: float = 0.0) -> torch.Tensor:
    """Sum over strings of per-string categorical cross-entropy, averaged over the batch."""
    loss = torch.zeros((), device=logits.device)
    for s in range(N_STRINGS):
        loss = loss + nn.functional.cross_entropy(logits[:, s], target[:, s].long(), label_smoothing=label_smoothing)
    return loss


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())
