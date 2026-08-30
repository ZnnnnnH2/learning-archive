#pragma once

#include <array>
#include <cctype>
#include <cstddef>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace gomoku {

constexpr int kBoardSize = 15;
constexpr int kMaxMoves = 200;

enum class Cell : char { Empty = '.', Black = 'B', White = 'W' };

struct Move {
  int x = -1;
  int y = -1;
  friend constexpr bool operator==(Move a, Move b) {
    return a.x == b.x && a.y == b.y;
  }
};

enum class Result { Ongoing, BlackWin, WhiteWin, Forbidden, Draw };
enum class MoveStatus {
  Legal,
  OutOfBounds,
  Occupied,
  Overline,
  DoubleFour,
  DoubleThree,
};

class Board {
public:
  Board() { cells_.fill(Cell::Empty); }

  bool inBounds(Move m) const {
    return m.x >= 0 && m.x < kBoardSize && m.y >= 0 && m.y < kBoardSize;
  }
  Cell at(Move m) const { return inBounds(m) ? cells_[index(m)] : Cell::Empty; }
  bool empty(Move m) const { return inBounds(m) && at(m) == Cell::Empty; }
  int moves() const { return moves_; }

  // Populate a serialized position without applying move legality. Proposed
  // moves must still go through checkMove/isLegal.
  void setCell(Move m, Cell value) {
    if (!inBounds(m)) throw std::out_of_range("cell coordinate out of bounds");
    Cell &slot = cells_[index(m)];
    if (slot == Cell::Empty && value != Cell::Empty) ++moves_;
    if (slot != Cell::Empty && value == Cell::Empty) --moves_;
    slot = value;
  }

  bool isLegal(Move m, Cell color) const {
    if (color != Cell::Black && color != Cell::White)
      return false;
    if (!empty(m))
      return false;
    if (color == Cell::White)
      return true;
    return checkBlackMove(m) == MoveStatus::Legal;
  }

  // Detailed Renju legality result for the forbidden-color (black).
  MoveStatus checkBlackMove(Move m) const {
    if (!inBounds(m)) return MoveStatus::OutOfBounds;
    if (!empty(m)) return MoveStatus::Occupied;
    Board next = *this;
    next.cells_[index(m)] = Cell::Black;
    ++next.moves_;
    if (next.blackWinAt(m)) return MoveStatus::Legal;
    if (next.hasOverlineAt(m)) return MoveStatus::Overline;
    if (next.hasFourFour(m)) return MoveStatus::DoubleFour;
    if (next.hasThreeThree(m)) return MoveStatus::DoubleThree;
    return MoveStatus::Legal;
  }

  // Naming used by the contest handout; equivalent to isLegal.
  bool checkMove(Move m, Cell color) const { return isLegal(m, color); }
  MoveStatus checkMove(Move m) const { return checkBlackMove(m); }

  bool play(Move m, Cell color) {
    if (!isLegal(m, color))
      return false;
    cells_[index(m)] = color;
    ++moves_;
    return true;
  }

  Result resultAfter(Move m, Cell color) const {
    if (!inBounds(m) || !empty(m))
      return Result::Forbidden;
    Board next = *this;
    if (!next.play(m, color))
      return Result::Forbidden;
    if (color == Cell::Black && next.blackWinAt(m))
      return Result::BlackWin;
    if (color == Cell::White && next.hasFiveOrMoreAt(m))
      return Result::WhiteWin;
    if (next.moves_ >= kMaxMoves || !next.hasAnyLegalMove(opposite(color)))
      return Result::Draw;
    return Result::Ongoing;
  }

  // Evaluates the current position for the side that would move next.
  Result state(Cell sideToMove) const {
    for (int y = 0; y < kBoardSize; ++y) {
      for (int x = 0; x < kBoardSize; ++x) {
        Move m{x, y};
        if (at(m) == Cell::Black && blackWinAt(m))
          return Result::BlackWin;
        if (at(m) == Cell::White && hasFiveOrMoreAt(m))
          return Result::WhiteWin;
      }
    }
    if (moves_ >= kMaxMoves || !hasAnyLegalMove(sideToMove))
      return Result::Draw;
    return Result::Ongoing;
  }

  bool hasAnyLegalMove(Cell color) const {
    for (int y = 0; y < kBoardSize; ++y)
      for (int x = 0; x < kBoardSize; ++x)
        if (isLegal({x, y}, color))
          return true;
    return false;
  }

  static Cell opposite(Cell c) {
    return c == Cell::Black ? Cell::White : Cell::Black;
  }

private:
  std::array<Cell, kBoardSize * kBoardSize> cells_{};
  int moves_ = 0;

  static std::size_t index(Move m) {
    return static_cast<std::size_t>(m.y * kBoardSize + m.x);
  }

  int lineLength(Move m, int dx, int dy) const {
    int n = 1;
    for (int s : {-1, 1}) {
      int x = m.x + s * dx, y = m.y + s * dy;
      while (x >= 0 && x < kBoardSize && y >= 0 && y < kBoardSize &&
             at({x, y}) == at(m)) {
        ++n;
        x += s * dx;
        y += s * dy;
      }
    }
    return n;
  }

  bool containsOnLine(Move origin, Move point, int dx, int dy) const {
    int x = origin.x, y = origin.y;
    while (inBounds({x - dx, y - dy}) && at({x - dx, y - dy}) == Cell::Black) {
      x -= dx;
      y -= dy;
    }
    for (int i = 0; i < kBoardSize; ++i) {
      if (x == point.x && y == point.y) return true;
      if (!inBounds({x, y}) || at({x, y}) != Cell::Black) return false;
      x += dx;
      y += dy;
    }
    return false;
  }

