import {
  closeShellNotification,
  sendShellNotification,
} from "./ipc";

interface DesktopNotificationOptions {
  title: string;
  body: string;
  tag: string;
  timeoutMs?: number;
}

function normalizeNotificationTag(tag: string): string | null {
  const normalizedTag = tag.trim();
  return normalizedTag || null;
}

export async function sendDesktopNotification(
  options: DesktopNotificationOptions
): Promise<boolean> {
  try {
    const tag = normalizeNotificationTag(options.tag);
    if (!tag) {
      return false;
    }
    try {
      await closeShellNotification(tag);
    } catch (error) {
      console.warn("failed to close previous desktop notification", error);
    }
    await sendShellNotification({
      title: options.title,
      body: options.body,
      tag,
      timeoutMs: options.timeoutMs,
    });
    return true;
  } catch (error) {
    console.warn("desktop notification failed", error);
    return false;
  }
}

export function closeDesktopNotification(tag: string) {
  const normalizedTag = normalizeNotificationTag(tag);
  if (!normalizedTag) {
    return;
  }
  void closeShellNotification(normalizedTag).catch((error) => {
    console.warn("failed to close desktop notification", error);
  });
}
