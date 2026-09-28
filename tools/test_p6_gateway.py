from contextlib import closing
import base64
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import queue
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from backend import gateway as g
from tools.fake_device import make_event, next_nonce

class GatewayIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old = g.DB_FILE
        g.DB_FILE = str(Path(self.tmp.name) / 'gateway.sqlite')
        self.addCleanup(setattr, g, 'DB_FILE', self.old)
        g.init_db()
        g.heartbeat_lost.clear()
        g.tx_queue = queue.Queue()
        self.vector = json.loads(Path('docs/test_vectors.json').read_text())
        self.device = self.vector['device'].lower()
        self.raw = bytes(4800)
        self.event = make_event(self.vector['privateKey'], 1, 2000000000, 1, self.raw)
        self.patcher = patch.object(g, 'get_on_duty', return_value=dict(primary=None, backup=None, center='provider', family='family'))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def message(self, suffix, data):
        g.on_message(None, None, SimpleNamespace(topic=f'carensla/{self.device}/{suffix}',payload=json.dumps(data).encode()))

    def test_hash_both_orders_and_corrupt_first_byte(self):
        for raw_first in (True, False):
            for valid in (True, False):
                with self.subTest(raw_first=raw_first, valid=valid):
                    with closing(sqlite3.connect(g.DB_FILE)) as db, db:
                        db.execute('DELETE FROM events'); db.execute('DELETE FROM raw_data')
                    raw = dict(device=self.device, nonce=1, samples_b64=base64.b64encode(self.raw if valid else b'\x01'+self.raw[1:]).decode())
                    out = io.StringIO()
                    with redirect_stdout(out):
                        for suffix, payload in ([('raw', raw), ('event', self.event)] if raw_first else [('event', self.event), ('raw', raw)]):
                            self.message(suffix, payload)
                    self.assertIn('Raw hash OK' if valid else 'dataHash mismatch',out.getvalue())

    def test_heartbeat_one_alert_per_outage_and_recovery(self):
        with closing(sqlite3.connect(g.DB_FILE)) as db, db:
            db.execute('INSERT INTO heartbeats VALUES (?, ?, ?)',(self.device, 100, 100))
        with patch.object(g, 'send_telegram') as send:
            g.check_heartbeats(221); g.check_heartbeats(231)
            self.assertEqual(send.call_count,2)
            with closing(sqlite3.connect(g.DB_FILE)) as db, db:
                db.execute('UPDATE heartbeats SET t_received=232')
            g.check_heartbeats(232); g.check_heartbeats(240)
            self.assertEqual(send.call_count,4)
            g.check_heartbeats(353)
            self.assertEqual(send.call_count,6)

    def test_alert_never_waits_for_rpc(self):
        with patch.object(g, 'contract') as contract:
            # Hàm thật chỉ tra cấu hình chat, không được chạm RPC.
            self.patcher.stop()
            g.get_on_duty(1, 100)
            contract.functions.getOnDuty.assert_not_called()

    def test_fake_signature_matches_official_vectors(self):
        from eth_account import Account
        from eth_account.messages import encode_defunct
        from web3 import Web3
        for vector in self.vector['vectors']:
            raw_hash = bytes.fromhex(vector['dataHash'].removeprefix('0x'))
            packed = bytes.fromhex(self.device[2:]) + bytes([vector['eventType']]) + vector['timestamp'].to_bytes(8,'big') + vector['nonce'].to_bytes(8,'big') + raw_hash
            signed=Account.sign_message(encode_defunct(Web3.keccak(packed)),self.vector['privateKey'])
            self.assertEqual('0x'+signed.signature.hex(),vector['sig'])
        self.assertEqual(g.recover_signer(self.device,1,2000000000,1,self.event['dataHash'],self.event['sig']),self.device)
        path = Path(self.tmp.name)/'nonce.sqlite'
        self.assertEqual(next_nonce(path,self.device),1)
        self.assertEqual(next_nonce(path,self.device),2)

if __name__ == '__main__':
    unittest.main()
