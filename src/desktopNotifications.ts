interface DesktopNotificationOptions {
  title: string;
  body: string;
  tag?: string;
  timeoutMs?: number;
  onClick?: () => void | Promise<void>;
}

let permissionRequest: Promise<NotificationPermission> | null = null;
const activeNotifications = new Map<
  string,
  { notification: Notification; timeoutId: number | null }
>();

async function ensureNotificationPermission(): Promise<NotificationPermission> {
  if (typeof window === "undefined" || !("Notification" in window)) {
    return "denied";
  }

  if (Notification.permission !== "default") {
    return Notification.permission;
  }

  if (!permissionRequest) {
    permissionRequest = Notification.requestPermission().finally(() => {
      permissionRequest = null;
    });
  }

  try {
    return await permissionRequest;
  } catch {
    return "denied";
  }
}

export async function sendDesktopNotification(
  options: DesktopNotificationOptions
): Promise<boolean> {
  const permission = await ensureNotificationPermission();
  if (permission !== "granted") {
    return false;
  }

  try {
    const tag = options.tag?.trim() || undefined;
    if (tag) {
      closeDesktopNotification(tag);
    }

    const notification = new Notification(options.title, {
      body: options.body,
      tag,
      requireInteraction: false,
      silent: true,
    });

    let timeoutId: number | null = null;
    const cleanup = () => {
      if (timeoutId != null) {
        window.clearTimeout(timeoutId);
      }
      if (tag && activeNotifications.get(tag)?.notification === notification) {
        activeNotifications.delete(tag);
      }
    };

    notification.onclick = () => {
      cleanup();
      notification.close();
      void options.onClick?.();
    };
    notification.onclose = cleanup;

    const timeoutMs = options.timeoutMs ?? 3000;
    timeoutId = window.setTimeout(() => {
      cleanup();
      notification.close();
    }, timeoutMs);

    if (tag) {
      activeNotifications.set(tag, { notification, timeoutId });
    }
    return true;
  } catch (error) {
    console.warn("desktop notification failed", error);
    return false;
  }
}

export function closeDesktopNotification(tag: string) {
  const normalizedTag = tag.trim();
  if (!normalizedTag) {
    return;
  }
  const active = activeNotifications.get(normalizedTag);
  if (!active) {
    return;
  }
  if (active.timeoutId != null) {
    window.clearTimeout(active.timeoutId);
  }
  activeNotifications.delete(normalizedTag);
  active.notification.close();
}
