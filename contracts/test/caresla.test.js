const fs = require("node:fs");
const path = require("node:path");
const { expect } = require("chai");
const { ethers } = require("hardhat");
const { loadFixture, time } = require("@nomicfoundation/hardhat-network-helpers");
const { anyValue } = require("@nomicfoundation/hardhat-chai-matchers/withArgs");
const { signEvent } = require("./helpers/events");
const { parsedEvent } = require("../scripts/common");

const artifactPath = path.resolve(__dirname, "../artifacts/contracts/CareSLA.sol/CareSLA.json");
const artifact = fs.existsSync(artifactPath) ? JSON.parse(fs.readFileSync(artifactPath, "utf8")) : { abi: [] };
const functions = new Set(artifact.abi.filter((item) => item.type === "function").map((item) => item.name));
const PLAN = ["createCarePlan", "acceptPlan", "commitShift"];
const FALL = [...PLAN, "reportFall"];
const TIMEOUT = [...FALL, "checkTimeout"];
const DEPOSIT = ethers.parseEther("0.01");
const PENALTY = ethers.parseEther("0.002");
const SLA = 60n;
// Một mẫu ax,ay,az,gx,gy,gz int16 LE để dataHash có nguồn dữ liệu thô thật.
const DATA_HASH = ethers.keccak256("0x010002000300040005000600");

function scenario(name, required, run) {
  const missing = required.filter((method) => !functions.has(method));
  if (missing.length && process.env.REQUIRE_CARESLA === "true") {
    it(name, function () { throw new Error(`P1 chưa cung cấp: ${missing.join(", ")}`); });
  } else if (missing.length) {
    it.skip(`${name} [chờ P1: ${missing.join(", ")}]`, run);
  } else {
    it(name, run);
  }
}

async function deployedFixture() {
  const [family, provider, primary, backup, stranger] = await ethers.getSigners();
  const device = ethers.Wallet.createRandom();
  const contract = await ethers.deployContract("CareSLA");
  await contract.waitForDeployment();
  return { contract, family, provider, primary, backup, stranger, device };
}

async function acceptedFixture() {
  const f = await deployedFixture();
  const now = await time.latest();
  const periodEnd = now + 7200;
  const receipt = await (await f.contract.createCarePlan(
    f.provider.address, f.device.address, SLA, PENALTY, periodEnd, { value: DEPOSIT },
  )).wait();
  const { planId } = parsedEvent(f.contract, receipt, "PlanCreated");
  await f.contract.connect(f.provider).acceptPlan(planId);
  return { ...f, planId, now, periodEnd };
}

async function planFixture() {
  const f = await acceptedFixture();
  const { now, periodEnd, planId } = f;
  const start = now + 30;
  await f.contract.connect(f.provider).commitShift(planId, start, periodEnd, f.primary.address, f.backup.address);
  await time.increaseTo(start);
  return { ...f, planId, start, periodEnd };
}

async function sendFall(f, nonce = 1n, timestamp) {
  const ts = timestamp ?? await time.latest();
  const { sig } = await signEvent(f.device, 1, ts, nonce, DATA_HASH);
  const tx = await f.contract.connect(f.stranger).reportFall(f.planId, ts, nonce, DATA_HASH, sig);
  const receipt = await tx.wait();
  const reported = parsedEvent(f.contract, receipt, "FallReported");
  return { tx, receipt, reported, eventId: reported.eventId, ts, nonce, sig };
}

async function fallFixture() {
  const f = await planFixture();
  return { ...f, fall: await sendFall(f) };
}

async function escalateTwice(f) {
  await time.increaseTo(f.fall.reported.deadline + 1n);
  const first = await (await f.contract.connect(f.stranger).checkTimeout(f.fall.eventId)).wait();
  const next = parsedEvent(f.contract, first, "Escalated").newDeadline;
  await time.increaseTo(next + 1n);
  const second = await (await f.contract.connect(f.stranger).checkTimeout(f.fall.eventId)).wait();
  return { first, second };
}

