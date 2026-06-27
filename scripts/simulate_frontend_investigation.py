import sys
import json
import time
import subprocess
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.investigation_scope import InvestigationScope
from scripts.run_incident_investigation import run_investigation, cleanup_runtime_cache


def run_cmd(cmd: List[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=capture,
    )

    if check and result.returncode != 0:
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")

    return result


def get_kubernetes_names(resource: str) -> List[str]:
    result = run_cmd(["kubectl", "get", resource, "-o", "json"])
    payload = json.loads(result.stdout)

    return [
        item["metadata"]["name"]
        for item in payload.get("items", [])
        if item.get("metadata", {}).get("name")
    ]


def get_nodes() -> List[str]:
    return get_kubernetes_names("nodes")


def get_namespaces() -> List[str]:
    return get_kubernetes_names("namespaces")


def get_scenarios() -> List[Path]:
    scenarios_dir = PROJECT_ROOT / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(list(scenarios_dir.glob("*.yml")) + list(scenarios_dir.glob("*.yaml")))
    return files


def choose_from_list(title: str, options: List[str], default_index: int = 0) -> str:
    if not options:
        raise ValueError(f"No options available for {title}")

    print("")
    print(title)
    print("-" * len(title))

    for index, option in enumerate(options, start=1):
        marker = " default" if index - 1 == default_index else ""
        print(f"{index}. {option}{marker}")

    while True:
        raw = input(f"Choose 1-{len(options)} [{default_index + 1}]: ").strip()

        if not raw:
            return options[default_index]

        if raw.isdigit():
            selected = int(raw)
            if 1 <= selected <= len(options):
                return options[selected - 1]

        print("Invalid choice. Try again.")


def yes_no(question: str, default: bool = True) -> bool:
    suffix = "Y/n" if default else "y/N"

    while True:
        raw = input(f"{question} [{suffix}]: ").strip().lower()

        if not raw:
            return default

        if raw in {"y", "yes"}:
            return True

        if raw in {"n", "no"}:
            return False

        print("Please answer yes or no.")


def ask_namespace(existing_namespaces: List[str]) -> str:
    print("")
    print("Namespace")
    print("---------")
    print("Existing namespaces:")
    for ns in existing_namespaces:
        print(f"- {ns}")

    namespace = input("Enter investigation namespace [opslens-test]: ").strip()
    return namespace or "opslens-test"


def reset_namespace(namespace: str) -> None:
    print(f"\nDeleting namespace if exists: {namespace}")
    run_cmd(["kubectl", "delete", "namespace", namespace, "--ignore-not-found"], check=False, capture=False)
    time.sleep(3)


def ensure_namespace(namespace: str) -> None:
    print(f"\nEnsuring namespace exists: {namespace}")
    run_cmd(["kubectl", "create", "namespace", namespace], check=False, capture=False)


def render_scenario_for_namespace(scenario_path: Path, namespace: str) -> Path:
    """
    Current scenarios may use opslens-demo as the default namespace.
    This renders a temporary copy with the user-selected namespace.

    This mimics frontend behavior:
    user chooses namespace -> backend applies scenario in that namespace.
    """

    text = scenario_path.read_text(encoding="utf-8")
    text = text.replace("opslens-demo", namespace)

    live_dir = PROJECT_ROOT / "data" / "live"
    live_dir.mkdir(parents=True, exist_ok=True)

    rendered_path = live_dir / f"rendered_{scenario_path.stem}_{namespace}.yml"
    rendered_path.write_text(text, encoding="utf-8")

    return rendered_path


def apply_scenario(scenario_path: Path, namespace: str) -> None:
    rendered_path = render_scenario_for_namespace(scenario_path, namespace)

    print(f"\nApplying scenario:")
    print(f"- source:   {scenario_path}")
    print(f"- rendered: {rendered_path}")
    print(f"- namespace: {namespace}")

    run_cmd(["kubectl", "apply", "-f", str(rendered_path)], capture=False)


def main() -> None:
    print("")
    print("OpsLens Frontend Investigation Simulator")
    print("=======================================")

    nodes = get_nodes()
    namespaces = get_namespaces()
    scenarios = get_scenarios()

    if not nodes:
        raise RuntimeError("No Kubernetes nodes found. Is your cluster running?")

    node_name = choose_from_list("Select Node", nodes, default_index=0)
    namespace = ask_namespace(namespaces)

    scenario_path: Optional[Path] = None

    if scenarios:
        scenario_options = ["Skip scenario apply"] + [str(path.relative_to(PROJECT_ROOT)) for path in scenarios]
        selected_scenario = choose_from_list("Select Scenario", scenario_options, default_index=1 if len(scenario_options) > 1 else 0)

        if selected_scenario != "Skip scenario apply":
            scenario_path = PROJECT_ROOT / selected_scenario
    else:
        print("\nNo scenarios found under scenarios/. Investigation will run against existing cluster state.")

    reset_first = yes_no("Reset namespace before applying/running investigation?", default=True)
    apply_selected = scenario_path is not None and yes_no("Apply selected scenario?", default=True)
    seed_metrics = yes_no("Seed demo resource anomaly readings for Metrics Agent test?", default=True)
    wait_seconds = input("Wait seconds after scenario apply [45]: ").strip()

    try:
        wait_seconds = int(wait_seconds or "45")
    except ValueError:
        wait_seconds = 45

    print("")
    print("Investigation Request")
    print("---------------------")
    print(f"node_name:         {node_name}")
    print(f"namespace:         {namespace}")
    print(f"scenario:          {scenario_path if scenario_path else 'none'}")
    print(f"reset_namespace:   {reset_first}")
    print(f"apply_scenario:    {apply_selected}")
    print(f"demo_seed_metrics: {seed_metrics}")
    print(f"wait_seconds:      {wait_seconds}")

    if not yes_no("Run this investigation request?", default=True):
        print("Cancelled.")
        return

    cleanup_runtime_cache()

    if reset_first:
        reset_namespace(namespace)

    ensure_namespace(namespace)

    if apply_selected and scenario_path:
        apply_scenario(scenario_path, namespace)
        print(f"\nWaiting {wait_seconds} seconds for Kubernetes events/logs...")
        time.sleep(wait_seconds)

    scope = InvestigationScope(
        node_name=node_name,
        namespace=namespace,
    )
    scope.validate()

    print("")
    print("Running OpsLens investigation...")
    print("-------------------------------")

    final_report = run_investigation(
        scope=scope,
        demo_seed_metrics=seed_metrics,
    )

    print("")
    print("Investigation completed.")
    print("------------------------")
    print(f"generation_mode: {final_report.get('generation_mode')}")
    print(f"model_used:      {final_report.get('model_used')}")
    print(f"title:           {final_report.get('title')}")
    print(f"severity:        {final_report.get('severity')}")
    print(f"confidence:      {final_report.get('confidence')}")
    print(f"markdown_report: {final_report.get('markdown_report_path')}")
    print(f"json_report:     {final_report.get('json_report_path')}")

    print("")
    print("Open latest report with:")
    print("Get-Content (Get-ChildItem .\\data\\final_incident_reports\\*.md | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName")


if __name__ == "__main__":
    main()
