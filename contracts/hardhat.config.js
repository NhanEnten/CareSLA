// ⚠️ File cấu hình TẠM do P1 dựng để viết contract. P2 sở hữu file này và có thể thay thế.
require("@nomicfoundation/hardhat-toolbox");

module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: { enabled: true, runs: 200 },
      viaIR: true, // cần vì getPlan/getFallEvent trả về nhiều giá trị (tránh "stack too deep")
      evmVersion: "cancun", // MessageHashUtils của OZ 5.6 cần ^0.8.24
    },
  },
};
