# 五子棋对战裁判台

用于课堂演示和验收的五子棋可视化裁判。裁判台负责维护棋盘、规则、禁手和胜负；
学生程序只需根据当前局面返回下一手。

## 运行

首次使用时创建环境：

```sh
conda env create -f environment.yml
```

之后在本目录运行：

```sh
conda run -n gobang-gui python gobang_gui.py
```

## 使用程序对战

学生提交一个可执行程序即可。在界面中为黑方和/或白方导入程序，再开始对局。

- macOS 上导入可在 macOS 运行的可执行程序。
- Windows 上导入 `.exe` 程序。
- 请勿导入来源不可信的程序；这是教学裁判台，不是安全沙箱。

支持三种模式：

- **玩家 vs 程序**：玩家点击棋盘，程序负责另一方落子。
- **程序 vs 程序**：分别导入两名选手的程序，可设置轮次和胜/和/负积分；每局会自动交换先后手。
- **自由摆棋**：双方均由鼠标落子，适合演示和调试局面。

棋盘支持 9×9 至 19×19。程序每次落子都会作为一个新的、无状态进程启动。

## 对局导出与回放

可将当前对局导出为 `gomoku-record-1.0` JSON。打开记录后，裁判会重新验证每一步的
轮次、坐标、禁手和终局，并提供逐步或自动回放。回放只读。

## 规则

完整的课堂规则、禁手定义和判定边界见 [RULES.md](RULES.md)。

- `renju_classroom`（默认）：先手首手必须落在天元；先手恰五获胜，长连、四四、三三判负；后手五连或长连获胜。
- `freestyle`：无禁手，任一方五连或以上获胜。

## 程序通信协议

每一步，裁判台会向当前程序的标准输入写入一行 `gomoku-1.0` JSON，请求中包含棋盘、
当前方、上一手、棋盘尺寸、规则及时间限制。棋盘中 `0` 为空、`1` 为黑、`2` 为白；
坐标为 0-based `[row, col]`。

例如，在 9×9 棋盘上已走完三手、轮到白方时，程序会收到：

```json
{
  "protocol_version": "gomoku-1.0",
  "case_id": "a1b2c3d4:003",
  "game_id": "a1b2c3d4",
  "ply": 3,
  "board_size": 9,
  "board": [
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 1, 2, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0]
  ],
  "side_to_move": 2,
  "player_color": 2,
  "last_move": [3, 3],
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
    "opening_center": [4, 4],
    "adjudication": "automatic",
    "time_limit_ms": 2000
  }
}
```

其中 `side_to_move` 与 `player_color` 是本次应落子的颜色；`last_move` 为上一手，开局时
两个 `last_move` 字段均为 `null`。`case_id` 用于关联本局的这一回合。

程序必须输出恰好一行带 `move` 的 JSON：

```json
{"case_id":"a1b2c3d4:007","move":[7,8]}
```

`move` 是下一手坐标。在 **程序 vs 程序** 模式中，`case_id` 必须原样回传；在玩家 vs
程序模式中可省略，但建议始终回传。其他调试信息可以输出到标准输出或标准错误，裁判会
记录到日志；但不要让其他 JSON 使用 `move` 字段。

超时、崩溃、非法落子、缺少或重复 Response 都会判该程序负。默认每手时限为 2000 ms，
可在界面调整。
