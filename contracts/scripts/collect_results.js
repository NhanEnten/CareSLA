// Thu bằng chứng chạy thật; test pending và exit code lỗi vẫn được giữ nguyên.
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { root, safeError } = require("./common");

const python = process.env.PYTHON_EXECUTABLE || path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const cli = require.resolve("hardhat/internal/cli/cli");
const checks = [
  ["hardhat --version", process.execPath, [cli, "--version"], path.join(root, "contracts")],
  ["hardhat compile", process.execPath, [cli, "compile"], path.join(root, "contracts")],
  ["hardhat test", process.execPath, [cli, "test"], path.join(root, "contracts")],
  ["test:required", process.execPath, [path.join(__dirname, "test_required.js")], path.join(root, "contracts")],
  ["Python keeper unit tests (RPC giả)", python, ["-m", "unittest", "discover", "-s", "contracts/test", "-p", "test_*.py", "-v"], root],
  ["keeper --dry-run --once", python, ["backend/keeper.py", "--dry-run", "--once"], root],
];
const results = [];
for (const [label, executable, args, cwd] of checks) {
  const result = spawnSync(executable, args, { cwd, encoding: "utf8", env: { ...process.env, PYTHONIOENCODING: "utf-8" }, timeout: 120000 });
  const output = safeError({ message: (result.stdout || "") + (result.stderr || "") + (result.error?.message || "") });
  results.push({ check: label, exitCode: result.status, output });
  console.log(`${label}: exit=${result.status}`);
}
const report = {
  capturedAt: new Date().toISOString(),
  note: "Test contract kiểm chứng luật SLA trên Hardhat; unit keeper dùng RPC giả. Dry-run chỉ đọc chain, không chứng minh keeper đã gửi tx. Đây không phải nghiệm thu E2E hoặc Sepolia.",
  contractSourcePresent: fs.existsSync(path.join(root, "contracts/contracts/CareSLA.sol")),
  node: process.version,
  results,
};
const reportDir = path.join(root, "docs/report");
fs.mkdirSync(reportDir, { recursive: true });
fs.writeFileSync(path.join(reportDir, "P2_test_results.json"), JSON.stringify(report, null, 2) + "\n");
fs.writeFileSync(path.join(reportDir, "P2_test_results.txt"), `${report.capturedAt}\n${report.note}\n\n` + results.map((r) => `${r.check} (exit=${r.exitCode})\n${r.output}`).join("\n\n"));
console.log("Đã ghi docs/report/P2_test_results.json và .txt; xem exit code từng bước.");
if (results.some((r) => r.exitCode !== 0)) process.exitCode = 1;
