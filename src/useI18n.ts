import { translate, type MessageKey } from "./i18n";
import { useAppStore } from "./store";

export function useI18n() {
  const locale = useAppStore((s) => s.terminalSettings.locale);

  return {
    locale,
    t: (key: MessageKey, vars?: Record<string, string | number>) =>
      translate(locale, key, vars),
  };
}
