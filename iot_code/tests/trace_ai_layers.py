"""Luu thong ke output tung op tren PC de so voi AI_TRACE tu ESP32."""
import json
from pathlib import Path
import numpy as np
from ai_edge_litert.interpreter import Interpreter, OpResolverType

root = Path(__file__).resolve().parents[2]
package = root / "carensla_esp32_model"
vector = json.loads((package / "golden_inputs_synthetic.json").read_text())["vectors"][0]
for mode in [OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES, OpResolverType.BUILTIN_REF]:
    engine = Interpreter(model_path=str(package / "dilated_aug_s0_int8.tflite"),
                         experimental_preserve_all_tensors=True,
                         experimental_op_resolver_type=mode, num_threads=1)
    engine.allocate_tensors()
    engine.set_tensor(engine.get_input_details()[0]["index"], np.array(vector["input_int8"], dtype=np.int8)[None])
    engine.invoke()
    print(mode.name, vector["name"])
    for op in engine._get_ops_details():
        for index in op["outputs"]:
            values = engine.get_tensor(int(index)).flatten()
            if values.dtype != np.int8:
                continue
            checksum = 2166136261
            for value in values:
                checksum = ((checksum ^ (int(value) & 255)) * 16777619) & 0xffffffff
            print(f"AI_TRACE op={op['index']} tensor={index} n={len(values)} sum={int(values.sum())} "
                  f"min={int(values.min())} max={int(values.max())} hash={checksum:08x} {op['op_name']}")
