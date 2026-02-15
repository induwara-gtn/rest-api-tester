# -*- coding: utf-8 -*-
"""
AI-Powered REST API Test Suite
================================
Uses Google Gemini to intelligently analyze API endpoints.

Features:
  - Parses complex URLs with many query parameters
  - Tests with and without auth token
  - Identifies required vs optional parameters
  - Tests filter/parameter edge cases
  - AI-powered response analysis via Gemini
  - Generates comprehensive api_report.md

Usage:
  python ai_api_tester.py "<full_url>"

Config:
  Edit config.json to update your auth token (expires every 30 min).
"""

import requests
import json
import sys
import os
import time
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from datetime import datetime

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# --- Configuration -----------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
REPORT_PATH = os.path.join(SCRIPT_DIR, "api_report.md")


def load_config():
    """Load config from config.json."""
    if not os.path.exists(CONFIG_PATH):
        print("[ERROR] config.json not found. Please create it with your API key and auth token.")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# --- URL Parsing --------------------------------------------------------------

def parse_url(url: str) -> dict:
    """Break a URL into its components: base, path, and individual parameters."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    # Flatten single-value lists
    flat_params = {k: v[0] if len(v) == 1 else v for k, v in params.items()}
    base_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    return {
        "full_url": url,
        "base_url": base_url,
        "scheme": parsed.scheme,
        "host": parsed.netloc,
        "path": parsed.path,
        "params": flat_params,
        "param_count": len(flat_params),
    }


def rebuild_url(base_url: str, params: dict) -> str:
    """Rebuild a URL from base + params dict."""
    query = urlencode(params, doseq=True)
    parsed = urlparse(base_url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", query, ""))


# --- API Calling --------------------------------------------------------------

def call_endpoint(url: str, headers: dict = None, timeout: int = 10) -> dict:
    """Make a GET request and return structured result."""
    result = {
        "url": url,
        "status_code": None,
        "response_time_ms": None,
        "is_json": False,
        "json_body": None,
        "body_preview": None,
        "error": None,
        "headers": None,
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        result["status_code"] = resp.status_code
        result["response_time_ms"] = round(resp.elapsed.total_seconds() * 1000, 2)
        result["headers"] = dict(resp.headers)
        try:
            result["json_body"] = resp.json()
            result["is_json"] = True
            # Truncated preview for AI analysis
            body_str = json.dumps(result["json_body"], indent=2)
            result["body_preview"] = body_str[:3000] + ("..." if len(body_str) > 3000 else "")
        except (json.JSONDecodeError, ValueError):
            result["is_json"] = False
            result["body_preview"] = resp.text[:1500]
    except requests.exceptions.ConnectionError:
        result["error"] = "Connection refused or DNS failure"
    except requests.exceptions.Timeout:
        result["error"] = f"Request timed out (>{timeout}s)"
    except requests.exceptions.RequestException as e:
        result["error"] = str(e)
    return result


# --- Test Phases --------------------------------------------------------------

def run_baseline_test(url: str, headers: dict, config: dict) -> dict:
    """Phase 1: Test the full URL as-is with auth."""
    print("\n  [Phase 1] Baseline Test (full URL with auth)")
    result = call_endpoint(url, headers=headers, timeout=config["timeout_seconds"])
    limit = config["response_time_limit_ms"]
    status = "PASS" if result["status_code"] == 200 else "FAIL"
    json_ok = "PASS" if result["is_json"] else "FAIL"
    time_ok = "PASS" if result["response_time_ms"] and result["response_time_ms"] < limit else "FAIL"
    print(f"     Status: {result['status_code']} [{status}] | JSON: [{json_ok}] | Time: {result['response_time_ms']}ms [{time_ok}]")
    if result["error"]:
        print(f"     WARNING: {result['error']}")
    return result


def run_auth_test(url: str, config: dict) -> dict:
    """Phase 2: Test WITHOUT auth token to verify auth is enforced."""
    print("\n  [Phase 2] Auth Enforcement Test (no token)")
    result = call_endpoint(url, headers={}, timeout=config["timeout_seconds"])
    if result["status_code"] in (401, 403):
        print(f"     [PASS] Auth enforced - returned {result['status_code']}")
    elif result["status_code"] == 200:
        print(f"     [WARN] Endpoint returned 200 WITHOUT auth - possible security issue!")
    elif result["error"]:
        print(f"     [WARN] Error: {result['error']}")
    else:
        print(f"     [INFO] Returned status {result['status_code']} without auth")
    return result


def run_required_params_test(url_info: dict, headers: dict, config: dict) -> list:
    """Phase 3: Remove each parameter one-by-one to find required ones."""
    print(f"\n  [Phase 3] Required Parameter Detection ({url_info['param_count']} params)")
    results = []
    for param_name in url_info["params"]:
        reduced_params = {k: v for k, v in url_info["params"].items() if k != param_name}
        test_url = rebuild_url(url_info["base_url"], reduced_params)
        result = call_endpoint(test_url, headers=headers, timeout=config["timeout_seconds"])
        is_required = result["status_code"] != 200 or result.get("error") is not None
        label = "[REQUIRED]" if is_required else "[OPTIONAL]"
        status_info = result['error'] if result['error'] else f"status={result['status_code']}"
        print(f"     {label} {param_name} -> {status_info}")
        results.append({
            "param": param_name,
            "value": url_info["params"][param_name],
            "is_required": is_required,
            "status_without": result["status_code"],
            "error_without": result["error"],
        })
        time.sleep(0.15)  # Be polite to the API
    return results


def run_empty_value_test(url_info: dict, headers: dict, config: dict) -> list:
    """Phase 4: Send each parameter with an empty value."""
    print(f"\n  [Phase 4] Empty Value Testing")
    results = []
    for param_name in url_info["params"]:
        modified_params = dict(url_info["params"])
        modified_params[param_name] = ""
        test_url = rebuild_url(url_info["base_url"], modified_params)
        result = call_endpoint(test_url, headers=headers, timeout=config["timeout_seconds"])
        handled = result["status_code"] in (200, 400, 422)
        label = "[OK]" if handled else "[WARN]"
        print(f"     {label} {param_name}='' -> status={result['status_code']}")
        results.append({
            "param": param_name,
            "status_with_empty": result["status_code"],
            "handled_gracefully": handled,
            "error": result["error"],
        })
        time.sleep(0.15)
    return results


# --- Gemini AI Analysis ------------------------------------------------------

# Free tier models ordered by daily quota (highest first)
GEMINI_MODELS = [
    "gemini-2.5-flash-lite",  # 15 RPM, 1000 RPD (best free tier)
    "gemini-2.5-flash",       # 10 RPM, 250 RPD
    "gemini-2.5-pro",         #  5 RPM, 100 RPD
]


def ask_gemini(prompt: str, api_key: str) -> str:
    """Send a prompt to Gemini with automatic model fallback and retry on 429."""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 4096,
        }
    }

    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"       Trying {model} (attempt {attempt + 1}/{max_retries})...")
                resp = requests.post(url, json=payload, timeout=60)
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"       [OK] {model} responded successfully")
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                elif resp.status_code == 429:
                    wait = 2 ** (attempt + 1)  # 2s, 4s, 8s
                    print(f"       [429] Rate limited on {model}. Waiting {wait}s...")
                    time.sleep(wait)
                    continue
                elif resp.status_code == 404:
                    print(f"       [404] {model} not available, trying next model...")
                    break  # Skip to next model
                else:
                    print(f"       [{resp.status_code}] Error on {model}, trying next model...")
                    break  # Skip to next model
            except requests.exceptions.Timeout:
                print(f"       [TIMEOUT] {model} timed out, retrying...")
                continue
            except Exception as e:
                return f"[Gemini request failed] {str(e)}"

    return "[All Gemini models exhausted] Could not get AI analysis. Check your API key quota at https://ai.dev/rate-limit"


def run_ai_analysis(url_info: dict, baseline: dict, auth_test: dict,
                    param_results: list, empty_results: list, config: dict) -> str:
    """Phase 5: Send all test data to Gemini for intelligent analysis."""
    print("\n  [Phase 5] AI-Powered Analysis (Gemini)")

    prompt = f"""You are an expert API QA engineer. Analyze the following REST API test results and provide a concise, actionable report.

