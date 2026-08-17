#!/usr/bin/env python3
"""
Deja el bot corriendo como servicio en este equipo, arrancando solo.

Funciona en cualquier equipo donde se clone el repositorio: detecta el sistema
operativo y usa el mecanismo nativo, sin rutas fijas y sin pedir permisos de
administrador.

    python bot/install_service.py              # instalar y arrancar
    python bot/install_service.py --status     # ver si está corriendo
    python bot/install_service.py --restart    # reiniciar
    python bot/install_service.py --uninstall  # quitar

Por sistema:
  Windows  Tarea programada «ALCPT Bot», se lanza al iniciar sesión.
  Linux    Unidad de usuario de systemd, con lingering para sobrevivir al logout.
  macOS    LaunchAgent en ~/Library/LaunchAgents.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BOT = REPO / "bot" / "alcpt_bot.py"
NAME = "ALCPT Bot"
SLUG = "alcpt-bot"


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def check_ready():
    """Avisa de lo que le falta a este equipo antes de instalar nada."""
    problems, warnings = [], []
    if not BOT.exists():
        problems.append(f"No encuentro {BOT}")
    env = REPO / ".env"
    if not env.exists():
        problems.append("Falta el archivo .env (copia .env.example y complétalo).")
    else:
        text = env.read_text(encoding="utf-8")
        if "TELEGRAM_TOKEN=" not in text or not _value(text, "TELEGRAM_TOKEN"):
            problems.append("Falta TELEGRAM_TOKEN en .env")
        if not _value(text, "ALLOWED_USER_IDS"):
            warnings.append("ALLOWED_USER_IDS está vacío: cualquiera podrá escribirle al bot. "
                            "Corre antes: python bot/capture_id.py")
    try:
        import requests  # noqa: F401
    except ImportError:
        problems.append("Falta 'requests'. Instala: pip install -r bot/requirements.txt")
    if not shutil.which("claude") and not _value_env("CLAUDE_BIN"):
        warnings.append("No encuentro Claude Code en el PATH. Las traducciones y las "
                        "capturas no se procesarán. Define CLAUDE_BIN en .env.")
    if not shutil.which("git"):
        warnings.append("No encuentro git: el bot no podrá subir los cambios.")
    return problems, warnings


def _value(text, key):
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(f"{key}=") and not line.startswith("#"):
            return line.split("=", 1)[1].strip()
    return ""


def _value_env(key):
    env = REPO / ".env"
    return _value(env.read_text(encoding="utf-8"), key) if env.exists() else ""


def python_for_service(windowless=False):
    """Intérprete a usar; en Windows conviene pythonw para que no abra consola."""
    exe = Path(sys.executable)
    if windowless:
        pw = exe.with_name("pythonw.exe")
        if pw.exists():
            return pw
    return exe


# ------------------------------------------------------------------ Windows
def powershell(script):
    """Los cmdlets de ScheduledTasks funcionan donde schtasks.exe está restringido."""
    exe = shutil.which("powershell") or shutil.which("pwsh") or "powershell"
    return run([exe, "-NoProfile", "-NonInteractive", "-Command", script])


def win_install():
    py = python_for_service(windowless=True)
    script = f"""
$ErrorActionPreference = 'Stop'
try {{
  $action  = New-ScheduledTaskAction -Execute '{py}' -Argument '"{BOT}"' -WorkingDirectory '{REPO}'
  $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $set     = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
               -DontStopIfGoingOnBatteries -RestartCount 999 `
               -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
  Register-ScheduledTask -TaskName '{NAME}' -Action $action -Trigger $trigger `
               -Settings $set -Force | Out-Null
  Start-ScheduledTask -TaskName '{NAME}'
  'OK'
}} catch {{ "ERROR: $($_.Exception.Message)" }}
"""
    res = powershell(script)
    out = (res.stdout or "").strip()
    if "OK" not in out:
        # último recurso: la herramienta clásica, por si PowerShell no está disponible
        alt = run(["schtasks", "/Create", "/TN", NAME, "/SC", "ONLOGON", "/RL", "LIMITED",
                   "/F", "/TR", f'"{py}" "{BOT}"'])
        if alt.returncode != 0:
            return (f"No se pudo crear la tarea.\nPowerShell: {out or res.stderr.strip()}\n"
                    f"schtasks: {(alt.stderr or alt.stdout).strip()}")
        run(["schtasks", "/Run", "/TN", NAME])
    return None


def win_status():
    res = powershell(
        f"$t = Get-ScheduledTask -TaskName '{NAME}' -ErrorAction SilentlyContinue; "
        "if (-not $t) { 'No instalado.' } else { "
        f"$i = Get-ScheduledTaskInfo -TaskName '{NAME}'; "
        "\"Estado: $($t.State)`nUltima ejecucion: $($i.LastRunTime)`n"
        "Resultado: $($i.LastTaskResult)\" }")
    out = (res.stdout or res.stderr or "").strip()
    log_file = REPO / "bot" / "bot.log"
    if log_file.exists():
        tail = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
        out += "\n\nUltimas lineas del registro:\n" + "\n".join(tail)
    return out


def win_uninstall():
    res = powershell(
        f"Stop-ScheduledTask -TaskName '{NAME}' -ErrorAction SilentlyContinue; "
        f"Unregister-ScheduledTask -TaskName '{NAME}' -Confirm:$false "
        "-ErrorAction SilentlyContinue; 'OK'")
    return None if "OK" in (res.stdout or "") else (res.stderr or res.stdout).strip()


def win_restart():
    res = powershell(
        f"Stop-ScheduledTask -TaskName '{NAME}' -ErrorAction SilentlyContinue; "
        "Start-Sleep -Seconds 2; "
        f"Start-ScheduledTask -TaskName '{NAME}'; 'OK'")
    return None if "OK" in (res.stdout or "") else (res.stderr or res.stdout).strip()


# ------------------------------------------------------------------ Linux
UNIT = """[Unit]
Description=Bot ALCPT (diccionario por Telegram)
After=network-online.target

