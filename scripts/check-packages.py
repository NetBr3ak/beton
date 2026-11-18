"""Build release artifacts and exercise their installed consumer entry points."""

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], directory: Path) -> str:
    result = subprocess.run(command, cwd=directory, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(
            f"{command!r} failed ({result.returncode}):\n{result.stdout}\n{result.stderr}"
        )
    return result.stdout.strip()


def verify(command: list[str], project: Path) -> None:
    expected = [str(project / "tests/test_checkout.py")]
    result = run([*command, "affected", "pricing.py", "--json"], project)
    if json.loads(result) != expected:
        raise AssertionError(f"{command!r}: wrong affected tests: {result}")
    empty = run([*command, "affected", "unused.py", "--json"], project)
    if json.loads(empty) != []:
        raise AssertionError(f"{command!r}: wrong empty result: {empty}")
    marker = project / "executed"
    if marker.exists():
        raise AssertionError("Discovery executed project code")
    invalid = subprocess.run(
        [*command, "affected", "missing.py"], cwd=project, capture_output=True
    )
    if invalid.returncode != 2:
        raise AssertionError(f"{command!r}: missing source did not exit 2")
    print(f"PASS consumer: {' '.join(command)}", flush=True)


def main() -> None:
    artifacts = ROOT / "dist"
    artifacts.mkdir(exist_ok=True)
    run(["uv", "build", "--out-dir", str(artifacts)], ROOT)
    npm_archive = json.loads(
        run(["npm", "pack", "--json", "--pack-destination", str(artifacts)], ROOT)
    )[0]
    run(["cargo", "fmt", "--check"], ROOT)
    run(
        [
            "cargo",
            "clippy",
            "--offline",
            "--no-default-features",
            "--",
            "-D",
            "warnings",
        ],
        ROOT,
    )
    run(
        ["cargo", "package", "--offline", "--allow-dirty", "--no-default-features"],
        ROOT,
    )
    shutil.copy2(ROOT / "target/package/beton-checks-0.3.0.crate", artifacts)
    with tempfile.TemporaryDirectory(prefix="beton-packages-") as scratch:
        directory = Path(scratch).resolve()
        project = directory / "project with spaces"
        (project / "tests").mkdir(parents=True)
        (project / "pyproject.toml").touch()
        (project / "pricing.py").write_text(
            "from pathlib import Path\nPath('executed').touch()\n"
        )
        (project / "unused.py").touch()
        (project / "tests/test_checkout.py").write_text("import pricing\n")
        for distribution in (
            artifacts / "beton_checks-0.3.0-py3-none-any.whl",
            artifacts / "beton_checks-0.3.0.tar.gz",
        ):
            environment = directory / distribution.name
            run(["uv", "venv", "--python", sys.executable, str(environment)], directory)
            executable = environment / (
                "Scripts/python.exe" if os.name == "nt" else "bin/python"
            )
            run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(executable),
                    "--no-deps",
                    str(distribution),
                ],
                directory,
            )
            verify([str(executable), "-m", "beton_checks"], project)
            console = environment / (
                "Scripts/beton.exe" if os.name == "nt" else "bin/beton"
            )
            verify([str(console)], project)
        node_project = directory / "node-consumer"
        node_project.mkdir()
        run(
            [
                "npm",
                "install",
                "--ignore-scripts",
                "--no-audit",
                "--no-fund",
                "--prefix",
                str(node_project),
                str(artifacts / npm_archive["filename"]),
            ],
            directory,
        )
        verify(
            [
                "node",
                str(node_project / "node_modules/beton-checks/packaging/beton.cjs"),
            ],
            project,
        )
        verify(
            ["npm", "exec", "--prefix", str(node_project), "--offline", "--", "beton"],
            project,
        )
        plugin = node_project / "node_modules/beton-checks"
        manifest = json.loads((plugin / ".claude-plugin/plugin.json").read_text())
        if manifest["version"] != "0.3.0":
            raise AssertionError("npm archive has the wrong plugin version")
        for name in (
            "hooks/_guard_eval.py",
            "bin/lib.sh",
            "commands/beton.md",
            "agents/localize.md",
            "skills/beton/SKILL.md",
        ):
            if not (plugin / name).is_file():
                raise AssertionError(f"npm plugin is missing {name}")
        isolated_home = directory / "plugin-home"
        isolated_home.mkdir()
        plugin_environment = dict(
            os.environ,
            HOME=str(isolated_home),
            CLAUDE_PLUGIN_ROOT=str(plugin),
            BETON_MODE="strict",
            BETON_BYPASS_GUARD="on",
        )
        activation = subprocess.run(
            ["node", str(plugin / "hooks/beton-activate.js")],
            env=plugin_environment,
            capture_output=True,
            text=True,
            check=True,
        )
        if "Active skill: beton-swebench" not in activation.stdout:
            raise AssertionError("Installed plugin could not load its skill")
        guard = subprocess.run(
            ["bash", str(plugin / "hooks/pre-tool-guard.sh")],
            input=json.dumps(
                {"tool_name": "Edit", "tool_input": {"new_string": "x = 1  # noqa"}}
            ),
            env=plugin_environment,
            capture_output=True,
            text=True,
            check=True,
        )
        if json.loads(guard.stdout)["decision"] != "block":
            raise AssertionError("Installed plugin guard did not reject a suppression")
        selected = run(
            [
                "bash",
                str(plugin / "bin/run-affected-tests"),
                str(project / "pricing.py"),
                "--dry-run",
            ],
            project,
        )
        if selected != str(project / "tests/test_checkout.py"):
            raise AssertionError(
                "Installed plugin did not load the shared discovery engine"
            )
        print(
            "PASS installed npm plugin: manifest, skill, guard, discovery", flush=True
        )
        archive = artifacts / "beton-checks-0.3.0.crate"
        with tarfile.open(archive) as package:
            package.extractall(directory, filter="data")
        cargo_root = directory / "cargo-consumer"
        run(
            [
                "cargo",
                "install",
                "--offline",
                "--locked",
                "--no-default-features",
                "--path",
                str(directory / "beton-checks-0.3.0"),
                "--root",
                str(cargo_root),
            ],
            directory,
        )
        verify(
            [str(cargo_root / "bin" / ("beton.exe" if os.name == "nt" else "beton"))],
            project,
        )
    print("All standalone package consumers passed.")


if __name__ == "__main__":
    main()
