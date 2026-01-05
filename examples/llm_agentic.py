#!/usr/bin/env python3
"""LLM-based agentic workflow using local Ollama.

This example demonstrates:
1. Multi-step LLM workflow: Fetch -> Analyze -> Summarize
2. Using tools.llm.call with Ollama provider
3. Task dependencies and result passing
4. Agentic pattern with sequential LLM reasoning

Prerequisites:
- Ollama running locally (docker or native)
- A model installed (e.g., llama3.2, deepseek-r1:8b, qwen2.5:7b)
- Highway docker stack running

Run:
    python examples/llm_agentic.py
"""

from highway import Driver


def main():
    driver = Driver()

    # Step 1: Fetch content from an API
    @driver.task(http=True)
    def fetch_content():
        """Fetch sample JSON data to analyze."""
        return {
            "url": "https://httpbin.org/json",
            "method": "GET",
        }

    # Step 2: Analyze the fetched content with LLM
    @driver.task(tool="tools.llm.call", depends=["fetch_content"])
    def analyze():
        """Analyze JSON structure using LLM.

        Note: The actual LLM prompt will use {{task_result}} to access
        the previous task's output.
        """
        return {
            "provider": "ollama",
            "model": "qwen3-vl:235b-instruct-cloud",  # Available via Ollama cloud
            "system_prompt": "You are a data analyst. Analyze JSON structures concisely.",
            "prompt": "Analyze this JSON response and identify the key fields: {{fetch_content_result}}",
            "temperature": 0.3,
            "max_tokens": 500,
        }

    # Step 3: Create executive summary
    @driver.task(tool="tools.llm.call", depends=["analyze"])
    def summarize():
        """Create a brief executive summary."""
        return {
            "provider": "ollama",
            "model": "qwen3-vl:235b-instruct-cloud",  # Available via Ollama cloud
            "system_prompt": "You are a technical writer. Create brief, clear summaries.",
            "prompt": "In 2-3 sentences, summarize this analysis: {{analyze_result.response}}",
            "temperature": 0.5,
            "max_tokens": 200,
        }

    print("Running LLM agentic workflow...")
    print("Pipeline: fetch_content -> analyze -> summarize")
    print()

    result = driver.run(wait=True, timeout=300)

    print(f"Status: {result.status}")
    print(f"Run ID: {result.run_id}")
    print()

    if result.tasks:
        for task_name, task_result in result.tasks.items():
            print("=" * 60)
            print(f"Task: {task_name}")
            print("=" * 60)

            if task_result.result:
                # Handle different result types
                res = task_result.result

                # HTTP task results
                if "status_code" in res:
                    print("HTTP Status: {}".format(res.get("status_code")))
                    body = res.get("body", "")
                    if isinstance(body, str) and len(body) > 200:
                        print(f"Body: {body[:200]}...")
                    else:
                        print(f"Body: {body}")

                # LLM task results
                elif "response" in res:
                    print("LLM Response:")
                    print(res.get("response", ""))

                # Shell/other results
                elif "stdout" in res:
                    print("Output: {}".format(res.get("stdout", "").strip()))

                else:
                    print(f"Result: {res}")

            if task_result.error:
                print(f"Error: {task_result.error}")

            print()


if __name__ == "__main__":
    main()
