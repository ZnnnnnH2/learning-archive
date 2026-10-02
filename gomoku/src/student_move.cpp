#include "student_api.hpp"

using namespace gomoku;

// 学生只需要修改这个函数，也可以在本文件中增加任意辅助函数和类。
namespace gomoku {

Move chooseMove(const Position &position) {
  for (int y = 0; y < kBoardSize; ++y) {
    for (int x = 0; x < kBoardSize; ++x) {
      if (position.board.isLegal({x, y}, position.myColor)) return {x, y};
    }
  }
  return {-1, -1};
}

} // namespace gomoku
