#include "gomoku.hpp"
#include "student_api.hpp"
#include <chrono>
#include <exception>
#include <iostream>
#include <stdexcept>

using namespace gomoku;

namespace {

struct TimedMove {
  Move move{};
  std::chrono::steady_clock::duration elapsed{};
  std::exception_ptr exception;
};

TimedMove callStudent(const Position &position) {
  TimedMove result;
  const auto start = std::chrono::steady_clock::now();
  try {
    result.move = gomoku::chooseMove(position);
  } catch (...) {
    result.exception = std::current_exception();
  }
  result.elapsed = std::chrono::steady_clock::now() - start;
  return result;
}

} // namespace

int main() {
  try {
    Position position = parsePosition(std::cin);
    if (position.timeoutTurnMs < 0 || position.timeLeftMs < 0)
      throw std::runtime_error("invalid negative time budget");
    const TimedMove timed = callStudent(position);
    const auto elapsedUs = std::chrono::duration_cast<std::chrono::microseconds>(timed.elapsed).count();
    std::cerr << "THINK_TIME_US " << elapsedUs << '\n';

    const auto turnBudget = std::chrono::milliseconds(position.timeoutTurnMs);
    const auto matchBudget = std::chrono::milliseconds(position.timeLeftMs);
    // Prefer a timeout reason when an exception and a timeout happen together;
    // the Judge can then classify the result deterministically.
    if (timed.elapsed > turnBudget) {
      std::cerr << "TERMINAL_REASON TURN_TIMEOUT\n";
      throw std::runtime_error("chooseMove exceeded turn time limit");
    }
    if (timed.elapsed > matchBudget) {
      std::cerr << "TERMINAL_REASON MATCH_TIMEOUT\n";
      throw std::runtime_error("chooseMove exceeded remaining match time");
    }
    if (timed.exception) {
      std::cerr << "TERMINAL_REASON PROGRAM_EXCEPTION\n";
      std::rethrow_exception(timed.exception);
    }
    if (!position.board.isLegal(timed.move, position.myColor)) {
      std::cerr << "TERMINAL_REASON ILLEGAL_MOVE\n";
      throw std::runtime_error("chooseMove returned an illegal move");
    }
    writeMove(std::cout, timed.move);
    return 0;
  } catch (const std::exception& e) {
    std::cerr << "gomoku error: " << e.what() << '\n';
    return 1;
  } catch (...) {
    std::cerr << "TERMINAL_REASON PROGRAM_EXCEPTION\n";
    std::cerr << "gomoku error: unknown exception\n";
    return 1;
  }
}