[Service]
Type=simple
WorkingDirectory={repo}
ExecStart={python} {bot}
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
"""


def linux_unit_path():
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "systemd" / "user" / f"{SLUG}.service"


def linux_install():
    if not shutil.which("systemctl"):
        return "Este equipo no usa systemd; deja el bot corriendo con nohup o supervisord."
    path = linux_unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(UNIT.format(repo=REPO, python=sys.executable, bot=BOT), encoding="utf-8")
    run(["systemctl", "--user", "daemon-reload"])
    res = run(["systemctl", "--user", "enable", "--now", SLUG])
    if res.returncode != 0:
        return (res.stderr or res.stdout).strip()
    # que siga vivo aunque cierres la sesión
    run(["loginctl", "enable-linger", os.environ.get("USER", "")])
    return None


def linux_status():
    res = run(["systemctl", "--user", "status", SLUG, "--no-pager", "-n", "5"])
    return (res.stdout or res.stderr).strip()[:800] or "No instalado."


def linux_uninstall():
    run(["systemctl", "--user", "disable", "--now", SLUG])
    path = linux_unit_path()
    if path.exists():
        path.unlink()
    run(["systemctl", "--user", "daemon-reload"])
    return None


def linux_restart():
    res = run(["systemctl", "--user", "restart", SLUG])
    return None if res.returncode == 0 else (res.stderr or res.stdout).strip()


# ------------------------------------------------------------------ macOS
PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array><string>{python}</string><string>{bot}</string></array>
  <key>WorkingDirectory</key><string>{repo}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
"""
MAC_LABEL = "com.brayhan.alcptbot"


def mac_plist_path():
    return Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"


def mac_install():
    path = mac_plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PLIST.format(label=MAC_LABEL, python=sys.executable,
                                 bot=BOT, repo=REPO), encoding="utf-8")
    run(["launchctl", "unload", str(path)])
    res = run(["launchctl", "load", "-w", str(path)])
    return None if res.returncode == 0 else (res.stderr or res.stdout).strip()


def mac_status():
    res = run(["launchctl", "list", MAC_LABEL])
    return (res.stdout or "No instalado.").strip()[:600]


def mac_uninstall():
    path = mac_plist_path()
    run(["launchctl", "unload", str(path)])
    if path.exists():
        path.unlink()
    return None


def mac_restart():
    path = mac_plist_path()
    run(["launchctl", "unload", str(path)])
    res = run(["launchctl", "load", "-w", str(path)])
    return None if res.returncode == 0 else (res.stderr or res.stdout).strip()


# ------------------------------------------------------------------ despacho
BACKENDS = {
    "Windows": (win_install, win_status, win_uninstall, win_restart),
    "Linux":   (linux_install, linux_status, linux_uninstall, linux_restart),
    "Darwin":  (mac_install, mac_status, mac_uninstall, mac_restart),
}


def main():
    ap = argparse.ArgumentParser(description="Instala el bot ALCPT como servicio.")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--restart", action="store_true")
    args = ap.parse_args()

    system = platform.system()
    if system not in BACKENDS:
        sys.exit(f"Sistema no contemplado: {system}")
    install, status, uninstall, restart = BACKENDS[system]

    if args.status:
        print(status())
        return
    if args.uninstall:
        err = uninstall()
        print(err or "Servicio retirado.")
        return
    if args.restart:
        err = restart()
        print(err or "Servicio reiniciado.")
        return

    problems, warnings = check_ready()
    for w in warnings:
        print(f"AVISO: {w}")
    if problems:
        for p in problems:
            print(f"FALTA: {p}")
        sys.exit(1)

    err = install()
    if err:
        sys.exit(err)
    print(f"Servicio instalado y corriendo en {system}.")
    print(f"Repositorio: {REPO}")
    print("Comprobar:  python bot/install_service.py --status")


if __name__ == "__main__":
    main()