## Endpoint
- **URL:** {url_info['full_url']}
- **Base:** {url_info['base_url']}
- **Parameters ({url_info['param_count']}):** {json.dumps(list(url_info['params'].keys()))}

## Baseline Test (full URL, with auth)
- Status: {baseline['status_code']}
- Response Time: {baseline['response_time_ms']}ms  (limit: {config['response_time_limit_ms']}ms)
- Is JSON: {baseline['is_json']}
- Response Preview:
```json
{baseline.get('body_preview', 'N/A')}
```

## Auth Enforcement Test (no token)
- Status: {auth_test['status_code']}
- Error: {auth_test.get('error', 'None')}

## Required Parameter Detection
{json.dumps(param_results, indent=2)}

## Empty Value Test
{json.dumps(empty_results, indent=2)}

---
Please provide:
1. **Overall Health Assessment** - is this endpoint production-ready?
2. **Security Analysis** - is auth properly enforced? Any concerns?
3. **Parameter Analysis** - which params are truly required? Any surprising results?
4. **Error Handling Quality** - does the API handle edge cases well?
5. **Performance Notes** - response time assessment
6. **Response Structure Analysis** - analyze the JSON structure and data quality
7. **Actionable Recommendations** - specific improvements ranked by priority

Keep it professional but concise. Use markdown formatting."""

    print("     Sending data to Gemini for analysis...")
    analysis = ask_gemini(prompt, config["gemini_api_key"])
    print("     [DONE] AI analysis complete")
    return analysis


# --- Report Generation --------------------------------------------------------

def generate_report(url_info, baseline, auth_test, param_results,
                    empty_results, ai_analysis, config):
    """Generate the final api_report.md."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    limit = config["response_time_limit_ms"]

    lines = [
        "# AI-Powered API Test Report",
        "",
        f"**Generated:** {now}  ",
        f"**Endpoint:** `{url_info['base_url']}`  ",
        f"**Parameters:** {url_info['param_count']}  ",
        "",
        "---",
        "",
        "## Phase 1: Baseline Test",
        "",
        "| Check | Result |",
        "|-------|--------|",
    ]

    sc_pass = baseline["status_code"] == 200
    js_pass = baseline["is_json"]
    rt_pass = baseline["response_time_ms"] and baseline["response_time_ms"] < limit
    sc_text = "PASS (200)" if sc_pass else f"FAIL ({baseline['status_code']})"
    js_text = "PASS" if js_pass else "FAIL"
    rt_text = f"{baseline['response_time_ms']}ms - PASS" if rt_pass else f"{baseline['response_time_ms']}ms - FAIL (>{limit}ms)"
    overall = "PASS" if all([sc_pass, js_pass, rt_pass]) else "FAIL"
    lines.append(f"| Status Code | {sc_text} |")
    lines.append(f"| Valid JSON | {js_text} |")
    lines.append(f"| Response Time | {rt_text} |")
    lines.append(f"| Overall | **{overall}** |")

    if baseline.get("error"):
        lines += ["", f"> **Error:** {baseline['error']}"]

    # Auth test
    lines += [
        "",
        "---",
        "",
        "## Phase 2: Auth Enforcement",
        "",
    ]
    if auth_test["status_code"] in (401, 403):
        lines.append(f"**PASS** - Auth is enforced. Returned `{auth_test['status_code']}` without token.")
    elif auth_test["status_code"] == 200:
        lines.append("**WARNING:** Endpoint returned `200` without auth token! Possible security issue.")
    else:
        lines.append(f"Returned `{auth_test['status_code']}` without auth. {auth_test.get('error', '')}")

    # Required params
    lines += [
        "",
        "---",
        "",
        "## Phase 3: Parameter Analysis",
        "",
        "| Parameter | Value (truncated) | Required? | Status Without |",
        "|-----------|-------------------|:---------:|:--------------:|",
    ]
    for p in param_results:
        val = str(p["value"])[:40] + ("..." if len(str(p["value"])) > 40 else "")
        req = "Yes" if p["is_required"] else "No"
        st = p["error_without"] if p["error_without"] else str(p["status_without"])
        lines.append(f"| `{p['param']}` | `{val}` | {req} | {st} |")

    required = [p["param"] for p in param_results if p["is_required"]]
    optional = [p["param"] for p in param_results if not p["is_required"]]
    lines += [
        "",
        f"**Required ({len(required)}):** {', '.join(f'`{p}`' for p in required) if required else 'None detected'}  ",
        f"**Optional ({len(optional)}):** {', '.join(f'`{p}`' for p in optional) if optional else 'None detected'}",
    ]

    # Empty value test
    lines += [
        "",
        "---",
        "",
        "## Phase 4: Empty Value Handling",
        "",
        "| Parameter | Status (empty value) | Handled Gracefully? |",
        "|-----------|:--------------------:|:-------------------:|",
    ]
    for e in empty_results:
        ok = "Yes" if e["handled_gracefully"] else "Warning"
        lines.append(f"| `{e['param']}` | {e['status_with_empty']} | {ok} |")

    # AI Analysis
    lines += [
        "",
        "---",
        "",
        "## Phase 5: AI Analysis (Gemini)",
        "",
        ai_analysis,
        "",
        "---",
        "",
        f"*Report generated by AI-Powered REST API Test Suite - {now}*",
    ]

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return REPORT_PATH


