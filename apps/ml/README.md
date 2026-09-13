# guitarista-ml

ML sidecar for Guitarista's audio → tab tier. A small CLI that wraps
[basic-pitch](https://github.com/spotify/basic-pitch) (pitch transcription),
our own **TabCNN** (string/fret transcription, see `docs/tabcnn.md`) and
[Demucs](https://github.com/facebookresearch/demucs) (source separation) and
speaks JSON over stdout so `apps/api` can drive it as a subprocess.

It is a separate uv project on **Python 3.11** because basic-pitch 0.4 does
not support 3.12+.

## Install

```bash
cd apps/ml
uv sync                      # transcription (basic-pitch + CoreML, TabCNN via onnxruntime)
uv sync --extra separate     # + demucs / torch / torchaudio (~2 GB)
uv sync --extra train        # + torch / onnx for training and exporting TabCNN
uv run pytest -q             # includes a real 3 s transcription
```

`uv run guitarista-ml --help` lists commands. If `VIRTUAL_ENV` points at some
other environment (e.g. a conda env) uv prints a warning and ignores it; that is
harmless.

## Contract

Every command prints exactly **one JSON object as the last line of stdout**.
Progress goes to stderr as `{"progress": 0.0-1.0, "stage": "..."}` lines
(library chatter is also routed to stderr). On failure the exit code is
non-zero and stdout carries `{"error": "...", "type": "..."}`.

| Command | Result | Exit codes |
|---|---|---|
| `version` | `{"version": "0.1.0"}` | 0 |
| `probe` | `{"basic_pitch": bool, "backend": "coreml"\|"tf"\|"onnx"\|"tflite"\|null, "demucs": bool, "tabcnn": bool, "device": "mps"\|"cpu", "torch": str\|null}` | always 0; never imports torch unless installed |
| `transcribe IN.wav OUT.json [--model basic-pitch\|tabcnn] [--onset 0.5] [--frame 0.3] [--min-note-ms 58] [--fmin 80] [--fmax 1300] [--estimate-tempo]` | writes `OUT.json` (see below); prints `{"ok": true, "out", "note_count", "tempo_bpm"}` | 2 invalid input, 4 model/inference failure (incl. missing TabCNN weights) |
| `guitarset-fetch [--parts annotation,mic,mix]` | downloads GuitarSet (CC-BY-4.0, ~0.7 GB per audio part) into `$GUITARISTA_ML_DATA` (default `apps/ml/data`) | |
| `tabcnn-train [--config baseline\|improved] [--fold 0-5\|all] [--sources mic,mix] [--epochs N] …` | trains TabCNN, writes `runs/<name>/weights.pt` + `metrics.json` (extra: train) | 3 torch missing |
| `tabcnn-export WEIGHTS.pt [OUT.onnx]` | exports to ONNX (default: the shipped `src/guitarista_ml/models/tabcnn.onnx`) and checks parity | 3 torch missing |
| `tabcnn-eval [--fold 5] [--model tabcnn\|basic-pitch\|both] [--source mic\|mix]` | frame-level tab/pitch P/R/F + TDR on the held-out player | |
| `separate IN.wav OUT_DIR [--model htdemucs_6s] [--stems guitar,other] [--device auto\|mps\|cpu]` | `{"stems": {"guitar": "OUT_DIR/IN.guitar.wav", ...}, "model": "htdemucs_6s"}` | 3 demucs not installed (run `uv sync --extra separate`), 2 invalid input, 4 failure |

`OUT.json` (`TranscriptionResult`, see `src/guitarista_ml/schema.py`):

```json
{
  "notes": [{"onset_s": 0.01, "offset_s": 0.95, "pitch_midi": 40, "velocity": 0.76, "pitch_bend": [0, 0, ...] , "confidence": 0.76, "string": null, "fret": null}],
  "tempo_bpm": 60.1,
  "beats_s": [0.48, 1.47, 2.46],
  "source_audio": "/abs/path/in.wav",
  "stem": "mix",
  "model": "basic-pitch/icassp2022",
  "duration_s": 3.0
}
```

`velocity` is basic-pitch's note amplitude in 0..1; basic-pitch has no separate
note score, so `confidence` repeats it. With `--model tabcnn` every note also
carries `string` (canonical: 1 = highest string) and `fret`, and `velocity` /
`confidence` are the mean class probability over the note. `tempo_bpm` is
`null` and `beats_s` empty unless `--estimate-tempo` is passed (librosa
`beat_track`; `apps/api` aligns its rhythm grid to the beat times). The default
`--fmin 80 --fmax 1300` brackets a standard-tuned guitar (E2 ≈ 82 Hz up to the
24th fret of the high E ≈ 1319 Hz); widen it for drop tunings.

`GUITARISTA_TABCNN_WEIGHTS=/path/to/model.onnx` makes `probe`/`transcribe --model tabcnn`
use a candidate model instead of the shipped `src/guitarista_ml/models/tabcnn.onnx`.

**Only `.wav` input is accepted.** The caller (`apps/api`) converts uploads /
yt-dlp output to mono 22.05 kHz wav with ffmpeg first; ffmpeg is not a
dependency of this package.

## macOS notes (Apple Silicon)

- **basic-pitch backend**: with the `coreml` extra (default) inference runs
  through `coremltools` on CPU (`ComputeUnit.CPU_ONLY`, which is what
  basic-pitch itself selects). On the dev M2 the first `transcribe` of a fresh
  install took ~6.4 s for a 3 s clip (CoreML compiling the `.mlpackage`);
  once macOS has cached the compiled model, subsequent processes take ~2.5 s
  end-to-end including interpreter start-up. Detected
  pitches for E2/A2/D3 were exactly 40/45/50 plus one short low-amplitude
  harmonic ghost — filter by `velocity` downstream.
- **ONNX fallback**: if CoreML fails to load (`"type": "model_load"`), run
  `uv sync --extra onnx`. basic-pitch prefers TF > CoreML > TFLite > ONNX when
  several are present, so to force ONNX also remove `coremltools`. On this
  machine CoreML worked first try, so ONNX was not needed.
- **`pkg_resources`**: basic-pitch pins `resampy<0.4.3`, which still does
  `import pkg_resources`; setuptools ≥81 removed it. `pyproject.toml` therefore
  pins `setuptools>=69,<81`. Do not bump it until basic-pitch relaxes the
  resampy pin.
- **Demucs device**: `--device auto` uses MPS when `torch.backends.mps.is_available()`,
  else CPU. If MPS separation throws (op gaps in older torch), the CLI retries
  on CPU automatically. `htdemucs_6s` is the only bundled model with a
  `guitar` stem; expect roughly real-time on MPS and several× slower on CPU.
- **`TORCH_HOME`**: Demucs downloads weights (~80 MB per model) into
  `$TORCH_HOME/hub/checkpoints`. `apps/api` sets `TORCH_HOME` to
  `data/models` before spawning the sidecar; set it yourself when running by
  hand so weights do not land in `~/.cache/torch`.
- `numpy<2` is required by basic-pitch/coremltools; keep the pin.

## Layout

```
src/guitarista_ml/
  cli.py         argparse entry point, JSON/exit-code contract
  io.py          emit_result / emit_progress / quiet_stdout / CliError
  schema.py      dataclasses + TypedDicts for every JSON shape
  probe.py       capability report (lazy, crash-free)
  transcribe.py  basic-pitch / TabCNN dispatch
  separate.py    demucs wrapper (lazy imports)
  tabcnn/        features (CQT), labels (JAMS), model+train+export (torch), infer (onnxruntime), metrics, evaluate
  models/        tabcnn.onnx (shipped weights)
tests/test_cli.py     subprocess tests incl. a real transcription of a synthesized clip
tests/test_tabcnn.py  feature/label/metric/decoder units + torch→ONNX round trip (train extra)
```
