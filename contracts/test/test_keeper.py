"""Unit test keeper bằng RPC giả; KHÔNG phải kiểm thử contract/end-to-end.

Chạy tại repo root: python -m unittest discover -s contracts/test -p "test_*.py" -v
"""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from eth_abi import encode
from eth_account import Account
from hexbytes import HexBytes
from web3 import Web3
from web3.exceptions import TransactionNotFound

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("keeper", ROOT / "backend" / "keeper.py")
keeper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(keeper)
ADDRESS = "0x1111111111111111111111111111111111111111"

# ABI fixture chỉ của 4 event đã chốt ở AGENTS.md; không xuất thành ABI production.
EVENT_FIELDS = {
    "FallReported": [("eventId", "uint256", True), ("planId", "uint256", True), ("dataHash", "bytes32", False), ("primary", "address", False), ("deadline", "uint64", False)],
    "Acknowledged": [("eventId", "uint256", True), ("caregiver", "address", True), ("at", "uint64", False)],
    "Arrived": [("eventId", "uint256", True), ("at", "uint64", False)],
    "Escalated": [("eventId", "uint256", True), ("level", "uint8", False), ("to", "address", False), ("newDeadline", "uint64", False)],
}
ABI = [
    {"type": "event", "name": name, "anonymous": False, "inputs": [
        {"name": field, "type": kind, "indexed": indexed} for field, kind, indexed in fields
    ]} for name, fields in EVENT_FIELDS.items()
]


def log_event(name, values, index=0):
    fields = EVENT_FIELDS[name]
    signature = name + "(" + ",".join(kind for _, kind, _ in fields) + ")"
    topics = [Web3.keccak(text=signature)]
    topics += [HexBytes(encode([kind], [values[field]])) for field, kind, indexed in fields if indexed]
    data = encode([kind for _, kind, indexed in fields if not indexed], [values[field] for field, _, indexed in fields if not indexed])
    return {"address": ADDRESS, "topics": topics, "data": HexBytes(data), "blockNumber": 10,
            "transactionIndex": 0, "logIndex": index, "transactionHash": HexBytes("0x" + "11" * 32),
            "blockHash": HexBytes("0x" + "22" * 32)}


def fall(event_id=0, deadline=1000, index=0):
    return log_event("FallReported", {"eventId": event_id, "planId": 1, "dataHash": b"\0" * 32, "primary": ADDRESS, "deadline": deadline}, index)


def fixture(logs=None, timestamp=1001, dry_run=False):
    logs = [fall()] if logs is None else logs
    w3 = MagicMock()
    w3.keccak = Web3.keccak
    w3.eth.chain_id = 31337
    w3.eth.get_code.return_value = b"\x60\x00"
    head = {"number": 10, "timestamp": timestamp, "hash": HexBytes("0x" + "22" * 32)}
    w3.eth.get_block.return_value = head
    w3.eth.get_logs.return_value = logs
    w3.eth.get_transaction_count.return_value = 5
    contract = MagicMock()
    contract.address = ADDRESS
    contract.events = Web3().eth.contract(address=ADDRESS, abi=ABI).events
    contract.functions.eventCount.return_value.call.return_value = sum(log["topics"][0] == Web3.keccak(text="FallReported(uint256,uint256,bytes32,address,uint64)") for log in logs)
    contract.functions.checkTimeout.return_value.build_transaction.return_value = {
        "chainId": 31337, "nonce": 5, "to": ADDRESS, "gas": 120000,
        "gasPrice": 1000000000, "value": 0, "data": "0x12345678",
    }
    account = Account.create()
    agent = keeper.Keeper(w3, contract, {"chainId": 31337, "deployBlock": 1}, account, dry_run)
    return agent, w3, contract, head


