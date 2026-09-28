const hre = require("hardhat");
const fs = require("node:fs");
const { readDeployment, parsedEvent, safeError } = require("./common");

function walletFromFile(filename, role) {
  if (!filename) throw new Error(`Sepolia cần --${role}-key-file; xem README. Không đưa khóa vào lệnh/chat.`);
  const key = fs.readFileSync(filename, "utf8").trim();
  if (!/^(0x)?[0-9a-fA-F]{64}$/.test(key)) throw new Error(`File khóa ${role} không hợp lệ.`);
  // Không để thư viện đưa khóa vào thông báo lỗi.
  try { return new hre.ethers.Wallet(key, hre.ethers.provider); }
  catch { throw new Error(`Khóa ${role} không hợp lệ.`); }
}

async function main(options = {}) {
  const { ethers } = hre;
  const deployment = await readDeployment(hre);
  const demoDevice = options.shortPlan ? ethers.Wallet.createRandom() : null;
  const devices = (process.env.REGISTERED_DEVICES || "").split(",").map((x) => x.trim()).filter(Boolean);
  const deviceInput = demoDevice?.address || options.device || (devices.length === 1 ? devices[0] : null);
  if (!deviceInput || !ethers.isAddress(deviceInput)) throw new Error("Cần --device 0x... hoặc REGISTERED_DEVICES có đúng 1 địa chỉ hợp lệ.");
  const device = ethers.getAddress(deviceInput);
  if (device === ethers.ZeroAddress) throw new Error("Địa chỉ thiết bị không được là zero.");
  let family, provider, primary, backup;
  if (hre.network.name === "localhost") {
    [, family, provider, primary, backup] = await ethers.getSigners();
    primary = primary.address;
    backup = backup.address;
  } else {
    family = walletFromFile(options.familyKeyFile, "family");
    provider = walletFromFile(options.providerKeyFile, "provider");
    if (!ethers.isAddress(options.primary) || !ethers.isAddress(options.backup)) throw new Error("Sepolia cần --primary và --backup hợp lệ.");
    primary = ethers.getAddress(options.primary);
    backup = ethers.getAddress(options.backup);
  }
  if (new Set([family.address, provider.address, primary, backup].map((a) => a.toLowerCase())).size !== 4
      || [primary, backup].includes(ethers.ZeroAddress)) {
    throw new Error("Demo cần 4 địa chỉ family/provider/primary/backup khác nhau và khác zero.");
  }
  // Local: số tròn để thuyết trình (2 vi phạm → gia đình 40, trung tâm 60). Sepolia không có đủ ETH faucet.
  const local = hre.network.name === "localhost";
  const deposit = ethers.parseEther(local ? "100" : "0.01");
  const penalty = ethers.parseEther(local ? "20" : "0.002");
  const familyBalance = await ethers.provider.getBalance(family.address);
  const providerBalance = await ethers.provider.getBalance(provider.address);
  console.log(`Family: ${family.address}, balance=${ethers.formatEther(familyBalance)} ETH`);
  console.log(`Provider: ${provider.address}, balance=${ethers.formatEther(providerBalance)} ETH`);
  console.log(`Primary: ${primary}; backup: ${backup}; device: ${device}`);
  if (familyBalance <= deposit || providerBalance === 0n) throw new Error("Cần cấp đủ ETH ký quỹ và gas cho family/provider.");
  const contract = await ethers.getContractAt("CareSLA", deployment.address);
  const now = (await ethers.provider.getBlock("latest")).timestamp;
  const periodEnd = now + (options.shortPlan ? 5 * 60 : 2 * 60 * 60);
  const createReceipt = await (await contract.connect(family).createCarePlan(
    provider.address, device, 60, penalty, periodEnd, { value: deposit },
  )).wait();
  const { planId } = parsedEvent(contract, createReceipt, "PlanCreated");
  // In ngay để vẫn tìm được plan nếu bước accept/commit bị lỗi RPC.
  console.log(`PLAN_ID=${planId}; periodEnd=${periodEnd}; createTx=${createReceipt.hash}`);
  await (await contract.connect(provider).acceptPlan(planId)).wait();
  const start = (await ethers.provider.getBlock("latest")).timestamp + 60;
  if (start >= periodEnd) throw new Error("Setup quá chậm; plan đã hết khoảng trực demo.");
  const middle = start + Math.floor((periodEnd - start) / 2);
  const shifts = options.shortPlan ? [[start, periodEnd]] : [[start, middle], [middle, periodEnd]];
  for (const [shiftStart, shiftEnd] of shifts) {
    const receipt = await (await contract.connect(provider).commitShift(planId, shiftStart, shiftEnd, primary, backup)).wait();
    console.log(`Shift [${shiftStart}, ${shiftEnd}): ${receipt.hash}`);
  }
  console.log(`Sẵn sàng từ ${new Date(start * 1000).toISOString()}. ${options.shortPlan ? "Plan ngắn: không thay PLAN_ID của gateway" : `Ghi PLAN_ID=${planId} vào .env.`}`);
  console.log(`Settle chỉ sau timestamp=${periodEnd + 600} và pendingEvents=0. Keeper cần tiếp tục chạy.`);
  console.log("Mỗi lần chạy setup sẽ tạo plan mới. Không có ca trước start; chỉ phát FALL sau thời điểm này.");
  if (demoDevice) {
    console.log("Chờ ca của plan ngắn bắt đầu để gửi FALL mẫu; khóa mẫu chỉ nằm trong RAM.");
    const waitUntil = Date.now() + 180000;
    let block = await ethers.provider.getBlock("latest");
    while (block.timestamp < start) {
      if (Date.now() > waitUntil) throw new Error("Không thấy giờ chain tiến; kiểm tra node/RPC. Plan đã tạo, không tự tạo lại.");
      await new Promise((resolve) => setTimeout(resolve, 2000));
      block = await ethers.provider.getBlock("latest");
    }
    const dataHash = ethers.keccak256("0x010002000300040005000600");
    const messageHash = ethers.solidityPackedKeccak256(
      ["address", "uint8", "uint64", "uint64", "bytes32"], [device, 1, block.timestamp, 1, dataHash],
    );
    const sig = await demoDevice.signMessage(ethers.getBytes(messageHash));
    const receipt = await (await contract.connect(family).reportFall(planId, block.timestamp, 1, dataHash, sig)).wait();
    const event = parsedEvent(contract, receipt, "FallReported");
    console.log(`Plan ngắn: planId=${planId}; eventId=${event.eventId}; FALL tx=${receipt.hash}`);
    console.log("Chuẩn bị ít nhất 20 phút trước demo, để keeper xử lý 2 cấp; không giảm SETTLE_DELAY.");
  }
}

if (require.main === module) main().catch((error) => { console.error(safeError(error)); process.exitCode = 1; });
module.exports = { main };
