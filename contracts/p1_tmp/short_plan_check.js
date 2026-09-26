// Script TẠM: kiểm chứng đoạn code mẫu "hợp đồng kỳ ngắn" đề xuất cho demo_setup.js của P2.
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

// ===== Đoạn đề xuất cho demo_setup.js (giữ nguyên để copy) =====
async function setupShortPlan(c, family, provider, primary, backup, gateway) {
  const now = (await ethers.provider.getBlock("latest")).timestamp;
  const periodEnd = now + 5 * 60;                       // kỳ 5 phút
  const demoDevice = ethers.Wallet.createRandom();      // thiết bị "mẫu" chỉ cho hợp đồng này
  const tx = await c.connect(family).createCarePlan(
    provider.address, demoDevice.address, 60, ethers.parseEther("0.002"), periodEnd,
    { value: ethers.parseEther("0.01") });
  const planId = (await tx.wait()).logs.map((l) => c.interface.parseLog(l)).find((l) => l?.name === "PlanCreated").args.planId;
  await (await c.connect(provider).acceptPlan(planId)).wait();
  await (await c.connect(provider).commitShift(planId, now + 30, periodEnd, primary.address, backup.address)).wait();
  return { planId, periodEnd, demoDevice };
}
async function reportDemoFall(c, planId, demoDevice, gateway, nonce) {
  const ts = (await ethers.provider.getBlock("latest")).timestamp;
  const dataHash = ethers.keccak256(ethers.toUtf8Bytes("demo"));
  const h = await c.hashEvent(demoDevice.address, 1, ts, nonce, dataHash);
  const sig = await demoDevice.signMessage(ethers.getBytes(h));
  await (await c.connect(gateway).reportFall(planId, ts, nonce, dataHash, sig)).wait();
}
// ===============================================================

async function main() {
  const [family, provider, primary, backup, gateway, keeper] = await ethers.getSigners();
  const c = await ethers.deployContract("CareSLA");
  const { planId, periodEnd, demoDevice } = await setupShortPlan(c, family, provider, primary, backup, gateway);
  await time.increase(40);                               // ngoài đời: chờ ca bắt đầu
  await reportDemoFall(c, planId, demoDevice, gateway, 1);
  // Keeper tự chuyển cấp (ngoài đời diễn ra thật sau ~2 phút)
  await time.increase(61); await c.connect(keeper).checkTimeout(1);
  await time.increase(61); await c.connect(keeper).checkTimeout(1);
  await time.increaseTo(periodEnd + 601);                // giờ demo: ~15 phút sau khi chạy script
  const plan = await c.getPlan(planId);
  const now = (await ethers.provider.getBlock("latest")).timestamp;
  // Điều kiện hiện nút Settle đề xuất cho dashboard
  const canSettle = !plan.settled && now > Number(plan.periodEnd) + 600 && plan.pendingEvents === 0n;
  console.log("planId", planId.toString(), "| vi phạm", plan.violations.toString(), "| pendingEvents", plan.pendingEvents.toString(), "| hiện nút Settle:", canSettle);
  const before = await ethers.provider.getBalance(family.address);
  await (await c.connect(keeper).settle(planId)).wait();
  console.log("Gia đình nhận lại", ethers.formatEther((await ethers.provider.getBalance(family.address)) - before), "ETH (mong 0.004)");
}
main().catch((e) => { console.error(e); process.exitCode = 1; });
