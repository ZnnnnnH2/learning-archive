interface DesktopNotificationOptions {
  title: string;
  body: string;
  tag?: string;
}

let permissionRequest: Promise<NotificationPermission> | null = null;

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
    new Notification(options.title, {
      body: options.body,
      tag: options.tag,
      requireInteraction: true,
    });
    return true;
  } catch (error) {
    console.warn("desktop notification failed", error);
    return false;
  }
}
