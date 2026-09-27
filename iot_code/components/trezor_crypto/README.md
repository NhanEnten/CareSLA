# Trezor crypto — phần được dùng cho CareSLA

Nguồn: https://github.com/trezor/trezor-firmware/tree/ce266730eace422213124d344a68dce00cab10f5/crypto

Giữ nguyên các file nguồn và header trong src/, kèm LICENSE và thông báo bản quyền.
Chỉ build bignum, ECDSA secp256k1, RFC6979, SHA2/HMAC, Keccak và memzero.
Các chức năng ví khác bị linker loại bỏ. random_esp.c cung cấp random_buffer qua esp_fill_random.
Không dùng PRNG không an toàn của thư viện. Đây là tích hợp cho đồ án, chưa được kiểm toán bảo mật.
