// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {MessageHashUtils} from "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title CareSLA — hợp đồng chăm sóc có cam kết thời gian phản hồi té ngã
/// @notice Contract giữ tiền ký quỹ của gia đình và tự thực thi luật SLA.
contract CareSLA is ReentrancyGuard {
    // ------------------------------------------------------------------
    // Hằng số
    // ------------------------------------------------------------------
    uint8 public constant EVENT_FALL = 1;
    uint8 public constant EVENT_ARRIVAL = 2;
    uint8 public constant MAX_SHIFTS = 20;       // giới hạn vòng lặp tìm ca
    uint64 public constant TS_PAST_WINDOW = 600; // ts được phép cũ tối đa 10 phút
    uint64 public constant TS_FUTURE_WINDOW = 60; // ts được phép lệch tới tương lai 60 giây
    uint64 public constant SETTLE_DELAY = TS_PAST_WINDOW; // chờ thêm sau periodEnd để sự cố trong hàng đợi của gateway kịp lên chain (IC-12)

    // ------------------------------------------------------------------
    // Kiểu dữ liệu
    // ------------------------------------------------------------------
    enum Status { Open, Acknowledged, Arrived }

    struct Plan {
        address family;
        address provider;
        address device;       // địa chỉ Ethereum của thiết bị IoT
        uint64 slaSeconds;
        uint64 periodEnd;
        uint256 penaltyWei;   // tiền phạt cho mỗi vi phạm
        uint256 deposit;
        uint256 violations;
        uint256 pendingEvents; // số sự cố còn Open và chưa lên cấp 2 (IC-12)
        bool accepted;
        bool settled;
    }

    struct Shift {
        uint64 start;
        uint64 end;           // ca chứa ts nếu start <= ts < end
        address primary;
        address backup;
    }

    struct FallEvent {
        uint256 planId;
        uint64 ts;            // thời điểm thiết bị ghi nhận té ngã
        bytes32 dataHash;
        address primary;      // chụp lại người trực lúc té ngã, sau này không đổi
        address backup;
        uint64 reportedAt;
        uint64 deadline;      // 0 khi đã chuyển tới gia đình (cấp 2)
        uint8 level;          // 0 = primary, 1 = backup, 2 = gia đình
        Status status;
        address ackBy;
        uint64 ackAt;
        uint64 arrivedAt;
    }

    // ------------------------------------------------------------------
    // Biến trạng thái
    // ------------------------------------------------------------------
    uint256 public planCount;   // planId bắt đầu từ 1
    uint256 public eventCount;  // eventId bắt đầu từ 1

    mapping(uint256 => Plan) private plans;
    mapping(uint256 => Shift[]) private shifts;
    mapping(uint256 => FallEvent) private fallEvents;
    mapping(uint256 => uint64) public lastNonce; // planId => nonce lớn nhất đã dùng (IC-11: theo plan, không theo thiết bị)

    // ------------------------------------------------------------------
    // Event (đúng mục 6.3 AGENTS.md)
    // ------------------------------------------------------------------
    event PlanCreated(uint256 indexed planId, address indexed family, address indexed provider, address device, uint256 deposit);
    event PlanAccepted(uint256 indexed planId);
    event ShiftCommitted(uint256 indexed planId, uint64 start, uint64 end, address primary, address backup);
    event FallReported(uint256 indexed eventId, uint256 indexed planId, bytes32 dataHash, address primary, uint64 deadline);
    event Acknowledged(uint256 indexed eventId, address indexed caregiver, uint64 at);
    event Escalated(uint256 indexed eventId, uint8 level, address to, uint64 newDeadline);
    event SlaViolation(uint256 indexed eventId, uint256 indexed planId, uint256 totalViolations);
    event Arrived(uint256 indexed eventId, uint64 at);
    event Settled(uint256 indexed planId, uint256 toProvider, uint256 refundFamily);

    // ------------------------------------------------------------------
    // Modifier
    // ------------------------------------------------------------------
    modifier planExists(uint256 planId) {
        require(plans[planId].family != address(0), "no plan");
        _;
    }

    modifier eventExists(uint256 eventId) {
        require(fallEvents[eventId].planId != 0, "no event");
        _;
    }

    // ==================================================================
    // 1. Hợp đồng và ca trực
    // ==================================================================

    /// Gia đình tạo hợp đồng, msg.value là tiền ký quỹ.
    function createCarePlan(
        address provider,
        address device,
        uint64 slaSeconds,
        uint256 penaltyWei,
        uint64 periodEnd
    ) external payable returns (uint256 planId) {
        require(msg.value > 0, "no deposit");
        require(provider != address(0) && device != address(0), "zero address");
        require(provider != msg.sender, "provider is family");
        require(slaSeconds > 0, "sla is 0");
        require(penaltyWei <= msg.value, "penalty > deposit");
        require(periodEnd > block.timestamp, "period ended");

        planId = ++planCount;
        Plan storage p = plans[planId];
        p.family = msg.sender;
        p.provider = provider;
        p.device = device;
        p.slaSeconds = slaSeconds;
        p.periodEnd = periodEnd;
        p.penaltyWei = penaltyWei;
        p.deposit = msg.value;

        emit PlanCreated(planId, msg.sender, provider, device, msg.value);
    }

    /// Trung tâm chấp nhận hợp đồng.
    function acceptPlan(uint256 planId) external planExists(planId) {
        Plan storage p = plans[planId];
        require(msg.sender == p.provider, "not provider");
        require(!p.accepted, "already accepted");
        require(block.timestamp < p.periodEnd, "period ended");

        p.accepted = true;
        emit PlanAccepted(planId);
    }

    /// Trung tâm cam kết một ca trực. Ca phải bắt đầu trong tương lai, sau đó không sửa được.
    function commitShift(
        uint256 planId,
        uint64 start,
        uint64 end,
        address primary,
        address backup
    ) external planExists(planId) {
        Plan storage p = plans[planId];
        require(msg.sender == p.provider, "not provider");
        require(p.accepted, "not accepted");
        require(start > block.timestamp, "start in past"); // chặn sửa lịch sau sự cố
        require(end > start, "end <= start");
        require(end <= p.periodEnd, "end > periodEnd");
        require(primary != address(0) && backup != address(0), "zero address");
        require(primary != backup, "primary == backup");

        Shift[] storage list = shifts[planId];
        require(list.length < MAX_SHIFTS, "too many shifts");
        // Không cho ca chồng giờ, để mỗi thời điểm chỉ có đúng một người trực chính
        for (uint256 i = 0; i < list.length; i++) {
            require(end <= list[i].start || start >= list[i].end, "overlap");
        }

        list.push(Shift(start, end, primary, backup));
        emit ShiftCommitted(planId, start, end, primary, backup);
    }

    // ==================================================================
    // 2. Sự cố té ngã
    // ==================================================================

    /// Ai gọi cũng được (thường là gateway). Hợp lệ nhờ chữ ký của thiết bị, không nhờ người gọi.
    function reportFall(
        uint256 planId,
        uint64 ts,
        uint64 nonce,
        bytes32 dataHash,
        bytes calldata sig
    ) external planExists(planId) returns (uint256 eventId) {
        Plan storage p = plans[planId];
        require(p.accepted, "not accepted");
        require(!p.settled, "settled");
        require(ts <= p.periodEnd, "ts after period"); // té ngã phải xảy ra trong kỳ hợp đồng
        _checkTsWindow(ts);
        _verifyDevice(planId, EVENT_FALL, ts, nonce, dataHash, sig);

        (address primary, address backup) = _findOnDuty(planId, ts);
        require(primary != address(0), "no shift");

        uint64 deadline = uint64(block.timestamp) + p.slaSeconds;
        eventId = ++eventCount;
        FallEvent storage e = fallEvents[eventId];
        e.planId = planId;
        e.ts = ts;
        e.dataHash = dataHash;
        e.primary = primary;
        e.backup = backup;
        e.reportedAt = uint64(block.timestamp);
        e.deadline = deadline;
        // level = 0 và status = Open là giá trị mặc định
        p.pendingEvents += 1;

        emit FallReported(eventId, planId, dataHash, primary, deadline);
    }

    /// Nhân viên trực (primary hoặc backup) xác nhận đã nhận cảnh báo.
    function acknowledge(uint256 eventId) external eventExists(eventId) {
        FallEvent storage e = fallEvents[eventId];
        require(e.status == Status.Open, "not open");
        require(msg.sender == e.primary || msg.sender == e.backup, "not on duty");

        // Nếu đã quá hạn mà keeper chưa kịp gọi checkTimeout, ghi vi phạm trước (xem IC-08)
        _escalateIfExpired(eventId);
        _clearPending(eventId); // gọi trước khi đổi status

        e.status = Status.Acknowledged;
        e.ackBy = msg.sender;
        e.ackAt = uint64(block.timestamp);
        emit Acknowledged(eventId, msg.sender, uint64(block.timestamp));
    }

    /// Nhân viên có mặt và nhấn giữ nút trên thiết bị: thiết bị ký sự kiện ARRIVAL.
    function confirmArrival(
        uint256 eventId,
        uint64 ts,
        uint64 nonce,
        bytes32 dataHash,
        bytes calldata sig
    ) external eventExists(eventId) {
        FallEvent storage e = fallEvents[eventId];
        require(e.status != Status.Arrived, "already arrived");
        require(ts >= e.ts, "ts before fall");
        _checkTsWindow(ts);
        _verifyDevice(e.planId, EVENT_ARRIVAL, ts, nonce, dataHash, sig);

        // Có mặt khi chưa bấm nhận vẫn hợp lệ (IC-02), nhưng quá hạn thì vẫn ghi vi phạm
        if (e.status == Status.Open) {
            _escalateIfExpired(eventId);
            _clearPending(eventId);
        }

        e.status = Status.Arrived;
        e.arrivedAt = uint64(block.timestamp);
        emit Arrived(eventId, uint64(block.timestamp));
    }

    /// Ai gọi cũng được (keeper, gia đình...). Quá hạn thì ghi vi phạm và chuyển cấp.
    function checkTimeout(uint256 eventId) external eventExists(eventId) {
        FallEvent storage e = fallEvents[eventId];
        require(e.status == Status.Open, "not open");
        require(e.level < 2, "max level");
        require(block.timestamp > e.deadline, "not expired");
        _escalate(eventId);
    }

    // ==================================================================
    // 3. Chia tiền cuối kỳ
    // ==================================================================

    function settle(uint256 planId) external nonReentrant planExists(planId) {
        Plan storage p = plans[planId];
        // --- Checks ---
        require(block.timestamp > p.periodEnd + SETTLE_DELAY, "period not ended");
        require(!p.settled, "already settled");
        require(p.pendingEvents == 0, "pending events"); // mọi vi phạm phải được ghi xong (IC-12)

        // --- Effects: cập nhật trạng thái TRƯỚC khi chuyển tiền ---
        p.settled = true;
        uint256 toProvider;
        uint256 refundFamily;
        if (!p.accepted) {
            refundFamily = p.deposit; // trung tâm chưa nhận hợp đồng thì hoàn toàn bộ (IC-05)
        } else {
            uint256 penalty = p.violations * p.penaltyWei;
            if (penalty > p.deposit) penalty = p.deposit; // penalty = min(violations × penaltyWei, deposit)
            refundFamily = penalty;
            toProvider = p.deposit - penalty;
        }
        emit Settled(planId, toProvider, refundFamily);

        // --- Interactions: gửi ETH bằng call ---
        if (toProvider > 0) {
            (bool ok, ) = payable(p.provider).call{value: toProvider}("");
            require(ok, "pay provider failed");
        }
        if (refundFamily > 0) {
            (bool ok, ) = payable(p.family).call{value: refundFamily}("");
            require(ok, "refund family failed");
        }
    }

    // ==================================================================
    // 4. Hàm đọc
    // ==================================================================

    /// Trả về messageHash (chưa có tiền tố EIP-191), dùng để đối chiếu khi debug chữ ký.
    function hashEvent(
        address device,
        uint8 eventType,
        uint64 ts,
        uint64 nonce,
        bytes32 dataHash
    ) public pure returns (bytes32) {
        // 20 + 1 + 8 + 8 + 32 = 69 byte, số nguyên theo big-endian
        return keccak256(abi.encodePacked(device, eventType, ts, nonce, dataHash));
    }

    function getPlan(uint256 planId) external view returns (
        address family, address provider, address device,
        uint64 slaSeconds, uint256 penaltyWei, uint64 periodEnd,
        uint256 deposit, bool accepted, bool settled,
        uint256 violations, uint256 shiftCount, uint256 pendingEvents
    ) {
        Plan storage p = plans[planId];
        return (
            p.family, p.provider, p.device,
            p.slaSeconds, p.penaltyWei, p.periodEnd,
            p.deposit, p.accepted, p.settled,
            p.violations, shifts[planId].length, p.pendingEvents
        );
    }

    function getEvent(uint256 eventId) external view returns (
        uint256 planId, uint64 ts, bytes32 dataHash,
        address primary, address backup,
        uint64 reportedAt, uint64 deadline, uint8 level, uint8 status,
        address ackBy, uint64 ackAt, uint64 arrivedAt
    ) {
        FallEvent storage e = fallEvents[eventId];
        return (
            e.planId, e.ts, e.dataHash,
            e.primary, e.backup,
            e.reportedAt, e.deadline, e.level, uint8(e.status),
            e.ackBy, e.ackAt, e.arrivedAt
        );
    }

    function getOnDuty(uint256 planId, uint64 ts) external view returns (address primary, address backup) {
        return _findOnDuty(planId, ts);
    }

    // ==================================================================
    // 5. Hàm nội bộ
    // ==================================================================

    /// Kiểm tra chữ ký thiết bị và nonce, rồi cập nhật nonce. Sai thì revert.
    function _verifyDevice(
        uint256 planId,
        uint8 eventType,
        uint64 ts,
        uint64 nonce,
        bytes32 dataHash,
        bytes calldata sig
    ) internal {
        // Nonce theo plan: hợp đồng bù nhìn dùng chung thiết bị không tiêu được nonce của plan thật (IC-11)
        require(nonce > lastNonce[planId], "old nonce"); // chống gửi lại gói cũ

        address device = plans[planId].device;
        bytes32 messageHash = hashEvent(device, eventType, ts, nonce, dataHash);
        bytes32 ethSigned = MessageHashUtils.toEthSignedMessageHash(messageHash); // tiền tố EIP-191
        address signer = ECDSA.recover(ethSigned, sig); // khôi phục địa chỉ từ chữ ký
        require(signer == device, "bad sig");

        lastNonce[planId] = nonce;
    }

    function _checkTsWindow(uint64 ts) internal view {
        require(uint256(ts) + TS_PAST_WINDOW >= block.timestamp, "ts too old");
        require(uint256(ts) <= block.timestamp + TS_FUTURE_WINDOW, "ts in future");
    }

    function _findOnDuty(uint256 planId, uint64 ts) internal view returns (address, address) {
        Shift[] storage list = shifts[planId];
        for (uint256 i = 0; i < list.length; i++) { // tối đa 20 vòng
            if (list[i].start <= ts && ts < list[i].end) {
                return (list[i].primary, list[i].backup);
            }
        }
        return (address(0), address(0));
    }

    function _escalateIfExpired(uint256 eventId) internal {
        FallEvent storage e = fallEvents[eventId];
        if (e.level < 2 && block.timestamp > e.deadline) {
            _escalate(eventId);
        }
    }

    /// Sự cố đang Open ở cấp 0/1 thì bớt 1 khỏi pendingEvents. Cấp 2 đã được bớt trong _escalate.
    function _clearPending(uint256 eventId) internal {
        FallEvent storage e = fallEvents[eventId];
        if (e.status == Status.Open && e.level < 2) {
            plans[e.planId].pendingEvents -= 1;
        }
    }

    /// Ghi 1 vi phạm và nâng cấp chuyển thêm 1 bậc. Mỗi cấp chỉ ghi 1 lần vì level tăng ngay.
    function _escalate(uint256 eventId) internal {
        FallEvent storage e = fallEvents[eventId];
        Plan storage p = plans[e.planId];
        p.violations += 1;

        if (e.level == 0) {
            // Cấp 0 → 1: chuyển cho backup, đặt hạn mới
            e.level = 1;
            e.deadline = uint64(block.timestamp) + p.slaSeconds;
            emit Escalated(eventId, 1, e.backup, e.deadline);
        } else {
            // Cấp 1 → 2: báo gia đình, không chuyển tiếp nữa
            e.level = 2;
            e.deadline = 0;
            p.pendingEvents -= 1; // cấp 2 là cấp cuối, không thể bị phạt thêm
            emit Escalated(eventId, 2, p.family, 0);
        }
        emit SlaViolation(eventId, e.planId, p.violations);
    }
}
