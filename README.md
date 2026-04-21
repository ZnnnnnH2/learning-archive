# SideShell

SideShell 是一个面向开发工作流的桌面终端壳。它把“项目”和“终端会话”作为一等对象固定在侧边栏中，适合同时维护多个仓库、为同一项目打开多个 shell，或者把 Codex、Claude、Gemini、OpenCode 这类 agent CLI 会话和普通终端放在同一个工作区里管理。

基于 `Tauri 2`、`React 19` 和 `xterm.js` 构建，核心目标不是替代完整终端生态，而是把项目切换、会话保活、状态感知和 agent 恢复做得足够直接。

## 为什么是 SideShell

- 以项目为中心组织终端，而不是只堆标签页。
- 同一项目下可以长期保留多个 shell，切换时不会销毁后台任务。
- 侧边栏直接展示 shell 的名称、cwd、运行状态和 attention 提醒。
- 针对 agent CLI 做了自动命名、恢复目标保存和惰性恢复。
- 桌面应用形态更适合把多个开发上下文固定下来长期使用。

## 核心能力

### 项目与会话管理

- 按项目分组管理多个 shell，会话切换是即时的。
- 支持新增项目、重命名、移除、复制路径和项目搜索。
- 支持在项目下新建 shell、克隆 shell、关闭 shell 和拖拽重排。

### 后台保活

- 切换到其他 shell 时，原 PTY 不会被销毁。
- 正在运行的服务、构建、测试和交互式命令可以继续保持。

### 智能命名与状态感知

- 自动识别常见 agent 启动命令并生成更可读的会话名称。
- 优先使用终端发出的 title 更新 shell 名称，缺失时再回退到 agent 标签和首条消息摘要。
- 解析 `OSC 133`、终端标题、`BEL`、`OSC 9` 等信号，给出 `running`、`waiting`、`error`、`exited` 和 attention 状态。
- cwd 变化会同步到侧边栏，方便快速判断每个 shell 当前所在目录。

### Shell Integration

- 对 `bash`、`zsh`、`fish`、`pwsh`、`powershell` 自动注入 prompt hook。
- 尽量稳定发出 `OSC 7` 和 `OSC 133`，让 cwd 与命令生命周期不再只依赖标题猜测。

### 会话持久化与恢复

- 项目列表、shell 元数据、cwd、激活项、侧边栏宽度和终端设置会保存到本地配置目录。
- 应用重开后，shell 默认惰性恢复，只有真正点开时才创建 PTY。
- 对识别到的 agent shell，会在首次打开时尝试执行对应的 resume / continue 命令。

### 终端设置

- 可配置默认 shell 可执行文件。
- 可调整终端字体。
- 可为新启动的 shell 注入额外环境变量。
- 可配置 `BEL` / `OSC 9` 告警弹窗停留时长，默认 3 秒。

## 适合的场景

- 一个项目里同时跑前端、后端、构建和测试脚本。
- 多个仓库并行开发，需要稳定保留上下文。
- 使用终端驱动的 AI agent 工具，希望按项目归档多个对话会话。
- 想要一个比传统 terminal tabs 更偏项目视角的桌面终端。

## 技术栈

- Frontend: `React 19`、`TypeScript`、`Zustand`、`Tailwind CSS v4`、`xterm.js`、`Radix UI`
- Desktop: `Tauri 2`
- Backend: `Rust`、`portable-pty`

## 快速开始

### 前置要求

- Node.js
- `pnpm`
- Rust toolchain
- Tauri 对应平台的系统依赖

### 安装依赖

```bash
pnpm install
```

### 启动前端开发服务器

```bash
pnpm dev
```

### 启动桌面应用开发模式

```bash
pnpm tauri dev
```

### 构建桌面应用

```bash
pnpm tauri build
```

### 前端产物验证

```bash
pnpm build
pnpm preview
```

## 常用脚本

| 命令 | 说明 |
| --- | --- |
| `pnpm dev` | 启动 Vite 开发服务器 |
| `pnpm build` | 构建前端产物 |
| `pnpm preview` | 本地预览前端构建结果 |
| `pnpm tauri dev` | 启动桌面开发模式 |
| `pnpm tauri build` | 打包桌面应用 |
| `pnpm release` | 执行项目内置发布脚本 |
| `pnpm release:full` | 生成完整 Windows 安装包构建 |

## 快捷键

| 快捷键 | 作用 |
| --- | --- |
| `Ctrl/Cmd + B` | 显示或隐藏侧边栏 |
| `Ctrl/Cmd + T` | 在当前项目下新建 shell |
| `Ctrl/Cmd + Shift + D` | 克隆当前 shell |
| `Ctrl/Cmd + W` | 关闭当前 shell |
| `Ctrl/Cmd + 1..9` | 按顺序切换第 1 到第 9 个 shell |

## 运行细节

- Windows 下优先使用 `pwsh.exe`，不存在时回退到 `powershell.exe`。
- macOS / Linux 下默认使用当前环境的 `$SHELL`，未设置时回退到 `/bin/bash`。
- 恢复会话时，如果原 cwd 不存在，会回退到对应项目根目录。
- agent shell 的恢复属于 best-effort 行为，依赖已保存的恢复目标或恢复命令。
- 本地状态文件保存在系统配置目录下的 `SideShell/sessions.json`。

## 目录结构

```text
src/        React 前端、组件和状态管理
src-tauri/  Tauri / Rust 后端、PTY 管理与持久化
scripts/    发布和辅助脚本
public/     静态资源
```

## 当前定位

SideShell 当前聚焦于开发者和 agent 工作流：项目分组、多会话切换、状态可见、惰性恢复。它更像一个为多上下文开发设计的桌面终端工作台，而不是一个试图覆盖所有终端能力的“大而全”产品。
