idf_component_register(SRCS "src/bignum.c" "src/ecdsa.c" "src/secp256k1.c"
    "src/sha2.c" "src/sha3.c" "src/hmac.c" "src/hmac_drbg.c"
    "src/rfc6979.c" "src/memzero.c" "random_esp.c"
    INCLUDE_DIRS "src" REQUIRES esp_hw_support)
target_compile_definitions(${COMPONENT_LIB} PUBLIC USE_KECCAK=1 USE_RFC6979=1)
