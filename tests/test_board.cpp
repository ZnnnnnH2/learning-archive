#include "gomoku.hpp"
#include <cassert>
#include <sstream>

using namespace gomoku;

int main() {
  Board b;
  assert(b.empty({7, 7}));
  assert(b.play({7, 7}, Cell::Black));
  assert(!b.play({7, 7}, Cell::White));
  assert(!b.isLegal({-1, 0}, Cell::White));

  Board white;
  for (int x = 0; x < 4; ++x) assert(white.play({x, 0}, Cell::White));
  assert(white.resultAfter({4, 0}, Cell::White) == Result::WhiteWin);

  Board black;
  for (int x = 0; x < 4; ++x) assert(black.play({x, 0}, Cell::Black));
  assert(black.resultAfter({4, 0}, Cell::Black) == Result::BlackWin);
  assert(black.checkMove({4, 0}, Cell::Black));
  Board finished = black;
  assert(finished.play({4, 0}, Cell::Black));
  assert(finished.state(Cell::White) == Result::BlackWin);

  Board fivePriority;
  for (int x : {5, 6, 8, 9}) fivePriority.setCell({x, 7}, Cell::Black);
  for (int y = 4; y <= 6; ++y) fivePriority.setCell({7, y}, Cell::Black);
  for (int d = 4; d <= 6; ++d) fivePriority.setCell({d, d}, Cell::Black);
  assert(fivePriority.checkBlackMove({7, 7}) == MoveStatus::Legal);

  Board overline;
  for (int x = 0; x < 5; ++x) overline.setCell({x, 0}, Cell::Black);
  assert(!overline.checkMove({5, 0}, Cell::Black));
  assert(overline.checkBlackMove({5, 0}) == MoveStatus::Overline);

  Board doubleFour;
  for (int x = 4; x <= 6; ++x) doubleFour.setCell({x, 7}, Cell::Black);
  for (int y = 4; y <= 6; ++y) doubleFour.setCell({7, y}, Cell::Black);
  assert(!doubleFour.checkMove({7, 7}, Cell::Black));
  assert(doubleFour.checkBlackMove({7, 7}) == MoveStatus::DoubleFour);

  Board doubleThree;
  doubleThree.setCell({6, 7}, Cell::Black);
  doubleThree.setCell({8, 7}, Cell::Black);
  doubleThree.setCell({7, 6}, Cell::Black);
  doubleThree.setCell({7, 8}, Cell::Black);
  assert(!doubleThree.checkMove({7, 7}, Cell::Black));
  assert(doubleThree.checkBlackMove({7, 7}) == MoveStatus::DoubleThree);

  std::stringstream input;
  input << "GOMOKU 15\n";
  for (int y = 0; y < 15; ++y) input << "...............\n";
  input << "MY W SIDE W MOVE 5 TIME_TURN 2000 TIME_LEFT 45000 SEED 42\n";
  Position p = parsePosition(input);
  assert(p.myColor == Cell::White && p.seed == 42);
  assert(p.board.moves() == 0);
  return 0;
}
