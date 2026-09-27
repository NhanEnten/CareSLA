const fs = require("node:fs");
const { expect } = require("chai");
const hre = require("hardhat");
const solc = require("solc");
const { TASK_COMPILE_SOLIDITY_GET_SOLC_BUILD } = require("hardhat/builtin-tasks/task-names");

describe("P2 toolchain (không phải CareSLA.sol)", function () {
  it("solc 0.8.24 biên dịch được ECDSA, MessageHashUtils, ReentrancyGuard đã cài", async function () {
    expect(solc.version()).to.match(/^0\.8\.24\+/);
    const build = await hre.run(TASK_COMPILE_SOLIDITY_GET_SOLC_BUILD, { solcVersion: "0.8.24", quiet: true });
    expect(build.compilerPath).to.equal(require.resolve("solc/soljson.js"));
    // Probe chỉ kiểm tra dependency và cấu hình compiler, không cài luật SLA.
    const content = `// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
contract ToolchainProbe is ReentrancyGuard {
    function recover(bytes32 hash, bytes memory sig) external pure returns (address) {
        return ECDSA.recover(MessageHashUtils.toEthSignedMessageHash(hash), sig);
    }
}`;
    const settings = hre.config.solidity.compilers[0].settings;
    const result = JSON.parse(solc.compile(JSON.stringify({
      language: "Solidity",
      sources: { "ToolchainProbe.sol": { content } },
      settings: { ...settings, outputSelection: { "*": { "*": ["evm.bytecode.object"] } } },
    }), { import: (name) => ({ contents: fs.readFileSync(require.resolve(name), "utf8") }) }));
    expect((result.errors || []).filter((error) => error.severity === "error")).to.deep.equal([]);
    expect(result.contracts["ToolchainProbe.sol"].ToolchainProbe.evm.bytecode.object).not.to.equal("");
  });
});
