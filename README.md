# 五子棋助教端可视化原型

## Conda 环境与运行

```sh
cd /Users/hanyuhe/Desktop/design/gobang/visualizer
conda env create -f environment.yml  # 首次执行
conda activate gobang-gui
python3 gobang_gui.py
```

已创建环境后，也可以不激活它：

```sh
conda run -n gobang-gui python gobang_gui.py
```

界面选择学生提交的一份 `.cpp` 文件后，会用本机 `CXX`、`c++`、`g++` 或
`clang++` 编译它。每次点击“让学生程序走当前方”都会启动一个新进程：把当前
棋局的一行 JSON 写到标准输入，并要求学生程序在标准输出只写一行 JSON。

## 固定协议（`gomoku-1.0`）

Request 的关键字段如下，`0` 为空、`1` 为黑、`2` 为白；坐标一律为 0-based
`[row, col]`：

```json
{
  "protocol_version": "gomoku-1.0",
  "case_id": "live-0001",
  "board_size": 15,
  "board": [[0, 0, 0]],
  "side_to_move": 2,
  "last_move": [7, 7],
  "rules": {"win_length": 5, "forbidden_moves": "none", "time_limit_ms": 2000}
}
```

Response 最小格式：

```json
{"case_id":"live-0001","move":[7,8]}
```

`case_id` 可省略，但若输出则必须与 Request 一致。调试信息请写到 `stderr`，
不要写进 `stdout`。
