from contextlib import closing
import os
import time
import json
import sqlite3
import base64
import threading
import queue
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from web3 import Web3
from web3.exceptions import ContractLogicError
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

# Config additions
PLAN_ID = int(os.getenv("PLAN_ID", 1))
GATEWAY_PRIVATE_KEY = os.getenv("GATEWAY_PRIVATE_KEY")

contract = None
contract_address = os.getenv("CONTRACT_ADDRESS")
deploy_block = 0
tx_queue = queue.Queue()
latest_event_id = {}

def init_contract():
    global contract, contract_address, deploy_block
    abi_path = os.path.join(os.path.dirname(__file__), 'abi', 'CareSLA.json')
    try:
        with open(abi_path, 'r') as f:
            abi = json.load(f)
            if isinstance(abi, dict) and 'abi' in abi:
                abi = abi['abi']
    except Exception as e:
        print(f"Could not load ABI: {e}")
        return

    if not contract_address:
        deploy_path = os.path.join(os.path.dirname(__file__), '..', 'deployments', f'{NETWORK}.json')
        if os.path.exists(deploy_path):
            try:
                with open(deploy_path, 'r') as f:
                    deploy_info = json.load(f)
                    contract_address = deploy_info.get("address")
                    deploy_block = deploy_info.get("deployBlock", 0)
            except Exception as e:
                pass
                
    if contract_address:
        contract = w3.eth.contract(address=contract_address, abi=abi)
        print(f"Contract loaded at {contract_address}")
    else:
        print("Warning: Contract address not found. Blockchain disabled.")

def tx_worker():
    if not GATEWAY_PRIVATE_KEY:
        print("Tx worker stopped: GATEWAY_PRIVATE_KEY not set.")
        return
        
    account = Account.from_key(GATEWAY_PRIVATE_KEY)
    
    while True:
        task = tx_queue.get()
        if task is None:
            break
            
        task_type, kwargs = task
        
        while True:
            try:
                if not contract:
                    raise Exception("Contract not initialized")
                    
                nonce = w3.eth.get_transaction_count(account.address)
                
                if task_type == 'reportFall':
                    func = contract.functions.reportFall(
                        kwargs['plan_id'],
                        kwargs['ts'],
                        kwargs['device_nonce'],
                        kwargs['data_hash'],
                        kwargs['sig']
                    )
                elif task_type == 'confirmArrival':
                    event_id = latest_event_id.get(kwargs['device'])
                    if not event_id:
                        print(f"[confirmArrival] No eventId for {kwargs['device']}. Dropping task.")
                        break
                        
                    func = contract.functions.confirmArrival(
                        event_id,
                        kwargs['ts'],
                        kwargs['device_nonce'],
                        kwargs['data_hash'],
                        kwargs['sig']
                    )
                
                # Gọi thử trước khi gửi. Contract từ chối (mọi lý do, kể cả custom error của OpenZeppelin)
                # thì gửi lại cũng vô ích: bỏ task. Lỗi mạng/RPC rơi xuống except ngoài để thử lại.
                try:
                    func.call({'from': account.address})
                except ContractLogicError as e:
                    print(f"[{task_type}] Contract reverted: {e}. Dropping task.")
                    if task_type == 'reportFall':
                        # FALL không lên chain -> ARRIVAL sau đó không được gắn vào sự cố cũ
                        latest_event_id.pop(kwargs['device'], None)
                    break

                tx = func.build_transaction({
                    'chainId': w3.eth.chain_id,
                    'nonce': nonce,
                })
                
                signed_tx = w3.eth.account.sign_transaction(tx, private_key=GATEWAY_PRIVATE_KEY)
                try:
                    raw_tx = signed_tx.raw_transaction
                except AttributeError:
                    raw_tx = signed_tx.rawTransaction
                    
                tx_hash = w3.eth.send_raw_transaction(raw_tx)
                
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                if receipt.status == 1:
                    print(f"[{task_type}] Tx successful: {tx_hash.hex()}")
                    if task_type == 'reportFall':
                        logs = contract.events.FallReported().process_receipt(receipt)
                        if logs:
                            event_id = logs[0].args.eventId
                            latest_event_id[kwargs['device']] = event_id
                    elif task_type == 'confirmArrival':
                        latest_event_id.pop(kwargs['device'], None)
                else:
                    print(f"[{task_type}] Tx reverted on chain: {tx_hash.hex()}")
                    if task_type == 'reportFall':
                        latest_event_id.pop(kwargs['device'], None)
                
                break
                
            except Exception as e:
                print(f"[{task_type}] Network/RPC Error: {e}. Retrying in 2s...")
                time.sleep(2)
        
        tx_queue.task_done()

