'use strict';

const $ = (id) => document.getElementById(id);
const ERRORS = {
    'no deposit': 'Ký quỹ phải lớn hơn 0.',
    'zero address': 'Địa chỉ không được là địa chỉ 0.',
    'provider is family': 'Trung tâm phải khác ví gia đình.',
    'sla is 0': 'SLA phải lớn hơn 0 giây.',
    'penalty > deposit': 'Mức phạt không được vượt quá ký quỹ.',
    'period ended': 'Kỳ hợp đồng đã kết thúc.',
    'not provider': 'Chỉ ví trung tâm được thực hiện thao tác này.',
    'already accepted': 'Hợp đồng đã được chấp nhận.',
    'not accepted': 'Trung tâm chưa chấp nhận hợp đồng.',
    'start in past': 'Không thể cam kết ca trong quá khứ: giờ bắt đầu phải sau giờ chain.',
    'end <= start': 'Giờ kết thúc ca phải sau giờ bắt đầu.',
    'end > periodEnd': 'Ca trực không được kết thúc sau kỳ hợp đồng.',
    'primary == backup': 'Nhân viên chính và dự phòng phải khác nhau.',
    'too many shifts': 'Mỗi hợp đồng có tối đa 20 ca.',
    'overlap': 'Ca trực trùng thời gian với ca đã cam kết.',
    'period not ended': 'Chưa qua thời điểm kết thúc kỳ + 600 giây.',
    'pending events': 'Còn sự cố chờ xử lý; chưa thể chia tiền.',
    'already settled': 'Hợp đồng đã chia tiền.',
};
let rpc, reader, signer, writer, deployment, abi;
let planId = null, plan = null, shifts = [], chainTime = 0;
let local = false, unsupported = false, busy = false, polling = false, walletEpoch = 0;
const same = (a, b) => !!a && !!b && a.toLowerCase() === b.toLowerCase();
const short = (value) => `${value.slice(0, 8)}…${value.slice(-6)}`;
const eth = (value) => ethers.formatEther(value);
const date = (value) => new Date(Number(value) * 1000).toLocaleString('vi-VN');
function stored(key, value) {
    try {
        if (value === undefined) return localStorage.getItem(key);
        localStorage.setItem(key, value);
    } catch (_) { /* Chế độ riêng tư vẫn dùng được. */ }
    return null;
}
function dateInput(seconds) {
    const d = new Date(seconds * 1000);
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
}
function seconds(id) {
    const n = Math.floor(new Date($(id).value).getTime() / 1000);
    if (!Number.isSafeInteger(n) || n <= 0) throw new Error('Vui lòng nhập ngày giờ hợp lệ.');
    return n;
}
function message(text, error = false) {
    $('setup-message').textContent = text;
    $('setup-message').className = error ? 'highlight-err' : '';
}
function translated(error) {
    if (error.code === 'ACTION_REJECTED' || error.code === 4001 || error.info?.error?.code === 4001) return 'Đã hủy ký';
    const raw = error.reason || error.shortMessage || error.message || String(error);
    const detail = `${raw} ${error.info?.error?.message || ''}`;
    const key = Object.keys(ERRORS).find((k) => detail.includes(k));
    return key ? ERRORS[key] : raw;
}
async function action(fn) {
    if (busy) return;
    busy = true;
    render();
    try {
        await requireLocal();
        await fn();
    } catch (error) {
        const text = translated(error);
        message(text, text !== 'Đã hủy ký');
    } finally {
        busy = false;
        await refresh();
        render();
    }
}
async function requireLocal() {
    if (!local || !signer || Number(await window.ethereum.request({ method: 'eth_chainId' })) !== 31337 ||
        Number(await rpc.send('eth_chainId', [])) !== 31337) {
        local = false;
        render();
        throw new Error('Trang thiết lập chỉ dùng cho demo local');
    }
}
async function now() {
    // Đọc trực tiếp block mới, không dùng đồng hồ máy hoặc cache MetaMask.
    const block = await rpc.send('eth_getBlockByNumber', ['latest', false]);
    chainTime = Number(block.timestamp);
    return chainTime;
}
async function connectWallet(request = true) {
    const epoch = ++walletEpoch;
    local = false; signer = null; writer = null;
    render();
    try {
        if (!window.ethereum) throw new Error('Vui lòng cài đặt MetaMask.');
        const accounts = await window.ethereum.request({ method: request ? 'eth_requestAccounts' : 'eth_accounts' });
        const network = Number(await window.ethereum.request({ method: 'eth_chainId' }));
        if (epoch !== walletEpoch) return;
        unsupported = network !== 31337;
        if (unsupported) throw new Error('Trang thiết lập chỉ dùng cho demo local');
        if (!accounts.length) { message('Chưa có ví được kết nối.'); return; }
        const wallet = new ethers.BrowserProvider(window.ethereum);
        const nextSigner = await wallet.getSigner(accounts[0]);
        rpc = rpc || new ethers.JsonRpcProvider('http://127.0.0.1:8545', 31337, { staticNetwork: true });
        if (Number(await rpc.send('eth_chainId', [])) !== 31337) throw new Error('Trang thiết lập chỉ dùng cho demo local');
        const responses = await Promise.all([fetch('CareSLA.json'), fetch('../deployments/localhost.json', { cache: 'no-store' })]);
        if (responses.some((r) => !r.ok)) throw new Error('Không tải được ABI hoặc deployment localhost. Hãy deploy trước.');
        const [abiFile, dep] = await Promise.all(responses.map((r) => r.json()));
        if (Number(dep.chainId) !== 31337) throw new Error('Trang thiết lập chỉ dùng cho demo local');
        if (await rpc.getCode(dep.address) === '0x') throw new Error('Contract chưa được deploy trên node hiện tại.');
        if (epoch !== walletEpoch) return;
        abi = abiFile.abi || abiFile; deployment = dep; signer = nextSigner;
        reader = new ethers.Contract(dep.address, abi, rpc);
        writer = new ethers.Contract(dep.address, abi, signer);
        local = true;
        await now();
        if (!$('period-end').value) $('period-end').value = dateInput(chainTime + 900);
        const saved = new URLSearchParams(location.search).get('plan') || stored('caresla.setup.plan');
        if (!planId && saved) {
            try { await openPlan(saved); } catch (e) { message(translated(e), true); }
        } else { await refresh(); message('Đã kết nối Hardhat Local.'); }
    } catch (e) { message(translated(e), translated(e) !== 'Đã hủy ký'); }
    finally { if (epoch === walletEpoch) render(); }
}
async function openPlan(value) {
    if (!/^[1-9]\d*$/.test(String(value))) throw new Error('planId phải là số nguyên dương.');
    const next = await reader.getPlan(value);
    if (next.family === ethers.ZeroAddress) throw new Error('Không tìm thấy hợp đồng trên node hiện tại.');
    planId = String(value); plan = next; shifts = [];
    $('open-plan').value = planId;
    const url = new URL(location.href); url.searchParams.set('plan', planId);
    history.replaceState(null, '', url);
    stored('caresla.setup.plan', planId);
    $('create-balances').textContent = '';
    $('settle-balances').textContent = '';
    await refresh();
}
// Bỏ hợp đồng đang mở để tạo hợp đồng khác (dữ liệu trên chain không đổi)
function newPlan() {
    planId = null; plan = null; shifts = [];
    $('open-plan').value = '';
    const url = new URL(location.href); url.searchParams.delete('plan');
    history.replaceState(null, '', url);
    try { localStorage.removeItem('caresla.setup.plan'); } catch (_) { /* bỏ qua */ }
    for (const id of ['proof-1', 'proof-2', 'proof-3', 'proof-4', 'create-balances', 'settle-balances', 'plan-summary', 'checklist', 'gateway-hint']) $(id).textContent = '';
    $('shifts-body').replaceChildren();
    message('Đã bỏ hợp đồng đang mở. Dùng ví gia đình để tạo hợp đồng mới.');
}
function proof(log) {
    return log ? `✅ Tx ${short(log.transactionHash)} · block ${log.blockNumber}` : '';
}
async function refresh() {
    if (!local || !reader || polling) return;
    polling = true;
    try {
        await now();
        if (planId) {
            const id = planId;
            const [next, created, accepted, committed] = await Promise.all([
                reader.getPlan(id),
                reader.queryFilter(reader.filters.PlanCreated(id), deployment.deployBlock),
                reader.queryFilter(reader.filters.PlanAccepted(id), deployment.deployBlock),
                reader.queryFilter(reader.filters.ShiftCommitted(id), deployment.deployBlock),
            ]);
            if (id !== planId) return;
            if (next.family === ethers.ZeroAddress) throw new Error('Hợp đồng không còn tồn tại; có thể node đã khởi động lại.');
            plan = next; shifts = committed;
            $('proof-1').textContent = proof(created[0]);
            $('proof-2').textContent = proof(accepted[0]);
            $('proof-3').textContent = proof(committed.at(-1));
            $('proof-4').textContent = 'Giám sát là thao tác đọc, không tạo giao dịch.';
        }
        render();
    } catch (e) {
        local = false; render(); message(translated(e), true);
    } finally { polling = false; }
}
function render() {
    const address = signer?.address;
    const provider = same(address, plan ? plan.provider : $('provider-address').value);
    const staff = shifts.some((s) => same(address, s.args.primary) || same(address, s.args.backup));
    const family = plan ? same(address, plan.family) : !!address && !provider;
    $('wallet-role').textContent = `Ví đang dùng: ${!address ? 'Chưa kết nối' : provider ? 'Trung tâm' : family ? 'Gia đình' : staff ? 'Nhân viên' : 'Khác'}${address ? ' — ' + short(address) : ''}`;
    $('network-badge').textContent = local ? 'Hardhat Local' : 'Chưa kết nối local';
    $('network-badge').className = local ? 'badge local' : 'badge default';
    $('finish-section').hidden = !local;
    $('chain-clock').textContent = `Giờ chain: ${chainTime ? date(chainTime) : '—'}`;
    const enable = (id, condition) => { $(id).disabled = busy || !local || !condition; };
    // Mạng sai khóa mọi nút; chainChanged tự phục hồi khi chuyển về local.
    $('connect-btn').disabled = busy || unsupported;
    enable('open-btn', true); enable('new-btn', !!planId); enable('create-btn', !planId && family);
    const active = plan && !plan.settled && chainTime < Number(plan.periodEnd);
    enable('accept-btn', active && !plan.accepted && provider);
    enable('defaults-btn', active && plan.accepted && provider);
    enable('shift-btn', active && plan.accepted && provider && shifts.length < 20);
    enable('past-btn', active && plan.accepted && provider && shifts.length > 0);
    enable('copy-btn', !!planId);
    const onDuty = shifts.find((s) => Number(s.args.start) <= chainTime && chainTime < Number(s.args.end));
    enable('monitor-btn', active && plan.accepted && !!onDuty);
    enable('warp-btn', plan && !plan.settled && plan.pendingEvents === 0n);
    enable('settle-btn', plan && !plan.settled && plan.pendingEvents === 0n && chainTime > Number(plan.periodEnd) + 600);
    const done = [!!plan, !!plan?.accepted, shifts.length > 0, !!onDuty && !!plan?.accepted];
    for (let i = 1; i <= 4; i++) {
        $('progress-' + i).className = done[i - 1] ? 'setup-done' : '';
        $('step-' + i).classList.toggle('setup-locked', i > 1 && !done[i - 2]);
    }
    const end = new Date($('period-end').value).getTime() / 1000;
    $('period-remaining').textContent = Number.isFinite(end) ? `${date(end)} · còn ${Math.max(0, Math.ceil((end - chainTime) / 60))} phút` : '';
    if (!plan) return;
    $('plan-summary').textContent = `Hợp đồng #${planId}\nGia đình: ${plan.family}\nTrung tâm: ${plan.provider}\nThiết bị: ${plan.device}\nSLA: ${plan.slaSeconds} giây · phạt: ${eth(plan.penaltyWei)} ETH · ký quỹ: ${eth(plan.deposit)} ETH\nKết thúc: ${date(plan.periodEnd)}${plan.settled ? '\nĐã chia tiền' : ''}`;
    const future = shifts.filter((s) => Number(s.args.start) > chainTime).sort((a, b) => Number(a.args.start - b.args.start))[0];
    $('checklist').textContent = `${plan.accepted ? '✅ Đã chấp nhận' : '⏳ Chưa chấp nhận'} · ${onDuty ? '✅ Có ca đang trực' : future ? `Ca bắt đầu sau ${Number(future.args.start) - chainTime} giây` : 'Chưa có ca đang trực'} · ⚠️ Gateway phải dùng đúng planId.`;
    $('gateway-hint').textContent = `PLAN_ID trong .env phải bằng ${planId}. Nếu khác: sửa .env rồi chạy lại gateway. ${planId === '1' ? '✅ khớp mặc định .env (chưa kiểm tra file thực tế).' : ''}`;
    $('shifts-body').replaceChildren();
    for (const s of shifts) {
        const row = document.createElement('tr');
        const values = [date(s.args.start), date(s.args.end), s.args.primary, s.args.backup,
            chainTime < Number(s.args.start) ? 'Chưa bắt đầu' : chainTime < Number(s.args.end) ? 'Đang trực' : 'Đã hết',
            `${short(s.transactionHash)} / ${s.blockNumber}`];
        for (const value of values) { const cell = document.createElement('td'); cell.textContent = value; row.appendChild(cell); }
        $('shifts-body').appendChild(row);
    }
    const wait = Math.max(0, Number(plan.periodEnd) + 601 - chainTime);
    $('settle-countdown').textContent = `Được chia tiền khi giờ chain > kết thúc kỳ + 600 giây (SETTLE_DELAY), còn ${Math.ceil(wait / 60)} phút. Sự cố đang chờ: ${plan.pendingEvents}.`;
    const fine = plan.violations * plan.penaltyWei;
    const refund = !plan.accepted ? plan.deposit : fine < plan.deposit ? fine : plan.deposit;
    $('settle-formula').textContent = `${plan.violations} vi phạm · phạt = min(${plan.violations} × ${eth(plan.penaltyWei)}, ${eth(plan.deposit)}) ETH. Gia đình ${eth(refund)} ETH, trung tâm ${eth(plan.deposit - refund)} ETH.${!plan.accepted ? ' Chưa chấp nhận: hoàn toàn bộ ký quỹ.' : ''}${plan.settled ? ' Đã chia tiền.' : ''}`;
}
async function send(method, args) {
    await requireLocal();
    const tx = await writer[method](...args);
    message(`Đã gửi ${short(tx.hash)}; chờ xác nhận…`);
    const receipt = await tx.wait();
    message(`✅ Tx ${short(receipt.hash)} · block ${receipt.blockNumber}`);
    return receipt;
}
async function balance(address, block = 'latest') {
    return BigInt(await rpc.send('eth_getBalance', [address, typeof block === 'number' ? ethers.toQuantity(block) : block]));
}
async function createPlan() {
    const family = signer.address;
    const before = await balance(family);
    const device = ethers.getAddress($('device-address').value.trim());
    const receipt = await send('createCarePlan', [ethers.getAddress($('provider-address').value.trim()), device,
        BigInt($('sla').value), ethers.parseEther($('penalty').value), seconds('period-end'), { value: ethers.parseEther($('deposit').value) }]);
    const event = receipt.logs.map((log) => { try { return reader.interface.parseLog(log); } catch (_) { return null; } }).find((log) => log?.name === 'PlanCreated');
    if (!event) throw new Error('Giao dịch đã xác nhận nhưng chưa đọc được PlanCreated. Hãy mở lại planId từ chain.');
    stored('caresla.setup.device', device);
    await openPlan(event.args.planId.toString());
    const [after, locked] = await Promise.all([balance(family, receipt.blockNumber), balance(deployment.address, receipt.blockNumber)]);
    $('create-balances').textContent = `Gia đình trước: ${eth(before)} ETH → sau: ${eth(after)} ETH (đã gồm gas). Số dư contract: ${eth(locked)} ETH.`;
}
async function defaults() {
    await now();
    $('shift-start').value = dateInput(chainTime + 20);
    $('shift-end').value = dateInput(Number(plan.periodEnd));
}
function shiftArgs(start) {
    return [planId, start, seconds('shift-end'), ethers.getAddress($('primary-address').value.trim()), ethers.getAddress($('backup-address').value.trim())];
}
async function pastShift() {
    await now();
    try {
        await reader.commitShift.staticCall(...shiftArgs(chainTime - 60), { from: signer.address });
        throw new Error('Phép thử bất ngờ thành công; kiểm tra deployment.');
    } catch (e) {
        if (translated(e) !== ERRORS['start in past']) throw e;
        message(`✅ Contract từ chối: ${translated(e)} Không gửi giao dịch.`);
    }
}
async function warp() {
    if (!window.confirm('Sau khi tua, thiết bị không gửi được sự kiện mới cho chain này (bị từ chối "ts too old"). Tua giờ ảnh hưởng toàn bộ node. Chỉ bấm ở bước cuối. Tiếp tục?')) return;
    await requireLocal();
    await now();
    const latest = await reader.getPlan(planId);
    if (latest.pendingEvents !== 0n) throw new Error('Còn sự cố chờ xử lý; chưa thể tua giờ kết thúc demo.');
    const delta = Math.max(0, Number(latest.periodEnd) + 601 - chainTime);
    if (delta) await rpc.send('evm_increaseTime', [delta]);
    await rpc.send('evm_mine', []);
    message('Đã tua giờ. Bấm Settle ở đây hoặc trên trang giám sát.');
}
async function settle() {
    const family = plan.family, provider = plan.provider;
    const before = await Promise.all([balance(family), balance(provider)]);
    const receipt = await send('settle', [planId]);
    const after = await Promise.all([balance(family, receipt.blockNumber), balance(provider, receipt.blockNumber)]);
    const event = receipt.logs.map((log) => { try { return reader.interface.parseLog(log); } catch (_) { return null; } }).find((log) => log?.name === 'Settled');
    $('settle-balances').textContent = `Gia đình: ${eth(before[0])} → ${eth(after[0])} ETH.\nTrung tâm: ${eth(before[1])} → ${eth(after[1])} ETH.\nSố dư ví ký đã trừ gas. Settled: hoàn gia đình ${eth(event.args.refundFamily)} ETH; trung tâm ${eth(event.args.toProvider)} ETH.\nTx ${receipt.hash} · block ${receipt.blockNumber}`;
}
function init() {
    $('device-address').value = stored('caresla.setup.device') || '';
    $('device-address').addEventListener('change', () => stored('caresla.setup.device', $('device-address').value));
    $('provider-address').addEventListener('input', render);
    $('connect-btn').addEventListener('click', () => connectWallet());
    const handlers = {
        'open-btn': () => openPlan($('open-plan').value), 'new-btn': newPlan, 'create-btn': createPlan,
        'accept-btn': () => send('acceptPlan', [planId]), 'defaults-btn': defaults,
        'shift-btn': () => send('commitShift', shiftArgs(seconds('shift-start'))), 'past-btn': pastShift,
        'copy-btn': async () => { await navigator.clipboard.writeText(`PLAN_ID=${planId}`); message('Đã copy PLAN_ID.'); },
        'monitor-btn': () => { location.href = `index.html?plan=${planId}`; }, 'warp-btn': warp, 'settle-btn': settle,
    };
    for (const [id, fn] of Object.entries(handlers)) $(id).addEventListener('click', () => action(fn));
    if (window.ethereum) {
        window.ethereum.on('accountsChanged', () => connectWallet(false));
        window.ethereum.on('chainChanged', () => connectWallet(false));
    }
    setInterval(refresh, 1000);
    render();
}
window.addEventListener('load', init);