  bool hasFiveOrMoreAt(Move m) const {
    return lineLength(m, 1, 0) >= 5 || lineLength(m, 0, 1) >= 5 ||
           lineLength(m, 1, 1) >= 5 || lineLength(m, 1, -1) >= 5;
  }
  bool blackWinAt(Move m) const {
    return at(m) == Cell::Black && lineLength(m, 1, 0) == 5 ||
           at(m) == Cell::Black && lineLength(m, 0, 1) == 5 ||
           at(m) == Cell::Black && lineLength(m, 1, 1) == 5 ||
           at(m) == Cell::Black && lineLength(m, 1, -1) == 5;
  }
  bool hasOverlineAt(Move m) const {
    return at(m) == Cell::Black &&
           (lineLength(m, 1, 0) > 5 || lineLength(m, 0, 1) > 5 ||
            lineLength(m, 1, 1) > 5 || lineLength(m, 1, -1) > 5);
  }

  int completionCount(Move origin, int dx, int dy) const {
    int count = 0;
    for (int step = -4; step <= 4; ++step) {
      if (step == 0) continue;
      Move candidate{origin.x + step * dx, origin.y + step * dy};
      if (!empty(candidate)) continue;
      Board probe = *this;
      probe.setCell(candidate, Cell::Black);
      if (probe.lineLength(candidate, dx, dy) == 5 &&
          probe.containsOnLine(candidate, origin, dx, dy)) ++count;
    }
    return count;
  }

  bool hasFourFour(Move m) const {
    int directions = 0;
    for (auto [dx, dy] : directions_)
      if (completionCount(m, dx, dy) > 0) ++directions;
    return directions >= 2;
  }

  bool hasThreeThree(Move m) const {
    int directions = 0;
    for (auto [dx, dy] : directions_) {
      bool openThree = false;
      for (int step = -4; step <= 4 && !openThree; ++step) {
        if (step == 0) continue;
        Move extension{m.x + step * dx, m.y + step * dy};
        if (!empty(extension)) continue;
        Board probe = *this;
        probe.setCell(extension, Cell::Black);
        if (probe.lineLength(extension, dx, dy) < 5 &&
            !probe.hasOverlineAt(extension) &&
            probe.completionCount(m, dx, dy) >= 2) openThree = true;
      }
      if (openThree && ++directions >= 2) return true;
    }
    return false;
  }

  inline static const std::array<std::pair<int, int>, 4> directions_{{
      std::pair<int, int>{1, 0}, std::pair<int, int>{0, 1},
      std::pair<int, int>{1, 1}, std::pair<int, int>{1, -1}}};
};

struct Position {
  Board board;
  Cell myColor = Cell::Black;
  int moveNumber = 0;
  int timeoutTurnMs = 2000;
  int timeLeftMs = 45000;
  unsigned long long seed = 0;
};

inline Position parsePosition(std::istream &in) {
  Position p;
  Cell protocolSide = Cell::Black;
  bool hasProtocolSide = false;
  const auto parseColor = [](char value, const char *field) {
    const char normalized = static_cast<char>(std::toupper(static_cast<unsigned char>(value)));
    if (normalized == 'B') return Cell::Black;
    if (normalized == 'W') return Cell::White;
    throw std::runtime_error(std::string("invalid ") + field + " color");
  };
  std::string key;
  if (!(in >> key) || key != "GOMOKU")
    throw std::runtime_error("expected GOMOKU header");
  int rows = 0;
  if (!(in >> rows) || rows != kBoardSize)
    throw std::runtime_error("expected board size 15");
  for (int y = 0; y < kBoardSize; ++y) {
    std::string row;
    if (!(in >> row) || static_cast<int>(row.size()) != kBoardSize)
      throw std::runtime_error("invalid board row");
    for (int x = 0; x < kBoardSize; ++x) {
      char c =
          static_cast<char>(std::toupper(static_cast<unsigned char>(row[x])));
      Cell cell = c == 'B'   ? Cell::Black
                  : c == 'W' ? Cell::White
                  : c == '.' ? Cell::Empty
                             : throw std::runtime_error("invalid board cell");
      p.board.setCell({x, y}, cell);
    }
  }
  while (in >> key) {
    if (key == "MY") {
      char c;
      if (!(in >> c)) throw std::runtime_error("missing MY color");
      p.myColor = parseColor(c, "MY");
    } else if (key == "SIDE") {
      char c;
      if (!(in >> c)) throw std::runtime_error("missing SIDE color");
      protocolSide = parseColor(c, "SIDE");
      hasProtocolSide = true;
    } else if (key == "MOVE")
      in >> p.moveNumber;
    else if (key == "TIME_TURN")
      in >> p.timeoutTurnMs;
    else if (key == "TIME_LEFT")
      in >> p.timeLeftMs;
    else if (key == "SEED")
      in >> p.seed;
    else
      throw std::runtime_error("unknown position field: " + key);
  }
  if (p.moveNumber == 0)
    p.moveNumber = p.board.moves();
  if (hasProtocolSide && protocolSide != p.myColor)
    throw std::runtime_error("SIDE must match MY for a single-turn process");
  return p;
}

inline void writeMove(std::ostream &out, Move m) {
  out << m.x << ',' << m.y << '\n';
}

} // namespace gomoku
