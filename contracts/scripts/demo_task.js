const { task } = require("hardhat/config");

// Tham số riêng của script, không thêm/đổi biến môi trường chung IC-15.
task("demo-setup", "Tạo plan demo CareSLA (ký quỹ 100 ETH local / 0.01 ETH Sepolia)")
  .addOptionalParam("device", "Địa chỉ thiết bị; mặc định lấy REGISTERED_DEVICES nếu chỉ có 1 địa chỉ")
  .addOptionalParam("familyKeyFile", "File khóa testnet của family, ngoài Git")
  .addOptionalParam("providerKeyFile", "File khóa testnet của provider, ngoài Git")
  .addOptionalParam("primary", "Địa chỉ nhân viên chính trên Sepolia")
  .addOptionalParam("backup", "Địa chỉ nhân viên dự phòng trên Sepolia")
  .addFlag("shortPlan", "Tạo riêng plan 5 phút và gửi FALL mẫu; ký quỹ thêm một plan")
  .setAction(async (args, hre) => {
    await hre.run("compile");
    await require("./demo_setup").main(args);
  });
