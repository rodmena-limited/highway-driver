"""Sample workflow: Local git ls-files -> Highway foreach echo.

Demonstrates:
1. Local shell task (git ls-files)
2. Local Python task that parses output
3. Highway ForEach that processes each file in parallel
"""

from dotenv import load_dotenv

load_dotenv()

from highway import Driver

driver = Driver()


@driver.task(shell=True, local=True)
def list_files():
    """Get list of git-tracked files locally."""
    return "git ls-files"


@driver.task(py=True, local=True, depends=["list_files"])
def parse_files():
    """Parse git ls-files output into a list."""
    # INPUT contains upstream outputs: stdout, stderr, returncode
    stdout = INPUT.get("stdout", "")
    files = [f.strip() for f in stdout.strip().split("\n") if f.strip()]
    # Limit to first 5 files for demo
    return {"files": files[:5]}


@driver.foreach(items="{{parse_files_result.files}}", depends=["parse_files"])
def echo_file():
    """Echo each filename on Highway (ForEach loop)."""
    return "echo 'Processing: {{current_item}}'"


if __name__ == "__main__":
    # Clean up stale database
    import os
    if os.path.exists(".stabilize.db"):
        os.remove(".stabilize.db")

    print("Starting workflow...")
    print("  1. list_files (local shell) - git ls-files")
    print("  2. parse_files (local python) - parse into list")
    print("  3. echo_file (Highway foreach) - echo each file")
    print()

    result = driver.run(timeout=300)

    print(f"\nStatus: {result.status}")
    print(f"Run ID: {result.run_id}")

    print("\nTask Results:")
    for name, task in result.tasks.items():
        state = task.state.name
        print(f"  {name}: {state}")
        if task.error:
            print(f"    Error: {task.error}")

    # Show parse_files result (the files list)
    if "parse_files" in result.tasks:
        files = result.tasks["parse_files"].result.get("result", {}).get("files", [])
        print(f"\nFiles processed by foreach: {files}")

    # Show foreach iterations
    if "echo_file" in result.tasks:
        highway_result = result.tasks["echo_file"].result.get("highway_result", {})
        output = highway_result.get("output", [])
        if isinstance(output, list):
            print(f"Foreach ran {len(output)} iterations")
