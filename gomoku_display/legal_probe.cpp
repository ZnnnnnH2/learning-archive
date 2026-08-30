#include "gomoku.hpp"
#include <iostream>
#include <string>

using namespace gomoku;

static const char* statusName(MoveStatus status) {
  switch (status) {
    case MoveStatus::Legal: return "LEGAL";
    case MoveStatus::OutOfBounds: return "OUT_OF_BOUNDS";
    case MoveStatus::Occupied: return "OCCUPIED";
    case MoveStatus::Overline: return "OVERLINE";
    case MoveStatus::DoubleFour: return "DOUBLE_FOUR";
    case MoveStatus::DoubleThree: return "DOUBLE_THREE";
  }
  return "UNKNOWN";
}

static const char* resultName(Result result) {
  switch (result) {
    case Result::Ongoing: return "ONGOING";
    case Result::BlackWin: return "BLACK_WIN";
    case Result::WhiteWin: return "WHITE_WIN";
    case Result::Forbidden: return "FORBIDDEN";
    case Result::Draw: return "DRAW";
  }
  return "UNKNOWN";
}

int main() {
  try {
    Board board;
    for (int y = 0; y < kBoardSize; ++y) {
      std::string row;
      if (!(std::cin >> row) || row.size() != kBoardSize) return 2;
      for (int x = 0; x < kBoardSize; ++x) {
        if (row[x] == 'B') board.setCell({x, y}, Cell::Black);
        else if (row[x] == 'W') board.setCell({x, y}, Cell::White);
        else if (row[x] != '.') return 2;
      }
    }
    int x, y; char color;
    if (!(std::cin >> x >> y >> color)) return 2;
    const Cell cell = color == 'B' ? Cell::Black : color == 'W' ? Cell::White : Cell::Empty;
    if (cell == Cell::Empty) return 2;
    const Move move{x, y};
    const MoveStatus status = cell == Cell::Black ? board.checkBlackMove(move)
                                                   : (!board.inBounds(move) ? MoveStatus::OutOfBounds
                                                      : !board.empty(move) ? MoveStatus::Occupied : MoveStatus::Legal);
    const bool legal = board.isLegal(move, cell);
    const Result after = legal ? board.resultAfter(move, cell) : Result::Forbidden;
    std::cout << "{\"legal\":" << (legal ? "true" : "false")
              << ",\"status\":\"" << statusName(status) << "\""
              << ",\"result_after\":\"" << resultName(after) << "\"}\n";
  } catch (...) { return 3; }
}
