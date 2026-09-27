const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "../..");

function required(name) {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`Thiếu ${name} trong .env tại thư mục gốc.`);
  return value;
}

async function checkedNetwork(hre) {
  const expected = { localhost: 31337n, sepolia: 11155111n }[hre.network.name];
  if (!expected) throw new Error("Dùng --network localhost hoặc --network sepolia.");
  if (hre.network.name === "sepolia") required("SEPOLIA_RPC_URL");
  const { chainId } = await hre.ethers.provider.getNetwork();
  if (chainId !== expected) throw new Error("RPC trả về chainId không đúng mạng đã chọn.");
  return Number(chainId);
}

function deploymentPath(network) {
  return path.join(root, "deployments", `${network}.json`);
}

async function readDeployment(hre) {
  const chainId = await checkedNetwork(hre);
  const filename = deploymentPath(hre.network.name);
  if (!fs.existsSync(filename)) throw new Error("Chưa có deployment; chạy deploy.js trước.");
  const deployment = JSON.parse(fs.readFileSync(filename, "utf8"));
  if (deployment.chainId !== chainId) throw new Error("Deployment không khớp chainId.");
  if ((await hre.ethers.provider.getCode(deployment.address)) === "0x") {
    throw new Error("Không có contract tại địa chỉ đã lưu; node có thể đã restart. Deploy lại.");
  }
  return deployment;
}

function parsedEvent(contract, receipt, name) {
  for (const log of receipt.logs) {
    if (log.address.toLowerCase() !== contract.target.toLowerCase()) continue;
    try {
      const parsed = contract.interface.parseLog(log);
      if (parsed?.name === name) return parsed.args;
    } catch { /* Log của contract khác hoặc không nằm trong ABI. */ }
  }
  throw new Error(`Receipt không có event ${name}.`);
}

// Không in error object: RPC URL có thể chứa API key.
function safeError(error) {
  let message = String(error.shortMessage || error.message || "Lỗi không xác định");
  message = message.replace(/https?:\/\/\S+/g, "[RPC_URL]");
  for (const [name, value] of Object.entries(process.env)) {
    if (/PRIVATE_KEY|TOKEN|API_KEY|RPC_URL/.test(name) && value) {
      message = message.split(value).join(`[${name}]`);
    }
  }
  return message;
}

module.exports = { root, required, checkedNetwork, deploymentPath, readDeployment, parsedEvent, safeError };
