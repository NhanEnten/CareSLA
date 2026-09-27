#!/usr/bin/env python3
"""
Sinh docs/test_vectors.json — bộ vector chuẩn cho toàn nhóm (P1 test, P3 ESP32, P5 gateway).
Dùng cùng khóa và input với file mẫu contracts/p1_tmp/sample_test_vectors.json (ethers v6)
nên kết quả phải giống hệt từng byte.

Chạy:
    pip install web3 eth-account
    python tools/make_test_vector.py

Khóa CHỈ ĐỂ TEST — không bao giờ dùng cho thiết bị thật.
"""

import json
import struct
import base64
import os
import sys
from pathlib import Path

# Fix console encoding trên Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct


# ── Khóa test: keccak256("carensla test key - DO NOT USE") ──
TEST_SEED = b"carensla test key - DO NOT USE"
TEST_KEY = "0x" + Web3.keccak(text="carensla test key - DO NOT USE").hex()
account = Account.from_key(TEST_KEY)
DEVICE = account.address.lower()

print(f"Test key:  {TEST_KEY}")
print(f"Device:    {DEVICE}")


def samples_raw() -> bytes:
    """3 mẫu × 6 số int16 little-endian (ax, ay, az, gx, gy, gz)."""
    vals = [100, -200, 16384, 5, -5, 0,
            120, -180, 16000, 7, -3, 1,
            -32768, 32767, 0, 1, -1, 256]
    return struct.pack(f"<{len(vals)}h", *vals)


def make_vector(name: str, event_type: int, timestamp: int, nonce: int,
                data_hash: bytes, extra: dict | None = None) -> dict:
    """
    Tạo một vector theo đúng AGENTS.md mục 6.2:
      packed      = abi.encodePacked(address, uint8, uint64, uint64, bytes32)
      messageHash = keccak256(packed)
      ethSigned   = keccak256("\\x19Ethereum Signed Message:\\n32" || messageHash)
      sig         = secp256k1_sign(ethSigned)
    """
    # ── Pack: address(20) + uint8(1) + uint64(8, BE) + uint64(8, BE) + bytes32(32) = 69 byte ──
    device_bytes = bytes.fromhex(DEVICE[2:])                         # 20 byte
    packed = (
        device_bytes
        + event_type.to_bytes(1, "big")
        + timestamp.to_bytes(8, "big")
        + nonce.to_bytes(8, "big")
        + data_hash
    )
    assert len(packed) == 69, f"packed phải đúng 69 byte, nhưng có {len(packed)}"

    message_hash = Web3.keccak(packed)                               # bytes32
    # EIP-191: "\x19Ethereum Signed Message:\n32" + messageHash
    signable = encode_defunct(message_hash)
    signed = Account.sign_message(signable, private_key=TEST_KEY)

    sig_bytes = signed.signature                                     # bytes, 65 byte (r+s+v)
    v = sig_bytes[-1]  # 27 hoặc 28

    # Tính ethSigned giống ethers.hashMessage(): keccak256(prefix + messageHash)
    prefix = b"\x19Ethereum Signed Message:\n32"
    eth_signed = Web3.keccak(prefix + message_hash)

    result = {
        "name": name,
        "eventType": event_type,
        "timestamp": timestamp,
        "nonce": nonce,
        "dataHash": "0x" + data_hash.hex(),
    }
    if extra:
        result.update(extra)
    result.update({
        "packed": "0x" + packed.hex(),
        "messageHash": "0x" + message_hash.hex(),
        "ethSigned": "0x" + eth_signed.hex(),
        "sig": "0x" + sig_bytes.hex(),
        "v": v,
    })
    return result


def main():
    raw = samples_raw()
    fall_hash = Web3.keccak(raw)  # bytes32
    zero_hash = b"\x00" * 32
    T = 2000000000  # năm 2033 — tương lai để contract test tua giờ tới được

    vectors = [
        make_vector("fall_basic", 1, T, 42, fall_hash,
                     {"samples_b64": base64.b64encode(raw).decode()}),
        make_vector("arrival_basic", 2, T + 30, 43, fall_hash),
        make_vector("cancel_basic", 3, T + 60, 44, zero_hash),
        # nonce > 2^32: bắt lỗi big-endian uint64 ghi thiếu byte
        make_vector("fall_big_nonce", 1, T + 100, 2**40 + 7, fall_hash),
    ]

    # Đảm bảo có cả v = 27 và v = 28 (IC-14 yêu cầu)
    seen_v = set(vec["v"] for vec in vectors)
    n = 50
    while len(seen_v) < 2:
        vec = make_vector("fall_other_v", 1, T + 200, n, fall_hash)
        if vec["v"] not in seen_v:
            vectors.append(vec)
            seen_v.add(vec["v"])
        n += 1

    output = {
        "note": "Khóa CHỈ ĐỂ TEST, không dùng cho thiết bị thật",
        "generator": "tools/make_test_vector.py",
        "privateKey": TEST_KEY,
        "device": DEVICE,
        "vectors": vectors,
    }

    # Ghi ra docs/test_vectors.json
    out_path = Path(__file__).resolve().parent.parent / "docs" / "test_vectors.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\nĐã ghi {out_path}")
    print(f"Số vector: {len(vectors)}")
    for vec in vectors:
        print(f"  {vec['name']}: v={vec['v']}, nonce={vec['nonce']}")

    # ── Đối chiếu với file mẫu JS (nếu có) ──
    sample_path = Path(__file__).resolve().parent.parent / "contracts" / "p1_tmp" / "sample_test_vectors.json"
    if sample_path.exists():
        with open(sample_path, "r", encoding="utf-8") as f:
            sample = json.load(f)
        print(f"\n── Đối chiếu với {sample_path.name} ──")
        sample_vecs = {v["name"]: v for v in sample["vectors"]}
        all_match = True
        for vec in vectors:
            sv = sample_vecs.get(vec["name"])
            if sv is None:
                continue
            fields = ["packed", "messageHash", "ethSigned", "sig", "v"]
            for field in fields:
                if str(vec[field]) != str(sv[field]):
                    print(f"  ✗ {vec['name']}.{field} KHÁC!")
                    print(f"    Python: {vec[field]}")
                    print(f"    JS:     {sv[field]}")
                    all_match = False
                else:
                    print(f"  ✓ {vec['name']}.{field}")
        if all_match:
            print("  ✅ Tất cả đều khớp byte-by-byte!")
        else:
            print("  ❌ Có trường không khớp — cần kiểm tra lại!")
            exit(1)
    else:
        print(f"\n⚠️ Không tìm thấy {sample_path} để đối chiếu.")


if __name__ == "__main__":
    main()
