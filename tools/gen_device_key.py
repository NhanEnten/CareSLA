#!/usr/bin/env python3
"""
Sinh khóa thiết bị mới cho CareSLA.
In ra:
  - Khóa riêng (hex) để dán vào secrets.h (ESP32)
  - Địa chỉ Ethereum để dùng trong demo_setup.js và createCarePlan

Chạy:
    python tools/gen_device_key.py

⚠️ Chỉ dùng cho testnet. Không dùng cho mainnet.
"""

from eth_account import Account
import secrets


def main():
    # Sinh khóa ngẫu nhiên an toàn
    private_key = "0x" + secrets.token_hex(32)
    account = Account.from_key(private_key)
    address = account.address

    print("=" * 60)
    print("  CareSLA — Sinh khóa thiết bị mới")
    print("=" * 60)
    print()
    print(f"Địa chỉ Ethereum:  {address}")
    print(f"Địa chỉ (thường):  {address.lower()}")
    print(f"Khóa riêng:        {private_key}")
    print()
    print("── Dán vào secrets.h (ESP32) ──")
    print()

    # Chuyển khóa riêng thành mảng byte C
    key_bytes = bytes.fromhex(private_key[2:])
    hex_str = ", ".join(f"0x{b:02x}" for b in key_bytes)
    print(f'#define DEVICE_PRIVATE_KEY {{ {hex_str} }}')
    print()

    print("── Dùng trong demo_setup.js / createCarePlan ──")
    print()
    print(f'const DEVICE_ADDRESS = "{address.lower()}";')
    print()
    print("⚠️ Không commit khóa riêng vào Git. Thêm vào .env hoặc secrets.h (đã có trong .gitignore).")


if __name__ == "__main__":
    main()
