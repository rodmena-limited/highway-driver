#!/usr/bin/env python3
"""Example: Check access to Vault secrets in pod.

This checks if the execution environment can access
Vault-injected secrets in the Kubernetes pod.

Usage:
    python examples/vault_secrets_check.py
"""

from highway import Driver

driver = Driver()


@driver.task(py=True)
def check_vault_secrets():
    """Check for Vault secret injection in the pod."""
    import os

    results = {
        "vault_paths_checked": [],
        "secrets_found": [],
        "env_secrets": {},
        "kubernetes_secrets": [],
        "conclusion": "",
    }

    # Common Vault Agent injection paths
    vault_paths = [
        "/vault/secrets",
        "/vault/secrets/db",
        "/vault/secrets/config",
        "/vault/secrets/creds",
        "/etc/vault",
        "/run/secrets",
        "/var/run/secrets/vault",
    ]

    for path in vault_paths:
        results["vault_paths_checked"].append(path)
        if os.path.exists(path):
            try:
                if os.path.isdir(path):
                    files = os.listdir(path)
                    for f in files:
                        fpath = os.path.join(path, f)
                        try:
                            with open(fpath) as fp:
                                content = fp.read(500)
                            results["secrets_found"].append(
                                {
                                    "path": fpath,
                                    "content_preview": content[:200] + "..."
                                    if len(content) > 200
                                    else content,
                                    "size": len(content),
                                }
                            )
                        except Exception as e:
                            results["secrets_found"].append(
                                {
                                    "path": fpath,
                                    "error": str(e),
                                }
                            )
                else:
                    with open(path) as f:
                        content = f.read(500)
                    results["secrets_found"].append(
                        {
                            "path": path,
                            "content_preview": content[:200],
                            "size": len(content),
                        }
                    )
            except Exception as e:
                results["secrets_found"].append(
                    {
                        "path": path,
                        "error": str(e),
                    }
                )

    # Check environment variables for secrets
    secret_env_patterns = [
        "VAULT_",
        "SECRET_",
        "PASSWORD",
        "API_KEY",
        "TOKEN",
        "DB_",
        "POSTGRES_",
        "REDIS_",
        "JWT_",
    ]
    for key, value in os.environ.items():
        for pattern in secret_env_patterns:
            if pattern in key.upper():
                # Mask the value but show first/last chars
                if len(value) > 8:
                    masked = value[:3] + "*" * (len(value) - 6) + value[-3:]
                else:
                    masked = "*" * len(value)
                results["env_secrets"][key] = {
                    "masked_value": masked,
                    "length": len(value),
                }
                break

    # Check Kubernetes secrets mount
    k8s_secrets_path = "/var/run/secrets/kubernetes.io/serviceaccount"
    if os.path.exists(k8s_secrets_path):
        try:
            files = os.listdir(k8s_secrets_path)
            for f in files:
                fpath = os.path.join(k8s_secrets_path, f)
                try:
                    with open(fpath) as fp:
                        content = fp.read(200)
                    results["kubernetes_secrets"].append(
                        {
                            "name": f,
                            "preview": content[:100] + "..." if len(content) > 100 else content,
                        }
                    )
                except:
                    results["kubernetes_secrets"].append({"name": f, "readable": False})
        except Exception as e:
            results["kubernetes_secrets"].append({"error": str(e)})

    # Try to find any .env files or config files with secrets
    config_patterns = [
        "/app/.env",
        "/app/config.ini",
        "/etc/highway/config.ini",
        "/app/docker/.env",
    ]
    for pattern in config_patterns:
        if os.path.exists(pattern):
            try:
                with open(pattern) as f:
                    content = f.read(1000)
                results["secrets_found"].append(
                    {
                        "path": pattern,
                        "content_preview": content[:300] + "..." if len(content) > 300 else content,
                    }
                )
            except Exception as e:
                results["secrets_found"].append(
                    {
                        "path": pattern,
                        "error": str(e),
                    }
                )

    # Conclusion
    if results["secrets_found"]:
        results["conclusion"] = f"FOUND {len(results['secrets_found'])} secret files accessible!"
    else:
        results["conclusion"] = "No Vault secret files found in standard paths"

    return results


if __name__ == "__main__":
    print("Checking Vault secrets access in pod...")

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

                    print("\n--- VAULT SECRET FILES ---")
                    if report["secrets_found"]:
                        for secret in report["secrets_found"]:
                            print(f"\n  Path: {secret.get('path')}")
                            if "error" in secret:
                                print(f"  Error: {secret['error']}")
                            else:
                                print(f"  Size: {secret.get('size')} bytes")
                                print(f"  Content: {secret.get('content_preview', 'N/A')}")
                    else:
                        print("  (none found)")

                    print("\n--- ENVIRONMENT SECRETS ---")
                    if report["env_secrets"]:
                        for key, info in report["env_secrets"].items():
                            print(f"  {key}: {info['masked_value']} (len={info['length']})")
                    else:
                        print("  (none found)")

                    print("\n--- KUBERNETES SERVICE ACCOUNT ---")
                    for item in report["kubernetes_secrets"]:
                        if "name" in item:
                            print(f"  {item['name']}: {item.get('preview', 'not readable')[:50]}")
