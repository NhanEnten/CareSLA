// Hồi quy các giao diện IC-01 -> IC-15 đã chốt ngày 27/09/2026.
const { expect } = require("chai");
const { ethers } = require("hardhat");
const { loadFixture, time } = require("@nomicfoundation/hardhat-network-helpers");
const { signEvent } = require("./helpers/events");
const { parsedEvent } = require("../scripts/common");

const DEPOSIT = ethers.parseEther("0.01");
const PENALTY = ethers.parseEther("0.002");
const DATA = ethers.keccak256("0x010002000300040005000600");

async function fixture() {
  const [family, provider, primary, backup, relayer] = await ethers.getSigners();
  const device = ethers.Wallet.createRandom();
  const contract = await ethers.deployContract("CareSLA");
  const start = (await time.latest()) + 30;
  const end = start + 300;
  await contract.createCarePlan(provider.address, device.address, 60, PENALTY, end, { value: DEPOSIT });
  const planId = await contract.planCount();
  await contract.connect(provider).acceptPlan(planId);
  await contract.connect(provider).commitShift(planId, start, end, primary.address, backup.address);
  await time.increaseTo(start);
  return { contract, family, provider, primary, backup, relayer, device, planId, start, end };
}

async function fall(f, nonce = 1n) {
  const ts = await time.latest();
  const { sig } = await signEvent(f.device, 1, ts, nonce, DATA);
  const receipt = await (await f.contract.reportFall(f.planId, ts, nonce, DATA, sig)).wait();
  return parsedEvent(f.contract, receipt, "FallReported");
}