class KeeperTests(unittest.TestCase):
    def test_empty_chain(self):
        agent, w3, contract, _ = fixture([])
        self.assertTrue(agent.poll())
        contract.functions.eventCount.return_value.call.assert_called_once_with(block_identifier=10)
        contract.functions.getFallEvent.assert_not_called()
        w3.eth.send_raw_transaction.assert_not_called()

    def test_deadline_is_strict_chain_time(self):
        agent, w3, contract, _ = fixture(timestamp=1000)
        self.assertTrue(agent.poll())
        contract.functions.getFallEvent.assert_called_once_with(0)
        w3.eth.send_raw_transaction.assert_not_called()

    def test_due_uses_pending_nonce_and_signed_web3_v7_transaction(self):
        agent, w3, contract, _ = fixture()
        self.assertTrue(agent.poll())
        contract.functions.checkTimeout.assert_called_once_with(0)
        w3.eth.get_transaction_count.assert_called_once_with(agent.account.address, "pending")
        raw = w3.eth.send_raw_transaction.call_args.args[0]
        self.assertEqual(Account.recover_transaction(raw), agent.account.address)
        self.assertIsNotNone(agent.pending)

    def test_dry_run_never_signs_or_sends(self):
        agent, w3, contract, _ = fixture(dry_run=True)
        agent.account = None
        self.assertTrue(agent.poll())
        contract.functions.checkTimeout.assert_not_called()
        w3.eth.send_raw_transaction.assert_not_called()

    def test_acknowledged_or_arrived_skipped(self):
        for name, args in [("Acknowledged", {"eventId": 0, "caregiver": ADDRESS, "at": 999}), ("Arrived", {"eventId": 0, "at": 999})]:
            with self.subTest(name=name):
                agent, w3, _, _ = fixture([fall(), log_event(name, args, 1)])
                self.assertTrue(agent.poll())
                w3.eth.send_raw_transaction.assert_not_called()

    def test_level_two_never_sends_again(self):
        log = log_event("Escalated", {"eventId": 0, "level": 2, "to": ADDRESS, "newDeadline": 0}, 1)
        agent, w3, _, _ = fixture([fall(), log])
        self.assertTrue(agent.poll())
        w3.eth.send_raw_transaction.assert_not_called()

    def test_backup_uses_new_deadline(self):
        log = log_event("Escalated", {"eventId": 0, "level": 1, "to": ADDRESS, "newDeadline": 1100}, 1)
        agent, w3, _, _ = fixture([fall(), log], timestamp=1050)
        self.assertTrue(agent.poll())
        w3.eth.send_raw_transaction.assert_not_called()

    def test_ids_from_logs_not_assumed_zero_based(self):
        agent, _, contract, _ = fixture([fall(event_id=1)], dry_run=True)
        self.assertTrue(agent.poll())
        contract.functions.getFallEvent.assert_called_once_with(1)

    def test_wrong_chain_or_missing_code_rejected(self):
        for condition in ("chain", "code"):
            with self.subTest(condition=condition):
                agent, w3, _, _ = fixture()
                if condition == "chain":
                    w3.eth.chain_id = 1
                else:
                    w3.eth.get_code.return_value = b""
                with self.assertRaises(ValueError):
                    agent.poll()
                w3.eth.send_raw_transaction.assert_not_called()

    def test_count_mismatch_does_not_send(self):
        agent, w3, contract, _ = fixture()
        contract.functions.eventCount.return_value.call.return_value = 2
        with self.assertRaisesRegex(ValueError, "eventCount"):
            agent.poll()
        w3.eth.send_raw_transaction.assert_not_called()

    def test_revert_on_one_event_does_not_crash_or_block_next(self):
        agent, w3, contract, _ = fixture([fall(0), fall(1, index=1)])
        contract.functions.checkTimeout.return_value.call.side_effect = [ValueError("execution reverted"), None]
        self.assertFalse(agent.poll())
        self.assertEqual(contract.functions.getFallEvent.call_count, 2)
        w3.eth.send_raw_transaction.assert_called_once()

    def test_receipt_pending_prevents_duplicate_transaction(self):
        agent, w3, _, _ = fixture()
        agent.poll()
        w3.eth.get_transaction_receipt.side_effect = TransactionNotFound("pending")
        self.assertTrue(agent.poll())
        self.assertEqual(w3.eth.send_raw_transaction.call_count, 1)

    def test_lost_broadcast_retries_identical_bytes(self):
        agent, w3, _, _ = fixture()
        w3.eth.send_raw_transaction.side_effect = [ConnectionError("RPC unavailable"), b"ok"]
        self.assertFalse(agent.poll())
        w3.eth.get_transaction_receipt.side_effect = TransactionNotFound("unknown")
        w3.eth.get_transaction.side_effect = TransactionNotFound("unknown")
        self.assertTrue(agent.poll())
        calls = w3.eth.send_raw_transaction.call_args_list
        self.assertEqual(calls[0].args[0], calls[1].args[0])
        self.assertEqual(w3.eth.get_transaction_count.call_count, 1)

    def test_failed_receipt_is_logged_and_pending_cleared(self):
        agent, w3, _, _ = fixture()
        agent.poll()
        w3.eth.get_transaction_receipt.return_value = {"status": 0, "gasUsed": 30000}
        with self.assertLogs(keeper.LOG, level="WARNING"):
            self.assertFalse(agent.check_pending())
        self.assertIsNone(agent.pending)

    def test_failed_batch_can_be_retried(self):
        agent, w3, _, _ = fixture(dry_run=True)
        w3.eth.get_logs.side_effect = ConnectionError("offline")
        with self.assertRaises(ConnectionError):
            agent.poll()
        self.assertEqual(agent.next_block, 1)
        self.assertEqual(agent.states, {})
        w3.eth.get_logs.side_effect = None
        self.assertTrue(agent.poll())

    def test_reorg_rebuilds_ack_state(self):
        ack = log_event("Acknowledged", {"eventId": 0, "caregiver": ADDRESS, "at": 999}, 1)
        agent, w3, _, head = fixture([fall(), ack], dry_run=True)
        agent.poll()
        self.assertTrue(agent.states[0]["closed"])
        head["hash"] = HexBytes("0x" + "33" * 32)
        w3.eth.get_logs.return_value = [fall()]
        with self.assertLogs(keeper.LOG, level="WARNING"):
            agent.poll()
        self.assertFalse(agent.states[0]["closed"])

    def test_unknown_event_id_detects_incomplete_history(self):
        with self.assertRaisesRegex(ValueError, "Thiếu FallReported"):
            keeper.apply_event({}, "Arrived", {"eventId": 9})

    def test_loop_recovers_after_rpc_error(self):
        agent = MagicMock()
        agent.poll.side_effect = [ConnectionError("offline"), True]
        with patch.object(keeper, "load_keeper", return_value=agent), patch.object(keeper.time, "sleep", side_effect=[None, KeyboardInterrupt]):
            self.assertEqual(keeper.main([]), 0)
        self.assertEqual(agent.poll.call_count, 2)

    def test_once_failure_returns_nonzero(self):
        agent = MagicMock()
        agent.poll.side_effect = ConnectionError("offline")
        with patch.object(keeper, "load_keeper", return_value=agent):
            self.assertEqual(keeper.main(["--once"]), 1)

    def test_redacts_secrets_and_rpc_url(self):
        with patch.dict(os.environ, {"KEEPER_PRIVATE_KEY": "example-not-a-real-key", "SEPOLIA_RPC_URL": "https://rpc.invalid/token"}):
            message = keeper.safe_error(ValueError("example-not-a-real-key https://rpc.invalid/token"))
        self.assertNotIn("example-not-a-real-key", message)
        self.assertNotIn("rpc.invalid", message)


if __name__ == "__main__":
    unittest.main()
