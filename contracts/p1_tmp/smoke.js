// Script TẠM của P1: chạy nhanh toàn bộ luồng trên Hardhat local. Không phải test chính thức (test là của P2).
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

async function sign(device, eventType, ts, nonce, dataHash) {
  const messageHash = ethers.solidityPackedKeccak256(
    ["address", "uint8", "uint64", "uint64", "bytes32"],
    [device.address, eventType, ts, nonce, dataHash]
  );
  const sig = await device.signMessage(ethers.getBytes(messageHash)); // EIP-191, v = 27/28
  return { messageHash, sig };
}

async function expectRevert(promise, reason) {
  try { await promise; } catch (e) {
    if (e.message.includes(reason)) { console.log(`  ✓ revert đúng: "${reason}"`); return; }
    throw new Error(`Sai lý do revert, mong "${reason}", nhận: ${e.message}`);
  }
  throw new Error(`Mong revert "${reason}" nhưng lại thành công`);
}

async function main() {
  const [family, provider, primary, backup, gateway, stranger] = await ethers.getSigners();
  const device = ethers.Wallet.createRandom();
  const c = await ethers.deployContract("CareSLA");
  const E = ethers.parseEther;

  const now = await time.latest();
  const periodEnd = now + 3600;
  await c.connect(family).createCarePlan(provider.address, device.address, 60, E("0.1"), periodEnd, { value: E("1") });
  console.log("1. Tạo hợp đồng #1, ký quỹ 1 ETH");

  await expectRevert(c.connect(stranger).acceptPlan(1), "not provider");
  await c.connect(provider).acceptPlan(1);
  console.log("2. Trung tâm chấp nhận");

  await expectRevert(c.connect(provider).commitShift(1, now - 10, now + 100, primary.address, backup.address), "start in past");
  await c.connect(provider).commitShift(1, now + 10, now + 1800, primary.address, backup.address);
  await expectRevert(c.connect(provider).commitShift(1, now + 1000, now + 2000, primary.address, backup.address), "overlap");
  console.log("3. Cam kết ca trực");

  await time.increase(30);
  const ts = await time.latest();
  const dataHash = ethers.keccak256(ethers.toUtf8Bytes("raw samples"));
  const fall = await sign(device, 1, ts, 1, dataHash);
  const onchainHash = await c.hashEvent(device.address, 1, ts, 1, dataHash);
  console.log("4. hashEvent khớp JS:", onchainHash === fall.messageHash);
  if (onchainHash !== fall.messageHash) throw new Error("hash không khớp");

  const fake = await sign(ethers.Wallet.createRandom(), 1, ts, 1, dataHash);
  await expectRevert(c.connect(gateway).reportFall(1, ts, 1, dataHash, fake.sig), "bad sig");
  await c.connect(gateway).reportFall(1, ts, 1, dataHash, fall.sig);
  console.log("5. Gateway báo té ngã (sự cố #1)");
  await expectRevert(c.connect(gateway).reportFall(1, ts, 1, dataHash, fall.sig), "old nonce");

  await expectRevert(c.checkTimeout(1), "not expired");
  await time.increase(61);
  await c.connect(stranger).checkTimeout(1);
  await expectRevert(c.checkTimeout(1), "not expired"); // không ghi 2 lần ở cùng cấp
  let ev = await c.getFunction("getEvent")(1);
  console.log("6. Quá hạn → cấp", ev.level.toString(), "(backup), vi phạm:", (await c.getPlan(1)).violations.toString());

  await expectRevert(c.connect(stranger).acknowledge(1), "not on duty");
  await c.connect(backup).acknowledge(1);
  await expectRevert(c.checkTimeout(1), "not open");
  console.log("7. Backup xác nhận đã nhận");

  const ts2 = await time.latest();
  const arr = await sign(device, 2, ts2, 3, dataHash); // nonce 2 coi như đã dùng cho CANCEL off-chain
  await c.connect(gateway).confirmArrival(1, ts2, 3, dataHash, arr.sig);
  ev = await c.getFunction("getEvent")(1);
  console.log("8. Có mặt, status =", ev.status.toString(), "(2 = Arrived)");

  // Sự cố #2: không ai phản hồi → 2 vi phạm, lần xác nhận trễ không xóa vi phạm
  await time.increase(10);
  const ts3 = await time.latest();
  const fall2 = await sign(device, 1, ts3, 4, dataHash);
  await c.connect(gateway).reportFall(1, ts3, 4, dataHash, fall2.sig);
  await time.increase(61); await c.checkTimeout(2);
  await time.increase(61); await c.checkTimeout(2);
  await expectRevert(c.checkTimeout(2), "max level");
  await c.connect(primary).acknowledge(2);
  console.log("9. Sự cố #2: tổng vi phạm =", (await c.getPlan(1)).violations.toString());

  // Sự cố #3: nhân viên xác nhận trễ trước khi keeper kịp gọi → vẫn bị ghi vi phạm (IC-08)
  const ts4 = await time.latest();
  const fall3 = await sign(device, 1, ts4, 5, dataHash);
  await c.connect(gateway).reportFall(1, ts4, 5, dataHash, fall3.sig);
  await time.increase(70);
  await c.connect(primary).acknowledge(3);
  console.log("10. Sự cố #3 xác nhận trễ: tổng vi phạm =", (await c.getPlan(1)).violations.toString());

  await expectRevert(c.settle(1), "period not ended");
  await time.increaseTo(periodEnd + 1);
  await expectRevert(c.settle(1), "period not ended"); // còn phải chờ SETTLE_DELAY = 600 s
  console.log("   pendingEvents =", (await c.getPlan(1)).pendingEvents.toString(), "(mong 0)");
  await time.increaseTo(periodEnd + 601);
  const pBefore = await ethers.provider.getBalance(provider.address);
  const fBefore = await ethers.provider.getBalance(family.address);
  await c.connect(stranger).settle(1);
  const pGain = (await ethers.provider.getBalance(provider.address)) - pBefore;
  const fGain = (await ethers.provider.getBalance(family.address)) - fBefore;
  console.log(`11. Settle: trung tâm nhận ${ethers.formatEther(pGain)} ETH, gia đình nhận ${ethers.formatEther(fGain)} ETH`);
  await expectRevert(c.settle(1), "already settled");
  console.log("Số dư contract còn lại:", ethers.formatEther(await ethers.provider.getBalance(await c.getAddress())));
  console.log("\nSMOKE TEST OK");
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
