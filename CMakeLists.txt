cmake_minimum_required(VERSION 3.16)
project(gomoku_starter LANGUAGES CXX)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(gomoku INTERFACE)
target_include_directories(gomoku INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_options(gomoku INTERFACE
  "$<$<CXX_COMPILER_ID:MSVC>:/utf-8>"
  "$<$<CXX_COMPILER_ID:MSVC>:/EHsc>"
)

set(STUDENT_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/src/student_move.cpp" CACHE FILEPATH "学生提交的落子实现文件")
if(NOT EXISTS "${STUDENT_SOURCE}")
  message(FATAL_ERROR "STUDENT_SOURCE does not exist: ${STUDENT_SOURCE}")
endif()
add_executable(gomoku_player src/main.cpp "${STUDENT_SOURCE}")
target_link_libraries(gomoku_player PRIVATE gomoku)

enable_testing()
add_executable(gomoku_tests tests/test_board.cpp)
target_link_libraries(gomoku_tests PRIVATE gomoku)
add_test(NAME gomoku_tests COMMAND gomoku_tests)
