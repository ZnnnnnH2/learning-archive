# 五子棋对战裁判台

这是助教/课堂侧的可视化对战程序。学生只提交一个 C++17 单文件 AI；裁判台统一
维护棋盘和胜负，学生程序只根据当前局面返回下一手。

## Conda 环境与运行

```sh
cd /Users/hanyuhe/Desktop/design/gobang/visualizer
conda env create -f environment.yml  # 首次执行
conda activate gobang-gui
python3 gobang_gui.py
```

环境已创建时，也可以直接运行：

```sh
conda run -n gobang-gui python gobang_gui.py
```

界面会使用本机 `CXX`、`c++`、`g++` 或 `clang++` 编译学生的单文件程序。

## 对战模式

- **玩家 vs C++ 程序**：选择玩家执黑或执白；玩家点击棋盘，另一方由其 C++ 程序落子。
- **C++ 程序 vs C++ 程序**：分别为黑、白两方选择并编译一个 `.cpp` 文件，点击
  “开始 / 重新开始”后自动轮流对战。可暂停、继续和单步执行。
- **自由摆棋**：双方都由鼠标落子，用于演示与局面调试。

“交换黑白程序”应在开始对局前使用。每个 AI 回合都会启动一个**全新的、无状态的
进程**；黑白双方拥有互不共享的构建目录和可执行文件。

## 固定协议（`gomoku-1.0`）

每手棋，裁判台向当前方程序的标准输入写入一行 JSON：

```json
{
  "protocol_version": "gomoku-1.0",
  "case_id": "a1b2c3d4:007",
  "game_id": "a1b2c3d4",
  "ply": 7,
  "board_size": 15,
  "board": [[0, 0, 0]],
  "side_to_move": 2,
  "player_color": 2,
  "last_move": [7, 7],
  "last_move_color": 1,
  "rules": {
    "win_length": 5,
    "forbidden_moves": "none",
    "time_limit_ms": 2000
  }
}
```

棋盘中 `0` 为空、`1` 为黑、`2` 为白；所有坐标均为 0-based `[row, col]`。
`case_id`、`game_id`、`ply`、`player_color` 是新增关联字段，旧程序若只读取原有
棋盘字段仍可工作。

学生程序必须在标准输出只写一行 JSON：

```json
{"case_id":"a1b2c3d4:007","move":[7,8]}
```

`move` 是下一手的 `[row,col]`。在 **C++ vs C++** 模式，`case_id` 必须原样回传；
在玩家 vs C++ 模式，为兼容旧程序可以省略，但建议始终回传。调试输出请写入
`stderr`，不要写入 `stdout`。

## 裁判规则

- 棋盘、轮次、五连、和棋和合法性均由裁判台判定；程序不能修改局面。
- 每手时限由界面设置，默认 2000 ms。
- 在 **C++ vs C++** 中，超时、崩溃、非零退出、额外 stdout、无效 JSON、`case_id`
  不匹配或非法落子都会使该方判负。
- 在玩家 vs C++ 中，程序错误会暂停对局并保留局面，方便修正后使用“单步 AI”重试。

这是本地教学原型，不是操作系统级沙箱；不要在其中运行来源不可信的可执行程序。
