import type {
  PersistedShortcutKeymap,
  ShortcutActionId,
  ShortcutBindingConfig,
  ShortcutKeymap,
} from "./types";

export type ShortcutScope = "terminal" | "app";

export interface ShortcutActionDefinition {
  id: ShortcutActionId;
  scope: ShortcutScope;
  defaultBindings: string[];
}

export interface ShortcutConflict {
  scope: ShortcutScope;
  binding: string;
  actionIds: ShortcutActionId[];
}

const FOCUS_SHELL_ACTIONS = Array.from({ length: 9 }, (_, index) => ({
  id: `app.focusShell${index + 1}` as ShortcutActionId,
  scope: "app" as const,
  defaultBindings: [`Mod+${index + 1}`],
}));

export const SHORTCUT_ACTIONS: ShortcutActionDefinition[] = [
  {
    id: "terminal.copySelection",
    scope: "terminal",
    defaultBindings: ["Ctrl+Shift+C", "Ctrl+Insert"],
  },
  {
    id: "terminal.pasteClipboard",
    scope: "terminal",
    defaultBindings: ["Ctrl+Shift+V", "Shift+Insert"],
  },
  {
    id: "app.toggleSidebar",
    scope: "app",
    defaultBindings: ["Mod+B"],
  },
  {
    id: "app.newShell",
    scope: "app",
    defaultBindings: ["Mod+T"],
  },
  {
    id: "app.cloneShell",
    scope: "app",
    defaultBindings: ["Mod+Shift+D"],
  },
  {
    id: "app.closeShell",
    scope: "app",
    defaultBindings: ["Mod+W"],
  },
  ...FOCUS_SHELL_ACTIONS,
];

const ACTIONS_BY_ID = new Map(
  SHORTCUT_ACTIONS.map((action) => [action.id, action])
);

const MODIFIER_ALIASES: Record<string, string> = {
  control: "Ctrl",
  ctrl: "Ctrl",
  option: "Alt",
  alt: "Alt",
  shift: "Shift",
  command: "Meta",
  cmd: "Meta",
  meta: "Meta",
  win: "Meta",
  windows: "Meta",
  mod: "Mod",
};

const MODIFIER_ORDER = ["Mod", "Ctrl", "Alt", "Shift", "Meta"];
const MODIFIER_KEYS = new Set(["Control", "Shift", "Alt", "Meta", "OS"]);

export const DEFAULT_SHORTCUT_KEYMAP: ShortcutKeymap = Object.fromEntries(
  SHORTCUT_ACTIONS.map((action) => [
    action.id,
    {
      enabled: true,
      bindings: action.defaultBindings
        .map(normalizeShortcutBinding)
        .filter((binding): binding is string => Boolean(binding)),
    },
  ])
) as ShortcutKeymap;

export function normalizeShortcutKeymap(
  input?: PersistedShortcutKeymap | ShortcutKeymap | null
): ShortcutKeymap {
  const normalized: Partial<ShortcutKeymap> = {};

  for (const action of SHORTCUT_ACTIONS) {
    const fallback = DEFAULT_SHORTCUT_KEYMAP[action.id];
    const override =
      input && typeof input === "object" && !Array.isArray(input)
        ? input[action.id]
        : null;

    if (!override || typeof override !== "object" || Array.isArray(override)) {
      normalized[action.id] = cloneShortcutConfig(fallback);
      continue;
    }

    const bindings = Array.isArray(override.bindings)
      ? normalizeShortcutBindings(override.bindings)
      : fallback.bindings;

    normalized[action.id] = {
      enabled:
        typeof override.enabled === "boolean"
          ? override.enabled
          : fallback.enabled,
      bindings,
    };
  }

  return normalized as ShortcutKeymap;
}

export function normalizeShortcutBindings(bindings: readonly string[]): string[] {
  const seen = new Set<string>();
  const normalized: string[] = [];

  for (const binding of bindings) {
    const nextBinding = normalizeShortcutBinding(binding);
    if (!nextBinding || seen.has(nextBinding)) continue;
    seen.add(nextBinding);
    normalized.push(nextBinding);
  }

  return normalized;
}

export function normalizeShortcutBinding(value: string): string | null {
  const parts = value
    .split("+")
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length === 0) return null;

  const rawKey = parts[parts.length - 1];
  const key = normalizeShortcutKey(rawKey);
  if (!key) return null;

  const modifiers = new Set<string>();
  for (const rawModifier of parts.slice(0, -1)) {
    const modifier = MODIFIER_ALIASES[rawModifier.toLowerCase()];
    if (!modifier) return null;
    modifiers.add(modifier);
  }

  return [...MODIFIER_ORDER.filter((modifier) => modifiers.has(modifier)), key]
    .filter(Boolean)
    .join("+");
}

export function eventToShortcutBinding(event: KeyboardEvent): string | null {
  if (event.type !== "keydown" || MODIFIER_KEYS.has(event.key)) {
    return null;
  }

  const key = normalizeEventKey(event);
  if (!key) return null;

  const modifiers: string[] = [];
  if (event.ctrlKey) modifiers.push("Ctrl");
  if (event.altKey) modifiers.push("Alt");
  if (event.shiftKey) modifiers.push("Shift");
  if (event.metaKey) modifiers.push("Meta");
  return [...modifiers, key].join("+");
}

