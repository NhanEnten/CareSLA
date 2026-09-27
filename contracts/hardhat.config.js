const path = require("node:path");
require("dotenv").config({ path: path.resolve(__dirname, "../.env") });
require("@nomicfoundation/hardhat-toolbox");
require("./scripts/demo_task");
const { subtask } = require("hardhat/config");
const { TASK_COMPILE_SOLIDITY_GET_SOLC_BUILD } = require("hardhat/builtin-tasks/task-names");

// Dùng compiler đã khóa trong npm, không phải tải lại compiler lúc demo.
subtask(TASK_COMPILE_SOLIDITY_GET_SOLC_BUILD).setAction(async ({ solcVersion }, hre, runSuper) => {
  if (solcVersion !== "0.8.24") return runSuper();
  return {
    compilerPath: require.resolve("solc/soljson.js"),
    isSolcJs: true,
    version: solcVersion,
    longVersion: require("solc").version(),
  };
});

module.exports = {
  solidity: {
    version: "0.8.24",
    // Cancun cho MCOPY của OZ 5.6; viaIR tránh stack too deep ở getter 12 trường của P1.
    settings: { optimizer: { enabled: true, runs: 200 }, viaIR: true, evmVersion: "cancun" },
  },
  networks: {
    hardhat: {
      chainId: 31337,
      // Node demo cần block mới dù không có tx để thời gian SLA tiếp tục chạy.
      // Trong unit test dùng time.increase, không bật interval để tránh nhiễu.
      mining: { auto: true, interval: process.argv.includes("node") ? 1000 : 0 },
    },
    localhost: {
      url: "http://127.0.0.1:8545",
      chainId: 31337,
    },
    sepolia: {
      // URL dự phòng không dùng được: tránh kết nối mạng khác khi thiếu .env.
      url: process.env.SEPOLIA_RPC_URL || "http://127.0.0.1:1",
      chainId: 11155111,
      accounts: process.env.DEPLOYER_PRIVATE_KEY
        ? [process.env.DEPLOYER_PRIVATE_KEY]
        : [],
    },
  },
  etherscan: { apiKey: process.env.ETHERSCAN_API_KEY || "" },
  gasReporter: {
    enabled: process.env.REPORT_GAS === "true",
    outputFile: "gas-report.txt",
    noColors: true,
  },
  mocha: { timeout: 40000 },
};
