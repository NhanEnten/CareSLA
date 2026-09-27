"""Keeper CareSLA: kiểm tra mỗi 5 giây; bất kỳ ví nào cũng được gọi timeout.

Deadline/trạng thái được dựng từ event để khôi phục khi khởi động lại;
vẫn đọc eventCount() và getFallEvent(id) mỗi vòng theo IC-01/IC-09.
ID lấy từ FallReported, không giả định bộ đếm bắt đầu từ 0 hay 1.
"""

import argparse
import json
import logging
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
LOG = logging.getLogger("caresla.keeper")
EVENT_NAMES = ("FallReported", "Acknowledged", "Arrived", "Escalated")


def safe_error(error):
    message = str(error)
    for name, value in os.environ.items():
        if value and any(word in name for word in ("PRIVATE_KEY", "TOKEN", "API_KEY", "RPC_URL")):
            message = message.replace(value, "[REDACTED]")
    message = re.sub(r"https?://\S+", "[RPC_URL]", message)
    return f"{type(error).__name__}: {message}"


def apply_event(states, name, args):
    event_id = int(args["eventId"])
    if name == "FallReported":
        states[event_id] = {"deadline": int(args["deadline"]), "level": 0, "closed": False}
        return
    if event_id not in states:
        raise ValueError(f"Thiếu FallReported cho eventId={event_id}; kiểm tra deployBlock/ABI.")
    if name in ("Acknowledged", "Arrived"):
        states[event_id]["closed"] = True
    elif name == "Escalated":
        states[event_id]["level"] = int(args["level"])
        states[event_id]["deadline"] = int(args["newDeadline"])


def is_due(state, chain_timestamp):
    return not state["closed"] and state["level"] < 2 and chain_timestamp > state["deadline"]


