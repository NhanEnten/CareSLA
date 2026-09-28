"""Thiết bị giả cho demo local; ký EIP-191, nonce bền trong SQLite.

python tools/fake_device.py fall --key-file .keys/device.key
Không dùng chung khóa/nonce với ESP32 thật. Không in khóa ra log.
"""
from contextlib import closing
import argparse
import base64
import json
import os
from pathlib import Path
import sqlite3
import struct
import time

from dotenv import load_dotenv
from eth_account import Account
from eth_account.messages import encode_defunct
import paho.mqtt.client as mqtt
from web3 import Web3

ROOT = Path(__file__).resolve().parents[1]


def next_nonce(path, device):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS nonces (device TEXT PRIMARY KEY, value INTEGER NOT NULL)')
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT value FROM nonces WHERE device=?', (device,)).fetchone()
        nonce = (row[0] if row else 0) + 1
        db.execute('INSERT OR REPLACE INTO nonces VALUES (?, ?)', (device, nonce))
    return nonce  # Đã commit trước khi publish; lỗi mạng vẫn tiêu nonce.


def make_event(key, event_type, timestamp, nonce, raw):
    device = Account.from_key(key).address.lower()
    data_hash = bytes(32) if event_type == 3 else bytes(Web3.keccak(raw))
    packed = (bytes.fromhex(device[2:]) + bytes([event_type])
              + timestamp.to_bytes(8, 'big') + nonce.to_bytes(8, 'big') + data_hash)
    signed = Account.sign_message(encode_defunct(Web3.keccak(packed)), key)
    return dict(device=device, eventType=event_type, timestamp=timestamp, nonce=nonce,
                dataHash='0x' + data_hash.hex(), sig='0x' + signed.signature.hex())


def publish_event(client, key, kind, nonce_file, raw=None):
    device = Account.from_key(key).address.lower()
    topic = f'carensla/{device}'
    now = int(time.time())
    if kind == 'heartbeat':
        messages = [(topic + '/heartbeat', dict(device=device, timestamp=now, battery=None))]
    else:
        # 400 mẫu đứng yên giả, đúng ±16g và int16 little-endian; không phải dữ liệu thực nghiệm.
        raw = raw if raw is not None else struct.pack('<6h', 0, 0, 2048, 0, 0, 0) * 400
        if not raw or len(raw) % 12:
            raise ValueError('Raw phải chứa số nguyên mẫu 12 byte')
        nonce = next_nonce(nonce_file, device)
        payload = make_event(key, {'fall': 1, 'arrival': 2, 'cancel': 3}[kind], now, nonce, raw)
        messages = [(topic + '/event', payload)]
        if kind != 'cancel':
            messages.append((topic + '/raw', dict(device=device, nonce=nonce,
                            samples_b64=base64.b64encode(raw).decode('ascii'))))
    for name, payload in messages:
        info = client.publish(name, json.dumps(payload), qos=1)
        info.wait_for_publish(timeout=10)
        if not info.is_published():
            raise TimeoutError('Broker chưa xác nhận MQTT; nonce đã được giữ')
    print(f'Published {kind}: {device}' + (f' nonce={nonce}' if kind != 'heartbeat' else ''), flush=True)


def main():
    load_dotenv(ROOT / '.env')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=['fall', 'arrival', 'cancel', 'heartbeat'])
    parser.add_argument('--key-file', type=Path, required=True)
    parser.add_argument('--nonce-file', type=Path, default=ROOT / '.local/fake-device.sqlite')
    parser.add_argument('--raw-file', type=Path)
    parser.add_argument('--repeat', action='store_true', help='Chỉ heartbeat: lặp mỗi 60 giây')
    args = parser.parse_args()
    if args.repeat and args.kind != 'heartbeat':
        parser.error('--repeat chỉ dùng với heartbeat')
    try:
        key = args.key_file.read_text().strip()
        Account.from_key(key)
    except Exception:
        parser.error('Không đọc được khóa thiết bị hợp lệ từ file riêng')
    raw = args.raw_file.read_bytes() if args.raw_file else None
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(os.getenv('MQTT_HOST', '127.0.0.1'), int(os.getenv('MQTT_PORT', '1883')), 60)
    client.loop_start()
    try:
        while True:
            publish_event(client, key, args.kind, args.nonce_file, raw)
            if not args.repeat:
                break
            time.sleep(60)
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == '__main__':
    main()
