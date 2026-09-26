// Test vector chữ ký (P1). Chứng minh contract băm và kiểm chữ ký KHỚP với bộ vector chung
// mà ESP32 (P3) và gateway (P5) cũng phải khớp. Định dạng file: docs/interface_changes.md, IC-14.
//
// Chạy với file thật của P5:   npx hardhat test test/signature.vector.test.js
// Chạy với file mẫu của P1:    TEST_VECTORS=p1_tmp/sample_test_vectors.json npx hardhat test test/signature.vector.test.js
const fs = require("fs");
const path = require("path");
const { expect } = require("chai");
const { ethers } = require("hardhat");
const { loadFixture, time } = require("@nomicfoundation/hardhat-network-helpers");

const VECTOR_FILE = process.env.TEST_VECTORS
  ? path.resolve(process.env.TEST_VECTORS)
  : path.join(__dirname, "..", "..", "docs", "test_vectors.json");

const FALL = 1;
const ARRIVAL = 2;
const CANCEL = 3;
// Bậc của đường cong secp256k1. Chữ ký hợp lệ với OpenZeppelin phải có s <= N/2 ("low-s")
const SECP256K1_N = 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141n;

// Ghép 69 byte giống hệt abi.encodePacked trong contract
function packEvent(device, eventType, ts, nonce, dataHash) {
  return ethers.solidityPacked(
    ["address", "uint8", "uint64", "uint64", "bytes32"],
    [device, eventType, ts, nonce, dataHash]
  );
}

// Sửa 1 byte cuối của dataHash để tạo gói "bị giả mạo"
function tamper(hex) {
  const last = parseInt(hex.slice(-2), 16) ^ 0x01;
  return hex.slice(0, -2) + last.toString(16).padStart(2, "0");
}

async function deployFixture() {
  const [family, provider, primary, backup, gateway] = await ethers.getSigners();
  const c = await ethers.deployContract("CareSLA");
  return { c, family, provider, primary, backup, gateway };
}

// Tạo hợp đồng dùng thiết bị của vector, có 1 ca phủ quanh thời điểm ts
async function setupPlan(fx, device, ts) {
  const { c, family, provider, primary, backup } = fx;
  const now = await time.latest();
  if (now >= ts - 60) {
    throw new Error(`timestamp của vector (${ts}) phải ở tương lai so với chain (${now}); xem IC-14`);
  }
  await c.connect(family).createCarePlan(provider.address, device, 60, 1n, ts + 3600, { value: ethers.parseEther("1") });
  const planId = await c.planCount();
  await c.connect(provider).acceptPlan(planId);
  await c.connect(provider).commitShift(planId, ts - 60, ts + 3000, primary.address, backup.address);
  return planId;
}

const fileExists = fs.existsSync(VECTOR_FILE);
const data = fileExists ? JSON.parse(fs.readFileSync(VECTOR_FILE, "utf8")) : { vectors: [] };
const vectors = data.vectors || [];

