# CareSLA

Hệ thống giám sát té ngã và hợp đồng chăm sóc có cam kết thời gian phản hồi (SLA), đồ án của nhóm **5 người**.
Cảnh báo đi ESP32 → MQTT → Gateway → Telegram, không chờ blockchain.
Contract giữ ETH ký quỹ, xác thực thiết bị, cam kết lịch trực, ghi vi phạm và chia tiền theo SLA.

## Trạng thái bàn giao P2 — 27/09/2026

Đồng bộ với main `22ae021`, AGENTS.md và IC-01…IC-15 đã chốt. Bộ kiểm thử đạt **66 JavaScript** (38 nghiệp vụ P2, 24 chữ ký P1 dùng vector P5, 4 helper/toolchain) và **20 unit keeper**. Deploy/setup local và đọc chain bằng keeper đã chạy; xem [báo cáo P2](docs/report/P2_trien_khai_kiem_thu.md).

Main đã tích hợp firmware, model INT8, gateway và dashboard. Xem [tiến độ P6](docs/progress/P6.md) cho kiểm chứng mới nhất; chưa deploy/verify Sepolia. Không coi kết quả test contract là hoàn thành hệ thống.

## Thư mục và phụ trách

- `contracts/contracts/CareSLA.sol`: P1; `contracts/test/signature.vector.test.js`: P1.
- `contracts/test/`, `contracts/scripts/`, cấu hình Hardhat: P2.
- `backend/keeper.py`, `deployments/`, README và tài liệu P2: P2.
- `backend/gateway.py`, `backend/requirements.txt`, `dashboard/`, `tools/`, vector chuẩn: P5.
- `iot_code/`: P3; `ai_model/`: P4.
- `docs/progress/Px.md`, `docs/study/Px_on_phan_bien.md`: tiến độ và ôn phản biện.

## Chuẩn bị và kiểm thử

Cần Git, Node.js >=22, Python >=3.10. Phiên này đã chạy với Node 24.16, Python 3.13, Hardhat 2.29.1, ethers 6.17, web3 7.16. Dùng lockfile, không cài Hardhat 3. Firmware cần ESP-IDF 5.x; gateway cần Mosquitto và cấu hình Telegram.

Từ thư mục gốc (PowerShell; dùng đúng Python >=3.10 đã cài):

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item .env.example .env
cd contracts
npm ci
npm run compile
npm run test:required
npm run test:gas
cd ..
.venv\Scripts\python.exe -m unittest discover -s contracts/test -p "test_*.py" -v
```

`test:required` không chấp nhận thiếu source/API CareSLA. Gas được ghi vào `contracts/gas-report.txt`; số liệu local không phải giá giao dịch Sepolia.

Điền `.env` theo IC-15: `NETWORK`, `SEPOLIA_RPC_URL`, `DEPLOYER_PRIVATE_KEY`, `GATEWAY_PRIVATE_KEY`, `KEEPER_PRIVATE_KEY`, `ETHERSCAN_API_KEY`, `PLAN_ID`, MQTT/Telegram và `REGISTERED_DEVICES`. Local dùng cố định `http://127.0.0.1:8545`. Địa chỉ mặc định đọc từ `deployments/<NETWORK>.json`; keeper hiện luôn dùng file này, không dùng ghi đè `CONTRACT_ADDRESS`.

Không đưa khóa ví/token vào Git, chat hoặc lệnh shell. Chỉ dùng ví testnet riêng từng vai trò. Các khóa mặc định Hardhat và khóa vector chuẩn là khóa công khai để test, không bao giờ dùng trên mạng thật.

## Chạy Hardhat local

Terminal 1, tại `contracts/`:

```powershell
npm run node
```

Node tạo block mỗi giây để thời gian SLA tiếp tục chạy. Node có thể in khóa test mặc định; không chia sẻ log này như khóa ví cá nhân.

Terminal 2, tại `contracts/`:

```powershell
npm run deploy:local
npm run setup:local -- --device 0xDIA_CHI_THIET_BI
```

Thay địa chỉ mẫu bằng địa chỉ P3 cung cấp. Có thể bỏ `--device` nếu `REGISTERED_DEVICES` chỉ chứa một địa chỉ. Setup dùng tài khoản local #1 family, #2 provider, #3 primary, #4 backup; tạo plan 2 giờ, ký quỹ **100 ETH**, SLA 60 giây, phạt **20 ETH**/lần (Sepolia tự dùng 0.01 / 0.002 ETH), 2 ca liên tiếp bắt đầu sau khoảng 60 giây. Chép `PLAN_ID` được in vào `.env`; chỉ phát FALL sau thời điểm ca bắt đầu.

Deploy sinh **ABI thật** tại `backend/abi/CareSLA.json`, `dashboard/CareSLA.json` và metadata `{address,chainId,deployBlock}`. File `deployments/localhost.json` trong repo chỉ là kết quả phiên thử nghiệm, không có nghĩa máy bạn đang có contract. **Mỗi lần restart node phải deploy/setup lại**, khởi động lại gateway/keeper và xử lý nonce MetaMask.

