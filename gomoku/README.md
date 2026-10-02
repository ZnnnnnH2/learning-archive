# 五子棋 / Renju 学生起始框架

本项目将规则框架和学生算法分开。框架负责读取完整局面、维护棋盘、判断合法落子、检查黑棋禁手、计时和输出；学生只实现自己的搜索算法。

文件职责如下：

- `include/gomoku.hpp`：课程组提供的棋盘和规则库，只读。
- `include/student_api.hpp`：学生函数声明。
- `src/main.cpp`：课程组入口，负责解析、计时、合法性校验和输出，不应修改。
- `src/student_move.cpp`：学生唯一需要提交的文件。

## 学生需要提交什么

学生只提交一个文件：

```text
src/student_move.cpp
```

这个文件必须在 `gomoku` 命名空间中提供以下函数：

```cpp
namespace gomoku {
Move chooseMove(const Position& position);
}
```

可以在 `student_move.cpp` 中自由定义辅助函数、类、结构体、常量和搜索算法，但不要：

- 定义 `main`；
- 修改 `include/gomoku.hpp`、`include/student_api.hpp` 或 `src/main.cpp`；
- 向标准输出写入调试信息；
- 启动额外进程或通过后台线程绕过计时；`chooseMove` 返回时，学生创建的线程和异步任务必须已经结束。

函数签名必须完全匹配 `gomoku::Move chooseMove(const gomoku::Position&)`，不能声明为 `static`，也不能把 `chooseMove` 放进匿名命名空间；它必须具有外部链接，供框架入口调用。辅助函数和内部类可以放进匿名命名空间。

提交时，课程组可以用学生文件替换模板中的 `src/student_move.cpp`，再编译同一份框架。也可以通过 CMake 参数指定提交文件：

```sh
cmake -S . -B build -DSTUDENT_SOURCE=D:/提交目录/student_move.cpp
```

学生文件通过 `include/student_api.hpp` 获得公共接口。

## 从哪里开始

1. 安装支持 C++17 的编译器和 CMake。
2. 阅读 `include/gomoku.hpp` 中的 `Position`、`Board` 和公共枚举。
3. 只在 `src/student_move.cpp` 中实现 `chooseMove`。
4. 使用 `position.board` 读取当前局面，枚举候选点并进行搜索。
5. 编译并运行测试。

模板中的实现只返回第一个合法点，仅用于验证通信和接口。

## `using namespace gomoku`

可以在学生的 `.cpp` 文件中使用，但函数定义仍应放在 `gomoku` 命名空间中：

```cpp
#include "student_api.hpp"
using namespace gomoku;

namespace gomoku {
Move chooseMove(const Position& position) {
    // ...
}
}
```

上面的函数定义应位于 `namespace gomoku { ... }` 中；也可以写成带完整限定名的定义。

这样就可以直接写 `Position`、`Board`、`Move` 和 `Cell`。注意：仅写 `using namespace gomoku;` 不会把一个全局的 `Move chooseMove(...)` 自动变成 `gomoku::chooseMove`，因此请按上面的方式显式包在命名空间中。不要把 `using namespace gomoku;` 放进公共头文件，否则会污染所有包含该头文件的代码并可能造成命名冲突。

## `Position` 类

`Position` 是本回合传给 `chooseMove` 的完整局面。每次轮到程序行棋时，裁判启动一个新的进程，因此学生不能依赖上一次进程中的内存状态。

| 成员 | 类型 | 含义 | 默认值 |
|---|---|---|---|
| `board` | `Board` | 当前完整棋盘 | 空棋盘 |
| `myColor` | `Cell` | 本程序执棋颜色，也是当前行棋方 | `Cell::Black` |
| `moveNumber` | `int` | 当前总手数，包含 Opening 预置的棋子 | `0` |
| `timeoutTurnMs` | `int` | 本回合时间预算，单位毫秒 | `2000` |
| `timeLeftMs` | `int` | 本局剩余时间预算，单位毫秒 | `45000` |
| `seed` | `unsigned long long` | 裁判提供的随机种子 | `0` |

典型入口：

```cpp
namespace gomoku {
Move chooseMove(const Position& position) {
    const Board& board = position.board;
    const Cell me = position.myColor;

    // 在 board 上搜索，最后返回一个合法 Move。
    return {7, 7};
}
}
```

`timeoutTurnMs` 和 `timeLeftMs` 是裁判传入的预算信息，学生可以据此决定迭代加深何时停止。真正的耗时由框架从调用 `chooseMove` 前开始测量，到函数返回后结束。

## `Board` 类

