# 五子棋对战裁判台

这是助教/课堂侧的可视化对战程序。学生只提交一个 C++17 单文件 AI；裁判台统一
维护棋盘、胜负和禁手，学生程序只根据当前局面返回下一手。默认使用“连珠禁手
（课堂；先手首子天元）”，也可切换为无禁手的自由五子棋。

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
- **C++ 程序 vs C++ 程序**：分别选择并编译两份 `.cpp` 文件后，可设置对战轮次
  和“胜 / 和 / 负”积分。每盘结束，两个程序会自动交换先手（也就是交换本局黑白），
  积分表按稳定的选手 A/B 汇总；可暂停、继续、单步或终止系列赛。
- **自由摆棋**：双方都由鼠标落子，用于演示与局面调试。

棋盘可以选择 9×9、11×11、13×13、15×15、17×17 或 19×19；大小会写入每手
Request。“交换黑白程序”应在开始对局前使用。每个 AI 回合都会启动一个**全新的、
无状态的进程**；两份程序拥有互不共享的构建目录和可执行文件。

## 导出与文件回放

“导出当前对局”会把已走的每一手、棋盘大小、规则、选手标识和结果保存为
`gomoku-record-1.0` JSON 文件；未结束的局面也可以导出。点击“打开对局回放”载入
文件后，裁判会逐手重新验证棋谱的轮次、坐标、禁手和终局，再提供上一步、下一步与
自动回放。回放是只读的；“退出回放”会回到同尺寸、同规则的空棋盘。

## 规则与禁手

完整的课堂规则、禁手定义、判定优先级及与正式 RIF 赛事规则的边界，见
[RULES.md](RULES.md)。

界面提供两个预设：

- `renju_classroom`（默认）：**先手（本局黑方）**首手必须落在当前棋盘天元；
  先手恰五获胜，长连、四四、三三判负；后手五连或长连获胜。AI 系列赛中每盘交换
  先手，因此禁手也随本局的先手程序轮换。
- `freestyle`：无禁手，黑白任一方五连或更多即胜。

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
    "id": "renju_classroom",
    "win_length": 5,
    "black_win": "exactly_five",
    "white_win": "five_or_more",
    "first_player_color": 1,
    "first_player_win": "exactly_five",
    "forbidden_moves": "first_player_overline_double_four_double_three",
    "forbidden_player": "first_player_black",
    "opening": "first_player_center",
    "opening_center": [7, 7],
    "adjudication": "automatic",
    "time_limit_ms": 2000
  }
}
```

棋盘中 `0` 为空、`1` 为黑、`2` 为白；所有坐标均为 0-based `[row, col]`。
`case_id`、`game_id`、`ply`、`player_color` 是新增关联字段。`rules` 也是裁判协议
的一部分：学生 AI 必须据此跳过禁手点；其中 `first_player_color: 1` 表示本局的先手
始终是黑方。不要假定任何一局都没有禁手，也不要把选手身份与固定颜色绑定。

学生程序的标准输出必须包含**恰好一行**带 `move` 的 JSON Response：

```json
{"case_id":"a1b2c3d4:007","move":[7,8]}
```

`move` 是下一手的 `[row,col]`。在 **C++ vs C++** 模式，`case_id` 必须原样回传；
在玩家 vs C++ 模式，为兼容旧程序可以省略，但建议始终回传。

除这行 Response 外，学生可以在 `stdout` 或 `stderr` 输出任意调试文字；裁判台会将其
记入“对局 / 编译日志”，不把它当作协议错误。若 `stdout` 没有 Response、或出现两行及
以上带 `move` 的 JSON Response，才会判程序输出错误。单回合的 stdout 和 stderr 仍各有
1 MiB 上限；若调试信息本身是 JSON，请不要使用 `move` 字段。

## 裁判与程序错误

- 棋盘、轮次、五连、和棋、禁手和合法性均由裁判台判定；程序不能修改局面。
- 每手时限由界面设置，默认 2000 ms。
- 在 **C++ vs C++** 中，超时、崩溃、非零退出、缺少/重复 Response、无效 Response JSON、
  `case_id` 不匹配或非法落子都会使该方判负；额外调试输出本身不会判负。
- 在玩家 vs C++ 中，程序错误会暂停对局并保留局面，方便修正后使用“单步 AI”重试。
- 无论何种模式，连珠预设下走出先手（本局黑方）禁手均是**规则判负**，不会被当成
  可重试的程序格式错误。

规则单元测试可用以下命令运行：

```sh
conda run -n gobang-gui python -m unittest discover -s tests -v
```

这是本地教学原型，不是操作系统级沙箱；不要在其中运行来源不可信的可执行程序。
