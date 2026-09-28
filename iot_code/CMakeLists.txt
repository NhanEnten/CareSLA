cmake_minimum_required(VERSION 3.16)

set(TFLM_DIR "${CMAKE_CURRENT_LIST_DIR}/components/esp-tflite-micro")
set(TFLM_PATCH "${CMAKE_CURRENT_LIST_DIR}/patches/esp-tflite-micro.patch")
if(NOT EXISTS "${TFLM_DIR}/tensorflow/lite/micro/kernels/space_to_batch_nd.cc")
	message(FATAL_ERROR "Initialize submodules first: git submodule update --init --recursive")
endif()

## Kiểm tra chiều ngược trước: patch không có context có thể áp lặp lần hai.
execute_process(
	COMMAND git apply --unidiff-zero --reverse --check "${TFLM_PATCH}"
	WORKING_DIRECTORY "${TFLM_DIR}"
	RESULT_VARIABLE TFLM_PATCH_REVERSE_CHECK
	OUTPUT_QUIET ERROR_QUIET)
if(NOT TFLM_PATCH_REVERSE_CHECK EQUAL 0)
	execute_process(
		COMMAND git apply --unidiff-zero --check "${TFLM_PATCH}"
		WORKING_DIRECTORY "${TFLM_DIR}"
		RESULT_VARIABLE TFLM_PATCH_CHECK
		OUTPUT_QUIET ERROR_QUIET)
	if(NOT TFLM_PATCH_CHECK EQUAL 0)
		message(FATAL_ERROR "TFLite Micro source does not match the expected patch base")
	endif()
	execute_process(
		COMMAND git apply --unidiff-zero "${TFLM_PATCH}"
		WORKING_DIRECTORY "${TFLM_DIR}"
		RESULT_VARIABLE TFLM_PATCH_RESULT)
	if(NOT TFLM_PATCH_RESULT EQUAL 0)
		message(FATAL_ERROR "Failed to apply the CareSLA TFLite Micro patch")
	endif()
endif()

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(carensla_iot)
