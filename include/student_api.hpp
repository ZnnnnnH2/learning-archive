#pragma once

#include "gomoku.hpp"

namespace gomoku {

// 学生提交文件必须提供这个函数。允许在提交文件中定义任意辅助函数、
// 类和常量，但不要定义 main，也不要向 stdout 输出调试信息。
Move chooseMove(const Position &position);

} // namespace gomoku
