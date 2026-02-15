"""
REST API Test Suite
===================
Automatically tests API endpoints for:
  - HTTP 200 status code
  - Valid JSON response
  - Response time under 400ms

Generates a Markdown report: api_report.md
"""

import requests
import json
import sys
from datetime import datetime


def test_endpoint(url: str) -> dict:
    """
    Test a single API endpoint and return the results.
    """
    result = {
        "url": url,
        "status_code": None,
        "status_check": False,
        "json_check": False,
        "time_check": False,
        "response_time_ms": None,
        "error": None,
    }

    try:
        response = requests.get(url, timeout=10)
        result["status_code"] = response.status_code
        result["response_time_ms"] = round(response.elapsed.total_seconds() * 1000, 2)

        # Check 1: Status code is 200
        result["status_check"] = response.status_code == 200

        # Check 2: Response is valid JSON
        try:
            response.json()
            result["json_check"] = True
        except (json.JSONDecodeError, ValueError):
            result["json_check"] = False

        # Check 3: Response time under 400ms
        result["time_check"] = result["response_time_ms"] < 400

    except requests.exceptions.ConnectionError:
        result["error"] = "Connection refused or DNS failure"
    except requests.exceptions.Timeout:
        result["error"] = "Request timed out (>10s)"
    except requests.exceptions.RequestException as e:
        result["error"] = str(e)

    return result


def generate_report(results: list[dict], filepath: str = "api_report.md"):
    """
    Generate a Markdown report summarizing all test results.
    """
    total = len(results)
    passed = sum(1 for r in results if r["status_check"] and r["json_check"] and r["time_check"])
    failed = total - passed

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# REST API Test Report",
        "",
        f"**Generated:** {now}  ",
        f"**Total Endpoints Tested:** {total}  ",
        f"**Passed:** {passed} | **Failed:** {failed}",
        "",
        "---",
        "",
        "## Summary Table",
        "",
        "| # | Endpoint | Status Code | JSON Valid | Response Time (ms) | Result |",
        "|---|----------|:-----------:|:----------:|:------------------:|:------:|",
    ]

    for i, r in enumerate(results, 1):
        if r["error"]:
            lines.append(
                f"| {i} | `{r['url']}` | ❌ Error | ❌ | — | ❌ **FAIL** |"
            )
        else:
            sc = "✅" if r["status_check"] else f"❌ {r['status_code']}"
            js = "✅" if r["json_check"] else "❌"
            rt = f"{r['response_time_ms']}"
            tc = "✅" if r["time_check"] else f"❌ ({rt}ms)"
            overall = (
                "✅ **PASS**"
                if r["status_check"] and r["json_check"] and r["time_check"]
                else "❌ **FAIL**"
            )
            lines.append(f"| {i} | `{r['url']}` | {sc} | {js} | {rt} | {overall} |")

    lines += [
        "",
        "---",
        "",
        "## Detailed Results",
        "",
    ]

    for i, r in enumerate(results, 1):
        all_pass = r["status_check"] and r["json_check"] and r["time_check"]
        icon = "✅" if all_pass else "❌"
        lines.append(f"### {i}. {icon} `{r['url']}`")
        lines.append("")

        if r["error"]:
            lines.append(f"- **Error:** {r['error']}")
        else:
            lines.append(f"- **Status Code:** {r['status_code']} {'✅' if r['status_check'] else '❌'}")
            lines.append(f"- **Valid JSON:** {'Yes ✅' if r['json_check'] else 'No ❌'}")
            lines.append(
                f"- **Response Time:** {r['response_time_ms']}ms "
                f"{'✅' if r['time_check'] else '❌ (exceeds 400ms limit)'}"
            )

        lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


def main():
    """
    Entry point — accepts URLs as command-line arguments.
    Usage:  python api_tester.py <url1> <url2> ...
    """
    if len(sys.argv) < 2:
        print("Usage: python api_tester.py <url1> [url2] [url3] ...")
        print("Example: python api_tester.py https://jsonplaceholder.typicode.com/posts")
        sys.exit(1)

    urls = sys.argv[1:]

    print(f"\n{'='*60}")
    print(f"  REST API Test Suite")
    print(f"  Testing {len(urls)} endpoint(s)")
    print(f"{'='*60}\n")

    results = []
    for url in urls:
        print(f"  Testing: {url} ... ", end="", flush=True)
        result = test_endpoint(url)
        results.append(result)

        if result["error"]:
            print(f"❌ ERROR — {result['error']}")
        elif result["status_check"] and result["json_check"] and result["time_check"]:
            print(f"✅ PASS ({result['response_time_ms']}ms)")
        else:
            issues = []
            if not result["status_check"]:
                issues.append(f"status={result['status_code']}")
            if not result["json_check"]:
                issues.append("not JSON")
            if not result["time_check"]:
                issues.append(f"slow={result['response_time_ms']}ms")
            print(f"❌ FAIL ({', '.join(issues)})")

    report_path = generate_report(results)

    print(f"\n{'='*60}")
    print(f"  Results: {sum(1 for r in results if r['status_check'] and r['json_check'] and r['time_check'])}/{len(results)} passed")
    print(f"  Report saved to: {report_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
