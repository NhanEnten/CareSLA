// Script TẠM của P1: thử tấn công contract để rà bảo mật.
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");
const E = ethers.parseEther;

async function sign(device, eventType, ts, nonce, dataHash) {
  const h = ethers.solidityPackedKeccak256(["address","uint8","uint64","uint64","bytes32"], [device.address, eventType, ts, nonce, dataHash]);
  return device.signMessage(ethers.getBytes(h));
}
async function tryTx(p) { try { await p; return "OK"; } catch (e) { return "REVERT: " + (e.shortMessage || e.message).split("\n")[0]; } }

async function attack1() {
  console.log("=== Tấn công 1 (IC-11): hợp đồng bù nhìn dùng chung thiết bị ===");
  const [family, provider, primary, backup, gateway, accomplice] = await ethers.getSigners();
  const device = ethers.Wallet.createRandom();
  const c = await ethers.deployContract("CareSLA");
  const now = await time.latest();

  // Hợp đồng thật #1
  await c.connect(family).createCarePlan(provider.address, device.address, 60, E("0.1"), now + 3600, { value: E("1") });
  await c.connect(provider).acceptPlan(1);
  await c.connect(provider).commitShift(1, now + 10, now + 3000, primary.address, backup.address);

  // Trung tâm nhờ đồng bọn làm "gia đình" giả, tạo hợp đồng #2 với CÙNG địa chỉ thiết bị (địa chỉ là công khai)
  await c.connect(accomplice).createCarePlan(provider.address, device.address, 60, 1, now + 3600, { value: 1n });
  await c.connect(provider).acceptPlan(2);
  await c.connect(provider).commitShift(2, now + 10, now + 3000, primary.address, backup.address);

  await time.increase(30);
  const ts = await time.latest();
  const dh = ethers.keccak256("0x1234");
  const sig = await sign(device, 1, ts, 1, dh);
  // Chữ ký FALL thật xuất hiện (MQTT hoặc mempool Sepolia). Trung tâm nộp nó vào hợp đồng #2 trước
  console.log("  Trung tâm nộp FALL vào hợp đồng bù nhìn #2:", await tryTx(c.connect(provider).reportFall(2, ts, 1, dh, sig)));
  console.log("  Gateway nộp FALL vào hợp đồng thật #1:    ", await tryTx(c.connect(gateway).reportFall(1, ts, 1, dh, sig)));
  // Hợp đồng thật #1 là sự cố số 2 (sự cố số 1 thuộc plan bù nhìn)
  await time.increase(61); await c.checkTimeout(2);
  await time.increase(61); await c.checkTimeout(2);
  console.log("  → Vi phạm của hợp đồng thật:", (await c.getPlan(1)).violations.toString(), "(mong 2)\n");
}

async function attack2() {
  console.log("=== Tấn công 2 (IC-12): settle ngay khi hết kỳ để né phạt ===");
  const [family, provider, primary, backup, gateway] = await ethers.getSigners();
  const device = ethers.Wallet.createRandom();
  const c = await ethers.deployContract("CareSLA");
  const now = await time.latest();
  const periodEnd = now + 200;

  await c.connect(family).createCarePlan(provider.address, device.address, 60, E("0.5"), periodEnd, { value: E("1") });
  await c.connect(provider).acceptPlan(1);
  await c.connect(provider).commitShift(1, now + 10, periodEnd, primary.address, backup.address);

  await time.increaseTo(periodEnd - 20);           // té ngã 20 giây trước khi hết kỳ
  const ts = await time.latest();
  const dh = ethers.keccak256("0x1234");
  await c.connect(gateway).reportFall(1, ts, 1, dh, await sign(device, 1, ts, 1, dh));
  console.log("  Té ngã lúc periodEnd − 20 s, không ai phản hồi");

  await time.increaseTo(periodEnd + 1);            // hạn chót vẫn chưa tới, trung tâm settle luôn
  console.log("  Trung tâm gọi settle lúc periodEnd + 1 s:", await tryTx(c.connect(provider).settle(1)));
  await time.increaseTo(periodEnd + 601);
  const ts2 = await time.latest(); // té ngã xảy ra SAU khi hết kỳ thì không được báo
  console.log("  reportFall với ts sau periodEnd:", await tryTx(c.reportFall(1, ts2, 9, dh, await sign(device, 1, ts2, 9, dh))));
  console.log("  Trung tâm gọi settle lúc periodEnd + 601 s (keeper chết):", await tryTx(c.connect(provider).settle(1)));
  console.log("  Gia đình tự gọi checkTimeout:", await tryTx(c.connect(family).checkTimeout(1)));
  await time.increase(61);
  console.log("  Gia đình tự gọi checkTimeout lần 2:", await tryTx(c.connect(family).checkTimeout(1)));
  const fBefore = await ethers.provider.getBalance(family.address);
  console.log("  Trung tâm gọi settle:", await tryTx(c.connect(provider).settle(1)));
  const fGain = (await ethers.provider.getBalance(family.address)) - fBefore;
  console.log("  → Vi phạm:", (await c.getPlan(1)).violations.toString(), "| gia đình nhận lại", ethers.formatEther(fGain), "ETH (mong 1.0)");
  console.log("");
}

async function checklistExtras() {
  console.log("=== Kiểm tra thêm ===");
  const [family, provider, primary, backup, gateway, stranger] = await ethers.getSigners();
  const device = ethers.Wallet.createRandom();
  const c = await ethers.deployContract("CareSLA");
  const now = await time.latest();
  await c.connect(family).createCarePlan(provider.address, device.address, 60, E("0.1"), now + 36000, { value: E("1") });
  await c.connect(provider).acceptPlan(1);
  // Mục 3: tối đa 20 ca
  for (let i = 0; i < 20; i++) await c.connect(provider).commitShift(1, now + 100 + i * 100, now + 200 + i * 100, primary.address, backup.address);
  console.log("  Ca thứ 21:", await tryTx(c.connect(provider).commitShift(1, now + 5000, now + 5100, primary.address, backup.address)));
  // Mục 1: người lạ commitShift
  console.log("  Người lạ commitShift:", await tryTx(c.connect(stranger).commitShift(1, now + 9000, now + 9100, primary.address, backup.address)));
  // Mục 7: nonce bằng và nhỏ hơn
  await time.increaseTo(now + 150);
  const ts = await time.latest(); const dh = ethers.ZeroHash;
  await c.reportFall(1, ts, 5, dh, await sign(device, 1, ts, 5, dh));
  console.log("  Nonce 5 lần 2:", await tryTx(c.reportFall(1, ts, 5, dh, await sign(device, 1, ts, 5, dh))));
  console.log("  Nonce 4 sau 5:", await tryTx(c.reportFall(1, ts, 4, dh, await sign(device, 1, ts, 4, dh))));
  // Chữ ký FALL dùng làm ARRIVAL (đổi eventType)
  const fallSig = await sign(device, 1, ts, 6, dh);
  console.log("  Dùng chữ ký FALL cho confirmArrival:", await tryTx(c.confirmArrival(1, ts, 6, dh, fallSig)));
  // Gas của commitShift khi đã có 20 ca (vòng lặp dài nhất)
  const est = await c.connect(stranger).getOnDuty.estimateGas(1, now + 2150);
  console.log("  Gas getOnDuty tìm ca cuối trong 20 ca (ước lượng):", est.toString());
}

async function main() { await attack1(); await attack2(); await checklistExtras(); }
main().catch((e) => { console.error(e); process.exitCode = 1; });
