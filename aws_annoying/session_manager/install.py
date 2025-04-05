from __future__ import annotations

import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests
import typer
from rich import print  # noqa: A004
from rich.prompt import Confirm
from tqdm import tqdm

from ._app import session_manager_app


# https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html
@session_manager_app.command()
def install(
    # TODO(lasuillard): Will add options: --os, --arch, --skip-verify, --dry-run
) -> None:
    """Install AWS Session Manager plugin."""
    # Check session-manager-plugin already installed
    binary_path, version, is_installed = _verify_installation()
    if is_installed:
        print(f"✅ Session Manager plugin is already installed at {binary_path} (version: {version})")
        return

    # Install session-manager-plugin
    print("⬇️ Installing AWS Session Manager plugin. You could be prompted for admin privileges request.")
    system = platform.system()
    if system == "Windows":
        _install_windows()
    elif system == "Darwin":
        _install_macos()
    elif system == "Linux":
        _install_linux()
    else:
        print(f"❌ Unsupported platform: {system}")
        raise typer.Exit(1)

    # Verify installation
    binary_path, version, is_installed = _verify_installation()
    if is_installed:
        print(f"✅ Session Manager plugin successfully installed at {binary_path} (version: {version})")
    else:
        print("❌ Installation failed. Session Manager plugin not found.")
        raise typer.Exit(1)


def _verify_installation() -> tuple[Path | None, str | None, bool]:
    """Verify installation of AWS Session Manager plugin. Returns binary path and version string, and boolean flag indicating if installed."""  # noqa: E501
    if not (binary_path := shutil.which("session-manager-plugin")):
        # Binary not found
        return None, None, False

    # Check version
    result_bytes = subprocess.run(["session-manager-plugin", "--version"], check=True, capture_output=True)  # noqa: S603, S607
    result = result_bytes.stdout.decode().strip()
    if not bool(re.match(r"[\d\.]+", result)):
        return Path(binary_path), result, False

    return Path(binary_path), result, True