def escalated_monitor():
    if not contract:
        return
        
    last_block = deploy_block
    chats = get_on_duty(PLAN_ID, int(time.time()))
    
    while True:
        time.sleep(5)
        try:
            current_block = w3.eth.block_number
            if current_block > last_block:
                logs = contract.events.Escalated.get_logs(from_block=last_block, to_block=current_block)
                for event in logs:
                    event_id = event.args.eventId
                    level = event.args.level
                    
                    if level == 1:
                        chat = chats["backup"]
                        msg = f"⚠️ LEO THANG CẤP 1! Sự cố #{event_id} đã chuyển cho Backup."
                    elif level == 2:
                        chat = chats["family"]
                        msg = f"🚨 LEO THANG CẤP 2! Sự cố #{event_id} quá hạn, đã báo cho Gia đình."
                    else:
                        continue
                        
                    if chat:
                        send_telegram(chat, msg)
                        
                plan_logs = contract.events.PlanCreated.get_logs(from_block=last_block, to_block=current_block)
                if plan_logs:
                    print("New CarePlan created, resetting false alarms count...")
                    with closing(sqlite3.connect(DB_FILE)) as conn:
                        conn.execute('DELETE FROM events WHERE event_type = 3')
                        conn.commit()
                        
                last_block = current_block + 1
        except Exception as e:
            print(f"[escalated_monitor] Error: {e}")

def get_on_duty(plan_id, ts):
    # Danh sách chat đã cấu hình; đường cảnh báo không gọi RPC đồng bộ.
    return {
        "primary": os.getenv("TELEGRAM_CHAT_PRIMARY"),
        "backup": os.getenv("TELEGRAM_CHAT_BACKUP"),
        "family": os.getenv("TELEGRAM_CHAT_FAMILY"),
        "center": os.getenv("TELEGRAM_CHAT_PROVIDER")
    }

def handle_fall(device, ts, nonce, data_hash, sig_hex, t_received):
    print(f"FALL DETECTED from {device} (nonce {nonce})")
    # IC-17: nhóm bỏ Telegram; cảnh báo là dòng log này (+ còi trên thiết bị).
    # Luôn in độ trễ từ lúc nhận MQTT để đo cho báo cáo.
    print(f"ALERT_DISPATCH elapsed_ms={(time.time() - t_received) * 1000:.1f}")
    chats = get_on_duty(PLAN_ID, ts)
    primary_chat = chats["primary"]
    if primary_chat:
        # Telegram chỉ còn là tùy chọn, demo không cấu hình
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
        
    data_hash_bytes = bytes.fromhex(data_hash[2:]) if data_hash.startswith("0x") else bytes.fromhex(data_hash)
    sig_bytes = bytes.fromhex(sig_hex[2:]) if sig_hex.startswith("0x") else bytes.fromhex(sig_hex)
    
    tx_queue.put(('reportFall', {
        'device': device,
        'plan_id': PLAN_ID,
        'ts': ts,
        'device_nonce': nonce,
        'data_hash': data_hash_bytes,
        'sig': sig_bytes
    }))