`Board` 表示固定大小的 15×15 棋盘，是可复制的值对象，适合用于 Minimax、Alpha-Beta、PVS 等搜索。

### 棋盘坐标和棋子

- 坐标范围：`x = 0..14`、`y = 0..14`。
- `x` 从左向右增加，`y` 从上向下增加。
- `Cell::Empty` 对应 `.`, `Cell::Black` 对应 `B`, `Cell::White` 对应 `W`。

### 查询接口

```cpp
bool inBounds(Move move) const; // 是否在棋盘范围内
Cell at(Move move) const;       // 查询棋子；越界返回 Empty
bool empty(Move move) const;    // 是否为空位
int moves() const;              // 当前棋子总数
```

### 合法性和模拟落子

```cpp
bool isLegal(Move move, Cell color) const;
bool checkMove(Move move, Cell color) const;
bool play(Move move, Cell color);
```

`isLegal` 和双参数 `checkMove` 等价。白棋检查越界和占用；黑棋还检查恰五优先、长连、四四和三三禁手。`play` 只有在落子合法时才修改棋盘，并返回 `true`。

搜索时复制棋盘：

```cpp
Board next = position.board;
Move candidate{7, 7};
if (next.play(candidate, me)) {
    // candidate 已写入 next，可继续搜索 next
}
// position.board 没有改变
```

### 终局和禁手

```cpp
MoveStatus checkBlackMove(Move move) const;
MoveStatus checkMove(Move move) const;       // 黑棋详细结果
bool hasAnyLegalMove(Cell color) const;
Result resultAfter(Move move, Cell color) const;
Result state(Cell colorToMove) const;
```

黑棋详细状态包括 `Legal`、`OutOfBounds`、`Occupied`、`Overline`、`DoubleFour` 和 `DoubleThree`。恰好五连优先于禁手。`resultAfter` 会复制棋盘模拟落子，不会修改原对象，并按“合法性 → 禁手 → 胜负 → 和棋”判断。

`setCell` 只用于裁判解析或测试构造已有局面：

```cpp
Board board;
board.setCell({7, 7}, Cell::Black);
```

它不检查禁手；学生搜索产生的新走法必须使用 `play`。

## 输入格式

每个进程只处理一个回合：

```text
GOMOKU 15
...............
...............
...............
...............
...............
...............
...............
...............
...............
...............
...............
...............
...............
...............
...............
...............
MY W SIDE W MOVE 5 TIME_TURN 2000 TIME_LEFT 45000 SEED 42
```

棋盘后面的元数据顺序可以调整。`SIDE` 是协议完整性字段，必须与 `MY` 相同；它不会重复存储在 `Position` 中。`MOVE` 包含 Opening 的预置手数。

## 计时和输出

框架的计时区间严格为（使用单调的 `std::chrono::steady_clock`）：

```text
开始计时
    chooseMove(position)       // 学生文件中的函数
结束计时
```

计时开始点在函数调用前，结束点在函数返回值已经保存后。局面解析、返回后的合法性检查和坐标输出不计入学生用时。实测时间会写入标准错误，例如：

```text
THINK_TIME_US 18342
```

标准输出必须且只能包含一行坐标：

```text
7,8
```

调试信息必须写入标准错误。框架会在函数返回后严格按输入预算检查 `timeoutTurnMs` 和 `timeLeftMs`，并输出 `TERMINAL_REASON TURN_TIMEOUT` 或 `MATCH_TIMEOUT`。`THINK_TIME_US` 只是本地诊断字段，正式 Judge 应以父进程/看门狗的实际计时为准，不应信任学生自行输出的日志。规则允许的系统容差由正式 Judge 负责，不应由学生主动使用。主程序无法在 `chooseMove` 永久阻塞时自行停止它，因此硬超时必须由 Judge 的父进程/看门狗实现。由于每回合都会启动新进程，本程序不累计跨回合时间；Judge 应将每回合的实际用时累加并更新下一回合的 `timeLeftMs`。

## 构建与测试

```sh
cmake -S . -B build
cmake --build build --config Release
ctest --test-dir build --output-on-failure -C Release
```

`gomoku_player` 由 `src/main.cpp` 和 `STUDENT_SOURCE` 指定的学生文件链接生成。`src/main.cpp` 是框架入口，默认的 `src/student_move.cpp` 是学生可替换文件。

## IDE 配置

如果编辑器提示找不到 `gomoku.hpp` 或 `gomoku` 未声明，请打开项目根目录 `D:/Codes/gomoku`，重新执行 CMake Configure。仓库提供 `.vscode/c_cpp_properties.json`，已将 `include/` 加入 IntelliSense 搜索路径。