export function matchShortcutAction(
  keymap: ShortcutKeymap,
  event: KeyboardEvent,
  scope: ShortcutScope
): ShortcutActionId | null {
  for (const action of SHORTCUT_ACTIONS) {
    if (action.scope !== scope) continue;
    const config = keymap[action.id];
    if (!config?.enabled) continue;
    if (config.bindings.some((binding) => matchesShortcutEvent(binding, event))) {
      return action.id;
    }
  }
  return null;
}

export function findShortcutConflicts(
  keymap: ShortcutKeymap
): ShortcutConflict[] {
  const seen = new Map<
    string,
    { scope: ShortcutScope; binding: string; actionIds: ShortcutActionId[] }
  >();

  for (const action of SHORTCUT_ACTIONS) {
    const config = keymap[action.id];
    if (!config?.enabled) continue;

    for (const binding of config.bindings) {
      const conflictKey = `${action.scope}:${getEffectiveBinding(binding)}`;
      const existing = seen.get(conflictKey);
      if (existing) {
        existing.actionIds.push(action.id);
      } else {
        seen.set(conflictKey, {
          scope: action.scope,
          binding,
          actionIds: [action.id],
        });
      }
    }
  }

  return [...seen.values()].filter((conflict) => conflict.actionIds.length > 1);
}

export function areShortcutKeymapsEqual(
  a: ShortcutKeymap,
  b: ShortcutKeymap
): boolean {
  return SHORTCUT_ACTIONS.every((action) => {
    const left = a[action.id];
    const right = b[action.id];
    return (
      left.enabled === right.enabled &&
      left.bindings.length === right.bindings.length &&
      left.bindings.every((binding, index) => binding === right.bindings[index])
    );
  });
}

export function getShortcutActionDefinition(
  actionId: ShortcutActionId
): ShortcutActionDefinition {
  const action = ACTIONS_BY_ID.get(actionId);
  if (!action) {
    throw new Error(`Unknown shortcut action: ${actionId}`);
  }
  return action;
}

function matchesShortcutEvent(binding: string, event: KeyboardEvent): boolean {
  if (event.type !== "keydown") return false;
  const parsed = parseShortcutBinding(binding);
  if (!parsed) return false;

  const isMac = isMacPlatform();
  const requiredCtrl = parsed.modifiers.has("Ctrl") || (parsed.modifiers.has("Mod") && !isMac);
  const requiredMeta = parsed.modifiers.has("Meta") || (parsed.modifiers.has("Mod") && isMac);

  return (
    event.ctrlKey === requiredCtrl &&
    event.altKey === parsed.modifiers.has("Alt") &&
    event.shiftKey === parsed.modifiers.has("Shift") &&
    event.metaKey === requiredMeta &&
    normalizeEventKey(event) === parsed.key
  );
}

function parseShortcutBinding(
  binding: string
): { modifiers: Set<string>; key: string } | null {
  const normalized = normalizeShortcutBinding(binding);
  if (!normalized) return null;
  const parts = normalized.split("+");
  const key = parts[parts.length - 1];
  return {
    modifiers: new Set(parts.slice(0, -1)),
    key,
  };
}

function getEffectiveBinding(binding: string): string {
  const parsed = parseShortcutBinding(binding);
  if (!parsed) return binding;

  const modifiers = new Set(parsed.modifiers);
  if (modifiers.has("Mod")) {
    modifiers.delete("Mod");
    modifiers.add(isMacPlatform() ? "Meta" : "Ctrl");
  }

  return [...MODIFIER_ORDER.filter((modifier) => modifiers.has(modifier)), parsed.key]
    .filter((part) => part !== "Mod")
    .join("+");
}

function normalizeEventKey(event: KeyboardEvent): string | null {
  if (event.code?.startsWith("Digit") && event.code.length === 6) {
    return event.code.slice(5);
  }
  if (event.code?.startsWith("Key") && event.code.length === 4) {
    return event.code.slice(3).toUpperCase();
  }
  return normalizeShortcutKey(event.key);
}

function normalizeShortcutKey(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (MODIFIER_KEYS.has(trimmed)) return null;
  if (trimmed.length === 1) return trimmed.toUpperCase();

  const lower = trimmed.toLowerCase();
  const aliases: Record<string, string> = {
    esc: "Escape",
    escape: "Escape",
    enter: "Enter",
    return: "Enter",
    tab: "Tab",
    backspace: "Backspace",
    delete: "Delete",
    del: "Delete",
    insert: "Insert",
    ins: "Insert",
    home: "Home",
    end: "End",
    pageup: "PageUp",
    pagedown: "PageDown",
    space: "Space",
    arrowup: "ArrowUp",
    up: "ArrowUp",
    arrowdown: "ArrowDown",
    down: "ArrowDown",
    arrowleft: "ArrowLeft",
    left: "ArrowLeft",
    arrowright: "ArrowRight",
    right: "ArrowRight",
  };

  if (/^f([1-9]|1[0-9]|2[0-4])$/.test(lower)) {
    return lower.toUpperCase();
  }

  return aliases[lower] ?? trimmed;
}

function cloneShortcutConfig(
  config: ShortcutBindingConfig
): ShortcutBindingConfig {
  return {
    enabled: config.enabled,
    bindings: [...config.bindings],
  };
}

function isMacPlatform(): boolean {
  if (typeof navigator === "undefined") return false;
  return /Mac|iPhone|iPad|iPod/i.test(navigator.platform);
}