describe("P2 - hồi quy giao diện đã chốt", function () {
  it("IC-01: getter trả đúng trường, ID bắt đầu từ 1, pendingEvents tăng", async function () {
    const f = await loadFixture(fixture);
    const e = await fall(f);
    expect(f.planId).to.equal(1n);
    expect(e.eventId).to.equal(1n);
    const record = await f.contract.getFallEvent(e.eventId);
    expect(record.length).to.equal(12);
    expect(record.planId).to.equal(f.planId);
    expect(record.primary).to.equal(f.primary.address);
    expect(record.deadline).to.equal(e.deadline);
    expect(record.level).to.equal(0n);
    expect(record.status).to.equal(0n);
    expect((await f.contract.getPlan(f.planId)).pendingEvents).to.equal(1n);
  });

  it("IC-12: settle bị chặn trước và đúng periodEnd + 600, sau đó mới được", async function () {
    const f = await loadFixture(fixture);
    for (const timestamp of [f.end + 1, f.end + 599, f.end + 600]) {
      await time.setNextBlockTimestamp(timestamp);
      await expect(f.contract.settle(f.planId)).to.be.revertedWith("period not ended");
    }
    await time.setNextBlockTimestamp(f.end + 601);
    await expect(f.contract.connect(f.relayer).settle(f.planId))
      .to.changeEtherBalances([f.provider, f.family, f.contract], [DEPOSIT, 0n, -DEPOSIT]);
  });

  it("IC-12/04: settle chờ sự cố treo, cấp 2 xóa pending và deadline bằng 0", async function () {
    const f = await loadFixture(fixture);
    const e = await fall(f);
    await time.increaseTo(f.end + 601);
    await expect(f.contract.settle(f.planId)).to.be.revertedWith("pending events");
    await f.contract.checkTimeout(e.eventId);
    const next = await f.contract.getFallEvent(e.eventId);
    expect((await f.contract.getPlan(f.planId)).pendingEvents).to.equal(1n);
    await time.increaseTo(next.deadline + 1n);
    await f.contract.checkTimeout(e.eventId);
    const last = await f.contract.getFallEvent(e.eventId);
    expect(last.level).to.equal(2n);
    expect(last.deadline).to.equal(0n);
    expect((await f.contract.getPlan(f.planId)).pendingEvents).to.equal(0n);
    await expect(f.contract.checkTimeout(e.eventId)).to.be.revertedWith("max level");
    await expect(f.contract.settle(f.planId)).to.emit(f.contract, "Settled")
      .withArgs(f.planId, DEPOSIT - 2n * PENALTY, 2n * PENALTY);
  });

  it("IC-11: plan bù nhìn không tiêu nonce của plan thật dùng cùng thiết bị", async function () {
    const f = await loadFixture(fixture);
    await f.contract.connect(f.relayer).createCarePlan(f.provider.address, f.device.address, 60, PENALTY, f.end, { value: DEPOSIT });
    const decoy = await f.contract.planCount();
    await f.contract.connect(f.provider).acceptPlan(decoy);
    const start = (await time.latest()) + 10;
    await f.contract.connect(f.provider).commitShift(decoy, start, f.end, f.primary.address, f.backup.address);
    await time.increaseTo(start);
    const ts = await time.latest();
    const { sig } = await signEvent(f.device, 1, ts, 42, DATA);
    await f.contract.reportFall(decoy, ts, 42, DATA, sig);
    await expect(f.contract.reportFall(f.planId, ts, 42, DATA, sig)).to.emit(f.contract, "FallReported");
    expect(await f.contract.lastNonce(decoy)).to.equal(42n);
    expect(await f.contract.lastNonce(f.planId)).to.equal(42n);
    await expect(f.contract.reportFall(f.planId, ts, 42, DATA, sig)).to.be.revertedWith("old nonce");
  });

  it("IC-12: FALL có ts sau kỳ bị từ chối", async function () {
    const f = await loadFixture(fixture);
    await time.increaseTo(f.end + 1);
    const ts = await time.latest();
    const { sig } = await signEvent(f.device, 1, ts, 1, DATA);
    await expect(f.contract.reportFall(f.planId, ts, 1, DATA, sig)).to.be.revertedWith("ts after period");
  });

  it("IC-05: plan chưa accept hoàn toàn bộ cho family sau thời gian chờ", async function () {
    const f = await loadFixture(fixture);
    await f.contract.createCarePlan(f.provider.address, f.device.address, 60, PENALTY, f.end, { value: DEPOSIT });
    const planId = await f.contract.planCount();
    await time.increaseTo(f.end + 601);
    await expect(f.contract.connect(f.relayer).settle(planId))
      .to.changeEtherBalances([f.family, f.provider, f.contract], [DEPOSIT, 0n, -DEPOSIT]);
  });

  it("IC-06: từ chối ca chồng giờ và primary trùng backup", async function () {
    const f = await loadFixture(fixture);
    const start = (await time.latest()) + 10;
    await expect(f.contract.connect(f.provider).commitShift(f.planId, start, f.end, f.primary.address, f.backup.address))
      .to.be.revertedWith("overlap");
    await expect(f.contract.connect(f.provider).commitShift(f.planId, start, f.end, f.primary.address, f.primary.address))
      .to.be.revertedWith("primary == backup");
  });

  it("IC-08: nhận trễ khi keeper chưa gọi vẫn bị phạt và hết pending", async function () {
    const f = await loadFixture(fixture);
    const e = await fall(f);
    await time.increaseTo(e.deadline + 1n);
    await expect(f.contract.connect(f.primary).acknowledge(e.eventId))
      .to.emit(f.contract, "SlaViolation").withArgs(e.eventId, f.planId, 1n);
    const plan = await f.contract.getPlan(f.planId);
    expect(plan.violations).to.equal(1n);
    expect(plan.pendingEvents).to.equal(0n);
  });

  it("IC-02/07/08: ARRIVAL trước acknowledge, nonce nhảy số, đến trễ vẫn phạt", async function () {
    const f = await loadFixture(fixture);
    const e = await fall(f, 42n);
    await time.increaseTo(e.deadline + 1n);
    const ts = await time.latest();
    const { sig } = await signEvent(f.device, 2, ts, 44, DATA);
    const tx = await f.contract.confirmArrival(e.eventId, ts, 44, DATA, sig);
    await expect(tx).to.emit(f.contract, "SlaViolation").withArgs(e.eventId, f.planId, 1n);
    const block = await ethers.provider.getBlock((await tx.wait()).blockNumber);
    const record = await f.contract.getFallEvent(e.eventId);
    expect(record.status).to.equal(2n);
    expect(record.arrivedAt).to.equal(BigInt(block.timestamp));
    expect(await f.contract.lastNonce(f.planId)).to.equal(44n);
    expect((await f.contract.getPlan(f.planId)).pendingEvents).to.equal(0n);
  });
});
