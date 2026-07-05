use crate::runtime_log;
use anyhow::Context;
use anyhow::Result;
use std::collections::HashMap;
use std::fs;
use std::path::Path;
use std::path::PathBuf;

#[derive(Debug, Clone, Default)]
pub struct ShellLaunchConfig {
    pub executable: String,
    pub args: Vec<String>,
    pub env: HashMap<String, String>,
}

#[derive(Debug, Clone, Copy, Eq, PartialEq)]
enum ShellKind {
    Bash,
    Zsh,
    Fish,
    PowerShell,
    Cmd,
}

const INTEGRATION_VERSION: &str = "v1";

pub fn prepare_shell_launch(shell: &str) -> Result<ShellLaunchConfig> {
    let Some(kind) = detect_shell_kind(shell) else {
        return Ok(ShellLaunchConfig {
            executable: shell.to_string(),
            ..ShellLaunchConfig::default()
        });
    };

    let assets = ensure_integration_assets()?;
    let mut launch = ShellLaunchConfig {
        executable: shell.to_string(),
        ..ShellLaunchConfig::default()
    };

    match kind {
        ShellKind::Bash => {
            launch.args.push("--rcfile".to_string());
            launch.args.push(assets.bash_rc.display().to_string());
            launch.args.push("-i".to_string());
        }
        ShellKind::Zsh => {
            launch.args.push("-i".to_string());
            launch
                .env
                .insert("ZDOTDIR".to_string(), assets.zsh_dir.display().to_string());
        }
        ShellKind::Fish => {
            launch.args.push("-i".to_string());
            launch.args.push("-C".to_string());
            launch.args.push(format!(
                "source {}",
                quote_posix_arg(&assets.fish_init.display().to_string())
            ));
        }
        ShellKind::PowerShell => {
            launch.args.push("-NoExit".to_string());
            launch.args.push("-Command".to_string());
            launch.args.push(format!(
                ". {}",
                quote_powershell_arg(&assets.powershell_init.display().to_string())
            ));
        }
        ShellKind::Cmd => {
            launch.args.push("/D".to_string());
            launch.args.push("/K".to_string());
            launch.args.push("chcp 65001 > nul".to_string());
        }
    }

    runtime_log::info(
        "shell_integration",
        format!(
            "prepared launch shell={} kind={:?} args={}",
            shell,
            kind,
            launch.args.len()
        ),
    );
    Ok(launch)
}

fn detect_shell_kind(shell: &str) -> Option<ShellKind> {
    let stem = Path::new(shell)
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or(shell)
        .trim()
        .to_ascii_lowercase();

    match stem.as_str() {
        "bash" => Some(ShellKind::Bash),
        "zsh" => Some(ShellKind::Zsh),
        "fish" => Some(ShellKind::Fish),
        "pwsh" | "powershell" => Some(ShellKind::PowerShell),
        "cmd" => Some(ShellKind::Cmd),
        _ => None,
    }
}

struct IntegrationAssets {
    bash_rc: PathBuf,
    zsh_dir: PathBuf,
    fish_init: PathBuf,
    powershell_init: PathBuf,
}

fn ensure_integration_assets() -> Result<IntegrationAssets> {
    let mut root = dirs::config_dir().unwrap_or_else(std::env::temp_dir);
    root.push("SideShell");
    root.push("shell-integration");
    root.push(INTEGRATION_VERSION);
    fs::create_dir_all(&root)
        .with_context(|| format!("create shell integration dir at {}", root.display()))?;

    let bash_rc = root.join("bashrc.sh");
    let zsh_dir = root.join("zsh");
    let fish_dir = root.join("fish");
    let powershell_dir = root.join("powershell");

    fs::create_dir_all(&zsh_dir)?;
    fs::create_dir_all(&fish_dir)?;
    fs::create_dir_all(&powershell_dir)?;

    let zshenv = zsh_dir.join(".zshenv");
    let zshrc = zsh_dir.join(".zshrc");
    let fish_init = fish_dir.join("init.fish");
    let powershell_init = powershell_dir.join("init.ps1");

    write_if_changed(&bash_rc, bash_rc_script())?;
    write_if_changed(&zshenv, zshenv_script())?;
    write_if_changed(&zshrc, zshrc_script())?;
    write_if_changed(&fish_init, fish_init_script())?;
    write_if_changed(&powershell_init, powershell_init_script())?;

    Ok(IntegrationAssets {
        bash_rc,
        zsh_dir,
        fish_init,
        powershell_init,
    })
}

fn write_if_changed(path: &Path, contents: &str) -> Result<()> {
    let needs_write = match fs::read_to_string(path) {
        Ok(existing) => existing != contents,
        Err(_) => true,
    };
    if needs_write {
        fs::write(path, contents)
            .with_context(|| format!("write shell integration file {}", path.display()))?;
    }
    Ok(())
}

fn quote_posix_arg(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\"'\"'"))
}

fn quote_powershell_arg(value: &str) -> String {
    format!("'{}'", value.replace('\'', "''"))
}

fn bash_rc_script() -> &'static str {
    r#"if [ -n "${HOME:-}" ] && [ -f "$HOME/.bashrc" ]; then
  . "$HOME/.bashrc"
fi

__sideshell_emit() {
  printf '\033]%s\a' "$1"
}

__sideshell_emit_cwd() {
  printf '\033]7;file://%s%s\a' "${HOSTNAME:-localhost}" "$PWD"
}

__sideshell_in_command=0
__sideshell_in_precmd=0

__sideshell_preexec() {
  if [ "${__sideshell_in_precmd:-0}" -ne 0 ]; then
    return
  fi
  if [ "${__sideshell_in_command:-0}" -eq 0 ]; then
    __sideshell_emit '133;C'
    __sideshell_in_command=1
  fi
}

