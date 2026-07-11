from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import tempfile
from unittest import TestCase


class OpsApiTunnelTests(TestCase):
    script = Path("scripts/open_ops_api_ssh_tunnel.sh").resolve()

    def _write_executable(self, path: Path, body: str) -> None:
        path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def test_uses_password_environment_and_exports_local_url(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            bin_dir = temp / "bin"
            bin_dir.mkdir()
            args_path = temp / "sshpass-args"
            curl_args_path = temp / "curl-args"
            github_env = temp / "github-env"
            self._write_executable(bin_dir / "sshpass", 'printf "%s\\n" "$@" > "$ARGS_PATH"\n')
            self._write_executable(bin_dir / "curl", 'printf "%s\\n" "$@" > "$CURL_ARGS_PATH"\n')

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{bin_dir}:{env['PATH']}",
                    "HOME": str(temp / "home"),
                    "ECS_HOST": "ecs.example.test",
                    "ECS_USERNAME": "deploy-user",
                    "ECS_PASSWORD": "never-write-this-password",
                    "ECS_SSH_KNOWN_HOSTS": "ecs.example.test ssh-ed25519 pinned-test-key",
                    "ARGS_PATH": str(args_path),
                    "CURL_ARGS_PATH": str(curl_args_path),
                    "GITHUB_ENV": str(github_env),
                }
            )

            completed = subprocess.run(
                ["bash", str(self.script)],
                cwd=self.script.parents[1],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            sshpass_args = args_path.read_text(encoding="utf-8")
            self.assertIn("-e\nssh\n", sshpass_args)
            self.assertNotIn("never-write-this-password", sshpass_args)
            self.assertIn("StrictHostKeyChecking=yes", sshpass_args)
            self.assertEqual(
                "ecs.example.test ssh-ed25519 pinned-test-key\n",
                (temp / "home" / ".ssh" / "known_hosts").read_text(encoding="utf-8"),
            )
            curl_args = curl_args_path.read_text(encoding="utf-8")
            self.assertIn("--connect-timeout\n3\n", curl_args)
            self.assertIn("--max-time\n5\n", curl_args)
            self.assertEqual(
                "OPS_API_URL=http://127.0.0.1:18767\n",
                github_env.read_text(encoding="utf-8"),
            )

    def test_retries_transient_ssh_failures_three_times(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            bin_dir = temp / "bin"
            bin_dir.mkdir()
            attempt_path = temp / "attempts"
            self._write_executable(
                bin_dir / "sshpass",
                'attempt=0\n[ ! -f "$ATTEMPT_PATH" ] || attempt="$(cat "$ATTEMPT_PATH")"\n'
                'attempt=$((attempt + 1))\nprintf "%s" "$attempt" > "$ATTEMPT_PATH"\n'
                '[ "$attempt" -ge 3 ]\n',
            )
            self._write_executable(bin_dir / "curl", "exit 0\n")
            self._write_executable(bin_dir / "sleep", "exit 0\n")

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{bin_dir}:{env['PATH']}",
                    "HOME": str(temp / "home"),
                    "ECS_HOST": "ecs.example.test",
                    "ECS_USERNAME": "deploy-user",
                    "ECS_PASSWORD": "test-password",
                    "ECS_SSH_KNOWN_HOSTS": "ecs.example.test ssh-ed25519 pinned-test-key",
                    "ATTEMPT_PATH": str(attempt_path),
                }
            )

            completed = subprocess.run(
                ["bash", str(self.script)],
                cwd=self.script.parents[1],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual("3", attempt_path.read_text(encoding="utf-8"))

    def test_rejects_missing_pinned_host_key_before_ssh(self) -> None:
        env = os.environ.copy()
        env.update(
            {
                "ECS_HOST": "ecs.example.test",
                "ECS_USERNAME": "deploy-user",
                "ECS_PASSWORD": "test-password",
            }
        )
        env.pop("ECS_SSH_KNOWN_HOSTS", None)

        completed = subprocess.run(
            ["bash", str(self.script)],
            cwd=self.script.parents[1],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("ECS_SSH_KNOWN_HOSTS", completed.stderr)
