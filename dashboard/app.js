const PLAN_ID = Number(new URLSearchParams(location.search).get("plan") || 1);
let provider;
let signer;
let contract;          // ký giao dịch qua MetaMask (acknowledge, settle)
let readProvider;      // chỉ để đọc dữ liệu
let readContract;
let fetching = false;  // tránh hai lần đọc chồng nhau
const LOCAL_RPC = 'http://127.0.0.1:8545';
const POLL_MS = 2000;
let contractAddress;
let networkId;
let currentBlockTimestamp = Math.floor(Date.now() / 1000);

const connectBtn = document.getElementById('connect-btn');
const badge = document.getElementById('network-badge');
const tbody = document.querySelector('#events-table tbody');

async function init() {
    document.getElementById('display-plan-id').innerText = PLAN_ID;
    connectBtn.addEventListener('click', connectWallet);
    
    // Attempt to load metrics (Task 3.2)
    setInterval(loadMetrics, 4000);
    loadMetrics();
}

async function loadMetrics() {
    try {
        const res = await fetch('metrics.json');
        if (res.ok) {
            const data = await res.json();
            document.getElementById('metrics-section').style.display = 'grid';
            document.getElementById('metric-false-alarms').innerText = data.false_alarm_count || '0';
            
            const hbCount = data.last_heartbeat ? Object.keys(data.last_heartbeat).length : 0;
            document.getElementById('metric-heartbeats').innerText = `${hbCount} thiết bị`;
        }
    } catch (e) {
        // file doesn't exist yet, ignore
    }
}

async function connectWallet() {
    if (typeof window.ethereum === 'undefined') {
        alert('Vui lòng cài đặt MetaMask!');
        return;
    }

    try {
        await window.ethereum.request({ method: 'eth_requestAccounts' });
        provider = new ethers.BrowserProvider(window.ethereum);
        signer = await provider.getSigner();
        
        const network = await provider.getNetwork();
        networkId = Number(network.chainId);
        
        let deployFile = 'localhost.json';
        if (networkId === 11155111) {
            deployFile = 'sepolia.json';
            badge.innerText = 'Sepolia';
            badge.className = 'badge sepolia';
        } else if (networkId === 31337) {
            badge.innerText = 'Hardhat Local';
            badge.className = 'badge local';
        } else {
            badge.innerText = `Chain ${networkId}`;
            badge.className = 'badge default';
        }

        connectBtn.innerText = `${signer.address.substring(0, 6)}...${signer.address.substring(38)}`;
        connectBtn.disabled = true;

        // Load ABI and deploy info
        const abiRes = await fetch('CareSLA.json');
        const abiData = await abiRes.json();
        const abi = abiData.abi || abiData;

        const depRes = await fetch(`../deployments/${deployFile}`);
        if (!depRes.ok) {
            throw new Error(`Không tìm thấy file ${deployFile}. Hãy chắc chắn bạn đã deploy.`);
        }
        const depData = await depRes.json();
        contractAddress = depData.address;

        contract = new ethers.Contract(contractAddress, abi, signer);

        // Đọc thẳng từ Hardhat node: MetaMask cache kết quả đọc theo block và chỉ hỏi
        // block mới theo chu kỳ riêng, làm dashboard trễ hàng chục giây trên mạng local.
        readProvider = networkId === 31337
            ? new ethers.JsonRpcProvider(LOCAL_RPC, 31337, { staticNetwork: true })
            : provider;
        readContract = new ethers.Contract(contractAddress, abi, readProvider);

        // Start polling
        setInterval(fetchData, POLL_MS);
        fetchData();

    } catch (error) {
        console.error(error);
        alert('Lỗi kết nối: ' + error.message);
    }
}

