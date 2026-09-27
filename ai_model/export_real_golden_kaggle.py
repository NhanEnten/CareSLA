"""Run in the live kall-v2 notebook with `%run -i export_real_golden_kaggle.py`.

Requires Xte, yte, idte, GLOBAL_MEAN, GLOBAL_STD and the quantized .tflite.
Unlike golden_inputs_synthetic.json, these are labeled held-out KFall windows.
"""
import json
from pathlib import Path
import numpy as np
import tensorflow as tf

required = ["Xte", "yte", "idte", "GLOBAL_MEAN", "GLOBAL_STD"]
assert all(k in globals() for k in required), "Run this in the trained KFall notebook with %run -i"
path = Path("/kaggle/working/dilated_aug_s0_int8.tflite")
it = tf.lite.Interpreter(model_path=str(path))
it.allocate_tensors()
ii, oo = it.get_input_details()[0], it.get_output_details()[0]
isc, izp = ii["quantization"]
osc, ozp = oo["quantization"]
assert tuple(ii["shape"]) == (1, 50, 6) and ii["dtype"] == np.int8
assert tuple(oo["shape"]) == (1, 2) and oo["dtype"] == np.int8
threshold = float(np.log(.7 / .3))

vectors = []
selected_files = set()
for label in (0, 1):
    found = 0
    for k in np.flatnonzero(np.asarray(yte) == label):
        if idte[k] in selected_files:
            continue  # independent source trial for each vector
        q = np.clip(np.rint(Xte[k] / isc) + izp, -128, 127).astype(np.int8)
        it.set_tensor(ii["index"], q[None])
        it.invoke()
        out = it.get_tensor(oo["index"])[0]
        margin = float((int(out[1]) - int(out[0])) * osc)
        predicted = int(margin >= threshold)
        if predicted != label:
            continue
        selected_files.add(idte[k])
        vectors.append({
            "name": f"kfall_{'fall' if label else 'adl'}_{found+1:02d}",
            "source_trial": str(idte[k]),
            "ground_truth_window_label": int(label),
            "window_index_in_Xte": int(k),
            "input_int8": q.tolist(),
            "expected_output_int8": out.tolist(),
            "expected_margin": margin,
            "expected_p_fall": float(1 / (1 + np.exp(-margin))),
        })
        found += 1
        if found == 5:
            break
    if found != 5:
        raise RuntimeError(f"Found only {found}/5 labeled test windows for class {label}")

output = Path("/kaggle/working/golden_inputs_kfall_test.json")
output.write_text(json.dumps({
    "model": path.name, "dataset": "KFall test subjects only",
    "input_scale": float(isc), "input_zero_point": int(izp),
    "output_scale": float(osc), "output_zero_point": int(ozp),
    "vectors": vectors,
}, indent=2))
print("Wrote", output, "with", len(vectors), "labeled windows from independent trials")
