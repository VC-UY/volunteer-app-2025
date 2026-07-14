import platform
import logging
import subprocess
import getpass

logger = logging.getLogger("VC-Persistence")

def ensure_persistence():
    """Ensure the agent starts automatically on system boot."""
    os_type = platform.system().lower()
    if os_type == "linux":
        # Enable User Lingering (Critical for boot-time start without login)
        try:
            current_user = getpass.getuser()
            subprocess.run(["loginctl", "enable-linger", current_user], check=True)
            logger.info(f"Linux lingering enabled for user: {current_user}")
        except Exception as e:
            logger.warning(f"Could not enable linger: {e}")
            
        setup_linux_persistence()
    elif os_type == "windows":
        setup_windows_persistence()

import sys
import os

def setup_linux_persistence():
    """Create a systemd user service for the agent."""
    try:
        home = os.path.expanduser("~")
        service_dir = os.path.join(home, ".config/systemd/user")
        os.makedirs(service_dir, exist_ok=True)
        
        exe_path = os.path.abspath(sys.argv[0])
        python_path = sys.executable
        service_content = f"""[Unit]
Description=VC-UY1 Research Node (Persistent)
After=network.target

[Service]
ExecStart="{python_path}" "{exe_path}" --foreground
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
"""
        service_path = os.path.join(service_dir, "vc-agent.service")
        with open(service_path, "w") as f:
            f.write(service_content)

        # Activer + démarrer le service utilisateur (sinon le fichier reste inerte)
        try:
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                check=False,
                capture_output=True,
            )
            subprocess.run(
                ["systemctl", "--user", "enable", "--now", "vc-agent.service"],
                check=False,
                capture_output=True,
            )
        except Exception as exc:
            logger.warning("systemctl --user enable: %s", exc)

        logger.info("Linux persistence service créé et activé: %s", service_path)
    except Exception as e:
        logger.error(f"Failed to setup Linux persistence: {e}")

def setup_windows_persistence():
    """Install the agent as a Windows System Service (No login required)."""
    try:
        exe_path = os.path.abspath(sys.argv[0])
        service_name = "VC-UY1-ResearchNode"
        
        # Use sc.exe to create a system service (requires admin)
        # Type=own, Start=auto, binpath points to agent binary
        cmd = [
            "sc", "create", service_name,
            f"binPath= \"{exe_path}\" --foreground",
            "start= auto",
            "DisplayName= VC-UY1 Research Persistence Node"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("Windows System Service created successfully.")
            # Start the service immediately
            subprocess.run(["sc", "start", service_name])
        else:
            logger.warning(f"SC.EXE failed (check admin rights): {result.stderr}")
            # Fallback to registry if service creation fails
            setup_windows_registry_fallback(exe_path)
    except Exception as e:
        logger.error(f"Critical failure in Windows Service setup: {e}")

def setup_windows_registry_fallback(exe_path):
    """Fallback to registry Run key if service creation is denied."""
    try:
        import winreg
        key = winreg.HKEY_CURRENT_USER
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(key, key_path, 0, winreg.KEY_WRITE) as reg_key:
            winreg.SetValueEx(reg_key, "VC-UY-Agent", 0, winreg.REG_SZ, f'"{exe_path}"')
        logger.info("Windows registry fallback added (Active only after login).")
    except Exception as e:
        logger.error(f"Registry fallback failed: {e}")