describe("P2 CareSLA - yêu cầu AGENTS.md 6.3", function () {
  scenario("01 tạo/accept plan, giữ đúng tiền ký quỹ", ["createCarePlan", "acceptPlan"], async function () {
    const f = await loadFixture(deployedFixture);
    const end = (await time.latest()) + 7200;
    const tx = await f.contract.createCarePlan(f.provider.address, f.device.address, SLA, PENALTY, end, { value: DEPOSIT });
    await expect(tx).to.emit(f.contract, "PlanCreated").withArgs(anyValue, f.family.address, f.provider.address, f.device.address, DEPOSIT);
    const { planId } = parsedEvent(f.contract, await tx.wait(), "PlanCreated");
    expect(await ethers.provider.getBalance(f.contract.target)).to.equal(DEPOSIT);
    await expect(f.contract.connect(f.provider).acceptPlan(planId)).to.emit(f.contract, "PlanAccepted").withArgs(planId);
  });

  scenario("02 không cam kết ca đã bắt đầu", PLAN, async function () {
    const f = await loadFixture(acceptedFixture);
    await expect(f.contract.connect(f.provider).commitShift(f.planId, await time.latest(), f.periodEnd, f.primary.address, f.backup.address)).to.be.reverted;
  });

  scenario("03 chỉ provider cam kết ca", PLAN, async function () {
    const f = await loadFixture(acceptedFixture);
    const start = (await time.latest()) + 30;
    // Ca còn trống, thời gian hợp lệ: chỉ quyền người gọi là sai.
    await expect(f.contract.connect(f.stranger).commitShift(f.planId, start, f.periodEnd, f.primary.address, f.backup.address)).to.be.reverted;
    await expect(f.contract.connect(f.provider).commitShift(f.planId, start, f.periodEnd, f.primary.address, f.backup.address)).to.emit(f.contract, "ShiftCommitted");
  });

  scenario("04 FALL hợp lệ từ relayer bất kỳ, đúng primary và deadline theo block", FALL, async function () {
    const f = await loadFixture(planFixture);
    const fall = await sendFall(f);
    const block = await ethers.provider.getBlock(fall.receipt.blockNumber);
    await expect(fall.tx).to.emit(f.contract, "FallReported").withArgs(fall.eventId, f.planId, DATA_HASH, f.primary.address, BigInt(block.timestamp) + SLA);
  });

  scenario("05 từ chối chữ ký không phải thiết bị", FALL, async function () {
    const f = await loadFixture(planFixture);
    const ts = await time.latest();
    const { sig } = await signEvent(ethers.Wallet.createRandom(), 1, ts, 1, DATA_HASH, f.device.address);
    await expect(f.contract.reportFall(f.planId, ts, 1, DATA_HASH, sig)).to.be.reverted;
  });

  scenario("06 từ chối nonce đã dùng lại", FALL, async function () {
    const f = await loadFixture(fallFixture);
    await expect(f.contract.reportFall(f.planId, f.fall.ts, f.fall.nonce, DATA_HASH, f.fall.sig)).to.be.reverted;
  });

  scenario("07 từ chối timestamp cũ hơn 600 giây dù vẫn trong ca", FALL, async function () {
    const f = await loadFixture(planFixture);
    await time.increase(700);
    const ts = (await time.latest()) - 601;
    expect(ts).to.be.greaterThan(f.start);
    const { sig } = await signEvent(f.device, 1, ts, 1, DATA_HASH);
    await expect(f.contract.reportFall(f.planId, ts, 1, DATA_HASH, sig)).to.be.reverted;
  });

  scenario("08 acknowledge đúng hạn không bị phạt khi settle", [...TIMEOUT, "acknowledge", "settle"], async function () {
    const f = await loadFixture(fallFixture);
    await expect(f.contract.connect(f.primary).acknowledge(f.fall.eventId)).to.emit(f.contract, "Acknowledged").withArgs(f.fall.eventId, f.primary.address, anyValue);
    await time.increaseTo(f.fall.reported.deadline + 1n);
    await expect(f.contract.checkTimeout(f.fall.eventId)).to.be.revertedWith("not open");
    await time.increaseTo(f.periodEnd + 601);
    await expect(f.contract.connect(f.stranger).settle(f.planId)).to.emit(f.contract, "Settled").withArgs(f.planId, DEPOSIT, 0n);
  });

  scenario("09a timeout lần 1 chuyển backup và ghi đúng 1 vi phạm", TIMEOUT, async function () {
    const f = await loadFixture(fallFixture);
    await time.increaseTo(f.fall.reported.deadline + 1n);
    const tx = await f.contract.connect(f.stranger).checkTimeout(f.fall.eventId);
    const receipt = await tx.wait();
    const block = await ethers.provider.getBlock(receipt.blockNumber);
    await expect(tx).to.emit(f.contract, "Escalated").withArgs(f.fall.eventId, 1, f.backup.address, BigInt(block.timestamp) + SLA);
    await expect(tx).to.emit(f.contract, "SlaViolation").withArgs(f.fall.eventId, f.planId, 1);
  });

  scenario("09b timeout lần 2 chuyển gia đình và tổng 2 vi phạm", TIMEOUT, async function () {
    const f = await loadFixture(fallFixture);
    const { second } = await escalateTwice(f);
    const escalation = parsedEvent(f.contract, second, "Escalated");
    expect(escalation.level).to.equal(2n);
    expect(escalation.to).to.equal(f.family.address);
    expect(parsedEvent(f.contract, second, "SlaViolation").totalViolations).to.equal(2n);
  });

  scenario("10a checkTimeout trước hạn bị revert", TIMEOUT, async function () {
    const f = await loadFixture(fallFixture);
    await expect(f.contract.checkTimeout(f.fall.eventId)).to.be.reverted;
  });

  scenario("10b lặp timeout ngay sau chuyển cấp không tăng vi phạm", TIMEOUT, async function () {
    const f = await loadFixture(fallFixture);
    await time.increaseTo(f.fall.reported.deadline + 1n);
    await f.contract.checkTimeout(f.fall.eventId);
    await expect(f.contract.checkTimeout(f.fall.eventId)).to.be.reverted;
    const violations = await f.contract.queryFilter(f.contract.filters.SlaViolation(f.fall.eventId));
    expect(violations).to.have.length(1);
  });

  scenario("10c dừng tại cấp 2, không ghi thêm tiền phạt", [...TIMEOUT, "settle"], async function () {
    const f = await loadFixture(fallFixture);
    await escalateTwice(f);
    await time.increase(180);
    await expect(f.contract.checkTimeout(f.fall.eventId)).to.be.revertedWith("max level");
    const violations = await f.contract.queryFilter(f.contract.filters.SlaViolation(f.fall.eventId));
    expect(violations).to.have.length(2);
    await time.increaseTo(f.periodEnd + 601);
    await expect(f.contract.connect(f.stranger).settle(f.planId)).to.emit(f.contract, "Settled").withArgs(f.planId, DEPOSIT - 2n * PENALTY, 2n * PENALTY);
  });

  scenario("11 người lạ không được acknowledge", [...FALL, "acknowledge"], async function () {
    const f = await loadFixture(fallFixture);
    await expect(f.contract.connect(f.stranger).acknowledge(f.fall.eventId)).to.be.reverted;
  });

  scenario("12 ARRIVAL chữ ký hợp lệ phát Arrived", [...FALL, "confirmArrival"], async function () {
    const f = await loadFixture(fallFixture);
    await time.increase(3);
    const ts = await time.latest();
    const { sig } = await signEvent(f.device, 2, ts, 2, DATA_HASH);
    await expect(f.contract.connect(f.stranger).confirmArrival(f.fall.eventId, ts, 2, DATA_HASH, sig)).to.emit(f.contract, "Arrived").withArgs(f.fall.eventId, anyValue);
  });

  scenario("13a không settle trước periodEnd", [...PLAN, "settle"], async function () {
    const f = await loadFixture(planFixture);
    await expect(f.contract.settle(f.planId)).to.be.reverted;
  });

  scenario("13b settle trả ETH đúng hai bên, chỉ một lần", [...TIMEOUT, "settle"], async function () {
    const f = await loadFixture(fallFixture);
    await escalateTwice(f);
    await time.increaseTo(f.periodEnd + 601);
    const tx = await f.contract.connect(f.stranger).settle(f.planId);
    await expect(tx).to.changeEtherBalances([f.provider, f.family, f.contract], [DEPOSIT - PENALTY * 2n, PENALTY * 2n, -DEPOSIT]);
    await expect(tx).to.emit(f.contract, "Settled").withArgs(f.planId, DEPOSIT - PENALTY * 2n, PENALTY * 2n);
    await expect(f.contract.settle(f.planId)).to.be.reverted;
  });

  scenario("14 tiền phạt bị chặn ở tiền ký quỹ", [...TIMEOUT, "acknowledge", "confirmArrival", "settle"], async function () {
    const f = await loadFixture(planFixture);
    // 3 sự cố x 2 vi phạm x 0.002 ETH = 0.012 ETH > ký quỹ 0.01 ETH.
    for (let i = 0; i < 3; i++) {
      f.fall = await sendFall(f, BigInt(i * 2 + 1));
      await escalateTwice(f);
      await f.contract.connect(f.primary).acknowledge(f.fall.eventId);
      const ts = await time.latest();
      const nonce = BigInt(i * 2 + 2);
      const { sig } = await signEvent(f.device, 2, ts, nonce, DATA_HASH);
      await f.contract.confirmArrival(f.fall.eventId, ts, nonce, DATA_HASH, sig);
    }
    await time.increaseTo(f.periodEnd + 601);
    const tx = await f.contract.connect(f.stranger).settle(f.planId);
    await expect(tx).to.emit(f.contract, "Settled").withArgs(f.planId, 0n, DEPOSIT);
    await expect(tx).to.changeEtherBalances([f.provider, f.family, f.contract], [0n, DEPOSIT, -DEPOSIT]);
  });

  scenario("15 hashEvent khớp helper ethers v6", ["hashEvent"], async function () {
    const f = await loadFixture(deployedFixture);
    const { messageHash } = await signEvent(f.device, 1, 1760000000, 42, DATA_HASH);
    expect(await f.contract.hashEvent(f.device.address, 1, 1760000000, 42, DATA_HASH)).to.equal(messageHash);
  });

  scenario("16 từ chối FALL có timestamp tương lai quá 60 giây", FALL, async function () {
    const f = await loadFixture(planFixture);
    const ts = (await time.latest()) + 120;
    const { sig } = await signEvent(f.device, 1, ts, 1, DATA_HASH);
    await expect(f.contract.reportFall(f.planId, ts, 1, DATA_HASH, sig)).to.be.reverted;
  });

  scenario("17 FALL không có ca trực bị từ chối", FALL, async function () {
    const f = await loadFixture(deployedFixture);
    const ts = await time.latest();
    const receipt = await (await f.contract.createCarePlan(f.provider.address, f.device.address, SLA, PENALTY, ts + 7200, { value: DEPOSIT })).wait();
    const { planId } = parsedEvent(f.contract, receipt, "PlanCreated");
    await f.contract.connect(f.provider).acceptPlan(planId);
    const { sig } = await signEvent(f.device, 1, ts, 1, DATA_HASH);
    await expect(f.contract.reportFall(planId, ts, 1, DATA_HASH, sig)).to.be.reverted;
  });

  scenario("18 primary và backup acknowledge được ở mọi cấp; giữ nguyên phạt", [...TIMEOUT, "acknowledge", "settle"], async function () {
    for (const role of ["primary", "backup"]) {
      for (let level = 0; level <= 2; level++) {
        const f = await loadFixture(fallFixture);
        if (level === 2) await escalateTwice(f);
        if (level === 1) {
          await time.increaseTo(f.fall.reported.deadline + 1n);
          await f.contract.checkTimeout(f.fall.eventId);
        }
        await expect(f.contract.connect(f[role]).acknowledge(f.fall.eventId)).to.emit(f.contract, "Acknowledged").withArgs(f.fall.eventId, f[role].address, anyValue);
        await time.increaseTo(f.periodEnd + 601);
        await expect(f.contract.connect(f.stranger).settle(f.planId)).to.emit(f.contract, "Settled").withArgs(f.planId, DEPOSIT - BigInt(level) * PENALTY, BigInt(level) * PENALTY);
      }
    }
  });

  scenario("19 không dùng chữ ký FALL làm ARRIVAL", [...FALL, "confirmArrival"], async function () {
    const f = await loadFixture(fallFixture);
    const ts = await time.latest();
    const { sig } = await signEvent(f.device, 1, ts, 2, DATA_HASH);
    await expect(f.contract.confirmArrival(f.fall.eventId, ts, 2, DATA_HASH, sig)).to.be.reverted;
  });

  scenario("20 ARRIVAL không được dùng nonce FALL cũ", [...FALL, "confirmArrival"], async function () {
    const f = await loadFixture(fallFixture);
    const ts = await time.latest();
    const { sig } = await signEvent(f.device, 2, ts, 1, DATA_HASH);
    await expect(f.contract.confirmArrival(f.fall.eventId, ts, 1, DATA_HASH, sig)).to.be.reverted;
  });

  scenario("21 eventCount tăng đúng một và có thể đọc getFallEvent/getPlan", [...FALL, "eventCount", "getFallEvent", "getPlan"], async function () {
    const f = await loadFixture(planFixture);
    const before = await f.contract.eventCount();
    const fall = await sendFall(f);
    expect(await f.contract.eventCount()).to.equal(before + 1n);
    expect(await f.contract.getFallEvent(fall.eventId)).not.to.equal(undefined);
    expect(await f.contract.getPlan(f.planId)).not.to.equal(undefined);
  });

  scenario("22 không thay được người trực bằng ca hồi tố", [...PLAN, "getOnDuty"], async function () {
    const f = await loadFixture(planFixture);
    const before = await f.contract.getOnDuty(f.planId, f.start);
    await expect(f.contract.connect(f.provider).commitShift(f.planId, f.start, f.periodEnd, f.stranger.address, f.family.address)).to.be.reverted;
    const after = await f.contract.getOnDuty(f.planId, f.start);
    expect(Array.from(after)).to.deep.equal(Array.from(before));
    expect(after[0]).to.equal(f.primary.address);
    expect(after[1]).to.equal(f.backup.address);
  });

  scenario("23 tối đa 20 ca trong một plan", PLAN, async function () {
    const f = await loadFixture(deployedFixture);
    const start = (await time.latest()) + 100;
    const receipt = await (await f.contract.createCarePlan(f.provider.address, f.device.address, SLA, PENALTY, start + 7200, { value: DEPOSIT })).wait();
    const { planId } = parsedEvent(f.contract, receipt, "PlanCreated");
    await f.contract.connect(f.provider).acceptPlan(planId);
    for (let i = 0; i < 20; i++) {
      await f.contract.connect(f.provider).commitShift(planId, start + i * 100, start + (i + 1) * 100, f.primary.address, f.backup.address);
    }
    await expect(f.contract.connect(f.provider).commitShift(planId, start + 2000, start + 2100, f.primary.address, f.backup.address)).to.be.reverted;
  });

  scenario("24 checkTimeout đúng deadline vẫn phải revert", TIMEOUT, async function () {
    const f = await loadFixture(fallFixture);
    await time.setNextBlockTimestamp(f.fall.reported.deadline);
    await expect(f.contract.checkTimeout(f.fall.eventId)).to.be.reverted;
  });

  scenario("25 chỉ provider được accept plan", ["createCarePlan", "acceptPlan"], async function () {
    const f = await loadFixture(deployedFixture);
    const end = (await time.latest()) + 7200;
    const receipt = await (await f.contract.createCarePlan(f.provider.address, f.device.address, SLA, PENALTY, end, { value: DEPOSIT })).wait();
    const { planId } = parsedEvent(f.contract, receipt, "PlanCreated");
    await expect(f.contract.connect(f.stranger).acceptPlan(planId)).to.be.reverted;
    await expect(f.contract.connect(f.provider).acceptPlan(planId)).to.emit(f.contract, "PlanAccepted");
  });
});
