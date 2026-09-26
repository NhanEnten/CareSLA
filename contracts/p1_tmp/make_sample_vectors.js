// Script TẠM của P1: sinh file vector MẪU đúng định dạng đề xuất (IC-14) để chạy thử
// signature.vector.test.js trong lúc chờ docs/test_vectors.json thật của P5.
// Cài đặt độc lập bằng ethers (JS). P5 cài bằng Python (web3 + eth_account), nên hai bên có thể đối chiếu chéo.
// Chạy: node p1_tmp/make_sample_vectors.js
const { ethers } = require("ethers");
const fs = require("fs");
const path = require("path");

// Khóa CHỈ ĐỂ TEST, công khai, không bao giờ dùng cho thiết bị thật
const TEST_KEY = ethers.keccak256(ethers.toUtf8Bytes("carensla test key - DO NOT USE"));
const wallet = new ethers.Wallet(TEST_KEY);
const device = wallet.address.toLowerCase();

function samplesB64() {
  // 3 mẫu × 6 số int16 little-endian: ax, ay, az, gx, gy, gz
  const vals = [100, -200, 16384, 5, -5, 0, 120, -180, 16000, 7, -3, 1, -32768, 32767, 0, 1, -1, 256];
  const buf = Buffer.alloc(vals.length * 2);
  vals.forEach((v, i) => buf.writeInt16LE(v, i * 2));
  return buf;
}

async function makeVector(name, eventType, timestamp, nonce, dataHash, extra = {}) {
  const packed = ethers.solidityPacked(
    ["address", "uint8", "uint64", "uint64", "bytes32"], [device, eventType, timestamp, nonce, dataHash]);
  const messageHash = ethers.keccak256(packed);
  const ethSigned = ethers.hashMessage(ethers.getBytes(messageHash)); // EIP-191
  const sig = await wallet.signMessage(ethers.getBytes(messageHash));
  const v = parseInt(sig.slice(-2), 16);
  return { name, eventType, timestamp, nonce, dataHash, ...extra, packed, messageHash, ethSigned, sig, v };
}

async function main() {
  const raw = samplesB64();
  const fallHash = ethers.keccak256(raw);
  const T = 2000000000; // năm 2033: ở tương lai để contract test tua giờ tới được
  const vectors = [
    await makeVector("fall_basic", 1, T, 42, fallHash, { samples_b64: raw.toString("base64") }),
    await makeVector("arrival_basic", 2, T + 30, 43, fallHash),
    await makeVector("cancel_basic", 3, T + 60, 44, ethers.ZeroHash),
    await makeVector("fall_big_nonce", 1, T + 100, 2 ** 40 + 7, fallHash), // nonce > 32 bit: bắt lỗi big-endian
  ];
  // Tìm thêm 1 FALL sao cho có cả v = 27 và v = 28
  const seen = new Set(vectors.map((x) => x.v));
  for (let n = 50; seen.size < 2; n++) {
    const x = await makeVector("fall_other_v", 1, T + 200, n, fallHash);
    if (!seen.has(x.v)) { vectors.push(x); seen.add(x.v); }
  }
  const out = {
    note: "FILE MẪU do P1 sinh bằng ethers để chạy thử. File thật là docs/test_vectors.json của P5. Khóa chỉ để test.",
    generator: "contracts/p1_tmp/make_sample_vectors.js (ethers v6)",
    privateKey: TEST_KEY,
    device,
    vectors,
  };
  const file = path.join(__dirname, "sample_test_vectors.json");
  fs.writeFileSync(file, JSON.stringify(out, null, 2) + "\n");
  console.log("Đã ghi", file, "| v:", vectors.map((x) => `${x.name}=${x.v}`).join(", "));
}
main();
