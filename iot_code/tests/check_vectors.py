"""Compile cùng signer C, đối chiếu từng byte với vector độc lập P1/P5."""
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
vector_path = Path(sys.argv[1]) if len(sys.argv) > 1 else root.parent / "docs/test_vectors.json"
if not vector_path.exists():
    raise SystemExit("Chua co test vector chinh thuc. Truyen duong dan vector P1 de thu tam.")
data = json.loads(vector_path.read_text(encoding="utf-8-sig"))
build = root / "build" / "host_tests"
build.mkdir(parents=True, exist_ok=True)
src = root / "components/trezor_crypto/src"
files = ["bignum", "ecdsa", "secp256k1", "sha2", "sha3", "hmac", "hmac_drbg", "rfc6979", "memzero"]
exe = build / "signer_test.exe"
command = ["gcc", "-std=gnu11", "-O2", "-flto", "-ffunction-sections", "-fdata-sections",
           "-I" + str(src), "-I" + str(root / "main"),
           str(root / "tests/signer_host.c"), str(root / "main/signer.c")]
command += [str(src / (name + ".c")) for name in files]
command += ["-Wl,--gc-sections", "-lbcrypt", "-o", str(exe)]
subprocess.run(command, check=True)
for vector in data["vectors"]:
    text = f'{data["privateKey"]} {vector["eventType"]} {vector["timestamp"]} {vector["nonce"]} {vector["dataHash"]}\n'
    result = subprocess.run([str(exe)], input=text, text=True, capture_output=True, check=True)
    expected = [data["device"], vector["packed"], vector["messageHash"], vector["ethSigned"], vector["sig"]]
    assert result.stdout.splitlines() == [item.lower() for item in expected], vector["name"]
    print("PASS:", vector["name"], "address / packed / messageHash / ethSigned / sig")
print("Host vectors passed; van can chay tren ESP32 va vector chinh thuc P5.")
