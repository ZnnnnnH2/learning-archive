# Gomoku 期末展评平台

本项目在本机提供一个可投屏的五子棋期末展评控制台。裁判是唯一可信棋盘持有者；学生提交公开 GitHub 仓库，仓库名和 C++ 文件名均可任意。

## 快速开始

```sh
python3 -m gomoku_display --data-dir ./event-data init \
  --framework-root /Users/hanyuhe/Desktop/gomoku
python3 -m gomoku_display --data-dir ./event-data import-roster roster.csv
python3 -m gomoku_display --data-dir ./event-data import-github
python3 -m gomoku_display --data-dir ./event-data draw --seed 20260830
python3 -m gomoku_display --data-dir ./event-data serve --port 8080
```

在操作台打开 `http://127.0.0.1:8080/`，投屏页面打开 `http://127.0.0.1:8080/display`。

`roster.csv` 至少含有 `student_id,display_name,github_url`。`github_url` 必须是公开的 `https://github.com/<owner>/<repo>`；可选 `submission_path` 指向仓库内任意 `.cpp` 文件。

`import-github` 只浅克隆公开仓库，不执行仓库代码；它会锁定 commit 并寻找唯一实现 `gomoku::chooseMove(const Position&)` 的 `.cpp`。仓库中有多个候选文件时必须填写 `submission_path`。不在名单、无法获取、无法定位实现或无法编译的提交会保留诊断并标为 DQ，不进入抽签。

## Docker 运行器

真实比赛使用 Docker。默认镜像为 `gcc:13`，需要先拉取：

```sh
docker pull gcc:13
```

运行器对学生进程使用 `--network none`、1 CPU、512 MiB、PID 上限、只读根文件系统和每手 2.1 秒硬超时。启动容器的开销不计入课程单手预算；记录的思考时间来自冻结课程入口在 `chooseMove` 返回后写出的最终 `THINK_TIME_US` 标记，并会同时保留完整 stderr 供审核。

## 规则资产

- 赛制固定为 21 人：A 组 6 人、B/C/D 组各 5 人。
- Opening pool 是 Gomocup 2026 Renju 15×15 官方公布的 12 个五手开局。
- 同分依次比较积分、同分小循环、SB、胜局、至多三轮双局加赛、白方成绩、累计可信思考时间、学号。
- `init` 会复制并 SHA-256 锁定课程框架。锁定后源框架有变化会拒绝继续比赛，需重新初始化新赛事数据目录。

所有赛事决定均写入 SQLite 和 append-only JSONL 事件日志；每局可从 opening 开始逐手重放并再次调用同一冻结规则库验证。