def handle_arrival(device, ts, nonce, data_hash, sig_hex, t_received):
    print(f"ARRIVAL DETECTED from {device} (nonce {nonce})")
    chats = get_on_duty(PLAN_ID, ts)
    if chats["primary"]:
        send_telegram(chats["primary"], f"✅ NHÂN VIÊN ĐĐ ĐẾN! Thiết bị: {device}, Nonce: {nonce}")
        
    data_hash_bytes = bytes.fromhex(data_hash[2:]) if data_hash.startswith("0x") else bytes.fromhex(data_hash)
    sig_bytes = bytes.fromhex(sig_hex[2:]) if sig_hex.startswith("0x") else bytes.fromhex(sig_hex)
    
    tx_queue.put(('confirmArrival', {
        'device': device,
        'ts': ts,
        'device_nonce': nonce,
        'data_hash': data_hash_bytes,
        'sig': sig_bytes
    }))

SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

def recover_signer(device, event_type, timestamp, nonce, data_hash_hex, sig_hex):
    # Chữ ký r(32) s(32) v(1). Từ chối high-s giống OpenZeppelin ECDSA (IC-14)
    sig_body = sig_hex[2:] if sig_hex.startswith("0x") else sig_hex
    if len(sig_body) != 130 or int(sig_body[64:128], 16) > SECP256K1_N // 2:
        print("Signature rejected: wrong length or high-s")
        return None
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

def verify_raw_hash(device, nonce, samples_b64, data_hash):
    try:
        raw = base64.b64decode(samples_b64, validate=True)
        if not raw or len(raw) % 12:
            raise ValueError("raw phải gồm các mẫu 6 số int16")
        valid = bytes(Web3.keccak(raw)) == bytes.fromhex(data_hash.removeprefix("0x"))
    except (ValueError, TypeError):
        valid = False
    print(f"{'Raw hash OK' if valid else 'Warning: dataHash mismatch'} for {device} nonce {nonce}")
    return valid


def on_message(client, userdata, msg):
    try:
        t_received = time.time()
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            print(f"Invalid JSON on topic {topic}")
            return

        if topic.endswith("/event"):
            device = data.get("device")
            event_type = data.get("eventType")
            ts = data.get("timestamp")
            nonce = data.get("nonce")
            data_hash = data.get("dataHash")
            sig = data.get("sig")
            
            if None in (device, event_type, ts, nonce, data_hash, sig):
                print(f"Missing fields in event payload: {data}")
                return

            device = str(device).lower()

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
            
            c.execute('SELECT samples_b64 FROM raw_data WHERE device=? AND nonce=?', (device, nonce))
            row = c.fetchone()
            conn.close()

            if row:
                samples_b64 = row[0]
                verify_raw_hash(device, nonce, samples_b64, data_hash)

            if event_type == 1:
                handle_fall(device, ts, nonce, data_hash, sig, t_received)
            elif event_type == 2:
                handle_arrival(device, ts, nonce, data_hash, sig, t_received)
            elif event_type == 3:
                print(f"CANCEL from {device} (nonce {nonce})")

        elif topic.endswith("/raw"):
            device = data.get("device")
            nonce = data.get("nonce")
            samples_b64 = data.get("samples_b64")
            
            if None in (device, nonce, samples_b64):
                print(f"Missing fields in raw payload: {data}")
                return
                
            device = str(device).lower()
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                INSERT INTO raw_data (device, nonce, samples_b64, t_received)
                VALUES (?, ?, ?, ?)
            ''', (device, nonce, samples_b64, t_received))
            conn.commit()
            c.execute('SELECT data_hash FROM events WHERE device=? AND nonce=? AND event_type IN (1, 2)', (device, nonce))
            hashes = c.fetchall()
            conn.close()
            for (data_hash,) in hashes:
                verify_raw_hash(device, nonce, samples_b64, data_hash)

            # --- PHƯƠNG ÁN DỰ PHÒNG AI (GIAI ĐOẠN 3) ---
            # Dùng nếu ESP32 không đủ tài nguyên chạy model
            # import sys
            # sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'ai_model'))
            # try:
            #     import infer
            #     raw_bytes = base64.b64decode(samples_b64)
            #     is_fall = infer.predict(raw_bytes)
            #     if not is_fall:
            #         print(f"AI Gateway: Nhận diện không phải té ngã cho {device}, hủy event.")
            #         return
            # except ImportError:
            #     pass
            # ------------------------------------------

        elif topic.endswith("/heartbeat"):
            device = data.get("device")
            ts = data.get("timestamp")
            
            if None in (device, ts):
                print(f"Missing fields in heartbeat payload: {data}")
                return
                
            device = str(device).lower()
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                INSERT INTO heartbeats (device, timestamp, t_received)
                VALUES (?, ?, ?)
                ON CONFLICT(device) DO UPDATE SET timestamp=excluded.timestamp, t_received=excluded.t_received
            ''', (device, ts, t_received))
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"Error in on_message: {e}")