# --- Main ---------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("\nUsage: python ai_api_tester.py \"<full_url>\"")
        print('Example: python ai_api_tester.py "https://api.example.com/search?q=test&limit=10"')
        sys.exit(1)

    url = sys.argv[1]
    config = load_config()

    # Validate config
    if config.get("auth_token", "PASTE_YOUR_TOKEN_HERE") == "PASTE_YOUR_TOKEN_HERE":
        print("[WARN] auth_token in config.json is not set.")
        print("   Edit config.json and paste your current auth token.")
        print("   Proceeding without auth...\n")
        auth_headers = {}
    else:
        auth_type = config.get("auth_type", "Bearer")
        auth_header_key = config.get("auth_header", "Authorization")
        auth_headers = {auth_header_key: f"{auth_type} {config['auth_token']}"}

    print(f"\n{'='*65}")
    print(f"  AI-Powered REST API Test Suite")
    print(f"{'='*65}")

    # Parse URL
    url_info = parse_url(url)
    print(f"\n  Endpoint: {url_info['base_url']}")
    print(f"  Parameters: {url_info['param_count']}")
    for k, v in url_info["params"].items():
        val_preview = str(v)[:60] + ("..." if len(str(v)) > 60 else "")
        print(f"    - {k} = {val_preview}")

    # Run all test phases
    baseline = run_baseline_test(url, auth_headers, config)
    auth_test = run_auth_test(url, config)
    param_results = run_required_params_test(url_info, auth_headers, config)
    empty_results = run_empty_value_test(url_info, auth_headers, config)

    # AI Analysis
    ai_analysis = run_ai_analysis(url_info, baseline, auth_test,
                                  param_results, empty_results, config)

    # Generate report
    report_path = generate_report(url_info, baseline, auth_test,
                                  param_results, empty_results,
                                  ai_analysis, config)

    total_tests = 2 + len(param_results) + len(empty_results)
    print(f"\n{'='*65}")
    print(f"  All {total_tests} tests complete")
    print(f"  Report saved to: {report_path}")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
