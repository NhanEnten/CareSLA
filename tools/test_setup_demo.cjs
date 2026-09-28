/* VM + RPC thật + MQTT thật. Không giả kết quả contract hoặc thời gian SLA. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const pinnedEthers = path.join(root, '.local/ethers-6.13.4.cjs');
const installedEthers = fs.existsSync(pinnedEthers) ? require(pinnedEthers)
    : createRequire(path.join(root, 'contracts/package.json'))('ethers');
const rpcUrl = process.env.P6_TEST_RPC || 'http://127.0.0.1:8545';
// Adapter transport riêng cho test để không tua giờ node demo của người dùng.
const ethers = { ...installedEthers, JsonRpcProvider: class extends installedEthers.JsonRpcProvider {
    constructor(url, ...args) { super(url === 'http://127.0.0.1:8545' ? rpcUrl : url, ...args); }
} };
const work = process.argv[2];
const fixture = JSON.parse(fs.readFileSync(path.join(work, 'fixture.json')));
const abi = JSON.parse(fs.readFileSync(path.join(root, 'dashboard/CareSLA.json')));
const rpc = new ethers.JsonRpcProvider('http://127.0.0.1:8545', 31337, { staticNetwork: true });
const read = new ethers.Contract(fixture.deployment.address, abi, rpc);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(check, timeout = 20000) {
    const end = performance.now() + timeout;
    while (performance.now() < end) { if (await check()) return; await sleep(250); }
    throw new Error('Hết thời gian chờ điều kiện');
}
function element() {
    return { value: '', textContent: '', innerText: '', innerHTML: '', className: '', disabled: false,
        hidden: false, children: [], style: {}, listeners: {},
        classList: { toggle() {} },
        addEventListener(name, fn) { this.listeners[name] = fn; },
        replaceChildren() { this.children = []; },
        appendChild(child) { this.children.push(child); },
    };
}
function page(file, account, storage = new Map(), query = '') {
    const html = fs.readFileSync(path.join(root, `dashboard/${file === 'setup' ? 'setup' : 'index'}.html`), 'utf8');
    const nodes = new Map();
    for (const match of html.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g)) {
        const node = element();
        node.value = /\bvalue="([^"]*)"/.exec(match[0])?.[1] || '';
        nodes.set(match[1], node);
    }
    const handlers = {}, timers = [];
    let selected = account, network = '0x7a69', reject = false;
    const walletCalls = [];
    const ethereum = {
        on(event, fn) { handlers[event] = fn; },
        async request({ method, params = [] }) {
            walletCalls.push(method);
            if (method === 'eth_chainId') return network;
            if (method === 'eth_accounts' || method === 'eth_requestAccounts') return selected ? [selected] : [];
            if (method === 'eth_sendTransaction' && reject) { const e = new Error('Rejected'); e.code = 4001; throw e; }
            return rpc.send(method, params);
        },
    };
    const location = { search: query, href: `http://127.0.0.1:8000/dashboard/${file}.html${query}` };
    const context = vm.createContext({ ethers, console, URL, URLSearchParams, location,
        document: { getElementById(id) { assert(nodes.has(id), `HTML thiếu id ${id}`); return nodes.get(id); },
            createElement: element, querySelector() { return nodes.get('events-table'); } },
        window: { ethereum, confirm: () => true, addEventListener(name, fn) { handlers[name] = fn; } },
        localStorage: { getItem: (key) => storage.get(key) || null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) },
        history: { replaceState(_a, _b, url) { location.href = String(url); location.search = new URL(url).search; } },
        navigator: { clipboard: { async writeText() {} } }, alert() {},
        setInterval(fn) { timers.push(fn); return timers.length; },
        async fetch(url) { return { ok: url !== 'metrics.json', async json() {
            return url === 'CareSLA.json' ? abi : fixture.deployment;
        } }; },
    });
    vm.runInContext(fs.readFileSync(path.join(root, `dashboard/${file}.js`), 'utf8'), context);
    const run = (source) => vm.runInContext(source, context);
    return { nodes, context, run, handlers, walletCalls, storage,
        async start() { await handlers.load(); },
        async switchAccount(value) { selected = value; await handlers.accountsChanged(); await until(() => run('signer?.address') === value); },
        async switchNetwork(value) { network = value; await handlers.chainChanged(); await sleep(300); },
        reject(value) { reject = value; },
        async click(id) { assert(!nodes.get(id).disabled, `${id} đang khóa`); await nodes.get(id).listeners.click(); },
    };
}
async function main() {
    const accounts = await rpc.send('eth_accounts', []);
    const wallets = accounts.map(ethers.getAddress);
    const p = page('setup', wallets[1]);
    await p.start();
    await p.click('connect-btn');
    assert.equal(await p.run('local'), true);
    p.nodes.get('device-address').value = fixture.device;
    const marks = [];
    const begin = performance.now();
    function mark(step) { const record = { step, seconds: Number(((performance.now() - begin) / 1000).toFixed(2)) }; marks.push(record); console.log(JSON.stringify(record)); }
    p.reject(true);
    await p.click('create-btn');
    assert.equal(p.nodes.get('setup-message').textContent, 'Đã hủy ký');
    assert.equal(p.nodes.get('setup-message').className, '');
    p.reject(false);
    await p.click('create-btn');
    assert.equal(await p.run('planId'), '1');
    assert.equal((await read.getPlan(1)).deposit, ethers.parseEther('100'));
    assert.match(p.nodes.get('create-balances').textContent, /Số dư contract: 100\.0 ETH/);
    assert(p.nodes.get('accept-btn').disabled);
    mark('Tạo hợp đồng, khóa 100 ETH');
    await p.switchAccount(wallets[2]);
    assert.match(p.nodes.get('wallet-role').textContent, /Trung tâm/);
    await p.click('accept-btn');
    assert((await read.getPlan(1)).accepted);
    mark('Chấp nhận');
    await p.click('defaults-btn');
    await p.click('shift-btn');
    assert.equal(p.nodes.get('shifts-body').children.length, 1);
    await p.click('past-btn');
    assert.match(p.nodes.get('setup-message').textContent, /Không thể cam kết ca trong quá khứ/);
    assert.equal((await read.getPlan(1)).shiftCount, 1n);
    mark('Cam kết ca và từ chối ca quá khứ');
    // Khôi phục URL/localStorage và quyền ví, không phụ thuộc bộ nhớ trang cũ.
    const resumed = page('setup', wallets[2], p.storage);
    await resumed.start(); await resumed.click('connect-btn');
    assert.equal(await resumed.run('planId'), '1');
    assert.equal(resumed.nodes.get('shifts-body').children.length, 1);
    await resumed.click('new-btn');
    assert.equal(await resumed.run('planId'), null);
    assert.equal(resumed.storage.get('caresla.setup.plan'), undefined);
    assert.equal(new URL(resumed.run('location.href')).searchParams.get('plan'), null);
    assert.equal(resumed.nodes.get('shifts-body').children.length, 0);
    assert.equal((await read.getPlan(1)).shiftCount, 1n);
    resumed.nodes.get('open-plan').value = '1';
    await resumed.click('open-btn');
    assert.equal(await resumed.run('planId'), '1');
    await resumed.switchNetwork('0xaa36a7');
    assert.equal(resumed.nodes.get('setup-message').textContent, 'Trang thiết lập chỉ dùng cho demo local');
    assert(resumed.nodes.get('warp-btn').disabled);
    assert(resumed.nodes.get('finish-section').hidden);
    await resumed.switchNetwork('0x7a69');
    await until(async () => { await p.run('refresh()'); return !p.nodes.get('monitor-btn').disabled; }, 30000);
    await p.click('monitor-btn');
    assert.equal(p.run('location.href'), 'index.html?plan=1');
    // fake_device ký bằng đồng hồ máy. Giao dịch automine có thể đẩy chain sớm vài giây.
    const shiftLogs = await read.queryFilter(read.filters.ShiftCommitted(1), fixture.deployment.deployBlock);
    await until(() => Date.now() / 1000 >= Number(shiftLogs[0].args.start) + 1, 15000);
    mark('Ca bắt đầu, mở giám sát');
    const monitor = page('app', wallets[3], new Map(), '?plan=1');
    await monitor.start(); await monitor.run('connectWallet()');
    await until(() => monitor.run('!fetching'));
    function fake(kind) {
        execFileSync(process.env.P6_PYTHON, [path.join(root, 'tools/fake_device.py'), kind,
            '--key-file', path.join(work, 'device.key'), '--nonce-file', path.join(work, 'nonce.sqlite')],
            { cwd: root, env: process.env, stdio: 'pipe', windowsHide: true, timeout: 25000 });
    }
    fake('cancel');
    await until(() => fs.readFileSync(path.join(work, 'gateway.log'), 'utf8').includes('CANCEL from'));
    assert.equal(await read.eventCount(), 0n);
    mark('CANCEL chỉ off-chain');
    fake('fall');
    await until(async () => await read.eventCount() === 1n);
    await monitor.run('fetchData()');
    assert.match(monitor.nodes.get('events-table').innerHTML, /Mở \(Open\)/);
    await monitor.run('acknowledge(1)');
    fake('arrival');
    await until(async () => (await read.getFallEvent(1)).status === 2n);
    assert.equal((await read.getPlan(1)).violations, 0n);
    mark('FALL #1, dashboard acknowledge, ARRIVAL không vi phạm');
    fake('fall');
    await until(async () => await read.eventCount() === 2n);
    mark('FALL #2, bắt đầu chờ keeper theo giờ thực');
    const sla = Number((await read.getPlan(1)).slaSeconds);
    await until(async () => (await read.getFallEvent(2)).level === 1n, (sla + 15) * 1000);
    mark('Keeper chuyển cấp 1');
    await until(async () => (await read.getFallEvent(2)).level === 2n, (sla + 15) * 1000);
    mark('Keeper chuyển cấp 2');
    fake('arrival');
    await until(async () => (await read.getFallEvent(2)).status === 2n);
    await monitor.run('fetchData()');
    assert.equal((await read.getPlan(1)).violations, 2n);
    assert.match(monitor.nodes.get('events-table').innerHTML, /Đã đến nơi/);
    assert(!monitor.walletCalls.includes('eth_call'), 'Trang giám sát đọc qua MetaMask');
    await p.run('refresh()');
    await p.click('warp-btn');
    // Ví #0 gọi settle để số dư #1/#2 tăng đúng khoản chia, không trừ gas.
    await p.switchAccount(wallets[0]);
    const before = await Promise.all([rpc.send('eth_getBalance', [wallets[1], 'latest']), rpc.send('eth_getBalance', [wallets[2], 'latest'])]);
    await p.click('settle-btn');
    const after = await Promise.all([rpc.send('eth_getBalance', [wallets[1], 'latest']), rpc.send('eth_getBalance', [wallets[2], 'latest'])]);
    assert.equal(BigInt(after[0]) - BigInt(before[0]), ethers.parseEther('40'));
    assert.equal(BigInt(after[1]) - BigInt(before[1]), ethers.parseEther('60'));
    assert((await read.getPlan(1)).settled);
    assert.match(p.nodes.get('settle-balances').textContent, /hoàn gia đình 40\.0 ETH; trung tâm 60\.0 ETH/);
    assert(!p.walletCalls.includes('eth_call'), 'Trang thiết lập đọc qua MetaMask');
    mark('Tua giờ cuối demo và chia 40 / 60 ETH');
    assert(marks.at(-1).seconds <= 600);
    fs.writeFileSync(path.join(work, 'results.json'), JSON.stringify({ result: 'PASS', ethers: ethers.version,
        sla, marks, violations: 2, refundETH: '40', providerETH: '60',
        mode: 'Timed software rehearsal: real RPC/MQTT/gateway/keeper/fake_device; VM DOM and simulated wallet, not manual MetaMask',
    }, null, 2));
    console.log('PASS: setup VM, chuyển ví/mạng, khôi phục, MQTT, keeper, dashboard, settlement.');
}
main().then(() => process.exit(0)).catch((error) => { console.error(error); process.exit(1); });
