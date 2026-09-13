# TabCNN in Guitarista

String/fret transcription for the audio tier. Reimplementation of **Wiggins & Kim, "Guitar
Tablature Estimation with a Convolutional Neural Network" (ISMIR 2019)** in PyTorch, shipped as
ONNX so the sidecar never needs torch at inference time.

## Why

basic-pitch predicts pitches only; the Viterbi solver (`apps/api/.../solver`) then has to guess
strings from playability heuristics. TabCNN predicts `(string, fret)` per frame directly from the
audio, which the solver receives as hints (`ChordEvent.meta["hints"]`, cost term
`BaselineWeights.hint_mismatch`). The solver stays the source of truth, so the tuning/capo
invariant and playability filters still hold and impossible predictions get corrected.

## Recipe

| | original (tab-cnn repo) | ours |
|---|---|---|
| audio | GuitarSet `audio_mono-mic`, 22.05 kHz | same (+ optional `audio_mono-pickup_mix` as extra examples) |
| input | `|CQT|`, hop 512, 192 bins, 24/octave (C1 …) | log-magnitude CQT, standardised per clip (level-invariant; matters for Demucs stems and phone recordings) |
| window | 9 frames | `baseline`: 9 · `improved`: 25 |
| net | conv 32/64/64 (3×3) → maxpool → dense 128 → 6×21 | `baseline`: identical · `improved`: + BatchNorm, + conv 64 & second maxpool |
| loss | Σ per-string categorical CE | same (+ label smoothing 0.05 in `improved`) |
| optimiser | Adadelta, 8 epochs, batch 128 | `baseline`: Adadelta · `improved`: Adam 1e-3 cosine, ≤30 epochs, early stopping on held-out tab F1 |
| augmentation | none | ±1 semitone = ±2-bin CQT roll with fret labels shifted; Gaussian noise |
| decode | per-frame argmax | per-string Viterbi (switch penalty 2 nats) + run-length → notes, split at spectral-flux onsets |
| labels | class 0 = silent, 1..20 = fret 0..19 | same |
| string order | index 0 = low E (MIDI 40) | same internally; converted to canonical (1 = high E) at the note level — pin test in `tests/test_tabcnn.py` |
| split | 6-fold by player | same (`--fold 0..5`), `--fold all` for the shipped weights |

## Commands

```bash
cd apps/ml
uv sync --extra train
uv run guitarista-ml guitarset-fetch --parts annotation,mic      # ~0.7 GB into apps/ml/data
uv run guitarista-ml tabcnn-train --config baseline --fold 5     # reproduce the paper's setup
uv run guitarista-ml tabcnn-train --config improved --fold 5
uv run guitarista-ml tabcnn-eval --fold 5 --model both --weights runs/<run>/weights.pt
uv run guitarista-ml tabcnn-train --config improved --fold all   # final weights
uv run guitarista-ml tabcnn-export runs/<run>/weights.pt         # → src/guitarista_ml/models/tabcnn.onnx
cd ../api && uv run python scripts/eval_audio_tier.py --fold 5   # end-to-end: sidecar → solver → tab
```

`GUITARISTA_TABCNN_WEIGHTS=<onnx>` points the sidecar at a candidate model for A/B runs.
`GUITARISTA_AUDIO_MODEL=tabcnn` switches the API's audio tier over; `/api/v1/health` reports
`tabcnn_available` and `audio_model`.

## Results

Frame-level metrics on the held-out player (fold 5, mic audio), TabCNN paper definitions
(`tabcnn/metrics.py`): pitch P/R/F over the multipitch implied by the tab, tab P/R/F over
(string, fret), TDR = tab precision / pitch precision.

_To be filled in from `runs/*/metrics.json` and `tabcnn-eval` output._

## Known limits / next data

GuitarSet is solo acoustic guitar. Expect a drop on electric tones, effects and full mixes; use the
Demucs guitar stem (`GUITARISTA_ENABLE_SEPARATION=1`) for real songs. Candidate data to close the
gap: EGDB (electric, hex pickup), SynthTab-style rendered Guitar Pro, effects augmentation
(robust-guitar-tabs). TabCNN has no onset head, so re-plucked repeated notes rely on the
spectral-flux onset split in `infer.decode`.