__sideshell_precmd() {
  local exit_code=$?
  __sideshell_in_precmd=1
  if [ "${__sideshell_in_command:-0}" -eq 1 ]; then
    __sideshell_emit "133;D;${exit_code}"
    __sideshell_in_command=0
  fi
  __sideshell_emit_cwd
  __sideshell_emit '133;A'
  __sideshell_emit '133;B'
  __sideshell_in_precmd=0
}

trap '__sideshell_preexec' DEBUG
if [ -n "${PROMPT_COMMAND:-}" ]; then
  PROMPT_COMMAND="__sideshell_precmd;${PROMPT_COMMAND}"
else
  PROMPT_COMMAND="__sideshell_precmd"
fi
"#
}

fn zshenv_script() -> &'static str {
    r#"if [[ -n "${HOME:-}" && -f "$HOME/.zshenv" ]]; then
  source "$HOME/.zshenv"
fi
"#
}

fn zshrc_script() -> &'static str {
    r#"if [[ -n "${HOME:-}" && -f "$HOME/.zshrc" ]]; then
  source "$HOME/.zshrc"
fi

__sideshell_emit() {
  printf '\033]%s\a' "$1"
}

__sideshell_emit_cwd() {
  printf '\033]7;file://%s%s\a' "${HOST:-localhost}" "$PWD"
}

typeset -g __sideshell_in_command=0

__sideshell_preexec() {
  if [[ $__sideshell_in_command -eq 0 ]]; then
    __sideshell_emit '133;C'
    __sideshell_in_command=1
  fi
}

__sideshell_precmd() {
  local exit_code=$?
  if [[ $__sideshell_in_command -eq 1 ]]; then
    __sideshell_emit "133;D;${exit_code}"
    __sideshell_in_command=0
  fi
  __sideshell_emit_cwd
  __sideshell_emit '133;A'
  __sideshell_emit '133;B'
}

typeset -ga precmd_functions preexec_functions chpwd_functions
[[ " ${precmd_functions[*]} " == *" __sideshell_precmd "* ]] || precmd_functions+=(__sideshell_precmd)
[[ " ${preexec_functions[*]} " == *" __sideshell_preexec "* ]] || preexec_functions+=(__sideshell_preexec)
[[ " ${chpwd_functions[*]} " == *" __sideshell_emit_cwd "* ]] || chpwd_functions+=(__sideshell_emit_cwd)
"#
}

fn fish_init_script() -> &'static str {
    r#"function __sideshell_emit --argument-names payload
  printf '\e]%s\a' $payload
end

function __sideshell_emit_cwd
  printf '\e]7;file://%s%s\a' (hostname) "$PWD"
end

set -g __sideshell_in_command 0

if functions -q fish_prompt
  if not functions -q __sideshell_original_fish_prompt
    functions -c fish_prompt __sideshell_original_fish_prompt
  end
else
  function __sideshell_original_fish_prompt
  end
end

function fish_prompt
  set -l exit_code $status
  if test "$__sideshell_in_command" = "1"
    __sideshell_emit "133;D;$exit_code"
    set -g __sideshell_in_command 0
  end
  __sideshell_emit_cwd
  __sideshell_emit '133;A'
  __sideshell_emit '133;B'
  __sideshell_original_fish_prompt
end

function __sideshell_preexec --on-event fish_preexec
  if test "$__sideshell_in_command" != "1"
    set -g __sideshell_in_command 1
    __sideshell_emit '133;C'
  end
end

function __sideshell_pwd_change --on-variable PWD
  __sideshell_emit_cwd
end
"#
}

fn powershell_init_script() -> &'static str {
    r#"try {
  $global:__sideshellUtf8Encoding = [System.Text.UTF8Encoding]::new($false)
  [Console]::InputEncoding = $global:__sideshellUtf8Encoding
  [Console]::OutputEncoding = $global:__sideshellUtf8Encoding
  $OutputEncoding = $global:__sideshellUtf8Encoding
  if (Get-Command chcp.com -ErrorAction Ignore) {
    chcp.com 65001 | Out-Null
  }
} catch {}

$global:__sideshellHost = try { [System.Net.Dns]::GetHostName() } catch { "localhost" }
$global:__sideshellInCommand = $false

function global:__sideshell_emit([string]$payload) {
  [Console]::Out.Write("`e]$payload`a")
}

function global:__sideshell_emit_cwd() {
  $path = $PWD.Path -replace '\\', '/'
  if (-not $path.StartsWith('/')) {
    $path = "/$path"
  }
  __sideshell_emit("7;file://$global:__sideshellHost$path")
}

$function:__sideshell_original_prompt = if (Test-Path Function:\prompt) {
  $function:prompt
} else {
  { 'PS> ' }
}

function global:prompt {
  $lastSuccess = $?
  $lastExitCode = $LASTEXITCODE
  if ($global:__sideshellInCommand) {
    $code = if ($lastSuccess) {
      0
    } elseif ($null -ne $lastExitCode) {
      [int]$lastExitCode
    } else {
      1
    }
    __sideshell_emit("133;D;$code")
    $global:__sideshellInCommand = $false
  }
  __sideshell_emit_cwd
  __sideshell_emit('133;A')
  __sideshell_emit('133;B')
  & $function:__sideshell_original_prompt
}

if (Get-Command Set-PSReadLineKeyHandler -ErrorAction Ignore) {
  Set-PSReadLineKeyHandler -Key Enter -BriefDescription 'SideShellAcceptLine' -ScriptBlock {
    $global:__sideshellInCommand = $true
    __sideshell_emit('133;C')
    [Microsoft.PowerShell.PSConsoleReadLine]::AcceptLine()
  }
}
"#
}
