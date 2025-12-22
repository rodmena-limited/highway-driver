#!/usr/bin/env python3
"""Example: Python task using external libraries (requests).

Tests that AST decorator stripping works correctly with imports.
"""

from highway import Driver

driver = Driver()


@driver.task(py=True)
def fetch_and_analyze():
    """Fetch data from a public API and analyze it."""
    from collections import Counter
    from dataclasses import dataclass

    import requests

    @dataclass
    class AnalysisResult:
        total_posts: int
        unique_users: int
        avg_title_length: float
        most_common_words: list

    # Fetch posts from JSONPlaceholder (public test API)
    response = requests.get("https://jsonplaceholder.typicode.com/posts", timeout=10)
    response.raise_for_status()
    posts = response.json()

    # Analyze the data
    user_ids = set()
    title_lengths = []
    all_words = []

    for post in posts:
        user_ids.add(post["userId"])
        title_lengths.append(len(post["title"]))
        # Extract words from title
        words = post["title"].lower().split()
        all_words.extend(words)

    # Find most common words (excluding short ones)
    word_counts = Counter(w for w in all_words if len(w) > 3)
    most_common = word_counts.most_common(5)

    result = AnalysisResult(
        total_posts=len(posts),
        unique_users=len(user_ids),
        avg_title_length=sum(title_lengths) / len(title_lengths) if title_lengths else 0,
        most_common_words=[{"word": w, "count": c} for w, c in most_common],
    )

    return {
        "total_posts": result.total_posts,
        "unique_users": result.unique_users,
        "avg_title_length": round(result.avg_title_length, 2),
        "most_common_words": result.most_common_words,
        "sample_post": posts[0] if posts else None,
    }


if __name__ == "__main__":
    print("Fetching and analyzing posts from JSONPlaceholder API...")

    result = driver.run(wait=True, timeout=60)

    print(f"\nWorkflow Status: {result.status}")
    print(f"Run ID: {result.run_id}")

    if result.tasks:
        for task_name, task_result in result.tasks.items():
            print(f"\n=== {task_name} ===")
            if task_result.result and "stdout" in task_result.result:
                stdout = task_result.result["stdout"]
                if "__HIGHWAY_RESULT__:" in stdout:
                    import json

                    json_str = stdout.split("__HIGHWAY_RESULT__:")[1].strip()
                    data = json.loads(json_str)
                    print(f"Total posts: {data['total_posts']}")
                    print(f"Unique users: {data['unique_users']}")
                    print(f"Avg title length: {data['avg_title_length']} chars")
                    print("Most common words:")
                    for item in data["most_common_words"]:
                        print(f"  - '{item['word']}': {item['count']} times")
                else:
                    print(f"Output: {stdout[:500]}")
            if task_result.error:
                print(f"Error: {task_result.error}")
