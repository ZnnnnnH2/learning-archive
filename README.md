# PySide6 三维魔方 Solver 可视化器

这是给学生裸文本 solver 使用的三维展示工具。它不实现搜索、不编译学生代码、不读写回放文件；它只校验初态和 stdout 动作流，在一个 PySide6 `QOpenGLWidget` 中执行对应的 3D 动画。

## 安装与启动

需要 Python 3.12。推荐使用 Conda；该方案只安装 Python 与 PySide6：

```bash
cd /Users/hanyuhe/Desktop/design/cube/visualizer
conda env create -f environment.yml
conda activate cube-visualizer
python app.py
```

若环境已存在，使用下面命令同步配置：

```bash
conda env update -f environment.yml --prune
```

也可以创建标准 `venv`：

```bash
cd /Users/hanyuhe/Desktop/design/cube/visualizer
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Windows 下将最后两条命令中的 `.venv/bin/python` 替换为 `.venv\\Scripts\\python.exe`。PySide6 自带 Qt 的 OpenGL 支持，项目没有其他直接依赖。

## 学生 solver 固定接口

在界面中选择**已经编译好的可执行文件绝对路径**。可视化器用无 shell 的 `QProcess` 启动它，最长运行 5 分钟；stdout 和 stderr 各最多保留 1 MiB。

不要选择 `ms-Astar.cpp` 这类源码文件；它不能直接运行。每个系统都必须使用在**该系统上编译**的程序：macOS 的 Mach-O 可执行文件与 Windows 的 `.exe` 不能互相运行。

macOS 上可在终端编译，再在界面中选择生成的无后缀文件：

```bash
clang++ -std=c++17 -O2 /完整路径/ms-Astar.cpp -o /完整路径/ms-Astar
```

Windows 上可使用 Visual Studio 的 Developer PowerShell：

```powershell
cl /std:c++17 /O2 C:\完整路径\ms-Astar.cpp /Fe:C:\完整路径\ms-Astar.exe
```

也可使用 MinGW：

```powershell
g++ -std=c++17 -O2 C:\完整路径\ms-Astar.cpp -o C:\完整路径\ms-Astar.exe
```

工具不会替学生编译源码，避免把编译器参数、依赖和运行时错误混入 solver 协议检查；误选源码、跨平台程序或没有执行权限的文件时，界面会在启动前说明原因。

stdin 是编辑器里的原始 UTF-8 文本，格式严格为以下六个区块，顺序不可改变。每个格子都是一个非空白、可打印 ASCII 字符；一共恰好六种字符，每种九张。

题面采用的展开图为 `back` 在 `up` 上方、`front` 和 `down` 在其下方、`left/up/right` 横向相连。工具会自动把该展开图转成三维坐标：`left` 逆时针 90°、`right` 顺时针 90°、`back` 180°，其余三面不转。不要自行旋转输入矩阵。

```text
back:
g g r
r y r
y b y

down:
r r b
w r w
r r b

front:
w p w
g w g
b b p

left:
w w r
p g g
w y g

right:
p y y
b b b
b w y

up:
g y g
p p p
p y p
```

stdout 只能输出动作 token，空白分隔、以换行结束，例如：

```text
3- 6+ 4-
```

每个 token 只能是 `0+` 至 `8-`。stdout 中的调试文字会被判定为协议错误；请将调试信息输出到 stderr，界面会单独展示它。空 stdout 仅在输入初态已经六面同色时被视为完成。

动作沿用课件定义：`0..2` 为从左到右的三层，`3..5` 为从下到上的三层，`6..8` 为从前到后的三层；`+/-` 表示课件所定义的相反 90°方向。标准色标为 `y/r/g/p/w/b`；默认已复原视图按题面示例中心色显示为 left=`g`、front=`w`、right=`b`、up=`p`、down=`r`、back=`y`。其他满足六色九张规则的字符也会以稳定的可区分颜色显示。

## 操作

- 左键拖动旋转相机，滚轮缩放，“重置视角”恢复默认观察角度。
- solver 成功后，工具会预计算每一步状态，并自动播放；可暂停、上一步、下一步，或拖动滑块直接跳转。
- 每一层先显示 90°动画，动画结束才提交下一离散状态，因此三维画面和规则状态保持一致。
- 当前会话只保存在内存中：初态、动作、每步状态、stdout、stderr 和当前位置会在关闭窗口或成功启动下一次 solver 后清空。

## 自检

```bash
conda run --no-capture-output -n cube-visualizer python -m unittest discover -s tests -v
conda run --no-capture-output -n cube-visualizer python app.py --smoke-test

# 或在 venv 中：
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python app.py --smoke-test
```

测试覆盖课程输入、18 个动作的方向/互逆/四次复原、3D 几何和动画层、时间轴，以及 `QProcess` 的合法/非法 stdout、非零退出、超时、取消和输出上限。
