#!/usr/bin/env python3
"""Example: Check if running in a container/pod.

This checks for container/Kubernetes indicators to verify
the execution environment is properly isolated.

Usage:
    python examples/container_check.py
"""

from highway import Driver

driver = Driver()


@driver.task(py=True)
def check_container_environment():
    """Check if running in a container/Kubernetes pod."""
    import os
    import platform

    results = {
        "container_indicators": {},
        "kubernetes_indicators": {},
        "resources": {},
        "hostname": platform.node(),
        "conclusion": "",
    }

    # Container indicators
    # Check for /.dockerenv (Docker)
    results["container_indicators"]["dockerenv_exists"] = os.path.exists("/.dockerenv")

    # Check /proc/1/cgroup for container signatures
    try:
        with open("/proc/1/cgroup") as f:
            cgroup = f.read()
        results["container_indicators"]["cgroup_content"] = cgroup[:200]
        results["container_indicators"]["is_docker"] = "docker" in cgroup.lower()
        results["container_indicators"]["is_containerd"] = "containerd" in cgroup.lower()
        results["container_indicators"]["is_kubepods"] = "kubepods" in cgroup.lower()
    except Exception as e:
        results["container_indicators"]["cgroup_error"] = str(e)

    # Check for container runtime
    try:
        with open("/proc/1/sched") as f:
            sched = f.read(100)
        # In container, PID 1 is usually not "init" or "systemd"
        results["container_indicators"]["pid1_sched"] = sched.split("\n")[0]
    except Exception as e:
        results["container_indicators"]["sched_error"] = str(e)

    # Kubernetes indicators
    k8s_env_vars = [
        "KUBERNETES_SERVICE_HOST",
        "KUBERNETES_SERVICE_PORT",
        "KUBERNETES_PORT",
        "POD_NAME",
        "POD_NAMESPACE",
        "POD_IP",
        "NODE_NAME",
        "HOSTNAME",
    ]
    for var in k8s_env_vars:
        val = os.environ.get(var)
        if val:
            results["kubernetes_indicators"][var] = val

    # Check for Kubernetes service account
    results["kubernetes_indicators"]["has_service_account"] = os.path.exists(
        "/var/run/secrets/kubernetes.io/serviceaccount"
    )

    # Memory info
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
        for line in lines[:5]:
            key, val = line.split(":")
            results["resources"][key.strip()] = val.strip()

        # Also check cgroup memory limits (container-specific)
        mem_limit_paths = [
            "/sys/fs/cgroup/memory/memory.limit_in_bytes",
            "/sys/fs/cgroup/memory.max",
        ]
        for path in mem_limit_paths:
            if os.path.exists(path):
                with open(path) as f:
                    limit = f.read().strip()
                results["resources"]["cgroup_memory_limit"] = limit
                break
    except Exception as e:
        results["resources"]["meminfo_error"] = str(e)

    # CPU info
    try:
        with open("/proc/cpuinfo") as f:
            cpuinfo = f.read()
        cpu_count = cpuinfo.count("processor")
        results["resources"]["cpu_count"] = cpu_count

        # Check cgroup CPU limits
        cpu_quota_paths = [
            "/sys/fs/cgroup/cpu/cpu.cfs_quota_us",
            "/sys/fs/cgroup/cpu.max",
        ]
        for path in cpu_quota_paths:
            if os.path.exists(path):
                with open(path) as f:
                    quota = f.read().strip()
                results["resources"]["cgroup_cpu_quota"] = quota
                break
    except Exception as e:
        results["resources"]["cpuinfo_error"] = str(e)

    # Disk info
    try:
        statvfs = os.statvfs("/")
        results["resources"]["disk_total_gb"] = round(
            (statvfs.f_blocks * statvfs.f_frsize) / (1024**3), 2
        )
        results["resources"]["disk_free_gb"] = round(
            (statvfs.f_bfree * statvfs.f_frsize) / (1024**3), 2
        )
    except Exception as e:
        results["resources"]["disk_error"] = str(e)

    # Conclusion
    is_container = (
        results["container_indicators"].get("dockerenv_exists")
        or results["container_indicators"].get("is_docker")
        or results["container_indicators"].get("is_containerd")
        or results["container_indicators"].get("is_kubepods")
    )
    is_kubernetes = results["kubernetes_indicators"].get("KUBERNETES_SERVICE_HOST") or results[
        "kubernetes_indicators"
    ].get("has_service_account")

    if is_kubernetes:
        results["conclusion"] = "KUBERNETES POD - Isolated execution environment"
    elif is_container:
        results["conclusion"] = "DOCKER CONTAINER - Isolated execution environment"
    else:
        results["conclusion"] = "BARE METAL/VM - NOT isolated!"

    return results


if __name__ == "__main__":
    print("Checking container/Kubernetes environment...")

    result = driver.run(wait=True, timeout=60)

    print(f"\nWorkflow Status: {result.status}")
    print(f"Run ID: {result.run_id}")

    if result.tasks:
        for task_name, task_result in result.tasks.items():
            if task_result.result and "stdout" in task_result.result:
                stdout = task_result.result["stdout"]
                if "__HIGHWAY_RESULT__:" in stdout:
                    import json

                    json_str = stdout.split("__HIGHWAY_RESULT__:")[1].strip()
                    report = json.loads(json_str)

                    print(f"\n{'=' * 50}")
                    print(f"CONCLUSION: {report['conclusion']}")
                    print(f"{'=' * 50}")

                    print(f"\nHostname: {report['hostname']}")

                    print("\n--- CONTAINER INDICATORS ---")
                    for k, v in report["container_indicators"].items():
                        if k != "cgroup_content":
                            print(f"  {k}: {v}")

                    print("\n--- KUBERNETES INDICATORS ---")
                    if report["kubernetes_indicators"]:
                        for k, v in report["kubernetes_indicators"].items():
                            print(f"  {k}: {v}")
                    else:
                        print("  (none found)")

                    print("\n--- RESOURCES ---")
                    for k, v in report["resources"].items():
                        print(f"  {k}: {v}")
