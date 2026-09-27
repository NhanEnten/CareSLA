"""Chỉ build, không flash. Tạm đổi config rồi khôi phục nguyên byte ban đầu.

Chạy trong ESP-IDF Terminal, không sửa config.h đồng thời khi test đang chạy.
"""
import os
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
config = root / "main/config.h"
original = config.read_bytes()
current = original
idf = Path(os.environ["IDF_PATH"]) / "tools/idf.py"
logs = root / "build/host_tests"
logs.mkdir(parents=True, exist_ok=True)

def build(name):
    with (logs / f"build_{name}.log").open("w", encoding="utf-8") as out:
        result = subprocess.run([sys.executable, str(idf), "build"], cwd=root,
                                stdout=out, stderr=subprocess.STDOUT)
    print(f"{name}: exit={result.returncode}, log={logs / ('build_' + name + '.log')}", flush=True)
    if result.returncode:
        raise RuntimeError(f"Build {name} failed")

try:
    for name, monitor, passive in [("standalone", 0, 0), ("monitor_active", 1, 0), ("monitor_passive", 1, 1)]:
        if config.read_bytes() != current:
            raise RuntimeError("config.h changed externally; stop to preserve user edits")
        text = original.decode("utf-8")
        values = {"PIN_SDA": 21, "PIN_SCL": 22, "PIN_BUTTON": 23, "PIN_BUZZER": 25,
                  "RUN_MONITOR": monitor, "P4_SPEC_CONFIRMED": 1, "BUZZER_PASSIVE": passive}
        for key, value in values.items():
            text = re.sub(rf"(?m)^#define {key}\s+[^\r\n]+", f"#define {key} {value}", text)
        current = text.encode("utf-8")
        config.write_bytes(current)
        build(name)
finally:
    if config.read_bytes() == current:
        config.write_bytes(original)
        build("restored")
    else:
        raise RuntimeError("config.h edited concurrently; not overwritten; rebuild manually")
