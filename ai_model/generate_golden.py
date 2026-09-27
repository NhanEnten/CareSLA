"""Generate deterministic *synthetic* firmware comparison vectors.

These are numerical regression fixtures, not labeled KFall trials or accuracy evidence.
Requires: pip install numpy ai-edge-litert
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from ai_edge_litert.interpreter import Interpreter

ROOT = Path(__file__).resolve().parent
MODEL = ROOT / "dilated_aug_s0_int8.tflite"
SPEC = json.loads((ROOT / "dilated_aug_s0_input_spec.json").read_text())
SCALE = 0.0313725508749485
ZERO = -1
OUT_SCALE = 0.102272629737854
OUT_ZERO = -8
THRESHOLD = float(np.log(0.7 / 0.3))

interpreter = Interpreter(model_path=str(MODEL), num_threads=1)
interpreter.allocate_tensors()
in_info = interpreter.get_input_details()[0]
out_info = interpreter.get_output_details()[0]
assert tuple(in_info["shape"]) == (1, 50, 6) and in_info["dtype"] == np.int8
assert tuple(out_info["shape"]) == (1, 2) and out_info["dtype"] == np.int8
assert in_info["quantization"] == (SCALE, ZERO)
assert out_info["quantization"] == (OUT_SCALE, OUT_ZERO)

rng = np.random.default_rng(20260927)
mean = np.asarray(SPEC["mean"], dtype=np.float32)
std = np.asarray(SPEC["std"], dtype=np.float32)
vectors = []
counts = {"FALL": 0, "ADL": 0}
for trial in range(3000):
    # Physically plausible *illustrations* in g and deg/s, not real labeled motions.
    raw = np.tile(np.array([0, -1, 0, 0, 0, 0], dtype=np.float32), (50, 1))
    raw += rng.normal(0, [.04, .04, .04, 5, 5, 5], size=(50, 6)).astype(np.float32)
    if trial % 2:
        pos = int(rng.integers(0, 30))
        end = min(50, pos + int(rng.integers(10, 40)))
        n = end - pos
        raw[pos:end, :3] += rng.normal(0, rng.uniform(.1, 3), (n, 3))
        raw[pos:end, 3:] += rng.normal(0, rng.uniform(10, 500), (n, 3))

    normalized = np.clip((raw - mean) / std, -4, 4)
    q = np.clip(np.rint(normalized / SCALE) + ZERO, -128, 127).astype(np.int8)
    interpreter.set_tensor(in_info["index"], q[None])
    interpreter.invoke()
    out = interpreter.get_tensor(out_info["index"])[0]
    logits = (out.astype(np.float32) - OUT_ZERO) * OUT_SCALE
    margin = float((int(out[1]) - int(out[0])) * OUT_SCALE)
    p = float(1 / (1 + np.exp(-margin)))
    category = "FALL" if margin >= THRESHOLD else "ADL"
    if counts[category] >= 5:
        continue
    counts[category] += 1
    vectors.append({
        "name": f"synthetic_{category.lower()}_{counts[category]:02d}",
        "origin": "synthetic, model-predicted; no ground-truth activity label",
        "model_prediction": category,
        "normalized_input_int8_shape": [1, 50, 6],
        "input_int8": q.tolist(),
        "expected_output_int8": out.tolist(),
        "expected_dequant_logits": [float(x) for x in logits],
        "expected_margin": margin,
        "expected_p_fall": p,
    })
    if all(n == 5 for n in counts.values()):
        break
assert counts == {"FALL": 5, "ADL": 5}, counts
payload = {
    "model_file": MODEL.name,
    "model_sha256": hashlib.sha256(MODEL.read_bytes()).hexdigest(),
    "note": "Synthetic numerical golden vectors only; not KFall test samples.",
    "input_quantization": {"scale": SCALE, "zero_point": ZERO},
    "output_quantization": {"scale": OUT_SCALE, "zero_point": OUT_ZERO},
    "vectors": vectors,
}
(ROOT / "golden_inputs_synthetic.json").write_text(json.dumps(payload, indent=2))
print(counts, "wrote", ROOT / "golden_inputs_synthetic.json")
