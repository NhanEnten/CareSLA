"""Doi chieu header firmware, JSON P4 va inference tren PC; khong sua dap an."""
import hashlib
import json
from pathlib import Path
import re

import numpy as np
from ai_edge_litert.interpreter import Interpreter, OpResolverType

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "carensla_esp32_model"
payload = json.loads((PACKAGE / "golden_inputs_synthetic.json").read_text())
model = (PACKAGE / "dilated_aug_s0_int8.tflite").read_bytes()
embedded = bytes(int(x, 16) for x in re.findall(
    r"0x([0-9a-fA-F]{2})", (ROOT / "iot_code/main/model_data.cc").read_text()))
assert model == embedded
assert hashlib.sha256(model).hexdigest() == payload["model_sha256"]
header = (ROOT / "iot_code/main/golden_inputs.h").read_text()
blocks = re.findall(r'\{"(synthetic_[^"]+)",\s*\{(.*?)\},\s*\{([^}]+)\},\s*([01])\}', header, re.S)
assert len(blocks) == len(payload["vectors"]) == 10
vectors = {v["name"]: v for v in payload["vectors"]}
for name, inputs, expected, candidate in blocks:
    v = vectors[name]
    numbers = [int(x) for x in re.findall(r"-?\d+", inputs)]
    assert numbers == np.asarray(v["input_int8"]).flatten().tolist(), name
    assert [int(x) for x in expected.split(",")] == v["expected_output_int8"], name
    assert int(candidate) == (v["model_prediction"] == "FALL"), name
print("Model bytes, SHA256 and all header/JSON vectors match", flush=True)

failed = False
for mode in [OpResolverType.AUTO, OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES, OpResolverType.BUILTIN_REF]:
    engine = Interpreter(model_content=model, num_threads=1, experimental_op_resolver_type=mode)
    engine.allocate_tensors()
    in_index = engine.get_input_details()[0]["index"]
    out_index = engine.get_output_details()[0]["index"]
    print(mode, flush=True)
    for name, inputs, expected, candidate in blocks:
        v = vectors[name]
        engine.set_tensor(in_index, np.asarray(v["input_int8"], dtype=np.int8)[None])
        engine.invoke()
        actual = engine.get_tensor(out_index)[0].tolist()
        matched = actual == v["expected_output_int8"]
        failed |= not matched
        print(name, "actual=", actual, "expected=", v["expected_output_int8"], "PASS" if matched else "FAIL", flush=True)
raise SystemExit(1 if failed else 0)