# Chỉ thread heartbeat sở hữu trạng thái này, tránh cảnh báo lặp mỗi vòng.
heartbeat_lost = set()

def check_heartbeats(now=None):
    now = time.time() if now is None else now
    with closing(sqlite3.connect(DB_FILE)) as conn:
        rows = conn.execute('SELECT device, t_received FROM heartbeats').fetchall()
    for device, received in rows:
        lost = now - received > 120
        if lost and device not in heartbeat_lost:
            heartbeat_lost.add(device)
            message = f"HEARTBEAT LOST: {device} quá 120s"
        elif not lost and device in heartbeat_lost:
            heartbeat_lost.remove(device)
            message = f"HEARTBEAT RESTORED: {device} đã kết nối lại"
        else:
            continue
        print(message)
        chats = get_on_duty(PLAN_ID, int(now))
        for chat in dict.fromkeys([chats["center"], chats["family"]]):
            if chat:
                send_telegram(chat, message)

def heartbeat_monitor():
    while True:
        time.sleep(10)
        check_heartbeats()


def metrics_monitor():
    metrics_file = os.path.join(os.path.dirname(__file__), '..', 'dashboard', 'metrics.json')
    import datetime
    while True:
        time.sleep(10)
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            # 1. Telegram latency
            c.execute('SELECT t_received, t_telegram_ok FROM alerts WHERE t_telegram_ok IS NOT NULL')
            rows = c.fetchall()
            latencies = [(r[1] - r[0]) * 1000 for r in rows if r[1] > r[0]]
            avg_lat = round(sum(latencies) / len(latencies)) if latencies else 0
            max_lat = round(max(latencies)) if latencies else 0
            
            # 2. False alarms (CANCEL event_type = 3)
            c.execute('SELECT COUNT(*) FROM events WHERE event_type = 3')
            false_alarm_count = c.fetchone()[0]
            
            # 3. Heartbeats
            c.execute('SELECT device, timestamp FROM heartbeats')
            hb_rows = c.fetchall()
            last_heartbeat = {}
            for row in hb_rows:
                iso_time = datetime.datetime.fromtimestamp(row[1], datetime.timezone.utc).isoformat()
                if not iso_time.endswith("Z") and not "+" in iso_time:
                    iso_time += "Z"
                last_heartbeat[row[0]] = iso_time
                
            conn.close()
            
            metrics = {
                "avg_telegram_latency_ms": avg_lat,
                "max_telegram_latency_ms": max_lat,
                "false_alarm_count": false_alarm_count,
                "last_heartbeat": last_heartbeat
            }
            
            with open(metrics_file + '.tmp', 'w') as f:
                json.dump(metrics, f)
            os.replace(metrics_file + '.tmp', metrics_file)
        except Exception as e:
            pass

def main():
    init_db()
    init_contract()
    print("Gateway started. Phase 1, 2 & 3 ready.")
    
    # Start background threads
    threading.Thread(target=heartbeat_monitor, daemon=True).start()
    threading.Thread(target=tx_worker, daemon=True).start()
    threading.Thread(target=escalated_monitor, daemon=True).start()
    threading.Thread(target=metrics_monitor, daemon=True).start()

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
