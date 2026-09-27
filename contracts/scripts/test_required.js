// Chế độ tích hợp không được báo thành công nếu các test đang skip.
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

for (const filename of ["../../docs/test_vectors.json", "../test/signature.vector.test.js"]) {
  if (!fs.existsSync(path.resolve(__dirname, filename))) {
    console.error(`BLOCKED: thiếu đầu vào kiểm thử chữ ký bắt buộc: ${filename}`);
    process.exit(1);
  }
}

if (!fs.existsSync(path.resolve(__dirname, "../contracts/CareSLA.sol"))) {
  console.error("BLOCKED: thiếu contracts/contracts/CareSLA.sol của P1.");
  process.exit(1);
}
const result = spawnSync(process.execPath, [require.resolve("hardhat/internal/cli/cli"), "test"], {
  cwd: path.resolve(__dirname, ".."),
  stdio: "inherit",
  env: {
    ...process.env,
    REQUIRE_CARESLA: "true",
    REPORT_GAS: process.argv.includes("--gas") ? "true" : "false",
  },
});
process.exit(result.status ?? 1);