async function fetchData() {
    if (!readContract || fetching) return;
    fetching = true;
    try {
        // Đọc song song: giờ block, plan, số sự cố
        const [block, plan, count] = await Promise.all([
            readProvider.getBlock('latest'),
            readContract.getPlan(PLAN_ID),
            readContract.eventCount(),
        ]);
        currentBlockTimestamp = Number(block.timestamp);

        // [family, provider, device, slaSeconds, penaltyWei, periodEnd, deposit, accepted, settled, violations, shiftCount, pendingEvents]
        
        const periodEnd = Number(plan[5]);
        const deposit = ethers.formatEther(plan[6]);
        const settled = plan[8];
        const violations = Number(plan[9]);
        const pendingEvents = Number(plan[11]);

        document.getElementById('plan-deposit').innerText = `${deposit} ETH`;
        document.getElementById('plan-violations').innerText = violations;
        document.getElementById('plan-pending').innerText = pendingEvents;
        document.getElementById('plan-status').innerText = settled ? "Đã thanh lý (Settled)" : "Đang hoạt động";

        // Check Settle button
        const settleBtn = document.getElementById('settle-btn');
        if (!settled && currentBlockTimestamp > (periodEnd + 600) && pendingEvents === 0) {
            settleBtn.disabled = false;
            settleBtn.onclick = () => settlePlan();
        } else {
            settleBtn.disabled = true;
        }

        // Fetch Events
        const eventCount = Number(count);
        const ids = Array.from({ length: eventCount }, (_, k) => k + 1);
        const events = await Promise.all(ids.map((id) => readContract.getFallEvent(id)));
        let html = '';
        if (eventCount === 0) {
            html = '<tr><td colspan="5" class="text-center">Chưa có sự cố nào.</td></tr>';
        } else {
            for (let i = 1; i <= eventCount; i++) {
                const ev = events[i - 1];
                // [planId, ts, dataHash, primary, backup, reportedAt, deadline, level, status, ackBy, ackAt, arrivedAt]
                
                if (Number(ev[0]) !== PLAN_ID) continue; // Only for this plan
                
                const ts = Number(ev[1]);
                const deadline = Number(ev[6]);
                const level = Number(ev[7]);
                const status = Number(ev[8]);
                
                const fallTimeStr = new Date(ts * 1000).toLocaleTimeString('vi-VN');
                
                let statusLabel = '';
                let statusClass = '';
                if (status === 0) { statusLabel = 'Mở (Open)'; statusClass = 'status-open'; }
                else if (status === 1) { statusLabel = 'Đã nhận (Ack)'; statusClass = 'status-ack'; }
                else if (status === 2) { statusLabel = 'Đã đến nơi (Arrived)'; statusClass = 'status-arrived'; }

                let levelLabel = 'Primary';
                if (level === 1) levelLabel = 'Backup (Cấp 1)';
                if (level === 2) levelLabel = 'Gia đình (Cấp 2)';

                let countdownHtml = '--';
                let canAck = false;
                
                if (status === 0) {
                    canAck = true; // contract cho primary/backup xác nhận ở mọi cấp (IC-08)
                    if (level === 2) {
                        countdownHtml = '<span class="status-tag status-open" style="background:transparent; border: 1px solid var(--danger);">Đã báo Gia đình</span>';
                    } else {
                        const diff = deadline - currentBlockTimestamp;
                        if (diff > 0) {
                            countdownHtml = `<span class="countdown ${diff > 30 ? 'safe' : 'warn'}">${diff}s</span>`;
                        } else {
                            countdownHtml = `<span class="countdown danger">QUÁ HẠN (${Math.abs(diff)}s)</span>`;
                        }
                    }
                }

                let ackBtn = `<button class="btn primary-btn" onclick="acknowledge(${i})" ${!canAck ? 'disabled' : ''}>Xác nhận</button>`;

                let txLink = '';
                if (networkId === 11155111) { // Sepolia
                    txLink = `<a href="https://sepolia.etherscan.io/address/${contractAddress}" target="_blank" style="color:var(--accent); text-decoration:none; margin-left:10px; font-size: 0.85rem;">Etherscan ↗</a>`;
                }

                html += `
                    <tr>
                        <td>#${i} <br><small style="color:#888; font-size: 0.85rem;">(${fallTimeStr})</small> ${txLink}</td>
                        <td><span class="status-tag ${statusClass}">${statusLabel}</span></td>
                        <td>${levelLabel}</td>
                        <td>${countdownHtml}</td>
                        <td>${ackBtn}</td>
                    </tr>
                `;
            }
        }
        tbody.innerHTML = html;

    } catch (e) {
        console.error("Fetch Data Error:", e);
    } finally {
        fetching = false;
    }
}

async function acknowledge(eventId) {
    try {
        const tx = await contract.acknowledge(eventId);
        alert(`Đã gửi giao dịch xác nhận (Tx: ${tx.hash})`);
        await tx.wait();
        alert('Xác nhận thành công!');
        fetchData();
    } catch (e) {
        alert('Lỗi: ' + (e.reason || e.message));
    }
}

async function settlePlan() {
    try {
        const tx = await contract.settle(PLAN_ID);
        alert(`Đã gửi giao dịch thanh lý (Tx: ${tx.hash})`);
        await tx.wait();
        alert('Thanh lý hợp đồng thành công!');
        fetchData();
    } catch (e) {
        alert('Lỗi: ' + (e.reason || e.message));
    }
}

window.addEventListener('load', init);
