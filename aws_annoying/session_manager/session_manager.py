from __future__ import annotations

import json
import logging
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

import boto3

from aws_annoying.utils.platform import command_as_root, is_root, os_release

from .errors import PluginNotInstalledError, UnsupportedPlatformError

if TYPE_CHECKING:
    from aws_annoying.utils.downloader import AbstractDownloader

logger = logging.getLogger(__name__)


class SessionManager:
    """AWS Session Manager plugin manager."""

    def __init__(self, *, session: boto3.session.Session | None = None, downloader: AbstractDownloader) -> None:
        """Initialize SessionManager.

        Args:
            session: Boto3 session to use for AWS operations.
            downloader: File downloader to use for downloading the plugin.
        """
        self.session = session or boto3.session.Session()
        self.downloader = downloader

    # ------------------------------------------------------------------------
    # Installation
    # ------------------------------------------------------------------------
    def verify_installation(self) -> tuple[bool, Path | None, str | None]:
        """Verify installation of AWS Session Manager plugin.

        Returns:
            3-tuple of boolean flag indicating whether plugin installed, binary path and version string.
        """
        # Find plugin binary
        if not (binary_path_str := shutil.which("session-manager-plugin")):
            return False, None, None

        # Check version
        binary_path = Path(binary_path_str).absolute()
        result_bytes = subprocess.run(  # noqa: S603
            [str(binary_path), "--version"],
            check=True,
            capture_output=True,
        )
        result = result_bytes.stdout.decode().strip()
        if not bool(re.match(r"[\d\.]+", result)):
            return False, binary_path, result

        return True, binary_path, result

    def install(
        self,
        *,
        os: str | None = None,
        linux_distribution: _LinuxDistribution | None = None,
        arch: str | None = None,
        root: bool | None = None,
    ) -> None:
        """Install AWS Session Manager plugin.

        Args:
            os: The operating system to install the plugin on. If `None`, will use the current operating system.
            linux_distribution: The Linux distribution to install the plugin on.
                If `None` and current `os` is `"Linux"`, will try to detect the distribution from current system.
            arch: The architecture to install the plugin on. If `None`, will use the current architecture.
            root: Whether to run the installation as root. If `None`, will check if the current user is root.
        """
        os = os or platform.system()
        linux_distribution = linux_distribution or _detect_linux_distribution()
        arch = arch or platform.machine()
        root = root or is_root()

        if os == "Windows":
            self._install_windows()
        elif os == "Darwin":
            self._install_macos(arch=arch, root=root)
        elif os == "Linux":
            self._install_linux(linux_distribution=linux_distribution, arch=arch, root=root)
        else:
            msg = f"Unsupported operating system: {os}"
            raise UnsupportedPlatformError(msg)

    def before_install(self, command: list[str]) -> None:
        """Hook to run before invoking plugin installation command."""

    # https://docs.aws.amazon.com/systems-manager/latest/userguide/install-plugin-windows.html
    def _install_windows(self) -> None:
        """Install session-manager-plugin on Windows via EXE installer."""
        download_url = (
            "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/windows/SessionManagerPluginSetup.exe"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            p = Path(temp_dir)
            exe_installer = self.downloader.download(download_url, to=p / "SessionManagerPluginSetup.exe")
            command = [str(exe_installer), "/quiet"]
            self.before_install(command)
            subprocess.call(command, cwd=p)  # noqa: S603

    # https://docs.aws.amazon.com/systems-manager/latest/userguide/install-plugin-macos-overview.html
    def _install_macos(self, *, arch: str, root: bool) -> None:
        """Install session-manager-plugin on macOS via signed installer."""
        # ! Intel chip will not be supported
        if arch == "x86_64":
            download_url = (
                "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/mac/session-manager-plugin.pkg"
            )
        elif arch == "arm64":
            download_url = (
                "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/mac_arm64/session-manager-plugin.pkg"
            )
        else:
            msg = f"Architecture {arch} not supported for macOS"
            raise UnsupportedPlatformError(msg)

        with tempfile.TemporaryDirectory() as temp_dir:
            p = Path(temp_dir)
            pkg_installer = self.downloader.download(download_url, to=p / "session-manager-plugin.pkg")

            # Run installer
            command = command_as_root(
                ["installer", "-pkg", str(pkg_installer), "-target", "/"],
                root=root,
            )
            self.before_install(command)
            subprocess.call(command, cwd=p)  # noqa: S603

            # Symlink
            command = [
                "ln",
                "-s",
                "/usr/local/sessionmanagerplugin/bin/session-manager-plugin",
                "/usr/local/bin/session-manager-plugin",
            ]
            if not root:
                command = ["sudo", *command]

            logger.info("Running %s to create symlink", " ".join(command))
            Path("/usr/local/bin").mkdir(exist_ok=True)
            subprocess.call(command, cwd=p)  # noqa: S603

    # https://docs.aws.amazon.com/systems-manager/latest/userguide/install-plugin-linux-overview.html
    def _install_linux(
        self,
        *,
        linux_distribution: _LinuxDistribution,
        arch: str,
        root: bool,
    ) -> None:
        name = linux_distribution.name
        version = linux_distribution.version

        # Debian / Ubuntu
        if name in ("debian", "ubuntu"):
            logger.info("Detected Linux distribution: Debian / Ubuntu")

            # Download installer
            url_map = {
                "x86_64": "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb",
                "x86": "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_32bit/session-manager-plugin.deb",
                "arm64": "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_arm64/session-manager-plugin.deb",
            }
            download_url = url_map.get(arch)
            if not download_url:
                msg = f"Architecture {arch} not supported for distribution {name}"
                raise UnsupportedPlatformError(msg)

            with tempfile.TemporaryDirectory() as temp_dir:
                p = Path(temp_dir)
                deb_installer = self.downloader.download(download_url, to=p / "session-manager-plugin.deb")

                # Invoke installation command
                command = command_as_root(["dpkg", "--install", str(deb_installer)], root=root)
                self.before_install(command)
                subprocess.call(command, cwd=p)  # noqa: S603

        # Amazon Linux / RHEL
        elif name in ("amzn", "rhel"):
            logger.info("Detected Linux distribution: Amazon Linux / RHEL")

            # Determine package URL and package manager
            url_map = {
                "x86_64": "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/linux_64bit/session-manager-plugin.rpm",
                "x86": "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/linux_32bit/session-manager-plugin.rpm",
                "arm64": "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/linux_arm64/session-manager-plugin.rpm",
            }
            package_url = url_map.get(arch)
            if not package_url:
                msg = f"Architecture {arch} not supported for distribution {name}"
                raise UnsupportedPlatformError(msg)

            use_yum = (
                # Amazon Linux 2
                name == "amzn" and version.startswith("2")
            ) or (
                # RHEL 7 Maipo (8 Ootpa / 9 Plow)
                name == "rhel" and "Maipo" in version
            )  # ... else use dnf
            package_manager = "yum" if use_yum else "dnf"

            # Invoke installation command
            command = command_as_root([package_manager, "install", "-y", package_url], root=root)
            self.before_install(command)
            subprocess.call(command)  # noqa: S603

        else:
            msg = f"Unsupported distribution: {name}"
            raise UnsupportedPlatformError(msg)

    # ------------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------------
    def start(
        self,
        *,
        target: str,
        document_name: str,
        parameters: dict[str, Any],
        reason: str | None = None,
        log_file: Path | None = None,
    ) -> subprocess.Popen:
        """Start new session.

        Args:
            target: The target instance ID or name.
            document_name: The SSM document name to use for the session.
            parameters: The parameters to pass to the SSM document.
            reason: The reason for starting the session.
            log_file: Optional file to log output to.

        Returns:
            Process ID of the session.
        """
        is_installed, binary_path, version = self.verify_installation()
        if not is_installed:
            msg = "Session Manager plugin is not installed."
            raise PluginNotInstalledError(msg)

        ssm = self.session.client("ssm")
        response = ssm.start_session(
            Target=target,
            DocumentName=document_name,
            Parameters=parameters,
            # ? Reason is optional but it doesn't allow empty string or `None`
            **({"Reason": reason} if reason else {}),
        )

        region = self.session.region_name
        command = [
            str(binary_path),
            json.dumps(response),
            region,
            "StartSession",
            self.session.profile_name,
            json.dumps({"Target": target}),
            f"https://ssm.{region}.amazonaws.com",
        ]

        stdout: subprocess._FILE
        if log_file is not None:  # noqa: SIM108
            stdout = log_file.open(mode="at+", buffering=1)
        else:
            stdout = subprocess.DEVNULL

        return subprocess.Popen(  # noqa: S603
            command,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            close_fds=False,  # FD inherited from parent process
        )


# ? Could be moved to utils, but didn't because it's too specific to this module
class _LinuxDistribution(NamedTuple):
    name: str
    version: str


def _detect_linux_distribution() -> _LinuxDistribution:
    """Autodetect current Linux distribution."""
    osr = os_release()
    name = osr.get("ID", "").lower()
    version = osr.get("VERSION", "")
    return _LinuxDistribution(name=name, version=version)
