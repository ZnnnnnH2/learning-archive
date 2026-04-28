import { isShellAlertTag } from "./shellAlerts";

const SHELL_ALERT_DEEP_LINK_PROTOCOL = "sideshell:";
const SHELL_ALERT_DEEP_LINK_ROUTE = "shell-alert";

export function getShellAlertTagFromDeepLink(rawUrl: string): string | null {
  let url: URL;
  try {
    url = new URL(rawUrl);
  } catch {
    return null;
  }

  if (url.protocol !== SHELL_ALERT_DEEP_LINK_PROTOCOL) {
    return null;
  }

  const route = (url.hostname || url.pathname.replace(/^\/+/, "")).trim();
  if (route !== SHELL_ALERT_DEEP_LINK_ROUTE) {
    return null;
  }

  const tag = url.searchParams.get("tag")?.trim() ?? "";
  if (!tag || !isShellAlertTag(tag)) {
    return null;
  }

  return tag;
}
