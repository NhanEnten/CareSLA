import os
import time
import json
import sqlite3
import base64
import threading
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct
import requests

load_dotenv()

# Config
NETWORK = os.getenv("NETWORK", "localhost")
# Tên biến thống nhất theo IC-15: localhost cố định, sepolia đọc SEPOLIA_RPC_URL
RPC_URL = os.getenv("SEPOLIA_RPC_URL") if NETWORK == "sepolia" else "http://127.0.0.1:8545"
MQTT_BROKER = os.getenv("MQTT_HOST", "127.0.0.1")  # IC-15: biến môi trường tên MQTT_HOST
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REGISTERED_DEVICES = [addr.strip().lower() for addr in os.getenv("REGISTERED_DEVICES", "").split(",") if addr.strip()]

# SQLite Setup
DB_FILE = "gateway.db"
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device TEXT,
            event_type INTEGER,
            timestamp INTEGER,
            nonce INTEGER,
            data_hash TEXT,
            sig TEXT,
            t_received REAL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS raw_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device TEXT,
            nonce INTEGER,
            samples_b64 TEXT,
            t_received REAL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS heartbeats (
            device TEXT PRIMARY KEY,
            timestamp INTEGER,
            t_received REAL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device TEXT,
            event_type INTEGER,
            t_received REAL,
            t_telegram_ok REAL
        )
    ''')
    conn.commit()
    conn.close()

# Telegram sending
def send_telegram(chat_id, message):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        print(f"Telegram not configured. MSG: {message}")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        response = requests.post(url, json=payload, timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

# Web3 setup
w3 = Web3(Web3.HTTPProvider(RPC_URL))
# Load ABI and setup contract interaction later for phase 2.
# For now, we only need getOnDuty fallback.

def get_on_duty_fallback():
    return {
        "primary": os.getenv("TELEGRAM_CHAT_PRIMARY"),
        "backup": os.getenv("TELEGRAM_CHAT_BACKUP"),
        "family": os.getenv("TELEGRAM_CHAT_FAMILY"),
        "center": os.getenv("TELEGRAM_CHAT_PROVIDER")  # IC-15: trung tâm = provider
    }

def handle_fall(device, nonce, t_received):
    print(f"FALL DETECTED from {device} (nonce {nonce})")
    # Send Telegram immediately
    chats = get_on_duty_fallback()
    primary_chat = chats["primary"]
    if primary_chat:
        success = send_telegram(primary_chat, f"🚨 TÉ NGÃ PHÁT HIỆN! Thiết bị: {device}, Nonce: {nonce}")
        t_telegram_ok = time.time() if success else None
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            INSERT INTO alerts (device, event_type, t_received, t_telegram_ok)
            VALUES (?, ?, ?, ?)
        ''', (device, 1, t_received, t_telegram_ok))
        conn.commit()
        conn.close()

def recover_signer(device, event_type, timestamp, nonce, data_hash_hex, sig_hex):
    # packed = abi.encodePacked(address, uint8, uint64, uint64, bytes32)
    device_bytes = bytes.fromhex(device[2:])
    data_hash_bytes = bytes.fromhex(data_hash_hex[2:]) if data_hash_hex.startswith("0x") else bytes.fromhex(data_hash_hex)
    packed = (
        device_bytes
        + event_type.to_bytes(1, "big")
        + timestamp.to_bytes(8, "big")
        + nonce.to_bytes(8, "big")
        + data_hash_bytes
    )
    message_hash = Web3.keccak(packed)
    signable = encode_defunct(message_hash)
    try:
        recovered = Account.recover_message(signable, signature=sig_hex)
        return recovered.lower()
    except Exception as e:
        print(f"Signature recovery error: {e}")
        return None

def on_message(client, userdata, msg):
    t_received = time.time()
    topic = msg.topic
    payload = msg.payload.decode('utf-8')
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        print(f"Invalid JSON on topic {topic}")
        return

    if topic.endswith("/event"):
        # {"device": "0x...", "eventType": 1, "timestamp": 1760000000, "nonce": 42, "dataHash": "0x...", "sig": "0x..."}
        device = data.get("device", "").lower()
        event_type = data.get("eventType")
        ts = data.get("timestamp")
        nonce = data.get("nonce")
        data_hash = data.get("dataHash")
        sig = data.get("sig")

        if device not in REGISTERED_DEVICES and len(REGISTERED_DEVICES) > 0:
            print(f"Unregistered device {device}, ignoring.")
            return

        recovered = recover_signer(device, event_type, ts, nonce, data_hash, sig)
        if recovered != device:
            print(f"Invalid signature from {device}, ignoring.")
            return

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            INSERT INTO events (device, event_type, timestamp, nonce, data_hash, sig, t_received)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (device, event_type, ts, nonce, data_hash, sig, t_received))
        conn.commit()
        
        # Check matching raw data
        c.execute('SELECT samples_b64 FROM raw_data WHERE device=? AND nonce=?', (device, nonce))
        row = c.fetchone()
        conn.close()

        if row:
            samples_b64 = row[0]
            raw_bytes = base64.b64decode(samples_b64)
            calc_hash = Web3.keccak(raw_bytes).hex()
            if not data_hash.endswith(calc_hash[2:]):
                print(f"Warning: dataHash mismatch for {device} nonce {nonce}")

        if event_type == 1:
            handle_fall(device, nonce, t_received)
        elif event_type == 3:
            print(f"CANCEL from {device} (nonce {nonce})")

    elif topic.endswith("/raw"):
        # {"device": "0x...", "nonce": 42, "samples_b64": "..."}
        device = data.get("device", "").lower()
        nonce = data.get("nonce")
        samples_b64 = data.get("samples_b64")
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            INSERT INTO raw_data (device, nonce, samples_b64, t_received)
            VALUES (?, ?, ?, ?)
        ''', (device, nonce, samples_b64, t_received))
        conn.commit()
        conn.close()

    elif topic.endswith("/heartbeat"):
        # {"device": "0x...", "timestamp": 1760000000}
        device = data.get("device", "").lower()
        ts = data.get("timestamp")
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            INSERT INTO heartbeats (device, timestamp, t_received)
            VALUES (?, ?, ?)
            ON CONFLICT(device) DO UPDATE SET timestamp=excluded.timestamp, t_received=excluded.t_received
        ''', (device, ts, t_received))
        conn.commit()
        conn.close()

def heartbeat_monitor():
    while True:
        time.sleep(10)
        now = time.time()
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT device, t_received FROM heartbeats')
        rows = c.fetchall()
        conn.close()
        
        for device, t_received in rows:
            if now - t_received > 120:
                print(f"HEARTBEAT LOST for {device}!")
                chats = get_on_duty_fallback()
                for chat in [chats["center"], chats["family"]]:
                    if chat:
                        send_telegram(chat, f"⚠️ Mất kết nối thiết bị {device} quá 120s!")

def main():
    init_db()
    print("Gateway started. Phase 1 ready.")
    
    # Start heartbeat monitor in background
    t = threading.Thread(target=heartbeat_monitor, daemon=True)
    t.start()

    client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e:
        print(f"Could not connect to MQTT broker {MQTT_BROKER}:{MQTT_PORT} - {e}")
        return

    client.subscribe("carensla/+/event")
    client.subscribe("carensla/+/raw")
    client.subscribe("carensla/+/heartbeat")
    
    print(f"Subscribed to MQTT at {MQTT_BROKER}:{MQTT_PORT}")
    client.loop_forever()

if __name__ == "__main__":
    main()
