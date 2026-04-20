"""heliox agent — deploy, status, logs."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import typer
from rich.console import Console

from heliox_cli.config import get_api_key, get_api_url
from heliox_cli.output import print_error, print_info, print_success, print_warning

app = typer.Typer(help="Deploy and manage the Heliox GPU agent DaemonSet.")
console = Console()

_AGENT_IMAGE = "ghcr.io/heliox-ai/heliox-agent:latest"
_DAEMONSET_TEMPLATE = """\
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: heliox-agent
  namespace: {namespace}
spec:
  selector:
    matchLabels:
      app: heliox-agent
  updateStrategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: heliox-agent
    spec:
      hostPID: true
      tolerations:
        - key: "nvidia.com/gpu"
          operator: "Exists"
          effect: "NoSchedule"
      nodeSelector:
        accelerator: "true"
      containers:
        - name: heliox-agent
          image: {image}
          command: ["python", "/agent/heliox_agent.py"]
          args:
            - "--endpoint"
            - "{endpoint}"
            - "--api-key"
            - "$(HELIOX_API_KEY)"
            - "--interval"
            - "60"
          env:
            - name: HELIOX_API_KEY
              valueFrom:
                secretKeyRef:
                  name: heliox-agent-secret
                  key: api_key
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 200m
              memory: 128Mi
"""


def _kubectl(*args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["kubectl", *args], capture_output=True, text=True)
    return result


def _require_kubectl() -> None:
    if not shutil.which("kubectl"):
        print_error(
            "kubectl not found. Install it: https://kubernetes.io/docs/tasks/tools/ "
            "and ensure your KUBECONFIG is set."
        )


@app.command()
def deploy(
    namespace: str = typer.Option("heliox", "--namespace", "-n", help="Kubernetes namespace."),
    kubeconfig: str = typer.Option("", "--kubeconfig", help="Path to kubeconfig file."),
    image: str = typer.Option(_AGENT_IMAGE, "--image", help="Agent container image."),
    api_key_override: str = typer.Option(
        "", "--api-key", help="Override the stored API key for the agent."
    ),
) -> None:
    """Deploy the Heliox GPU agent DaemonSet to your cluster."""
    _require_kubectl()

    api_url = get_api_url()
    api_key = api_key_override or get_api_key()

    if not api_key:
        print_error(
            "No API key found. Run `heliox auth login` or pass --api-key."
        )

    env = {}
    if kubeconfig:
        import os
        env = {**__import__("os").environ, "KUBECONFIG": kubeconfig}

    # 1. Create namespace
    print_info(f"Creating namespace [bold]{namespace}[/bold]…")
    r = subprocess.run(
        ["kubectl", "create", "namespace", namespace, "--dry-run=client", "-o", "yaml"],
        capture_output=True, text=True, env=env or None,
    )
    subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=r.stdout, capture_output=True, text=True, env=env or None,
    )

    # 2. Create/update the API key Secret
    print_info("Creating agent Secret [bold]heliox-agent-secret[/bold]…")
    secret_result = subprocess.run(
        [
            "kubectl", "create", "secret", "generic", "heliox-agent-secret",
            f"--from-literal=api_key={api_key}",
            f"--namespace={namespace}",
            "--dry-run=client", "-o", "yaml",
        ],
        capture_output=True, text=True, env=env or None,
    )
    apply_secret = subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=secret_result.stdout, capture_output=True, text=True, env=env or None,
    )
    if apply_secret.returncode != 0:
        print_error(f"Failed to create Secret: {apply_secret.stderr}")

    # 3. Write DaemonSet manifest to a temp file and apply
    print_info("Applying agent DaemonSet…")
    manifest = _DAEMONSET_TEMPLATE.format(
        namespace=namespace,
        image=image,
        endpoint=api_url,
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(manifest)
        tmp_path = f.name

    apply_ds = subprocess.run(
        ["kubectl", "apply", "-f", tmp_path, f"--namespace={namespace}"],
        capture_output=True, text=True, env=env or None,
    )
    Path(tmp_path).unlink(missing_ok=True)

    if apply_ds.returncode != 0:
        print_error(f"DaemonSet apply failed:\n{apply_ds.stderr}")

    # 4. Wait for at least 1 pod to be Running
    print_info("Waiting for agent pod to become Running (timeout 120s)…")
    wait_result = subprocess.run(
        [
            "kubectl", "wait",
            "--for=condition=Ready", "pod",
            "-l", "app=heliox-agent",
            f"--namespace={namespace}",
            "--timeout=120s",
        ],
        capture_output=True, text=True, env=env or None,
    )

    if wait_result.returncode == 0:
        console.print()
        print_success(
            "Agent deployed successfully. "
            "GPU metrics will appear in your dashboard within 2 minutes."
        )
        console.print(f"\n  [dim]Run [bold]heliox agent status[/bold] to verify.[/dim]")
    else:
        print_warning(
            "Agent deployed but pods are not yet Ready. "
            "Check with `heliox agent status`."
        )
        console.print(f"  [dim]{wait_result.stderr}[/dim]")


@app.command()
def status(
    namespace: str = typer.Option("heliox", "--namespace", "-n", help="Kubernetes namespace."),
) -> None:
    """Check the DaemonSet status and pod health."""
    _require_kubectl()

    result = _kubectl(
        "get", "daemonset", "heliox-agent",
        f"--namespace={namespace}",
        "-o", "wide",
    )
    if result.returncode != 0:
        if "not found" in result.stderr:
            console.print(
                "[yellow]⚠[/yellow]  Agent DaemonSet not found in "
                f"namespace [bold]{namespace}[/bold].\n"
                "  Run [bold]heliox agent deploy[/bold] to install it."
            )
        else:
            print_error(result.stderr)
        return

    console.print(result.stdout)

    pods = _kubectl(
        "get", "pods",
        "-l", "app=heliox-agent",
        f"--namespace={namespace}",
        "-o", "wide",
    )
    if pods.returncode == 0:
        console.print(pods.stdout)


@app.command()
def logs(
    namespace: str = typer.Option("heliox", "--namespace", "-n", help="Kubernetes namespace."),
    tail: int = typer.Option(50, "--tail", "-t", help="Number of log lines to show."),
    follow: bool = typer.Option(False, "--follow", "-f", help="Stream logs continuously."),
) -> None:
    """Stream logs from the agent DaemonSet pods."""
    _require_kubectl()

    cmd = [
        "kubectl", "logs",
        "-l", "app=heliox-agent",
        f"--namespace={namespace}",
        f"--tail={tail}",
    ]
    if follow:
        cmd.append("-f")

    try:
        subprocess.run(cmd, check=False)
    except KeyboardInterrupt:
        pass
