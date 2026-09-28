"""Kiểm thử ba vòng với node/broker riêng do script sở hữu, không dùng ví thật.

Chạy từ gốc repo: python tools/check_local_e2e.py --mosquitto PATH_TO_EXE
Log và khóa test sinh ra chỉ nằm trong .local/. Không thay deployment của người dùng.
"""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import requests

from eth_account import Account
from web3 import Web3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.keeper import Keeper


def wait_for(check, seconds=30):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            result = check()
            if result:
                return result
        except (ConnectionError, OSError):
            pass
        time.sleep(0.1)
    raise TimeoutError('Condition did not become true')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mosquitto', required=True, type=Path)
    args = parser.parse_args()
    # Không kết nối/reset node của người dùng đang chạy sẵn.
    for port in (8545, 8546, 18884):
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                raise SystemExit(f'Port {port} already in use; stop that service or test later')
    work = ROOT / '.local' / ('e2e-' + time.strftime('%Y%m%d-%H%M%S'))
    work.mkdir(parents=True)
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    env['APPDATA'] = env['LOCALAPPDATA'] = str(work / 'appdata')
    processes, files = [], []

    def start(command, name, cwd=ROOT, variables=None):
        output = (work / name).open('w', encoding='utf-8')
        files.append(output)
        proc = subprocess.Popen(command, cwd=cwd, env=variables or env,
                                stdout=output, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        processes.append(proc)
        return proc

    def stop(proc):
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    report = []
    offline = threading.Event()

    class RpcProxy(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            if offline.is_set():
                self.send_error(503, 'Simulated RPC outage')
                return
            response = requests.post('http://127.0.0.1:8546', data=body,
                                     headers={'Content-Type': 'application/json'}, timeout=5)
            self.send_response(response.status_code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response.content)))
            self.end_headers()
            self.wfile.write(response.content)

    proxy = ThreadingHTTPServer(('127.0.0.1', 8545), RpcProxy)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    try:
        node = start(['node', 'node_modules/hardhat/internal/cli/cli.js', 'node', '--hostname', '127.0.0.1', '--port', '8546'],
                     'node.log', ROOT / 'contracts')
        start([str(args.mosquitto.resolve()), '-p', '18884'], 'broker.log')
        w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8546', request_kwargs={'timeout': 3}))
        wait_for(w3.is_connected, 60)
        keys = wait_for(lambda: re.findall(r'Private Key: (0x[0-9a-fA-F]{64})', (work/'node.log').read_text()), 30)
        assert len(keys) == 20
        artifact = json.loads((ROOT/'contracts/artifacts/contracts/CareSLA.sol/CareSLA.json').read_text())
        key = Account.create().key
        (work/'device.key').write_text(key.hex())
        device = Account.from_key(key).address
        for run in range(1, 4):
            if run > 1:
                w3.provider.make_request('hardhat_reset', [])
            wallets = w3.eth.accounts
            factory = w3.eth.contract(abi=artifact['abi'], bytecode=artifact['bytecode'])
            receipt = w3.eth.wait_for_transaction_receipt(factory.constructor().transact({'from': wallets[0]}))
            contract = w3.eth.contract(address=receipt.contractAddress, abi=artifact['abi'])
            deployment = dict(address=contract.address, chainId=31337, deployBlock=receipt.blockNumber)
            now = w3.eth.get_block('latest').timestamp
            end = now + 300
            deposit, penalty = 10**16, 2*10**15

            def tx(fn, sender, **extra):
                receipt = w3.eth.wait_for_transaction_receipt(fn.transact(dict({'from': sender}, **extra)))
                assert receipt.status == 1
                return receipt

            tx(contract.functions.createCarePlan(wallets[2], device, 60, penalty, end), wallets[1], value=deposit)
            tx(contract.functions.acceptPlan(1), wallets[2])
            start_at = w3.eth.get_block('latest').timestamp + 3
            tx(contract.functions.commitShift(1, start_at, end, wallets[3], wallets[4]), wallets[2])
            wait_for(lambda: time.time() >= start_at, 20)
            gw_env = dict(env, NETWORK='localhost', CONTRACT_ADDRESS=contract.address, PLAN_ID='1',
                          GATEWAY_PRIVATE_KEY=keys[5], REGISTERED_DEVICES=device.lower(),
                          MQTT_HOST='127.0.0.1', MQTT_PORT='18884', TELEGRAM_BOT_TOKEN='',
                          TELEGRAM_CHAT_PRIMARY='local-log', TELEGRAM_CHAT_BACKUP='local-log',
                          TELEGRAM_CHAT_FAMILY='local-log', TELEGRAM_CHAT_PROVIDER='local-log')
            run_dir = work / f'run-{run}'
            run_dir.mkdir()
            log = work / f'gateway-{run}.log'
            gateway = start([sys.executable, str(ROOT/'backend/gateway.py')], log.name, run_dir, gw_env)
            wait_for(lambda: 'Subscribed to MQTT' in log.read_text(encoding='utf-8'), 30)

            def fake(kind):
                result = subprocess.run([sys.executable, str(ROOT/'tools/fake_device.py'), kind,
                                         '--key-file', str(work/'device.key'), '--nonce-file', str(work/'nonce.sqlite')],
                                        cwd=ROOT, env=gw_env, capture_output=True, text=True, encoding='utf-8', timeout=25)
                if result.returncode:
                    raise RuntimeError(result.stderr)

            fake('heartbeat')
            fake('cancel')
            wait_for(lambda: 'CANCEL from' in log.read_text(encoding='utf-8'))
            assert contract.functions.eventCount().call() == 0
            offline.set()
            fake('fall')
            wait_for(lambda: 'ALERT_DISPATCH' in log.read_text(encoding='utf-8'))
            alert_ms = float(re.search(r'ALERT_DISPATCH elapsed_ms=([\d.]+)', log.read_text(encoding='utf-8'))[1])
            assert alert_ms < 2000
            assert contract.functions.eventCount().call() == 0
            wait_for(lambda: '[reportFall] Network/RPC Error:' in log.read_text(encoding='utf-8'), 25)
            offline.clear()
            wait_for(lambda: contract.functions.eventCount().call() == 1)
            wait_for(lambda: 'Raw hash OK' in log.read_text(encoding='utf-8'))
            keeper = Keeper(w3, contract, deployment, Account.from_key(keys[6]))
            for level in (1, 2):
                deadline = contract.functions.getFallEvent(1).call()[6]
                w3.provider.make_request('evm_setNextBlockTimestamp', [deadline+1])
                w3.provider.make_request('evm_mine', [])
                assert keeper.poll()
                wait_for(lambda: contract.functions.getFallEvent(1).call()[7] == level)
                keeper.poll()
            nonce_before = w3.eth.get_transaction_count(wallets[6])
            keeper.poll()
            assert w3.eth.get_transaction_count(wallets[6]) == nonce_before
            fake('arrival')
            wait_for(lambda: contract.functions.getFallEvent(1).call()[8] == 2)
            assert contract.functions.getPlan(1).call()[9] == 2
            wait_for(lambda: 'LEO THANG CẤP 2' in log.read_text(encoding='utf-8'), 15)
            w3.provider.make_request('evm_setNextBlockTimestamp', [end+601])
            w3.provider.make_request('evm_mine', [])
            family_before, provider_before = [w3.eth.get_balance(wallets[i]) for i in (1, 2)]
            settled = tx(contract.functions.settle(1), wallets[0])
            refund = w3.eth.get_balance(wallets[1])-family_before
            paid = w3.eth.get_balance(wallets[2])-provider_before
            assert (refund, paid) == (2*penalty, deposit-2*penalty)
            report.append(dict(run=run, result='PASS', contract=contract.address, violations=2,
                               status=2, refundWei=refund, providerWei=paid, settleTx=settled.transactionHash.hex(),
                               alertLogMs=alert_ms, rpcOutageRetry='PASS',
                               telegram='log fallback; no real Telegram measurement'))
            print(json.dumps(report[-1]), flush=True)
            stop(gateway)
        (work/'results.json').write_text(json.dumps(report, indent=2))
        print(f'PASS 3 consecutive software E2E runs. Evidence: {work}')
    finally:
        proxy.shutdown()
        proxy.server_close()
        for proc in reversed(processes):
            if proc.poll() is None:
                stop(proc)
        for output in files:
            output.close()


if __name__ == '__main__':
    main()