(fileExists ? describe : describe.skip)(`Test vector chữ ký (${path.basename(VECTOR_FILE)})`, function () {
  const device = (data.device || "").toLowerCase();

  it("file có device, privateKey và đủ 3 loại FALL / ARRIVAL / CANCEL", function () {
    expect(ethers.isAddress(device), "device không phải địa chỉ hợp lệ").to.equal(true);
    expect(new ethers.Wallet(data.privateKey).address.toLowerCase(), "privateKey không khớp device").to.equal(device);
    const types = new Set(vectors.map((v) => v.eventType));
    expect([...types].sort()).to.include.members([FALL, ARRIVAL, CANCEL]);
    const vs = new Set(vectors.map((v) => v.v));
    if (vs.size < 2) console.warn("      ⚠️ Chỉ có v =", [...vs], "- nên có cả v = 27 và v = 28 (IC-14)");
  });

  for (const vec of vectors) {
    describe(`${vec.name} (eventType ${vec.eventType}, nonce ${vec.nonce})`, function () {
      it("packed đúng 69 byte và khớp", function () {
        const packed = packEvent(device, vec.eventType, vec.timestamp, vec.nonce, vec.dataHash);
        expect(ethers.dataLength(packed)).to.equal(69);
        expect(packed).to.equal(vec.packed.toLowerCase());
      });

      it("hashEvent() của contract khớp messageHash", async function () {
        const { c } = await loadFixture(deployFixture);
        const onchain = await c.hashEvent(device, vec.eventType, vec.timestamp, vec.nonce, vec.dataHash);
        expect(onchain).to.equal(vec.messageHash.toLowerCase());
        expect(ethers.keccak256(vec.packed)).to.equal(vec.messageHash.toLowerCase());
      });

      it("ethSigned khớp tiền tố EIP-191", function () {
        expect(ethers.hashMessage(ethers.getBytes(vec.messageHash))).to.equal(vec.ethSigned.toLowerCase());
      });

      it("sig 65 byte, v = 27/28, low-s, khôi phục ra đúng device", function () {
        expect(ethers.dataLength(vec.sig)).to.equal(65);
        const s = BigInt("0x" + vec.sig.slice(66, 130));
        const v = parseInt(vec.sig.slice(130, 132), 16);
        expect([27, 28]).to.include(v);
        expect(s <= SECP256K1_N / 2n, "s cao: OpenZeppelin sẽ từ chối, cần chuẩn hóa low-s").to.equal(true);
        expect(ethers.recoverAddress(vec.ethSigned, vec.sig).toLowerCase()).to.equal(device);
      });

      if (vec.samples_b64) {
        it("dataHash = keccak256(bytes thô của samples_b64)", function () {
          const raw = Buffer.from(vec.samples_b64, "base64");
          expect(raw.length % 12, "mỗi mẫu phải là 6 × int16 = 12 byte").to.equal(0);
          expect(ethers.keccak256(raw)).to.equal(vec.dataHash.toLowerCase());
        });
      }

      if (vec.eventType === CANCEL) {
        it("CANCEL có dataHash = 0", function () {
          expect(vec.dataHash).to.equal(ethers.ZeroHash);
        });
      }

      if (vec.eventType === FALL) {
        it("reportFall chấp nhận chữ ký", async function () {
          const fx = await loadFixture(deployFixture);
          const planId = await setupPlan(fx, device, vec.timestamp);
          await time.setNextBlockTimestamp(vec.timestamp + 1);
          await expect(fx.c.connect(fx.gateway).reportFall(planId, vec.timestamp, vec.nonce, vec.dataHash, vec.sig))
            .to.emit(fx.c, "FallReported");
          expect(await fx.c.lastNonce(planId)).to.equal(BigInt(vec.nonce));
        });

        it("sửa 1 byte dataHash thì bị từ chối (bad sig)", async function () {
          const fx = await loadFixture(deployFixture);
          const planId = await setupPlan(fx, device, vec.timestamp);
          await time.setNextBlockTimestamp(vec.timestamp + 1);
          await expect(fx.c.reportFall(planId, vec.timestamp, vec.nonce, tamper(vec.dataHash), vec.sig))
            .to.be.revertedWith("bad sig");
        });
      }

      if (vec.eventType === ARRIVAL) {
        it("confirmArrival chấp nhận chữ ký (sau FALL có nonce nhỏ hơn)", async function () {
          // Chọn FALL có nonce lớn nhất nhỏ hơn nonce của ARRIVAL, và ts không muộn hơn
          const fall = vectors
            .filter((f) => f.eventType === FALL && f.nonce < vec.nonce && f.timestamp <= vec.timestamp)
            .sort((a, b) => b.nonce - a.nonce)[0];
          expect(fall, "cần một vector FALL có nonce < và timestamp <= ARRIVAL (IC-14)").to.not.equal(undefined);

          const fx = await loadFixture(deployFixture);
          const planId = await setupPlan(fx, device, fall.timestamp);
          await time.setNextBlockTimestamp(fall.timestamp + 1);
          await fx.c.reportFall(planId, fall.timestamp, fall.nonce, fall.dataHash, fall.sig);
          const eventId = await fx.c.eventCount();
          await time.setNextBlockTimestamp(Math.max(vec.timestamp, fall.timestamp + 1) + 1);
          await expect(fx.c.confirmArrival(eventId, vec.timestamp, vec.nonce, vec.dataHash, vec.sig))
            .to.emit(fx.c, "Arrived");
        });
      }
    });
  }
});

if (!fileExists) {
  describe("Test vector chữ ký", function () {
    it.skip(`chưa có ${VECTOR_FILE} (P5 tạo bằng tools/make_test_vector.py)`, function () {});
  });
}
