import { type ReactNode, useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Settings, X } from "lucide-react";
import { useAppStore } from "../store";
import {
  DEFAULT_ALERT_POPUP_DURATION_SECONDS,
  DEFAULT_TERMINAL_FONT_FAMILY,
  normalizeTerminalSettings,
  parseTerminalEnvText,
} from "../terminalConfig";
import type { TerminalSettings } from "../types";
import { useI18n } from "../useI18n";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SettingsDialog({ open, onOpenChange }: Props) {
  const { t } = useI18n();
  const terminalSettings = useAppStore((s) => s.terminalSettings);
  const setTerminalSettings = useAppStore((s) => s.setTerminalSettings);
  const [draft, setDraft] = useState<TerminalSettings>(terminalSettings);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setDraft(terminalSettings);
    setError(null);
  }, [open, terminalSettings]);

  const updateDraft = <K extends keyof TerminalSettings>(
    key: K,
    value: TerminalSettings[K]
  ) => {
    setDraft((current) => ({ ...current, [key]: value }));
    if (key === "extraEnvText" && error) {
      setError(null);
    }
  };

  const handleSave = () => {
    try {
      parseTerminalEnvText(draft.extraEnvText, {
        invalidLine: (line) =>
          t("settings.validation.env.invalid", { line }),
        missingKey: (line) =>
          t("settings.validation.env.missingKey", { line }),
      });
      setTerminalSettings(normalizeTerminalSettings(draft));
      onOpenChange(false);
    } catch (nextError) {
      const message =
        nextError instanceof Error ? nextError.message : String(nextError);
      setError(message);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-bg-0/70 backdrop-blur-sm" />
        <Dialog.Content className="no-drag fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100vh-24px)] w-[min(680px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border border-border bg-bg-1 shadow-2xl">
          <div className="flex shrink-0 items-center gap-3 border-b border-border px-5 py-4">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-accent/25 bg-accent/10 text-accent">
              <Settings size={16} />
            </div>
            <div className="min-w-0 flex-1">
              <Dialog.Title className="text-[14px] font-semibold text-text-0">
                {t("settings.title")}
              </Dialog.Title>
              <Dialog.Description className="mt-0.5 text-[12px] leading-relaxed text-text-2">
                {t("settings.description")}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button
                className="rounded-md p-1.5 text-text-2 transition hover:bg-bg-3 hover:text-text-0"
                title={t("settings.close")}
              >
                <X size={15} />
              </button>
            </Dialog.Close>
          </div>

          <div className="side-scroll flex-1 space-y-4 overflow-y-auto px-5 py-4">
            <Field
              label={t("settings.field.language.label")}
              hint={t("settings.field.language.hint")}
            >
              <select
                value={draft.locale}
                onChange={(e) =>
                  updateDraft("locale", e.target.value as TerminalSettings["locale"])
                }
                className="w-full rounded-lg border border-border bg-bg-2 px-3 py-2 text-[12.5px] text-text-0 outline-none transition focus:border-accent/60"
              >
                <option value="en">
                  {t("settings.field.language.option.en")}
                </option>
                <option value="zh-CN">
                  {t("settings.field.language.option.zh-CN")}
                </option>
              </select>
            </Field>

            <Field
              label={t("settings.field.shellExecutable.label")}
              hint={t("settings.field.shellExecutable.hint")}
            >
              <input
                value={draft.shellExecutable}
                onChange={(e) =>
                  updateDraft("shellExecutable", e.target.value)
                }
                placeholder={"pwsh.exe or C:\\Program Files\\PowerShell\\7\\pwsh.exe"}
                className="w-full rounded-lg border border-border bg-bg-2 px-3 py-2 text-[12.5px] text-text-0 outline-none transition placeholder:text-text-2 focus:border-accent/60"
              />
            </Field>

            <Field
              label={t("settings.field.fontFamily.label")}
              hint={t("settings.field.fontFamily.hint")}
            >
              <input
                value={draft.fontFamily}
                onChange={(e) => updateDraft("fontFamily", e.target.value)}
                placeholder={DEFAULT_TERMINAL_FONT_FAMILY}
                className="w-full rounded-lg border border-border bg-bg-2 px-3 py-2 text-[12.5px] text-text-0 outline-none transition placeholder:text-text-2 focus:border-accent/60"
              />
            </Field>

            <Field
              label={t("settings.field.extraEnv.label")}
              hint={t("settings.field.extraEnv.hint")}
            >
              <textarea
                value={draft.extraEnvText}
                onChange={(e) => updateDraft("extraEnvText", e.target.value)}
                placeholder={"TERM_PROGRAM=SideShell\nMY_AGENT_MODE=1"}
                spellCheck={false}
                className="min-h-32 w-full resize-y rounded-lg border border-border bg-bg-2 px-3 py-2 font-mono text-[12px] leading-5 text-text-0 outline-none transition placeholder:text-text-2 focus:border-accent/60"
              />
            </Field>

            <Field
              label={t("settings.field.alertDuration.label")}
              hint={t("settings.field.alertDuration.hint", {
                seconds: DEFAULT_ALERT_POPUP_DURATION_SECONDS,
              })}
            >
              <input
                type="number"
                min={1}
                step={1}
                value={draft.alertPopupDurationSeconds}
                onChange={(e) =>
                  updateDraft(
                    "alertPopupDurationSeconds",
                    Number.parseInt(e.target.value, 10) || 0
                  )
                }
                placeholder={String(DEFAULT_ALERT_POPUP_DURATION_SECONDS)}
                className="w-full rounded-lg border border-border bg-bg-2 px-3 py-2 text-[12.5px] text-text-0 outline-none transition placeholder:text-text-2 focus:border-accent/60"
              />
            </Field>

            <Field
              label={t("settings.field.codexTitle.label")}
              hint={t("settings.field.codexTitle.hint")}
            >
              <div className="flex items-start gap-3 rounded-lg border border-border bg-bg-2 px-3 py-3">
                <input
                  type="checkbox"
                  checked={draft.codexUseSelfSummaryTitle}
                  onChange={(e) =>
                    updateDraft(
                      "codexUseSelfSummaryTitle",
                      e.target.checked
                    )
                  }
                  className="mt-0.5 h-4 w-4 rounded border-border bg-bg-1 text-accent focus:ring-accent/40"
                />
                <div className="min-w-0">
                  <div className="text-[12.5px] font-medium text-text-0">
                    {t("settings.field.codexTitle.checkbox")}
                  </div>
                  <div className="mt-1 text-[11.5px] leading-relaxed text-text-2">
                    {t("settings.field.codexTitle.checkboxHint")}
                  </div>
                </div>
              </div>
            </Field>

            {error ? (
              <div className="rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-[12px] text-bad">
                {error}
              </div>
            ) : null}
          </div>

          <div className="flex shrink-0 items-center justify-between gap-3 border-t border-border px-5 py-4">
            <button
              onClick={() =>
                setDraft(normalizeTerminalSettings(undefined))
              }
              className="rounded-lg border border-border bg-bg-2 px-3 py-2 text-[12px] text-text-1 transition hover:bg-bg-3 hover:text-text-0"
            >
              {t("settings.action.reset")}
            </button>
            <div className="flex items-center gap-2">
              <Dialog.Close asChild>
                <button className="rounded-lg border border-border bg-bg-2 px-3 py-2 text-[12px] text-text-1 transition hover:bg-bg-3 hover:text-text-0">
                  {t("settings.action.cancel")}
                </button>
              </Dialog.Close>
              <button
                onClick={handleSave}
                className="rounded-lg border border-accent/35 bg-accent/20 px-3 py-2 text-[12px] text-text-0 transition hover:bg-accent/30"
              >
                {t("settings.action.save")}
              </button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <div className="mb-1.5 text-[12.5px] font-medium text-text-0">
        {label}
      </div>
      {children}
      <div className="mt-1.5 text-[11.5px] leading-relaxed text-text-2">
        {hint}
      </div>
    </label>
  );
}
