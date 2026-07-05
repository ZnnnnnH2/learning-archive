use crate::runtime_log;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::mpsc::{self, Receiver, Sender};
use std::thread;
use tauri::{AppHandle, Emitter};

pub const SHELL_ALERT_ACTIVATED_EVENT: &str = "shell_notification://activated";

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ShellNotificationRequest {
    pub tag: String,
    pub title: String,
    pub body: String,
    pub timeout_ms: Option<u32>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ShellNotificationActivatedPayload {
    pub tag: String,
}

enum NotificationCommand {
    Show(ShellNotificationRequest),
    Close { tag: String },
}

pub struct DesktopNotificationService {
    sender: Sender<NotificationCommand>,
}

impl DesktopNotificationService {
    pub fn new(app: AppHandle) -> Self {
        let (sender, receiver) = mpsc::channel();
        thread::spawn(move || run_notification_worker(app, receiver));
        Self { sender }
    }

    pub fn show(&self, request: ShellNotificationRequest) -> Result<(), String> {
        self.sender
            .send(NotificationCommand::Show(request))
            .map_err(|error| format!("failed to queue shell notification: {error}"))
    }

    pub fn close(&self, tag: String) -> Result<(), String> {
        self.sender
            .send(NotificationCommand::Close { tag })
            .map_err(|error| format!("failed to queue notification close: {error}"))
    }
}

fn run_notification_worker(app: AppHandle, receiver: Receiver<NotificationCommand>) {
    let mut notifier = PlatformNotifier::new(app.clone());

    while let Ok(command) = receiver.recv() {
        match command {
            NotificationCommand::Show(request) => {
                let tag = request.tag.trim().to_string();
                if tag.is_empty() {
                    continue;
                }

                if let Err(error) = notifier.show(&request) {
                    runtime_log::warn(
                        "desktop_notifications",
                        format!("desktop notification failed: {error}"),
                    );
                }
            }
            NotificationCommand::Close { tag } => {
                if let Err(error) = notifier.close(&tag) {
                    runtime_log::warn(
                        "desktop_notifications",
                        format!("desktop notification close failed: {error}"),
                    );
                }
            }
        }
    }
}

pub fn emit_shell_notification_activated(app: &AppHandle, tag: String) {
    let _ = app.emit(
        SHELL_ALERT_ACTIVATED_EVENT,
        ShellNotificationActivatedPayload { tag },
    );
}

struct PlatformNotifier {
    #[cfg(target_os = "windows")]
    inner: windows::WindowsNotifier,
    #[cfg(target_os = "linux")]
    inner: linux::LinuxNotifier,
    #[cfg(target_os = "macos")]
    inner: macos::MacOsNotifier,
    #[cfg(not(any(target_os = "windows", target_os = "linux", target_os = "macos")))]
    inner: unsupported::UnsupportedNotifier,
}

impl PlatformNotifier {
    fn new(app: AppHandle) -> Self {
        Self {
            #[cfg(target_os = "windows")]
            inner: windows::WindowsNotifier::new(app),
            #[cfg(target_os = "linux")]
            inner: linux::LinuxNotifier::new(app),
            #[cfg(target_os = "macos")]
            inner: macos::MacOsNotifier::new(app),
            #[cfg(not(any(target_os = "windows", target_os = "linux", target_os = "macos")))]
            inner: unsupported::UnsupportedNotifier::new(app),
        }
    }

    fn show(&mut self, request: &ShellNotificationRequest) -> Result<(), String> {
        self.inner.show(request)
    }

    fn close(&mut self, tag: &str) -> Result<(), String> {
        self.inner.close(tag)
    }
}

#[cfg(target_os = "windows")]
mod windows {
    use super::{emit_shell_notification_activated, AppHandle, HashMap, ShellNotificationRequest};
    use crate::runtime_log;
    use windows::{
        core::{IInspectable, Ref, HSTRING},
        Data::Xml::Dom::XmlDocument,
        Foundation::TypedEventHandler,
        UI::Notifications::{ToastFailedEventArgs, ToastNotification, ToastNotificationManager},
    };
    use winrt_toast_reborn::url::form_urlencoded;
    use winrt_toast_reborn::{register, ToastManager};

    const SHELL_ALERT_PROTOCOL: &str = "sideshell";
    const SHELL_ALERT_ROUTE: &str = "shell-alert";
    const WINDOWS_TOAST_GROUP: &str = "sideshell-shell-alerts";

    struct ActiveToast {
        _activated: TypedEventHandler<ToastNotification, IInspectable>,
        _failed: TypedEventHandler<ToastNotification, ToastFailedEventArgs>,
    }

    pub struct WindowsNotifier {
        app: AppHandle,
        active: HashMap<String, ActiveToast>,
        aumid: String,
    }

    impl WindowsNotifier {
        pub fn new(app: AppHandle) -> Self {
            let product_name = app.package_info().name.clone();
            let preferred_aumid = app.config().identifier.clone();
            let aumid = match register(&preferred_aumid, &product_name, None) {
                Ok(()) => preferred_aumid,
                Err(error) => {
                    runtime_log::warn(
                        "desktop_notifications",
                        format!("failed to register Windows toast AUMID, falling back: {error}"),
                    );
                    ToastManager::POWERSHELL_AUM_ID.to_string()
                }
            };

            Self {
                app,
                active: HashMap::new(),
                aumid,
            }
        }

        pub fn show(&mut self, request: &ShellNotificationRequest) -> Result<(), String> {
            self.close(&request.tag)?;

            let app = self.app.clone();
            let tag = request.tag.clone();
            let activation_url = build_shell_alert_activation_url(&request.tag);
            let toast_xml = build_shell_alert_toast_xml(request, &activation_url);

            let toast_doc = XmlDocument::new()
                .map_err(|error| format!("failed to create Windows toast XML: {error}"))?;
            toast_doc
                .LoadXml(&HSTRING::from(toast_xml))
                .map_err(|error| format!("failed to load Windows toast XML: {error}"))?;

            let toast = ToastNotification::CreateToastNotification(&toast_doc)
                .map_err(|error| format!("failed to create Windows toast: {error}"))?;
            toast
                .SetGroup(&HSTRING::from(WINDOWS_TOAST_GROUP))
                .map_err(|error| format!("failed to set Windows toast group: {error}"))?;
            toast
                .SetTag(&HSTRING::from(&request.tag))
                .map_err(|error| format!("failed to set Windows toast tag: {error}"))?;

            let activated = TypedEventHandler::new(
                move |_toast: Ref<'_, ToastNotification>, _args: Ref<'_, IInspectable>| {
                    emit_shell_notification_activated(&app, tag.clone());
                    Ok(())
                },
            );
            let failed_tag = request.tag.clone();
            let failed = TypedEventHandler::new(
                move |_toast: Ref<'_, ToastNotification>, args: Ref<'_, ToastFailedEventArgs>| {
                    let error_code = args.as_ref().and_then(|args| args.ErrorCode().ok());
                    runtime_log::warn(
                        "desktop_notifications",
                        format!("Windows toast callback error for {failed_tag}: {error_code:?}"),
                    );
                    Ok(())
                },
            );

            toast
                .Activated(&activated)
                .map_err(|error| format!("failed to attach Windows toast activation: {error}"))?;
            toast.Failed(&failed).map_err(|error| {
                format!("failed to attach Windows toast failure handler: {error}")
            })?;

            let notifier =
                ToastNotificationManager::CreateToastNotifierWithId(&HSTRING::from(&self.aumid))
                    .map_err(|error| format!("failed to create Windows toast notifier: {error}"))?;
            notifier
                .Show(&toast)
                .map_err(|error| format!("failed to show Windows toast: {error}"))?;

            self.active.insert(
                request.tag.clone(),
                ActiveToast {
                    _activated: activated,
                    _failed: failed,
                },
            );
            Ok(())
        }

        pub fn close(&mut self, tag: &str) -> Result<(), String> {
            let normalized_tag = tag.trim();
            if normalized_tag.is_empty() {
                return Ok(());
            }

            self.active.remove(normalized_tag);
            ToastNotificationManager::History()
                .map_err(|error| format!("failed to open Windows toast history: {error}"))?
                .RemoveGroupedTagWithId(
                    &HSTRING::from(normalized_tag),
                    &HSTRING::from(WINDOWS_TOAST_GROUP),
                    &HSTRING::from(&self.aumid),
                )
                .map_err(|error| format!("failed to remove Windows toast: {error}"))
        }
    }

    fn build_shell_alert_activation_url(tag: &str) -> String {
        let encoded_tag: String = form_urlencoded::byte_serialize(tag.as_bytes()).collect();
        format!("{SHELL_ALERT_PROTOCOL}://{SHELL_ALERT_ROUTE}?tag={encoded_tag}")
    }

    fn build_shell_alert_toast_xml(
        request: &ShellNotificationRequest,
        activation_url: &str,
    ) -> String {
        let duration = match request.timeout_ms.unwrap_or(3000) {
            0..=5000 => "short",
            _ => "long",
        };

        format!(
            "<toast activationType=\"protocol\" launch=\"{}\" duration=\"{}\"><visual><binding template=\"ToastGeneric\"><text>{}</text><text>{}</text></binding></visual></toast>",
            xml_escape(activation_url),
            duration,
            xml_escape(&request.title),
            xml_escape(&request.body),
        )
    }

    fn xml_escape(value: &str) -> String {
        let mut escaped = String::with_capacity(value.len());
        for ch in value.chars() {
            match ch {
                '&' => escaped.push_str("&amp;"),
                '<' => escaped.push_str("&lt;"),
                '>' => escaped.push_str("&gt;"),
                '"' => escaped.push_str("&quot;"),
                '\'' => escaped.push_str("&apos;"),
                _ => escaped.push(ch),
            }
        }
        escaped
    }
}

#[cfg(target_os = "linux")]
mod linux {
    use super::{emit_shell_notification_activated, AppHandle, HashMap, ShellNotificationRequest};
    use notify_rust::{handle_action, Notification, NotificationHandle, Timeout};

    pub struct LinuxNotifier {
        app: AppHandle,
        active: HashMap<String, NotificationHandle>,
        ids: HashMap<String, u32>,
    }

    impl LinuxNotifier {
        pub fn new(app: AppHandle) -> Self {
            Self {
                app,
                active: HashMap::new(),
                ids: HashMap::new(),
            }
        }

        pub fn show(&mut self, request: &ShellNotificationRequest) -> Result<(), String> {
            self.close(&request.tag)?;

            let mut notification = Notification::new();
            notification
                .summary(&request.title)
                .body(&request.body)
                .appname("SideShell")
                .timeout(Timeout::Milliseconds(
                    request.timeout_ms.unwrap_or(3000) as i32
                ))
                .action("default", "Open SideShell");

            if let Some(existing_id) = self.ids.get(&request.tag).copied() {
                notification.id(existing_id);
            }

            let handle = notification
                .show()
                .map_err(|error| format!("failed to show Linux notification: {error}"))?;
            let notification_id = handle.id();
            self.ids.insert(request.tag.clone(), notification_id);

            let app = self.app.clone();
            let tag = request.tag.clone();
            handle_action(notification_id, move |action| {
                if action == "default" {
                    emit_shell_notification_activated(&app, tag.clone());
                }
            });

            self.active.insert(request.tag.clone(), handle);
            Ok(())
        }

        pub fn close(&mut self, tag: &str) -> Result<(), String> {
            let normalized_tag = tag.trim();
            if normalized_tag.is_empty() {
                return Ok(());
            }

            if let Some(handle) = self.active.remove(normalized_tag) {
                handle
                    .close()
                    .map_err(|error| format!("failed to close Linux notification: {error}"))?;
            }
            self.ids.remove(normalized_tag);
            Ok(())
        }
    }
}

#[cfg(target_os = "macos")]
mod macos {
    use super::{AppHandle, ShellNotificationRequest};
    use notify_rust::Notification;

    pub struct MacOsNotifier {
        _app: AppHandle,
    }

    impl MacOsNotifier {
        pub fn new(app: AppHandle) -> Self {
            Self { _app: app }
        }

        pub fn show(&mut self, request: &ShellNotificationRequest) -> Result<(), String> {
            Notification::new()
                .summary(&request.title)
                .body(&request.body)
                .show()
                .map(|_| ())
                .map_err(|error| format!("failed to show macOS notification: {error}"))
        }

        pub fn close(&mut self, _tag: &str) -> Result<(), String> {
            Ok(())
        }
    }
}

#[cfg(not(any(target_os = "windows", target_os = "linux", target_os = "macos")))]
mod unsupported {
    use super::{AppHandle, ShellNotificationRequest};

    pub struct UnsupportedNotifier {
        _app: AppHandle,
    }

    impl UnsupportedNotifier {
        pub fn new(app: AppHandle) -> Self {
            Self { _app: app }
        }

        pub fn show(&mut self, _request: &ShellNotificationRequest) -> Result<(), String> {
            Ok(())
        }

        pub fn close(&mut self, _tag: &str) -> Result<(), String> {
            Ok(())
        }
    }
}