class Keeper:
    def __init__(self, w3, contract, deployment, account=None, dry_run=False):
        self.w3 = w3
        self.contract = contract
        self.deployment = deployment
        self.account = account
        self.dry_run = dry_run
        self.states = {}
        self.next_block = deployment["deployBlock"]
        self.last_block = None
        self.last_hash = None
        self.pending = None
        self.decoders = {}
        for name in EVENT_NAMES:
            event = getattr(contract.events, name)()
            abi = event.abi
            signature = name + "(" + ",".join(item["type"] for item in abi["inputs"]) + ")"
            self.decoders[w3.keccak(text=signature).hex()] = event

    def sync_events(self, head):
        # Nếu block cuối đã quét bị thay thế do reorg/reset, dựng lại từ deployment.
        if self.last_block is not None:
            if head["number"] < self.last_block or self.w3.eth.get_block(self.last_block)["hash"] != self.last_hash:
                LOG.warning("Chain reorg/reset: quét lại event từ deployBlock.")
                self.states = {}
                self.next_block = self.deployment["deployBlock"]
                self.last_block = None
        while self.next_block <= head["number"]:
            end = min(self.next_block + 999, head["number"])
            logs = self.w3.eth.get_logs({
                "address": self.contract.address,
                "fromBlock": self.next_block,
                "toBlock": end,
                "topics": [["0x" + topic.removeprefix("0x") for topic in self.decoders]],
            })
            # Cập nhật nguyên một batch: RPC/decode lỗi không để lại trạng thái nửa chừng.
            updated = {event_id: dict(state) for event_id, state in self.states.items()}
            for log in sorted(logs, key=lambda item: (item["blockNumber"], item["transactionIndex"], item["logIndex"])):
                decoded = self.decoders[log["topics"][0].hex()].process_log(log)
                apply_event(updated, decoded["event"], decoded["args"])
            block = self.w3.eth.get_block(end)
            self.states = updated
            self.next_block = end + 1
            self.last_block, self.last_hash = end, block["hash"]

    def check_pending(self):
        """Không tăng nonce/bắn tx mới khi tx cũ chưa rõ kết quả."""
        from web3.exceptions import TransactionNotFound

        if self.pending is None:
            return False
        tx_hash, raw, event_id = self.pending
        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            try:
                self.w3.eth.get_transaction(tx_hash)
            except TransactionNotFound:
                # Nếu gửi trước đó bị mất kết nối, thử lại đúng tx đã ký, cùng nonce.
                self.w3.eth.send_raw_transaction(raw)
            LOG.info("Đang chờ receipt: eventId=%s tx=%s", event_id, tx_hash.hex())
            return True
        self.pending = None
        if receipt["status"] == 1:
            LOG.info("Timeout thành công: eventId=%s tx=%s gas=%s", event_id, tx_hash.hex(), receipt["gasUsed"])
        else:
            LOG.warning("Tx revert (có thể người khác vừa acknowledge/timeout): eventId=%s tx=%s", event_id, tx_hash.hex())
        return False

    def poll(self):
        expected = self.deployment["chainId"]
        if self.w3.eth.chain_id != expected:
            raise ValueError("RPC chainId không khớp deployment; không gửi giao dịch.")
        if not self.w3.eth.get_code(self.contract.address):
            raise ValueError("Không có code tại deployment. Nếu node restart, deploy/setup lại.")
        # Receipt trước, snapshot chain sau: không dùng trạng thái cũ sau khi tx đã mine.
        waiting = self.check_pending()
        head = self.w3.eth.get_block("latest")
        self.sync_events(head)
        count = self.contract.functions.eventCount().call(block_identifier=head["number"])
        if count != len(self.states):
            raise ValueError(f"eventCount={count} nhưng có {len(self.states)} FallReported; kiểm tra deployBlock/ABI.")
        errors = 0
        for event_id, state in sorted(self.states.items()):
            try:
                # Kiểm tra hàm đọc tại cùng block; trạng thái dùng log đã đồng bộ ở trên.
                self.contract.functions.getFallEvent(event_id).call(block_identifier=head["number"])
                if not is_due(state, head["timestamp"]):
                    continue
                if self.dry_run:
                    LOG.info("DRY RUN: eventId=%s level=%s đã quá deadline=%s", event_id, state["level"], state["deadline"])
                    continue
                if waiting:
                    continue
                call = self.contract.functions.checkTimeout(event_id)
                call.call({"from": self.account.address})
                transaction = call.build_transaction({
                    "from": self.account.address,
                    "chainId": expected,
                    "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                })
                signed = self.account.sign_transaction(transaction)
                # Lưu trước khi gửi: lỗi mạng sau broadcast không tạo tx khác.
                self.pending = (signed.hash, signed.raw_transaction, event_id)
                waiting = True
                self.w3.eth.send_raw_transaction(signed.raw_transaction)
                LOG.info("Đã gửi checkTimeout: eventId=%s tx=%s", event_id, signed.hash.hex())
            except Exception as error:
                errors += 1
                LOG.warning("eventId=%s: %s", event_id, safe_error(error))
        LOG.info("Đã kiểm tra %s sự cố tại block=%s", count, head["number"])
        return errors == 0


def load_keeper(dry_run):
    from dotenv import load_dotenv
    from web3 import Web3

    load_dotenv(ROOT / ".env")
    network = os.getenv("NETWORK", "localhost")
    expected = {"localhost": 31337, "sepolia": 11155111}.get(network)
    if expected is None:
        raise ValueError("NETWORK chỉ nhận localhost hoặc sepolia.")
    rpc = "http://127.0.0.1:8545" if network == "localhost" else os.getenv("SEPOLIA_RPC_URL")
    if not rpc:
        raise ValueError("Thiếu SEPOLIA_RPC_URL trong .env.")
    deployment_file = ROOT / "deployments" / f"{network}.json"
    abi_file = ROOT / "backend" / "abi" / "CareSLA.json"
    if not deployment_file.exists() or not abi_file.exists():
        raise ValueError("Thiếu deployment hoặc ABI. Nhận CareSLA.sol từ P1, compile và chạy deploy.js.")
    deployment = json.loads(deployment_file.read_text(encoding="utf-8"))
    if deployment.get("chainId") != expected or not isinstance(deployment.get("deployBlock"), int) or deployment["deployBlock"] < 0:
        raise ValueError("Deployment có chainId/deployBlock không hợp lệ.")
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 15}))
    account = None
    if not dry_run:
        key = os.getenv("KEEPER_PRIVATE_KEY")
        if not key:
            raise ValueError("Thiếu KEEPER_PRIVATE_KEY; dùng --dry-run để chỉ đọc.")
        account = w3.eth.account.from_key(key)
        LOG.info("Keeper wallet: %s; network=%s", account.address, network)
    abi = json.loads(abi_file.read_text(encoding="utf-8"))
    if not isinstance(abi, list):
        raise ValueError("ABI phải là JSON array do deploy.js xuất.")
    contract = w3.eth.contract(address=Web3.to_checksum_address(deployment["address"]), abi=abi)
    return Keeper(w3, contract, deployment, account, dry_run)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Chạy một vòng; exit 1 nếu kiểm tra lỗi. Tx mới gửi có thể chưa mine.")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ đọc trạng thái, không cần khóa, không gửi tx.")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    if sys.version_info < (3, 10):
        LOG.error("Cần Python 3.10+ và web3 v7. Hãy dùng Python trong .venv.")
        return 1
    try:
        keeper = load_keeper(args.dry_run)
    except Exception as error:
        LOG.error("Không khởi động được keeper: %s", safe_error(error))
        return 1
    try:
        while True:
            started = time.monotonic()
            try:
                ok = keeper.poll()
            except Exception as error:
                LOG.warning("Vòng kiểm tra lỗi, sẽ thử lại: %s", safe_error(error))
                ok = False
            if args.once:
                return 0 if ok else 1
            time.sleep(max(0, 5 - (time.monotonic() - started)))
    except KeyboardInterrupt:
        LOG.info("Đã dừng keeper.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
