const { ethers } = require("hardhat");

async function signEvent(wallet, eventType, timestamp, nonce, dataHash, device = wallet.address) {
  const messageHash = ethers.solidityPackedKeccak256(
    ["address", "uint8", "uint64", "uint64", "bytes32"],
    [device, eventType, timestamp, nonce, dataHash],
  );
  // Ký 32 byte hash, không ký chuỗi ký tự "0x...".
  return { messageHash, sig: await wallet.signMessage(ethers.getBytes(messageHash)) };
}

module.exports = { signEvent };
