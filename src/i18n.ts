import type { AppLocale } from "./types";

const EN_MESSAGES = {
  "app.name": "SideShell",
  "app.loading": "loading...",
  "sidebar.title.settings": "Settings",
  "sidebar.title.addProject": "Add project folder",
  "sidebar.title.showSidebar": "Show sidebar (Ctrl+B)",
  "sidebar.title.hideSidebar": "Hide sidebar (Ctrl+B)",
  "sidebar.searchPlaceholder": "Search projects...",
  "sidebar.emptyTitle": "No projects yet.",
  "sidebar.emptyDescription": "Add a folder to spin up shells.",
  "sidebar.emptyAction": "+ Add folder",
  "project.newShellInProject": "New shell in this project",
  "project.menu.newShell": "New shell",
  "project.menu.rename": "Rename",
  "project.menu.copyPath": "Copy path",
  "project.menu.openIn": "Open in",
  "project.menu.fileExplorer": "File Explorer",
  "project.menu.removeProject": "Remove project",
  "project.error.openProject": "Failed to open project",
  "project.error.openProjectFolder": "Failed to open project folder",
  "shell.closeShell": "Close shell",
  "shell.menu.cloneShell": "Clone shell",
  "shell.menu.rename": "Rename",
  "shell.menu.useAutoName": "Use auto name",
  "shell.menu.copyCwd": "Copy cwd",
  "shell.menu.close": "Close",
  "shell.badge.pendingRestore": "Pending",
  "welcome.tagline": "Project-aware terminal with a tree-shaped sidebar.",
  "welcome.addProject": "Add a project folder",
  "welcome.description":
    "Each project can host multiple shells. Switching is instant - PTYs stay running in the background.",
  "restore.badge": "Restored Shell",
  "restore.description":
    "This shell was restored from app state. Choose whether to open the agent CLI's own resume flow, start a fresh agent session, or open a plain terminal.",
  "restore.action.resume": "Resume conversation",
  "restore.action.resume.description.codex":
    "Open Codex's built-in resume picker.",
  "restore.action.resume.description.claude":
    "Open Claude's built-in resume picker.",
  "restore.action.resume.description.gemini":
    "Show Gemini's saved session list so you can choose one manually.",
  "restore.action.resume.description.opencode":
    "Show OpenCode's saved session list so you can choose one manually.",
  "restore.action.resume.description.generic":
    "Open the CLI's own resume flow instead of restoring a specific session in SideShell.",
  "restore.action.newSession": "Start new session",
  "restore.action.newSession.description":
    "Launch the same agent here without restoring the old thread.",
  "restore.action.openTerminal": "Open terminal",
  "restore.action.openTerminal.description":
    "Discard agent restore state and open a plain shell.",
  "restore.action.change": "Change...",
  "restore.compact.hint":
    "Press Enter to run the default action. Press Esc or choose Change to see all options.",
  "restore.meta.agent": "Agent",
  "restore.meta.cwd": "Directory",
  "restore.meta.default": "Default",
  "restore.default.remember": "Remember this as the default for {agent}",
  "restore.default.current": "Current default for {agent}: {action}",
  "restore.default.clear": "Forget default",
  "terminalHost.emptyTitle": "Select a shell to start or resume it.",
  "terminalHost.emptyDescription":
    "Restored agent shells stay idle until you choose how to start them.",
  "settings.title": "Settings",
  "settings.description":
    "Font and interface language changes apply immediately. Shell executable and extra environment variables apply to newly started terminals.",
  "settings.close": "Close settings",
  "settings.field.language.label": "Interface language",
  "settings.field.language.hint":
    "Choose the language used by SideShell's interface, dialogs, and alerts.",
  "settings.field.language.option.en": "English",
  "settings.field.language.option.zh-CN": "Simplified Chinese",
  "settings.field.shellExecutable.label": "Shell executable",
  "settings.field.shellExecutable.hint":
    "Leave blank to use the current auto-detected default shell.",
  "settings.field.fontFamily.label": "Terminal font family",
  "settings.field.fontFamily.hint":
    "Use a CJK-capable monospaced font stack if Chinese text looks garbled.",
  "settings.field.extraEnv.label": "Extra environment variables",
  "settings.field.extraEnv.hint":
    "One KEY=VALUE per line. Blank lines and lines starting with # are ignored.",
  "settings.field.alertDuration.label": "Alert popup duration",
  "settings.field.alertDuration.hint":
    "How long BEL / OSC 9 alert toasts stay visible. Defaults to {seconds} seconds.",
  "settings.field.codexTitle.label": "Codex session title",
  "settings.field.codexTitle.hint":
    "Only affects Codex shells. When enabled, SideShell uses its own task summary as the shell title, but keeps Codex's spinner when one is present.",
  "settings.field.codexTitle.checkbox": "Use SideShell summary title for Codex",
  "settings.field.codexTitle.checkboxHint":
    "Off: prefer Codex's original terminal title. On: show the current task summary instead, with Codex's spinner preserved.",
  "settings.field.shortcuts.label": "Keyboard shortcuts",
  "settings.field.shortcuts.hint":
    "Terminal shortcuts only run inside the terminal. App shortcuts are ignored while a terminal or settings control has focus.",
  "settings.shortcuts.scope.terminal": "Terminal",
  "settings.shortcuts.scope.app": "App",
  "settings.shortcuts.enable": "Enable shortcut",
  "settings.shortcuts.record": "Record",
  "settings.shortcuts.recording": "Press keys",
  "settings.shortcuts.clear": "Clear shortcut",
  "settings.shortcuts.reset": "Reset shortcut",
  "settings.shortcuts.disabled": "Disabled",
  "settings.shortcuts.empty": "No shortcut",
  "settings.shortcuts.action.terminal.copySelection": "Copy terminal selection",
  "settings.shortcuts.action.terminal.pasteClipboard": "Paste clipboard",
  "settings.shortcuts.action.app.toggleSidebar": "Toggle sidebar",
  "settings.shortcuts.action.app.newShell": "New shell",
  "settings.shortcuts.action.app.cloneShell": "Clone shell",
  "settings.shortcuts.action.app.closeShell": "Close shell",
  "settings.shortcuts.action.app.focusShell": "Focus shell {number}",
  "settings.action.reset": "Reset to defaults",
  "settings.action.cancel": "Cancel",
  "settings.action.save": "Save",
  "settings.validation.env.invalid":
    "Invalid environment variable on line {line}. Use KEY=VALUE.",
  "settings.validation.env.missingKey":
    "Invalid environment variable on line {line}. Missing key.",
  "settings.validation.shortcuts.conflict":
    "{scope} shortcut {binding} is assigned to multiple actions: {actions}.",
  "status.needsAttention": "needs attention",
  "status.running": "running",
  "status.waiting": "waiting for input",
  "status.error": "error",
  "status.exited": "exited",
  "status.idle": "idle",
  "alerts.defaultProject": "Project",
  "alerts.defaultShell": "Shell",
  "alerts.defaultBody": "{shellName} in {projectName} needs attention.",
  "alerts.overlay.jump": "Click to jump to shell",
  "alerts.overlay.dismiss": "Dismiss alert",
  "terminal.startFailed": "[SideShell] Failed to start shell.",
} as const;

