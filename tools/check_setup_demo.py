"""Chạy demo P6 trên node/broker riêng; không reset dịch vụ có sẵn.

python tools/check_setup_demo.py --mosquitto .local/mosquitto/mosquitto.exe
Khóa chỉ sinh trong .local bị Git ignore; không dùng khóa ESP32 hoặc .env.
"""
import argparse
import json
import os
from pathlib import Path
import re
import runpy
import socket
import subprocess
import sys
import threading
import time

from eth_account import Account
from web3 import Web3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.keeper import Keeper


def wait_for(check, timeout=40):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if check():
                return
        except (OSError, ConnectionError):
            pass
        time.sleep(.2)
    raise TimeoutError('Dịch vụ chưa sẵn sàng')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mosquitto', required=True, type=Path)
    parser.add_argument('--rpc-port', type=int, default=18545)
    args = parser.parse_args()
    for port in (args.rpc_port, 18885):
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                raise SystemExit(f'Cổng {port} đang bận; không tác động dịch vụ có sẵn.')
    work = ROOT / '.local' / ('setup-demo-' + time.strftime('%Y%m%d-%H%M%S'))
    work.mkdir(parents=True)
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    env['APPDATA'] = env['LOCALAPPDATA'] = str(work / 'appdata')
    processes, outputs = [], []
    stop = threading.Event()
    worker = None

    def start(command, name, cwd=ROOT, variables=None):
        output = (work / name).open('w', encoding='utf-8')
        outputs.append(output)
        proc = subprocess.Popen(command, cwd=cwd, env=variables or env, stdout=output,
                                stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        processes.append(proc)
        return proc

    try:
        start(['node', 'node_modules/hardhat/internal/cli/cli.js', 'node', '--hostname', '127.0.0.1', '--port', str(args.rpc_port)],
              'node.log', ROOT / 'contracts')
        start([str(args.mosquitto.resolve()), '-p', '18885'], 'broker.log')
        rpc_url = f'http://127.0.0.1:{args.rpc_port}'
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 3}))
        wait_for(w3.is_connected)
        wait_for(lambda: len(re.findall(r'Private Key: (0x[0-9a-fA-F]{64})',
                 (work / 'node.log').read_text(encoding='utf-8'))) == 20)
        keys = re.findall(r'Private Key: (0x[0-9a-fA-F]{64})', (work / 'node.log').read_text(encoding='utf-8'))
        artifact = json.loads((ROOT / 'contracts/artifacts/contracts/CareSLA.sol/CareSLA.json').read_text())
        factory = w3.eth.contract(abi=artifact['abi'], bytecode=artifact['bytecode'])
        receipt = w3.eth.wait_for_transaction_receipt(factory.constructor().transact({'from': w3.eth.accounts[0]}))
        contract = w3.eth.contract(address=receipt.contractAddress, abi=artifact['abi'])
        deployment = dict(address=contract.address, chainId=31337, deployBlock=receipt.blockNumber)
        device = Account.create()
        (work / 'device.key').write_text(device.key.hex())
        (work / 'fixture.json').write_text(json.dumps(dict(deployment=deployment, device=device.address)))
        gw_env = dict(env, NETWORK='localhost', CONTRACT_ADDRESS=contract.address, PLAN_ID='1',
                      GATEWAY_PRIVATE_KEY=keys[5], REGISTERED_DEVICES=device.address.lower(),
                      MQTT_HOST='127.0.0.1', MQTT_PORT='18885', TELEGRAM_BOT_TOKEN='',
                      TELEGRAM_CHAT_PRIMARY='', TELEGRAM_CHAT_BACKUP='', TELEGRAM_CHAT_FAMILY='',
                      TELEGRAM_CHAT_PROVIDER='')
        gw_env['P6_TEST_RPC'] = rpc_url
        start([sys.executable, str(Path(__file__).resolve()), '--gateway-test'], 'gateway.log', work, gw_env)
        wait_for(lambda: 'Subscribed to MQTT' in (work / 'gateway.log').read_text(encoding='utf-8'))
        keeper = Keeper(w3, contract, deployment, Account.from_key(keys[6]))

        def keep():
            while not stop.wait(1):
                keeper.poll()

        worker = threading.Thread(target=keep, daemon=True)
        worker.start()
        # JS không nhận khóa gateway. Thiết bị giả đọc file test riêng.
        js_env = dict(env, MQTT_HOST='127.0.0.1', MQTT_PORT='18885', P6_PYTHON=sys.executable, P6_TEST_RPC=rpc_url)
        result = subprocess.run(['node', str(ROOT / 'tools/test_setup_demo.cjs'), str(work)],
                                cwd=ROOT, env=js_env, timeout=600)
        if result.returncode:
            raise SystemExit(result.returncode)
        print(f'Evidence: {work / "results.json"}', flush=True)
    finally:
        stop.set()
        if worker:
            worker.join(timeout=10)
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        for output in outputs:
            output.close()


if __name__ == '__main__':
    if sys.argv[1:] == ['--gateway-test']:
        # Chỉ đổi địa chỉ transport trong tiến trình test, không sửa gateway.
        original_provider = Web3.HTTPProvider
        Web3.HTTPProvider = lambda url, *a, **kw: original_provider(
            os.environ['P6_TEST_RPC'] if url == 'http://127.0.0.1:8545' else url, *a, **kw)
        runpy.run_path(str(ROOT / 'backend/gateway.py'), run_name='__main__')
    else:
        main()
