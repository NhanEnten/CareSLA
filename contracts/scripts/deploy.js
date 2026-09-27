const fs = require("node:fs");
const path = require("node:path");
const hre = require("hardhat");
const { root, required, checkedNetwork, deploymentPath, safeError } = require("./common");

async function main() {
  const chainId = await checkedNetwork(hre);
  if (hre.network.name === "sepolia") required("DEPLOYER_PRIVATE_KEY");
  if (!(await hre.artifacts.artifactExists("CareSLA"))) {
    throw new Error("Thiếu artifact CareSLA; nhận CareSLA.sol từ P1 rồi chạy npm run compile.");
  }
  const [deployer] = await hre.ethers.getSigners();
  const balance = await hre.ethers.provider.getBalance(deployer.address);
  console.log(`Deployer: ${deployer.address}; balance: ${hre.ethers.formatEther(balance)} ETH`);
  if (balance === 0n) throw new Error("Ví deployer chưa có ETH trên mạng đã chọn.");
  const contract = await hre.ethers.deployContract("CareSLA");
  await contract.waitForDeployment();
  const receipt = await contract.deploymentTransaction().wait();
  const deployment = { address: await contract.getAddress(), chainId, deployBlock: receipt.blockNumber };
  const { abi } = await hre.artifacts.readArtifact("CareSLA");
  // Chỉ xuất ABI của artifact thật, không tạo ABI giả trước khi có contract P1.
  for (const destination of ["backend/abi/CareSLA.json", "dashboard/CareSLA.json"]) {
    const filename = path.join(root, destination);
    fs.mkdirSync(path.dirname(filename), { recursive: true });
    fs.writeFileSync(filename, JSON.stringify(abi, null, 2) + "\n");
  }
  fs.mkdirSync(path.join(root, "deployments"), { recursive: true });
  fs.writeFileSync(deploymentPath(hre.network.name), JSON.stringify(deployment, null, 2) + "\n");
  console.log(JSON.stringify(deployment, null, 2));
  console.log(`Deploy tx: ${receipt.hash}; gasUsed: ${receipt.gasUsed}`);
  if (hre.network.name === "sepolia") {
    console.log(`https://sepolia.etherscan.io/address/${deployment.address}`);
  }
}

if (require.main === module) main().catch((error) => { console.error(safeError(error)); process.exitCode = 1; });
module.exports = { main };