export type MessageKey = keyof typeof EN_MESSAGES;

const ZH_CN_MESSAGES: Record<MessageKey, string> = {
  "app.name": "SideShell",
  "app.loading": "加载中...",
  "sidebar.title.settings": "设置",
  "sidebar.title.addProject": "添加项目文件夹",
  "sidebar.title.showSidebar": "显示侧边栏 (Ctrl+B)",
  "sidebar.title.hideSidebar": "隐藏侧边栏 (Ctrl+B)",
  "sidebar.searchPlaceholder": "搜索项目...",
  "sidebar.emptyTitle": "还没有项目。",
  "sidebar.emptyDescription": "添加一个文件夹来启动 shell。",
  "sidebar.emptyAction": "+ 添加文件夹",
  "project.newShellInProject": "在该项目中新建 shell",
  "project.menu.newShell": "新建 shell",
  "project.menu.rename": "重命名",
  "project.menu.copyPath": "复制路径",
  "project.menu.openIn": "打开方式",
  "project.menu.fileExplorer": "文件资源管理器",
  "project.menu.removeProject": "移除项目",
  "project.error.openProject": "打开项目失败",
  "project.error.openProjectFolder": "打开项目文件夹失败",
  "shell.closeShell": "关闭 shell",
  "shell.menu.cloneShell": "克隆 shell",
  "shell.menu.rename": "重命名",
  "shell.menu.useAutoName": "使用自动名称",
  "shell.menu.copyCwd": "复制当前目录",
  "shell.menu.close": "关闭",
  "shell.badge.pendingRestore": "待恢复",
  "welcome.tagline": "按项目组织的终端工作台，配合树形侧边栏管理上下文。",
  "welcome.addProject": "添加项目文件夹",
  "welcome.description":
    "每个项目都可以承载多个 shell。切换是即时的，PTY 会继续在后台运行。",
  "restore.badge": "已恢复的 Shell",
  "restore.description":
    "这个 shell 是从应用状态中恢复出来的。你可以选择进入 agent CLI 自己的恢复入口、启动一个新的 agent 会话，或直接打开普通终端。",
  "restore.action.resume": "继续会话",
  "restore.action.resume.description.codex":
    "打开 Codex 自带的恢复选择器。",
  "restore.action.resume.description.claude":
    "打开 Claude 自带的恢复选择器。",
  "restore.action.resume.description.gemini":
    "显示 Gemini 已保存的会话列表，方便你手动选择。",
  "restore.action.resume.description.opencode":
    "显示 OpenCode 已保存的会话列表，方便你手动选择。",
  "restore.action.resume.description.generic":
    "进入 CLI 自己的恢复流程，而不是由 SideShell 直接恢复到某个具体会话。",
  "restore.action.newSession": "启动新会话",
  "restore.action.newSession.description":
    "在这里启动同一个 agent，但不恢复旧线程。",
  "restore.action.openTerminal": "打开终端",
  "restore.action.openTerminal.description":
    "丢弃 agent 恢复状态，直接打开普通 shell。",
  "restore.action.change": "更改...",
  "restore.compact.hint":
    "按 Enter 执行默认动作，按 Esc 或点击“更改...”查看全部选项。",
  "restore.meta.agent": "Agent",
  "restore.meta.cwd": "目录",
  "restore.meta.default": "默认动作",
  "restore.default.remember": "记住为 {agent} 的默认恢复动作",
  "restore.default.current": "{agent} 当前默认动作：{action}",
  "restore.default.clear": "清除默认值",
  "terminalHost.emptyTitle": "选择一个 shell 来启动或恢复。",
  "terminalHost.emptyDescription":
    "恢复出来的 agent shell 会保持空闲，直到你决定如何启动它。",
  "settings.title": "设置",
  "settings.description":
    "字体和界面语言修改会立即生效。Shell 可执行文件和额外环境变量会应用到之后新启动的终端。",
  "settings.close": "关闭设置",
  "settings.field.language.label": "界面语言",
  "settings.field.language.hint":
    "选择 SideShell 界面、对话框和告警所使用的语言。",
  "settings.field.language.option.en": "English",
  "settings.field.language.option.zh-CN": "简体中文",
  "settings.field.shellExecutable.label": "Shell 可执行文件",
  "settings.field.shellExecutable.hint":
    "留空则继续使用当前自动检测到的默认 shell。",
  "settings.field.fontFamily.label": "终端字体族",
  "settings.field.fontFamily.hint":
    "如果中文显示错乱，请使用支持 CJK 的等宽字体栈。",
  "settings.field.extraEnv.label": "额外环境变量",
  "settings.field.extraEnv.hint":
    "每行一个 KEY=VALUE。空行和以 # 开头的行会被忽略。",
  "settings.field.alertDuration.label": "告警弹窗时长",
  "settings.field.alertDuration.hint":
    "BEL / OSC 9 告警弹窗的显示时长。默认 {seconds} 秒。",
  "settings.field.codexTitle.label": "Codex 会话标题",
  "settings.field.codexTitle.hint":
    "仅影响 Codex shell。启用后，SideShell 会用自己的任务摘要作为 shell 标题，同时保留 Codex 的 spinner。",
  "settings.field.codexTitle.checkbox": "对 Codex 使用 SideShell 摘要标题",
  "settings.field.codexTitle.checkboxHint":
    "关闭：优先使用 Codex 原始终端标题。开启：改为显示当前任务摘要，同时保留 Codex 的 spinner。",
  "settings.field.shortcuts.label": "快捷键",
  "settings.field.shortcuts.hint":
    "终端快捷键只在终端内生效。终端或设置控件获得焦点时，应用快捷键会避让。",
  "settings.shortcuts.scope.terminal": "终端",
  "settings.shortcuts.scope.app": "应用",
  "settings.shortcuts.enable": "启用快捷键",
  "settings.shortcuts.record": "录入",
  "settings.shortcuts.recording": "按下快捷键",
  "settings.shortcuts.clear": "清除快捷键",
  "settings.shortcuts.reset": "恢复快捷键默认值",
  "settings.shortcuts.disabled": "已禁用",
  "settings.shortcuts.empty": "未设置快捷键",
  "settings.shortcuts.action.terminal.copySelection": "复制终端选区",
  "settings.shortcuts.action.terminal.pasteClipboard": "粘贴剪贴板",
  "settings.shortcuts.action.app.toggleSidebar": "显示或隐藏侧边栏",
  "settings.shortcuts.action.app.newShell": "新建 shell",
  "settings.shortcuts.action.app.cloneShell": "克隆 shell",
  "settings.shortcuts.action.app.closeShell": "关闭 shell",
  "settings.shortcuts.action.app.focusShell": "切换到第 {number} 个 shell",
  "settings.action.reset": "恢复默认",
  "settings.action.cancel": "取消",
  "settings.action.save": "保存",
  "settings.validation.env.invalid":
    "第 {line} 行的环境变量格式不合法。请使用 KEY=VALUE。",
  "settings.validation.env.missingKey":
    "第 {line} 行的环境变量格式不合法，缺少键名。",
  "settings.validation.shortcuts.conflict":
    "{scope}快捷键 {binding} 同时分配给了多个动作：{actions}。",
  "status.needsAttention": "需要关注",
  "status.running": "运行中",
  "status.waiting": "等待输入",
  "status.error": "错误",
  "status.exited": "已退出",
  "status.idle": "空闲",
  "alerts.defaultProject": "项目",
  "alerts.defaultShell": "Shell",
  "alerts.defaultBody": "{projectName} 中的 {shellName} 需要关注。",
  "alerts.overlay.jump": "点击跳转到该 shell",
  "alerts.overlay.dismiss": "关闭告警",
  "terminal.startFailed": "[SideShell] 启动 shell 失败。",
};

const MESSAGES: Record<AppLocale, Record<MessageKey, string>> = {
  en: EN_MESSAGES,
  "zh-CN": ZH_CN_MESSAGES,
};

export function translate(
  locale: AppLocale,
  key: MessageKey,
  vars?: Record<string, string | number>
): string {
  const template = MESSAGES[locale][key] ?? EN_MESSAGES[key];
  if (!vars) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (_, name: string) => {
    const value = vars[name];
    return value == null ? "" : String(value);
  });
}
