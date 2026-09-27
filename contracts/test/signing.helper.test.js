const { expect } = require("chai");
const { ethers } = require("hardhat");
const { signEvent } = require("./helpers/events");

describe("P2 signing helper (off-chain, không thay thế vector P5)", function () {
  it("đóng gói đúng 69 byte và uint64 big-endian", async function () {
    const device = "0x1111111111111111111111111111111111111111";
    const hash = ethers.keccak256("0x00000100ffff");
    const packed = ethers.solidityPacked(
      ["address", "uint8", "uint64", "uint64", "bytes32"],
      [device, 1, 0x0102030405060708n, 42n, hash],
    );
    expect(ethers.getBytes(packed)).to.have.length(69);
    expect(packed).to.equal(device + "01" + "0102030405060708" + "000000000000002a" + hash.slice(2));
  });

  it("chữ ký EIP-191 khôi phục đúng thiết bị, dài 65 byte, v=27/28", async function () {
    const wallet = ethers.Wallet.createRandom();
    const { messageHash, sig } = await signEvent(wallet, 1, 1760000000, 42, ethers.keccak256("0x0000"));
    expect(ethers.verifyMessage(ethers.getBytes(messageHash), sig)).to.equal(wallet.address);
    expect(ethers.getBytes(sig)).to.have.length(65);
    expect([27, 28]).to.include(ethers.getBytes(sig)[64]);
    const prefix = ethers.toUtf8Bytes("\x19Ethereum Signed Message:\n32");
    expect(ethers.hashMessage(ethers.getBytes(messageHash))).to.equal(
      ethers.keccak256(ethers.concat([prefix, messageHash])),
    );
  });

  it("đổi eventType/nonce/dataHash làm chữ ký cũ không còn đúng thiết bị", async function () {
    const wallet = ethers.Wallet.createRandom();
    const dataHash = ethers.keccak256("0x0000");
    const signed = await signEvent(wallet, 1, 1760000000, 42, dataHash);
    for (const [eventType, nonce, hash] of [[2, 42, dataHash], [1, 43, dataHash], [1, 42, ethers.ZeroHash]]) {
      const changed = await signEvent(wallet, eventType, 1760000000, nonce, hash);
      expect(ethers.verifyMessage(ethers.getBytes(changed.messageHash), signed.sig)).not.to.equal(wallet.address);
    }
  });
});