# https://docs.aws.amazon.com/systems-manager/latest/userguide/install-plugin-windows.html
def _install_windows() -> None:
    """Install session-manager-plugin on Windows via EXE installer."""
    download_url = (
        "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/windows/SessionManagerPluginSetup.exe"
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        p = Path(temp_dir)
        _download_file(download_url, p / "SessionManagerPluginSetup.exe")

        command = "SessionManagerPluginSetup.exe /quiet"
        confirm = Confirm.ask(f"⚠️ Will run [bold red]{command}[/bold red]. Proceed?")
        if not confirm:
            raise typer.Abort

        subprocess.call(command, cwd=p, shell=True)  # noqa: S602


# https://docs.aws.amazon.com/systems-manager/latest/userguide/install-plugin-macos-overview.html
def _install_macos() -> None:
    """Install session-manager-plugin on macOS via signed installer."""
    # ! Intel chip will not be supported
    arch = platform.machine()
    if arch == "x86_64":
        download_url = "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/mac/session-manager-plugin.pkg"
    elif arch == "arm64":
        download_url = (
            "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/mac_arm64/session-manager-plugin.pkg"
        )
    else:
        print(f"❌ Architecture {arch} not supported for macOS")
        raise typer.Exit(1)

    with tempfile.TemporaryDirectory() as temp_dir:
        p = Path(temp_dir)
        _download_file(download_url, p / "session-manager-plugin.pkg")

        # Run installer
        command = "sudo installer -pkg ./session-manager-plugin.pkg -target /"
        confirm = Confirm.ask(f"⚠️ Will run [bold red]{command}[/bold red]. Proceed?")
        if not confirm:
            raise typer.Abort

        subprocess.call(command, cwd=p, shell=True)  # noqa: S602

        # Symlink
        command = "sudo ln -s /usr/local/sessionmanagerplugin/bin/session-manager-plugin /usr/local/bin/session-manager-plugin"  # noqa: E501
        print(f"🔗 Running [bold yellow]{command}[/bold yellow] to create symlink")
        Path("/usr/local/bin").mkdir(exist_ok=True)
        subprocess.call(command, shell=True, cwd=p)  # noqa: S602


# https://docs.aws.amazon.com/systems-manager/latest/userguide/install-plugin-linux-overview.html
def _install_linux() -> None:
    os_release = _os_release()
    distro = os_release["ID"]
    version = os_release["VERSION"]
    arch = platform.machine()

    # Debian / Ubuntu
    like_debian = distro in ("debian", "ubuntu")
    if like_debian:
        print("🐧 Detected Linux distribution: Debian / Ubuntu")

        # Download installer
        url_map = {
            "x86_64": "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb",
            "x86": "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_32bit/session-manager-plugin.deb",
            "arm64": "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_arm64/session-manager-plugin.deb",
        }
        download_url = url_map.get(arch)
        if not download_url:
            print(f"❌ Architecture {arch} not supported for distribution {distro}")
            raise typer.Exit(1)

        with tempfile.TemporaryDirectory() as temp_dir:
            p = Path(temp_dir)
            _download_file(download_url, p / "session-manager-plugin.deb")

            # Invoke installation command
            command = "sudo dpkg -i session-manager-plugin.deb"
            confirm = Confirm.ask(f"⚠️ Will run [bold red]{command}[/bold red]. Proceed?")
            if not confirm:
                raise typer.Abort

            subprocess.call(command, cwd=p, shell=True)  # noqa: S602

    # Amazon Linux / RHEL
    elif distro in ("amzn", "rhel"):
        print("🐧 Detected Linux distribution: Amazon Linux / RHEL")

        # Determine package URL and package manager
        url_map = {
            "x86_64": "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/linux_64bit/session-manager-plugin.rpm",
            "x86": "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/linux_32bit/session-manager-plugin.rpm",
            "arm64": "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/linux_arm64/session-manager-plugin.rpm",
        }
        package_url = url_map.get(arch)
        if not package_url:
            print(f"❌ Architecture {arch} not supported for distribution {distro}")
            raise typer.Exit(1)

        use_yum = (
            # Amazon Linux 2
            distro == "amzn" and version.startswith("2")
        ) or (
            # RHEL 7 Maipo (8 Ootpa / 9 Plow)
            distro == "rhel" and "Maipo" in version
        )  # ... else use dnf
        package_manager = "yum" if use_yum else "dnf"

        # Invoke installation command
        command = f"sudo {package_manager} install -y {package_url}"
        confirm = Confirm.ask(f"⚠️ Will run [bold red]{command}[/bold red]. Proceed?")
        if not confirm:
            raise typer.Abort

        subprocess.call(command, shell=True)  # noqa: S602

    else:
        print(f"❌ Unsupported distribution: {distro}")
        raise typer.Exit(1)


def _download_file(url: str, path: Path) -> None:
    """Download file from URL to path."""
    # https://gist.github.com/yanqd0/c13ed29e29432e3cf3e7c38467f42f51
    print(f"📥 Downloading file from URL ({url}) to {path}.")
    with requests.get(url, stream=True, timeout=10) as response:
        response.raise_for_status()
        total_size = int(response.headers.get("content-length", 0))
        with (
            path.open("wb") as f,
            tqdm(
                # Make the URL less verbose in the progress bar
                desc=url.replace("https://s3.amazonaws.com/session-manager-downloads/plugin", "..."),
                total=total_size,
                unit="iB",
                unit_scale=True,
                unit_divisor=1_024,
            ) as pbar,
        ):
            for chunk in response.iter_content(chunk_size=8192):
                size = f.write(chunk)
                pbar.update(size)


def _os_release() -> dict[str, str]:
    """Parse `/etc/os-release` file into a dictionary."""
    content = Path("/etc/os-release").read_text()
    return {
        key.strip('"'): value.strip('"')
        for key, value in (line.split("=", 1) for line in content.splitlines() if "=" in line)
    }