Terminal 3, tại thư mục gốc:

```powershell
.venv\Scripts\python.exe backend/keeper.py --dry-run --once
.venv\Scripts\python.exe backend/keeper.py
```

Lệnh thứ hai cần `KEEPER_PRIVATE_KEY` của ví local có ETH, tách khỏi gateway. Keeper kiểm tra mỗi 5 giây, chỉ gửi khi sự cố đang mở, cấp <2 và giờ chain > deadline. Dry-run không gửi giao dịch; `--once` không đảm bảo tx mới gửi đã có receipt.

## Demo chia tiền với plan ngắn

Tại `contracts/`, chạy thêm **ít nhất 20 phút trước buổi demo**:

```powershell
npm run setup:local -- --short-plan
```

Lệnh này tạo **thêm** plan 5 phút, tốn thêm 100 ETH local (0.01 ETH trên Sepolia); khóa thiết bị mẫu chỉ nằm trong RAM. Script chờ ca bắt đầu rồi gửi FALL có chữ ký. Giữ keeper chạy để chuyển cấp hai lần. Không thay `PLAN_ID` của gateway bằng ID plan ngắn. Không giảm `SETTLE_DELAY`.

Sau khi giờ chain > `periodEnd + 600` và `pendingEvents == 0`, gọi `settle(planId)` qua console Hardhat hoặc dashboard khi P5 bàn giao. Trong console `npx hardhat console --network localhost`, đọc địa chỉ từ deployment, dùng `ethers.getContractAt("CareSLA", address)` và chờ `(await contract.settle(planId)).wait()`. Plan có 2 vi phạm: family được 40 ETH, provider 60 ETH trên local (Sepolia: 0.004 / 0.006 ETH), chưa trừ gas. Giữ receipt/bằng chứng số dư thật.

Kịch bản toàn hệ thống cần cả nhóm xác nhận: CANCEL chỉ off-chain; FALL được nhận đúng hạn; FALL quá hạn hai cấp; ARRIVAL; chain lỗi nhưng Telegram vẫn tới; settle plan ngắn. Chạy thông 3 lần và quay video mới đạt Mốc 2.

## Gateway, dashboard và firmware

Từ gốc repo, sau khi cấu hình MQTT, Telegram, ABI/deployment và ví gateway:

```powershell
.venv\Scripts\python.exe backend/gateway.py
.venv\Scripts\python.exe -m http.server 8000
```

Mở **http://127.0.0.1:8000/dashboard/**. HTTP server phải đứng ở gốc repo để phục vụ cả `deployments/`; không mở bằng `file://`. Firmware và model đã có, xem `iot_code/README.md`. Kết quả kiểm thử phần mềm và giới hạn phần cứng được ghi riêng trong `docs/progress/P6.md`.

## Sepolia — chỉ làm sau baseline local

Chưa có địa chỉ Sepolia hoặc link contract đã verify. Cần RPC, Etherscan API key và ETH testnet cho các ví. Trong `.env`, đặt `NETWORK=sepolia`, cấu hình deployer/gateway/keeper riêng. Từ `contracts/`:

```powershell
npm run deploy:sepolia
npx hardhat verify --network sepolia 0xDIA_CHI_VUA_DEPLOY
npm run setup:sepolia -- --device 0xTHIET_BI --family-key-file ../.keys/family.key --provider-key-file ../.keys/provider.key --primary 0xNHAN_VIEN_CHINH --backup 0xDU_PHONG
```

Các file `.keys/*.key` do bạn tạo riêng chứa một khóa ví testnet, không commit; tham số chỉ là **đường dẫn**, không phải khóa. Bốn địa chỉ family/provider/primary/backup phải khác nhau. Có thể chạy setup lần nữa với `--short-plan` thay `--device` để chuẩn bị demo settle; vẫn cần đủ ví/phí. Compiler verify phải giữ solc 0.8.24, optimizer 200, viaIR, Cancun như cấu hình. Sau deploy dùng metadata Sepolia mới, chạy keeper từ gốc repo và lưu link/receipt thật trước khi ghi hoàn thành.

## Bằng chứng và giới hạn

Chạy `node scripts/collect_results.js` tại `contracts/` khi local node/deployment đã sẵn sàng để ghi `docs/report/P2_test_results.json` và `.txt`. Mặc định script dùng Python trong `.venv`; có thể đặt `PYTHON_EXECUTABLE` riêng cho công cụ thu log, không phải biến giao diện các tầng.

Xem [tiến độ](docs/progress/P2.md), [báo cáo](docs/report/P2_trien_khai_kiem_thu.md), [ôn phản biện](docs/study/P2_on_phan_bien.md). SLA hiện đo tới acknowledge, không phải tới hiện trường; chữ ký không gắn chainId/contract; chia ETH kiểu đẩy có thể thất bại nếu ví nhận là contract từ chối ETH. Keeper không có quyền đặc biệt và không tự gọi settle. Cần thành viên khác chạy README trên máy họ để nghiệm thu.
