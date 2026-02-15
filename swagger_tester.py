# -*- coding: utf-8 -*-
"""
Swagger-Driven API Test Suite
==============================
Auto-discovers ALL endpoints from OpenAPI/Swagger specs and tests each one.

Features:
  - Fetches OpenAPI specs from /v3/api-docs/swagger-config
  - Parses every endpoint: path, method, required/optional params, examples
  - Runs 5-phase test per endpoint (baseline, auth, required params, empty values, AI)
  - Generates a consolidated api_report.md for all endpoints
  - Supports --group and --tag filters

Usage:
  python swagger_tester.py                          # Test ALL discovered endpoints
  python swagger_tester.py --group "api clients"    # Test one API group only
  python swagger_tester.py --tag history             # Test endpoints with a specific tag
  python swagger_tester.py --list                    # Just list discovered endpoints

Config:
  Edit config.json to set swagger_base_url, auth_token, gemini_api_key.
"""

import requests
import json
import sys
import os
import time
import argparse
import random
import base64
from urllib.parse import urlencode, urlunparse, urlparse
from datetime import datetime
from itertools import combinations, product, chain
import re

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
        print("[ERROR] config.json not found.")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# --- Swagger Discovery -------------------------------------------------------

def fetch_swagger_config(base_url, timeout=10):
    """Fetch the swagger-config to discover all API groups."""
    url = f"{base_url.rstrip('/')}/v3/api-docs/swagger-config"
    print(f"  Fetching swagger config from: {url}")
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            groups = []
            for item in data.get("urls", []):
                groups.append({
                    "name": item.get("name", "unknown"),
                    "url": item.get("url", ""),
                })
            print(f"  Found {len(groups)} API group(s): {', '.join(g['name'] for g in groups)}")
            return groups
        else:
            print(f"  [ERROR] swagger-config returned {resp.status_code}")
            return []
    except Exception as e:
        print(f"  [ERROR] Failed to fetch swagger-config: {e}")
        return []


def fetch_openapi_spec(base_url, spec_path, timeout=15):
    """Fetch a single OpenAPI spec JSON."""
    url = f"{base_url.rstrip('/')}{spec_path}"
    print(f"    Fetching spec: {url}")
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"    [WARN] Spec returned {resp.status_code}")
            return None
    except Exception as e:
        print(f"    [WARN] Failed to fetch spec: {e}")
        return None


def parse_endpoints(spec, group_name):
    """Parse an OpenAPI spec into a list of testable endpoint definitions."""
    endpoints = []
    paths = spec.get("paths", {})

    for path, methods in paths.items():
        for method, details in methods.items():
            if method.lower() not in ("get", "post", "put", "delete", "patch"):
                continue

            tags = details.get("tags", [])
            summary = details.get("summary", "")
            operation_id = details.get("operationId", "")

            # Parse parameters
            params_raw = details.get("parameters", [])
            params = []
            for p in params_raw:
                param_info = {
                    "name": p.get("name", ""),
                    "in": p.get("in", "query"),       # query, path, header
                    "required": p.get("required", False),
                    "description": p.get("description", ""),
                    "example": None,
                    "default": None,
                    "type": "string",
                    "enum": None,
                }
                schema = p.get("schema", {})
                param_info["type"] = schema.get("type", "string")
                param_info["default"] = schema.get("default")
                param_info["enum"] = schema.get("enum")
                # Try to get example value
                if "example" in p:
                    param_info["example"] = p["example"]
                elif "example" in schema:
                    param_info["example"] = schema["example"]
                elif param_info["default"] is not None:
                    param_info["example"] = param_info["default"]
                elif param_info["enum"]:
                    param_info["example"] = param_info["enum"][0]
                else:
                    # Generate sensible defaults based on type
                    type_defaults = {
                        "string": "test",
                        "integer": "1",
                        "number": "1.0",
                        "boolean": "true",
                        "array": "test",
                    }
                    param_info["example"] = type_defaults.get(param_info["type"], "test")

                params.append(param_info)

            # Parse response schemas
            responses = details.get("responses", {})
            response_schemas = {}
            for code, resp_detail in responses.items():
                resp_desc = resp_detail.get("description", "")
                content = resp_detail.get("content", {})
                schema_ref = None
                if "application/json" in content:
                    schema_ref = content["application/json"].get("schema", {})
                response_schemas[code] = {
                    "description": resp_desc,
                    "schema": schema_ref,
                }

            # Parse requestBody (OpenAPI 3)
            request_body_schema = None
            req_body = details.get("requestBody", {})
            req_content = req_body.get("content", {})
            if "application/json" in req_content:
                request_body_schema = req_content["application/json"].get("schema", {})
                # Add body properties to params list so they appear in the UI table
                if request_body_schema and request_body_schema.get("properties"):
                    props = request_body_schema["properties"]
                    required_fields = request_body_schema.get("required", [])
                    for p_name, p_details in props.items():
                        # Avoid duplicates if already in params (though usually body fields are separate)
                        if any(existing["name"] == p_name for existing in params):
                            continue
                            
                        param_info = {
                            "name": p_name,
                            "in": "body",
                            "required": p_name in required_fields,
                            "description": p_details.get("description", ""),
                            "type": p_details.get("type", "string"),
                            "example": p_details.get("example") or p_details.get("default"),
                            "default": p_details.get("default"),
                            "enum": p_details.get("enum")
                        }
                        if not param_info["example"]:
                            type_defaults = {"string":"test", "integer":"1", "number":"1.0", "boolean":"true"}
                            param_info["example"] = type_defaults.get(param_info["type"], "test")
                        
                        params.append(param_info)

            endpoints.append({
                "group": group_name,
                "path": path,
                "method": method.upper(),
                "tags": tags,
                "summary": summary,
                "operation_id": operation_id,
                "params": params,
                "request_body_schema": request_body_schema,
                "response_schemas": response_schemas,
            })

    return endpoints


# --- URL Construction --------------------------------------------------------

def build_test_url(base_url, endpoint, param_overrides=None, skip_params=None,
                   empty_params=None, include_params=None):
    """Build a full test URL from endpoint definition + base URL."""
    path = endpoint["path"]
    query_params = {}

    for p in endpoint["params"]:
        name = p["name"]
        
        # skip_params is a blacklist (used for param removal tests)
        if skip_params and name in skip_params:
            continue
            
        # include_params is a whitelist (used for combinatorial and manual filtration)
        # Path parameters are always included to keep URL valid
        if include_params is not None and name not in include_params and p["in"] != "path":
            continue

        if p["in"] == "path":
            val = str(p["example"]) if p["example"] else "test"
            if param_overrides and name in param_overrides:
                val = param_overrides[name]
            path = path.replace("{" + name + "}", val)
        elif p["in"] == "query":
            if empty_params and name in empty_params:
                query_params[name] = ""
            elif param_overrides is not None:
                # If we have overrides (usually from UI), only include if present or required
                if name in param_overrides:
                    val = param_overrides[name]
                    if val is not None:
                        query_params[name] = val
                elif p.get("required"):
                    # Fallback to example only if required and missing from overrides
                    query_params[name] = str(p.get("example") or p.get("default") or "test")
            elif p.get("example") is not None:
                query_params[name] = str(p["example"])
            elif p.get("default") is not None:
                query_params[name] = str(p["default"])

    full_url = f"{base_url.rstrip('/')}{path}"
    if query_params:
        full_url += "?" + urlencode(query_params, doseq=True)
    
    # Generate JSON Body if request_body_schema exists
    json_body = {}
    if endpoint.get("request_body_schema"):
        schema = endpoint["request_body_schema"]
        props = schema.get("properties", {})
        required_body_fields = schema.get("required", [])
        
        for name, prop in props.items():
            # Check whitelist
            if include_params is not None and name not in include_params:
                continue

            # Check overrides first
            if param_overrides is not None:
                if name in param_overrides:
                    val = param_overrides[name]
                    if val is not None:
                        json_body[name] = val
                elif name in required_body_fields:
                    # Fallback for required fields
                    val = prop.get("example") or prop.get("default")
                    if val is not None:
                        json_body[name] = val
                    elif prop.get("type") == "string":
                        json_body[name] = "test"
                    elif prop.get("type") == "integer":
                        json_body[name] = 1
                # Optional fields not in overrides are skipped
            else:
                # No overrides, use defaults/examples from spec
                val = prop.get("example") or prop.get("default")
                if val is not None:
                    json_body[name] = val
                elif prop.get("type") == "string":
                    json_body[name] = "test"
                elif prop.get("type") == "integer":
                    json_body[name] = 1

    return full_url, json_body


# --- API Calling (reused from ai_api_tester) ---------------------------------

def call_endpoint(url, method="GET", headers=None, json_body=None, timeout=10):
    """Make an HTTP request and return structured result."""
    result = {
        "url": url,
        "method": method,
        "status_code": None,
        "response_time_ms": None,
        "is_json": False,
        "json_body": None,
        "body_preview": None,
        "error": None,
    }
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=timeout)
        elif method == "POST":
            resp = requests.post(url, headers=headers, json=json_body or {}, timeout=timeout)
        elif method == "PUT":
            resp = requests.put(url, headers=headers, json=json_body or {}, timeout=timeout)
        elif method == "DELETE":
            resp = requests.delete(url, headers=headers, timeout=timeout)
        elif method == "PATCH":
            resp = requests.patch(url, headers=headers, json=json_body or {}, timeout=timeout)
        else:
            resp = requests.get(url, headers=headers, timeout=timeout)

        result["status_code"] = resp.status_code
        result["response_time_ms"] = round(resp.elapsed.total_seconds() * 1000, 2)
        result["response_headers"] = dict(resp.headers)
        result["request_headers"] = dict(resp.request.headers)
        result["request_url"] = resp.request.url
        result["request_method"] = resp.request.method
        result["request_body"] = resp.request.body
        
        try:
            result["json_body"] = resp.json()
            result["is_json"] = True
            body_str = json.dumps(result["json_body"], indent=2)
            result["body_preview"] = body_str[:2000] + ("..." if len(body_str) > 2000 else "")
            result["body_full"] = body_str # Keep full body for detailed report
        except (json.JSONDecodeError, ValueError):
            result["is_json"] = False
            result["body_preview"] = resp.text[:1000]
            result["body_full"] = resp.text
    except requests.exceptions.ConnectionError:
        result["error"] = "Connection refused or DNS failure"
    except requests.exceptions.Timeout:
        result["error"] = f"Timed out (>{timeout}s)"
    except requests.exceptions.RequestException as e:
        result["error"] = str(e)
    return result

def validate_schema(response_json, schema_info):
    """Basic validation against expected schema type."""
    # schema_info is like {'type': 'array', ...} or None
    if not schema_info:
        return "N/A" # No schema defined
        
    expected_type = schema_info.get("type")
    if not expected_type:
        return "N/A"
        
    # Basic type map
    if expected_type == "array" and not isinstance(response_json, list):
        return "FAIL: Expected array, got object"
    if expected_type == "object" and not isinstance(response_json, dict):
        return "FAIL: Expected object, got list/primitive"
    if expected_type == "integer" and not isinstance(response_json, int):
        return "FAIL: Expected integer"
    if expected_type == "string" and not isinstance(response_json, str):
        return "FAIL: Expected string"
        
    return "PASS"


# --- Test Phases (per endpoint) ----------------------------------------------

def run_baseline(url, method, headers, config, json_body=None, endpoint_def=None):
    """Phase 1: Test with auth and all params."""
    result = call_endpoint(url, method=method, headers=headers, json_body=json_body,
                           timeout=config["timeout_seconds"])
    limit = config["response_time_limit_ms"]
    sc = "PASS" if result["status_code"] == 200 else "FAIL"
    js = "PASS" if result["is_json"] else "FAIL"
    tm = "PASS" if result["response_time_ms"] and result["response_time_ms"] < limit else "FAIL"
    
    # Schema Validation
    schema_status = "N/A"
    if endpoint_def and result["is_json"] and result["status_code"] == 200:
        # Find 200 OK schema
        ok_schema = endpoint_def.get("response_schemas", {}).get("200", {}).get("schema")
        if ok_schema:
            schema_status = validate_schema(result["json_body"], ok_schema)
            
    result["schema_validation"] = schema_status
    print(f"      Baseline: {result['status_code']} [{sc}] | JSON [{js}] | Schema [{schema_status}] | {result['response_time_ms']}ms [{tm}]")
    return result


def run_auth_check(url, method, config):
    """Phase 2: Test WITHOUT auth."""
    result = call_endpoint(url, method=method, headers={},
                           timeout=config["timeout_seconds"])
    if result["status_code"] in (401, 403):
        print(f"      Auth: ENFORCED ({result['status_code']})")
    elif result["status_code"] == 200:
        print(f"      Auth: WARNING - 200 without token!")
    else:
        print(f"      Auth: {result['status_code']}")
    return result


def run_param_removal(endpoint, base_url, headers, config, base_overrides=None, include_params=None):
    """Phase 3: Remove each query/body param one-by-one from the baseline set."""
    results = []
    
    # Identify all parameters that can be removed (query or body)
    removable_params = []
    for p in endpoint["params"]:
        if p["in"] == "query":
            removable_params.append(p)
    
    if endpoint.get("request_body_schema"):
        schema = endpoint["request_body_schema"]
        for name, prop in schema.get("properties", {}).items():
            removable_params.append({"name": name, "in": "body", "required": name in schema.get("required", [])})

    for p in removable_params:
        name = p["name"]
        
        # If include_params is passed, only audit those that are checked in the UI
        if include_params is not None and name not in include_params:
            continue
            
        # We want to skip THIS parameter 'p', but keep all others exactly as they were in the baseline
        test_url, test_body = build_test_url(base_url, endpoint, 
                                param_overrides=base_overrides,
                                skip_params={name},
                                include_params=include_params) # Pass include_params to build_test_url

        result = call_endpoint(test_url, method=endpoint["method"], headers=headers,
                               json_body=test_body, timeout=config["timeout_seconds"])
        is_required = result["status_code"] != 200 or result.get("error") is not None
        label = "REQ" if is_required else "OPT"
        print(f"      Param -{name}: [{label}] -> {result['status_code']}")
        results.append({
            "param": name,
            "required_by_spec": p["required"],
            "required_by_test": is_required,
            "status_without": result["status_code"],
        })
        time.sleep(0.1)
    return results


def run_empty_values(endpoint, base_url, headers, config, base_overrides=None, include_params=None):
    """Phase 4: Send each query/body param as empty, keeping others as baseline."""
    emptyable_params = []
    for p in endpoint["params"]:
        if p["in"] == "query":
            emptyable_params.append(p)
    
    if endpoint.get("request_body_schema"):
        schema = endpoint["request_body_schema"]
        for name, prop in schema.get("properties", {}).items():
            emptyable_params.append({"name": name, "in": "body", "required": name in schema.get("required", [])})

    results = []
    for p in emptyable_params:
        name = p["name"]
        
        # If include_params is passed, only audit those that are checked in the UI
        if include_params is not None and name not in include_params:
            continue

        test_url, test_body = build_test_url(base_url, endpoint, 
                                param_overrides=base_overrides,
                                empty_params={name},
                                include_params=include_params) # Pass include_params to build_test_url
        
        result = call_endpoint(test_url, method=endpoint["method"], headers=headers,
                               json_body=test_body, timeout=config["timeout_seconds"])
        ok = result["status_code"] in (200, 400, 422)
        label = "OK" if ok else "WARN"
        print(f"      Empty {name}: [{label}] -> {result['status_code']}")
        results.append({
            "param": name,
            "status_empty": result["status_code"],
            "graceful": ok,
        })
        time.sleep(0.1)
    return results


def run_negative_tests(endpoint, base_url, headers, config):
    """Phase 6: Negative Testing (Invalid Methods)."""
    results = []
    
    if endpoint["method"] == "GET":
        bad_method = "DELETE"
    else:
        bad_method = "PATCH"
        
    test_url, test_body = build_test_url(base_url, endpoint)
    result = call_endpoint(test_url, method=bad_method, headers=headers, json_body=test_body, timeout=config["timeout_seconds"])
    
    passed = result["status_code"] in (405, 403, 404, 501)
    status = "PASS" if passed else "FAIL"
    print(f"      Negative ({bad_method}): {result['status_code']} [{status}]")
    
    results.append({
        "test": f"Invalid Method ({bad_method})",
        "status_code": result["status_code"],
        "passed": passed,
        "response": result["body_preview"]
    })
    
    return results


def run_path_fuzzing(endpoint, base_url, headers, config, base_overrides=None):
    """Phase 7: Fuzz path parameters (e.g. /users/{id} -> /users/null)."""
    results = []
    path_params = [p for p in endpoint["params"] if p["in"] == "path"]
    
    fuzz_values = ["null", "undefined", "NaN", "0", "-1", "999999999", "INVALID_PATH"]
    
    for p in path_params:
        for val in fuzz_values:
            # Override JUST this path param
            overrides = base_overrides.copy() if base_overrides else {}
            overrides[p["name"]] = val
            
            test_url, test_body = build_test_url(base_url, endpoint, param_overrides=overrides)
            # Use baseline method (usually GET)
            res = call_endpoint(test_url, method=endpoint["method"], headers=headers, 
                               json_body=test_body, timeout=config["timeout_seconds"])
            
            # We expect 404, 400, or 422. 500 is BAD.
            status = "PASS" if res["status_code"] in (404, 400, 422) else "FAIL"
            if res["status_code"] == 200:
                status = "WARN (200 OK?)" 
                
            results.append({
                "param": p["name"],
                "value": val,
                "status_code": res["status_code"],
                "result": status,
                "response_preview": res["body_preview"]
            })
    return results


def run_enum_testing(endpoint, base_url, headers, config, base_overrides=None):
    """Phase 8: Test invalid values for Enum parameters."""
    results = []
    enum_params = [p for p in endpoint["params"] if p.get("enum")]
    
    for p in enum_params:
        # Try a value that is NOT in the enum
        invalid_val = "INVALID_ENUM_VALUE"
        
        overrides = base_overrides.copy() if base_overrides else {}
        overrides[p["name"]] = invalid_val
        
        test_url, test_body = build_test_url(base_url, endpoint, param_overrides=overrides)
        res = call_endpoint(test_url, method=endpoint["method"], headers=headers,
                          json_body=test_body, timeout=config["timeout_seconds"])
                          
        # Expect 400/422
        passed = res["status_code"] in (400, 422)
        results.append({
            "param": p["name"],
            "value": invalid_val,
            "status_code": res["status_code"],
            "passed": passed,
            "response": res["body_preview"]
        })
    return results

def run_combinatorial_tests(endpoint, base_url, headers, config, base_overrides=None, mode="minimal", offset=0, limit=64, multi_params=None, include_params=None, random_overrides=None, isolated_params=None):
    """
    Generate and run a subset of combinatorial tests.
    - PowerSets for multi-value params
    - Boolean auto-coverage (True/False)
    - Non-multi sample isolation (test each separately + empty)
    - Explicit parameter inclusion filtering
    - Isolated parameters (test independently from main pool)
    """
    if not endpoint.get("params"):
        return {"results": [], "total_count": 0, "offset": 0, "limit": limit}
    
    multi_params = multi_params or []
    include_params = include_params or [p["name"] for p in endpoint["params"]]
    isolated_params = isolated_params or []
    random_overrides = random_overrides or {}
    
    # 1. Build "Value Pools" for each parameter
    parameter_pools = {} # name -> list of values (where None means skip)
    baseline_values = {} # name -> single default value
    
    for p in endpoint["params"]:
        name = p["name"]
        
        # If not included, we just use a baseline value or skip it
        if name not in include_params:
            if p["required"]:
                ex = p.get("example") or p.get("default") or "test"
                parameter_pools[name] = [str(ex)]
            else:
                parameter_pools[name] = [None]
            baseline_values[name] = parameter_pools[name][0]
            continue

        if p["required"]:
            pool = []
        else:
            pool = [] # Start empty, we'll decide baseline below

        # Collate candidates: UI Samples + Spec Example + Defaults + Random Fuzz
        all_samples = []
        
        # UI Samples (comma separated)
        ui_val = (base_overrides or {}).get(name, "")
        if ui_val:
            if "," in str(ui_val):
                all_samples.extend([s.strip() for s in str(ui_val).split(",")])
            else:
                all_samples.append(str(ui_val))
        
        # Random Fuzz
        fuzz_val = random_overrides.get(name)
        if fuzz_val:
            all_samples.append(str(fuzz_val))
            
        # Boolean Auto-Coverage
        if p.get("type") == "boolean":
            if "true" not in [str(s).lower() for s in all_samples]: all_samples.append("true")
            if "false" not in [str(s).lower() for s in all_samples]: all_samples.append("false")

        candidates = []
        if name in multi_params:
            for i in range(1, len(all_samples) + 1):
                for combo in combinations(all_samples, i):
                    candidates.append(list(combo))
        else:
            for s in all_samples:
                candidates.append(s)
            
        # Deduplicate candidates (keeping order)
        seen = []
        for c in candidates:
            if c not in seen: seen.append(c)
        
        # FINAL POOL CONSTRUCTION:
        # If we have samples, they form the baseline (index 0). 
        # 'None' (missing) is added at the end for optional parameters.
        if seen:
            pool = seen
            if not p["required"] and None not in seen:
                pool.append(None)
        else:
            if p["required"]:
                ex = p.get("example") or p.get("default") or "test"
                pool = [str(ex), None]
            else:
                pool = [None]
            
        parameter_pools[name] = pool
        # Baseline is always the first item in the pool
        baseline_values[name] = pool[0]

    # for logic verification later, we need a baseline dict
    # 2. Construct the list of dicts to test
    # Split included parameters into "Main Pool" and "Isolated"
    main_pool_names = [name for name in include_params if name not in isolated_params]
    
    # Generate Main Combinations
    main_pools = [parameter_pools[name] for name in main_pool_names]
    all_combos_dicts = []
    
    # The Cartesion Product of all main pools
    for combo in product(*main_pools):
        d = baseline_values.copy()
        for i, name in enumerate(main_pool_names):
            d[name] = combo[i]
        all_combos_dicts.append(d)

    # Isolated Combinations (tested individually against current baseline_values)
    for name in isolated_params:
        if name not in parameter_pools: continue
        full_pool = parameter_pools[name]
        baseline_v = baseline_values[name]
        
        for val in full_pool:
            if val == baseline_v: continue # Already covered in main combos or baseline
            
            d = baseline_values.copy()
            d[name] = val
            all_combos_dicts.append(d)

    total_count = len(all_combos_dicts)
    if offset == 0:
        print(f"      [Comb] Total combinatorial test cases: {total_count}")
    
    if mode == "minimal":
        subset = all_combos_dicts[:1] # Just one
    else:
        subset = all_combos_dicts[offset : offset + limit]
    
    # 3. Run Tests
    results = []
    for i, test_params in enumerate(subset):
        current_idx = offset + i + 1
        print(f"      [Comb] Testing {current_idx}/{total_count}...")
        
        # Determine combination name for UI display
        display_parts = []
        for name, val in test_params.items():
            if name in include_params and val != baseline_values[name]:
                if isinstance(val, list):
                    display_parts.append(f"{name}=[{','.join(val)}]")
                else:
                    display_parts.append(f"{name}={val}")
        
        comb_name = ", ".join(display_parts) if display_parts else "Baseline (+)"
        
        test_url, test_body = build_test_url(base_url, endpoint, param_overrides=test_params)
        res = call_endpoint(test_url, method=endpoint["method"], headers=headers, 
                             json_body=test_body, timeout=config["timeout_seconds"])
        
        results.append({
            "combination": comb_name,
            "status_code": res["status_code"],
            "passed": 200 <= res["status_code"] < 300,
            "body_preview": res.get("body_preview", ""),
            "request_url": test_url,
            "request_body": test_body,
            "params_used": test_params
        })
        
    return {
        "results": results,
        "total_count": total_count,
        "offset": offset,
        "limit": limit
    }


def get_pairwise_combinations(params):
    """Simplified Binary All-Pairs."""
    if not params: return [set()]
    if len(params) == 1: return [set(), set(params)]
    tests = [set(params), set(), set(params[::2]), set(params[1::2])]
    if len(params) > 4:
        num_bits = (len(params) - 1).bit_length()
        for i in range(num_bits):
            mask_in = set()
            mask_out = set()
            for idx, p in enumerate(params):
                if (idx >> i) & 1: mask_in.add(p)
                else: mask_out.add(p)
            tests.extend([mask_in, mask_out])
    unique_tests = []
    seen = set()
    for t in tests:
        frozen = frozenset(t)
        if frozen not in seen:
            unique_tests.append(t)
            seen.add(frozen)
    return unique_tests


def run_logic_checks(endpoint, baseline_res, overrides, json_body=None):
    """Phase 10: Heuristic Logic Checks on Baseline Response."""
    findings = []
    
    if not baseline_res or not baseline_res.get("json_body"):
        return findings

    # 1. Echo Check (Field-to-Field Validation)
    # Check if sent values appear in the response JSON (at any level)
    sent_data = overrides.copy() if overrides else {}
    if json_body:
        sent_data.update(json_body)
    
    response_json = baseline_res["json_body"]
    
    def find_in_json(target_val, data):
        """Recursively search for target_val in JSON data."""
        if str(target_val).lower() == str(data).lower():
            return True
        if isinstance(data, dict):
            return any(find_in_json(target_val, v) for v in data.values())
        if isinstance(data, list):
            return any(find_in_json(target_val, item) for item in data)
        return False

    for key, val in sent_data.items():
        # Only check values that are somewhat unique (not common booleans/small ints)
        if val is not None and len(str(val)) > 1:
            if find_in_json(val, response_json):
                findings.append(f"Logic: `{key}={val}` correctly ECHOED in response.")
            else:
                # This might be normal for some fields, but worth checking
                findings.append(f"LOGIC WARN: Sent field `{key}={val}` NOT found in response.")

    # 2. Sensitive Data Scan
    body_str = baseline_res.get("body_full", "").lower()
    sensitive_keywords = ["password", "secret", "api_key", "access_token", "hash", "private_key"]
    for kw in sensitive_keywords:
        if f"\"{kw}\"" in body_str or f"'{kw}'" in body_str:
           findings.append(f"SECURITY: Response contains sensitive keyword `{kw}`!")

    return findings


def find_field_selectors(endpoint):
    """Identify parameters that likely control response fields."""
    selector_keywords = ["fields", "select", "required_fields", "include", "exclude"]
    return [p for p in endpoint["params"] if any(k in p["name"].lower() for k in selector_keywords)]


def run_field_progression_test(endpoint, base_url, headers, config, base_overrides=None):
    """
    Test how selector params affect fields:
    1. Empty (Default)
    2. Subset (One field)
    """
    selectors = find_field_selectors(endpoint)
    results = []
    
    for s in selectors:
        name = s["name"]
        current_val = base_overrides.get(name) if base_overrides else None
        if not current_val:
            current_val = s.get("example") or s.get("default")
            
        # A. Empty
        overrides_empty = base_overrides.copy() if base_overrides else {}
        overrides_empty[name] = ""
        u1, b1 = build_test_url(base_url, endpoint, param_overrides=overrides_empty)
        r1 = call_endpoint(u1, method=endpoint["method"], headers=headers, json_body=b1, timeout=config["timeout_seconds"])
        
        # B. Subset (If current_val has commas)
        sub_res = None
        if current_val and "," in str(current_val):
            single_field = str(current_val).split(",")[0].strip()
            overrides_sub = base_overrides.copy() if base_overrides else {}
            overrides_sub[name] = single_field
            u2, b2 = build_test_url(base_url, endpoint, param_overrides=overrides_sub)
            r2 = call_endpoint(u2, method=endpoint["method"], headers=headers, json_body=b2, timeout=config["timeout_seconds"])
            
            def get_keys(data):
                if isinstance(data, dict): return list(data.keys())
                if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict): return list(data[0].keys())
                return []

            sub_res = {
                "value": single_field,
                "status_code": r2["status_code"],
                "keys": get_keys(r2["json_body"])
            }

        def get_keys(data):
            if isinstance(data, dict): return list(data.keys())
            if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict): return list(data[0].keys())
            return []

        results.append({
            "param": name,
            "empty_status": r1["status_code"],
            "empty_keys": get_keys(r1["json_body"]),
            "subset": sub_res
        })
        
    return results


def run_single_smart_test(endpoint, base_url, headers, config, param, val):
    """Execute a single AI-suggested test case."""
    overrides = {param: val}
    u, b = build_test_url(base_url, endpoint, param_overrides=overrides)
    res = call_endpoint(u, method=endpoint["method"], headers=headers, json_body=b, timeout=config["timeout_seconds"])
    return res


def repair_json(text):
    """
    Robust LLM JSON cleanup:
    1. Strip markdown and chatter.
    2. Convert single-quoted keys/values to double-quotes (common LLM error).
    3. Convert Python literals (True, False, None) to JSON.
    4. Handle trailing commas.
    """
    import re
    if not text:
        return "{}"
        
    # 1. Strip markdown
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    # 2. Extract first { or [ until last } or ]
    start_idx_brace = text.find('{')
    start_idx_bracket = text.find('[')
    
    starts = []
    if start_idx_brace != -1: starts.append(start_idx_brace)
    if start_idx_bracket != -1: starts.append(start_idx_bracket)
    
    end_idx_brace = text.rfind('}')
    end_idx_bracket = text.rfind(']')
    
    ends = []
    if end_idx_brace != -1: ends.append(end_idx_brace)
    if end_idx_bracket != -1: ends.append(end_idx_bracket)

    if starts and ends:
        start_idx = min(starts)
        end_idx = max(ends)
        if start_idx < end_idx:
            text = text[start_idx:end_idx+1]

    # 3. Handle Python-style quotes and literals
    # Heuristic for the most common LLM single-quote issues
    text = re.sub(r"'(\w+)'\s*:", r'"\1":', text) # Keys
    text = re.sub(r":\s*'([^']*)'", r': "\1"', text) # Values
    text = re.sub(r",\s*'([^']*)'", r', "\1"', text) # Values in lists
    text = re.sub(r"\[\s*'([^']*)'", r'["\1"', text) # First value in list
    
    # Python literals
    text = text.replace(": True", ": true").replace(": False", ": false").replace(": None", ": null")
    text = text.replace(", True", ", true").replace(", False", ", false").replace(", None", ", null")
    text = text.replace("[True", "[true").replace("[False", "[false").replace("[None", "[null")

    # 4. Strip trailing commas before closing braces/brackets
    text = re.sub(r',\s*([\]}])', r'\1', text)
    
    return text


def generate_ai_smart_tests(endpoint, baseline_res, api_key, cr_description=None):
    """Use Gemini to analyze baseline response and suggest smart test cases."""
    if not baseline_res:
        return {"error": "No baseline response data available. Please run a baseline test first."}
    
    if baseline_res.get("json_body") is None and not baseline_res.get("is_json"):
        status = baseline_res.get("status_code", "Unknown")
        return {"error": f"Baseline response (Status {status}) is not a valid JSON response. AI Discovery requires JSON to analyze filters/sorting."}
    
    # Even if json_body is [] or {}, we can still suggest tests based on params
    json_sample = baseline_res.get("json_body")
    if json_sample is None:
        json_sample = "[]" # Fallback
    
    # Identify available params
    params = endpoint.get("params", [])
    
    # Intelligent sample for baseline
    sample, total = sample_json(baseline_res.get("json_body"))
    
    cr_context = f"\n    CONTEXT: The user is testing the following Change Request (CR):\n    {cr_description}\n    Please prioritize test cases that specifically validate this change.\n" if cr_description else ""

    # Prepare prompt (Be extremely specific to ensure clean JSON)
    prompt = f"""
    Suggest 6-9 high-value test cases for filtering, sorting, and edge cases.{cr_context}
    
    ENDPOINT: {endpoint['method']} {endpoint['path']}
    PARAMS: {[p['name'] for p in params]}
    BASELINE RESPONSE ({len(sample)} of {total} items): {json.dumps(sample, indent=2)}
    
    Instructions:
    1. FILTER TESTS: Identify fields in the response and suggest targeted values.
    2. SORT TESTS: Identify sortable fields. Suggest valid sort values (e.g., 'price:asc').
    3. EDGE CASES: Suggest empty strings, non-existent values, or invalid types.
    4. VARIETY: Suggest roughly 2-3 filters, 2-3 sorts, and 2-3 edge cases (Total 6-9).
    5. DATA ACCURACY: Ensure logic is consistent.
    6. STRICT JSON: Return ONLY a valid JSON object. DO NOT include trailing commas. Ensure all keys and values are double-quoted.
    
    Expected format (STRICT JSON ONLY):
    {{
      "filter_tests": [ {{"param": "p", "value": "val", "reason": "desc"}} ],
      "sort_tests": [ {{"param": "p", "value": "val", "reason": "desc"}} ],
      "edge_case_tests": [ {{"param": "p", "value": "val", "reason": "desc"}} ]
    }}
    """
    
    res_text = ask_gemini(prompt, api_key)
    try:
        clean_text = repair_json(res_text)
        test_plan = json.loads(clean_text)
        return test_plan
    except Exception as e:
        return {"error": f"Failed to parse AI response: {str(e)}", "raw": res_text[:200]}


def run_ai_smart_tests(endpoint, base_url, headers, config, baseline_res, cr_description=None):
    """Execute the AI-suggested tests."""
    api_key = config.get("gemini_api_key")
    if not api_key:
        return {"error": "Gemini API key not configured."}
    
    test_plan = generate_ai_smart_tests(endpoint, baseline_res, api_key, cr_description=cr_description)
    if not test_plan or "error" in test_plan:
        return test_plan
        
    all_results = []
    
    # Flatten tests
    all_test_cases = []
    for t in test_plan.get("filter_tests", []): all_test_cases.append(t)
    for t in test_plan.get("sort_tests", []): all_test_cases.append(t)
    for t in test_plan.get("edge_case_tests", []): all_test_cases.append(t)
    
    for tc in all_test_cases:
        param = tc["param"]
        val = tc["value"]
        
        # Build override
        overrides = {param: val}
        u, b = build_test_url(base_url, endpoint, param_overrides=overrides)
        res = call_endpoint(u, method=endpoint["method"], headers=headers, json_body=b, timeout=config["timeout_seconds"])
        
        all_results.append({
            "param": param,
            "value": val,
            "reason": tc.get("reason"),
            "status_code": res["status_code"],
            "body_preview": res["body_preview"]
        })
        
    return all_results


def sample_json(data, limit=15):
    """
    Intelligently sample rows from JSON. 
    Finds the first significant list and takes a slice.
    Returns (sampled_data, total_count).
    """
    if isinstance(data, list):
        return data[:limit], len(data)
    if isinstance(data, dict):
        # Look for the first list in the dict (e.g. 'items', 'data', 'tickers')
        for k, v in data.items():
            if isinstance(v, list) and len(v) > 0:
                return v[:limit], len(v)
    return data, 1

def analyze_test_logic(endpoint, baseline_res, test_res, test_case, api_key):
    """Use Gemini to verify if the logic of a test case (filter/sort) was applied."""
    if not baseline_res or not test_res:
        return "N/A: Missing response data."

    b_sample, b_total = sample_json(baseline_res.get('json_body'))
    t_sample, t_total = sample_json(test_res.get('json_body'))

    prompt = f"""
    Analyze the logic of this API test. Verify the result across ALL provided rows (if applicable).
    
    ENDPOINT: {endpoint['method']} {endpoint['path']}
    TEST CASE: Sent `{test_case['param']}={test_case['value']}`. Reason: {test_case['reason']}
    
    BASELINE SAMPLE ({len(b_sample)} of {b_total} rows):
    {json.dumps(b_sample, indent=2)}
    
    TEST RESPONSE SAMPLE ({len(t_sample)} of {t_total} rows):
    {json.dumps(t_sample, indent=2)}
    
    TEST STATUS CODE: {test_res['status_code']}
    
    Verification Requirements:
    - FILTER: Check if the value `{test_case['value']}` is present/respected in the {len(t_sample)} test rows.
    - SORT: Compare the order of the test rows compared to baseline. Verify if the sort field is consistent across all {len(t_sample)} rows.
    - EDGE CASE: Verify if the API handled it as expected (e.g., returned empty list or error code).
    
    Provide a concise (1-sentence) verdict. Be specific, e.g., "Verified: 10 rows are correctly sorted by name."
    """
    
    analysis = ask_gemini(prompt, api_key)
    return analysis.strip()


def suggest_test_scope_from_jira(jira_issue, all_endpoints, api_key):
    """
    Use AI to identify relevant endpoints for a given Jira issue.
    """
    endpoints_summary = "\n".join([
        f"{idx}: {ep['method']} {ep['path']} ({ep['summary'] or 'No summary'})"
        for idx, ep in enumerate(all_endpoints)
    ])

    comments_str = "\n".join(jira_issue.get("comments", []))
    prompt = f"""
    The following Jira task was assigned. Identify the API endpoints from the list below that are RELEVANT to this task.
    Provide a list of endpoint indices and a brief reason for each recommendation.
    
    JIRA TASK: {jira_issue.get('key')} - {jira_issue.get('summary')}
    DESCRIPTION: {jira_issue.get('description_text')}
    COMMENTS:
    {comments_str}
    
    ENDPOINTS:
    {endpoints_summary}
    
    Return a STRICT JSON object in this format:
    {{
      "recommendations": [
        {{"index": 0, "reason": "This endpoint handles ... which matches the Jira requirement."}}
      ]
    }}
    """
    
    res_text = ask_gemini(prompt, api_key)
    try:
        clean_text = repair_json(res_text)
        result = json.loads(clean_text)
        return result
    except Exception as e:
        return {"error": f"Failed to parse scoping recommendation: {str(e)}", "raw": res_text[:200]}


# --- Gemini AI Analysis (batched per group) ----------------------------------

GEMINI_MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]


def ask_gemini(prompt, api_key):
    """Send prompt to Gemini with model fallback."""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096},
    }
    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        for attempt in range(3):
            try:
                print(f"      AI: Trying {model} (attempt {attempt+1})...")
                resp = requests.post(url, json=payload, timeout=60)
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"      AI: {model} responded OK")
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                elif resp.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    print(f"      AI: Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                elif resp.status_code == 404:
                    print(f"      AI: {model} not found, trying next...")
                    break
                else:
                    print(f"      AI: {resp.status_code} on {model}, trying next...")
                    break
            except requests.exceptions.Timeout:
                print(f"      AI: Timeout on {model}, retrying...")
                continue
            except Exception as e:
                return f"[Gemini error] {e}"
    return "[All Gemini models exhausted] Check API key/quota."


def run_ai_analysis_batch(group_name, endpoint_summaries, config):
    """Phase 5: One AI call per group with summaries of all endpoints."""
    print(f"\n    [Phase 5] AI Analysis for group: {group_name}")

    # Build a compact summary for Gemini
    summary_text = ""
    for ep in endpoint_summaries:
        summary_text += f"\n### {ep['method']} {ep['path']}\n"
        summary_text += f"- Baseline: status={ep['baseline_status']}, time={ep['baseline_time']}ms, json={ep['baseline_json']}\n"
        summary_text += f"- Auth without token: {ep['auth_status']}\n"
        if ep.get("param_results"):
            req = [p["param"] for p in ep["param_results"] if p["required_by_test"]]
            opt = [p["param"] for p in ep["param_results"] if not p["required_by_test"]]
            summary_text += f"- Required params (by test): {req}\n"
            summary_text += f"- Optional params (by test): {opt}\n"
        if ep.get("empty_results"):
            warns = [p["param"] for p in ep["empty_results"] if not p["graceful"]]
            if warns:
                summary_text += f"- Empty value warnings: {warns}\n"
        if ep.get("body_preview"):
            summary_text += f"- Response preview: ```{ep['body_preview'][:500]}```\n"

    prompt = f"""You are an expert API QA engineer. Analyze these test results from the "{group_name}" API group.

## Endpoints Tested
{summary_text}

---
Provide a consolidated analysis:
1. **Overall API Health** - are these endpoints production-ready?
2. **Security Summary** - auth enforcement across endpoints
3. **Parameter Analysis** - required vs optional, any spec mismatches
4. **Error Handling** - how well do endpoints handle edge cases?
5. **Performance** - response times assessment
6. **Top 5 Issues** - ranked by severity
7. **Recommendations** - specific improvements

Keep it concise and actionable. Use markdown formatting."""

    analysis = ask_gemini(prompt, config["gemini_api_key"])
    return analysis


# --- Report Generation -------------------------------------------------------

def generate_report(all_results, ai_analyses, config):
    """Generate consolidated api_report.md."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    limit = config["response_time_limit_ms"]

    lines = [
        "# Swagger-Driven API Test Report",
        "",
        f"**Generated:** {now}  ",
        f"**Base URL:** `{config.get('swagger_base_url', 'N/A')}`  ",
        f"**Total Endpoints Tested:** {len(all_results)}  ",
        "",
    ]

    # Summary table
    lines += [
        "## Summary",
        "",
        "| # | Method | Path | Status | JSON | Time (ms) | Auth | Result |",
        "|---|--------|------|:------:|:----:|:---------:|:----:|:------:|",
    ]

    for i, ep in enumerate(all_results, 1):
        sc_ok = ep["baseline_status"] == 200
        js_ok = ep["baseline_json"]
        tm_ok = ep["baseline_time"] is not None and ep["baseline_time"] < limit
        auth_ok = ep["auth_status"] in (401, 403)
        overall = "PASS" if all([sc_ok, js_ok, tm_ok]) else "FAIL"
        auth_txt = "OK" if auth_ok else ("WARN" if ep["auth_status"] == 200 else str(ep["auth_status"]))
        time_txt = f"{ep['baseline_time']}" if ep["baseline_time"] else "ERR"
        lines.append(
            f"| {i} | {ep['method']} | `{ep['path']}` | {ep['baseline_status']} | "
            f"{'Y' if js_ok else 'N'} | {time_txt} | {auth_txt} | **{overall}** |"
        )

    # Stats
    total = len(all_results)
    passed = sum(1 for ep in all_results
                 if ep["baseline_status"] == 200
                 and ep["baseline_json"]
                 and ep["baseline_time"] is not None
                 and ep["baseline_time"] < limit)
    failed = total - passed
    auth_enforced = sum(1 for ep in all_results if ep["auth_status"] in (401, 403))
    auth_open = sum(1 for ep in all_results if ep["auth_status"] == 200)

    lines += [
        "",
        f"**Pass Rate:** {passed}/{total} ({round(passed/total*100) if total else 0}%)  ",
        f"**Auth Enforced:** {auth_enforced}/{total} | **Auth Open:** {auth_open}/{total}  ",
        "",
        "---",
        "",
    ]

    # Detailed results per group
    groups = {}
    for ep in all_results:
        g = ep["group"]
        if g not in groups:
            groups[g] = []
        groups[g].append(ep)

    for group_name, endpoints in groups.items():
        lines += [
            f"## Group: {group_name}",
            "",
        ]
        for ep in endpoints:
            lines += [
                f"### {ep['method']} `{ep['path']}`",
                "",
                f"**Summary:** {ep.get('summary', 'N/A')}  ",
                f"**Tags:** {', '.join(ep.get('tags', []))}  ",
                "",
                "#### Baseline Test",
                "",
                "| Check | Result |",
                "|-------|--------|",
                f"| Status Code | {ep['baseline_status']} {'PASS' if ep['baseline_status'] == 200 else 'FAIL'} |",
                f"| Valid JSON | {'PASS' if ep['baseline_json'] else 'FAIL'} |",
            ]
            if ep['baseline_time'] is not None:
                tm_pass = ep['baseline_time'] < limit
                lines.append(f"| Response Time | {ep['baseline_time']}ms {'PASS' if tm_pass else 'FAIL'} |")
            else:
                lines.append(f"| Response Time | ERROR |")

            # Schema Validation (New)
            schema_verdict = ep.get("schema_validation", "N/A")
            lines.append(f"| Schema Validation | {schema_verdict} |")

            if ep.get("baseline_error"):
                lines.append(f"| Error | {ep['baseline_error']} |")

            # Auth
            lines += [
                "",
                "#### Auth Enforcement",
                "",
            ]
            if ep["auth_status"] in (401, 403):
                lines.append(f"PASS - Returned `{ep['auth_status']}` without token.  ")
            elif ep["auth_status"] == 200:
                lines.append("**WARNING:** Returned `200` without auth token!  ")
            else:
                lines.append(f"Returned `{ep['auth_status']}` without auth.  ")

            # Error Message Extraction Helper
            # We want to find distinct error messages from all failures (Negative, Fuzz, Auth)
            error_messages = set()
            
            def extract_error(res):
                if res and res.get("status_code", 0) >= 400:
                    try:
                        # Try to find a message field
                        body = json.loads(res.get("body_preview", "{}"))
                        msg = body.get("message") or body.get("error") or body.get("detail")
                        if msg:
                            error_messages.add(f"{res.get('status_code')}: {msg}")
                    except:
                        pass

            # Scan all results for errors
            extract_error(ep.get("baseline"))
            if ep.get("negative_results"):
                for r in ep["negative_results"]: extract_error(r)
            if ep.get("fuzz_test_results"):
                for r in ep["fuzz_test_results"]: extract_error(r)
            if ep.get("special_auth"):
                for k, v in ep["special_auth"].items(): extract_error(v)

            # Display Error Summary
            if error_messages:
                lines += [
                    "",
                    "#### Distinct Error Messages Encountered",
                    ""
                ]
                for msg in error_messages:
                    lines.append(f"- `{msg}`")

                    lines.append(f"- `{msg}`")

            # Deep QA: Logic & Security Findings
            if ep.get("logic_findings"):
                 lines += [
                    "",
                    "#### Logic & Security Findings (Deep QA)",
                    ""
                ]
                 for f in ep["logic_findings"]:
                     icon = "⚠️" if "SECURITY" in f else "ℹ️"
                     lines.append(f"- {icon} {f}")

            # Deep QA: Path Fuzzing
            if ep.get("path_fuzz_results"):
                lines += [
                    "",
                    "#### Path Parameter Fuzzing",
                    "| Param | Value | Status | Result |",
                    "|-------|-------|:------:|:------:|",
                ]
                for pf in ep["path_fuzz_results"]:
                    lines.append(f"| `{pf['param']}` | `{pf['value']}` | {pf['status_code']} | {pf['result']} |")

            # Deep QA: Enum Testing
            if ep.get("enum_results"):
                lines += ["", "#### Enum Validation"]
                for er in ep["enum_results"]:
                     status = "PASS" if er["passed"] else "FAIL"
                     lines.append(f"- `{er['param']}` stuck with invalid value: **{status}** ({er['status_code']})")

            # Deep QA: Combinatorial
            if ep.get("combinatorial_result"):
                cr = ep["combinatorial_result"]
                status = "PASS" if cr["passed"] else "FAIL"
                lines += [
                    "",
                    "#### Combinatorial Test (Required Params Only)",
                    f"- **Status**: {status} ({cr['status_code']})",
                    f"- **Skipped (Optional)**: {', '.join(cr['skipped'])}"
                ]

            # Negative Testing (New)
            if ep.get("negative_results"):
                lines += [
                    "",
                    "#### Negative Testing",
                    "",
                    "| Test Case | Status Code | Pass/Fail | Response Preview |",
                    "|-----------|:-----------:|:---------:|------------------|",
                ]
                for neg in ep["negative_results"]:
                    preview = neg["response"][:50].replace("\n", " ") if neg["response"] else "-"
                    status = "PASS" if neg["passed"] else "FAIL"
                    lines.append(f"| {neg['test']} | {neg['status_code']} | {status} | `{preview}` |")

            # Fuzz Testing (New - Granular)
            if ep.get("fuzz_test_results"):
                lines += [
                    "",
                    "#### Fuzz Testing (Granular)",
                    "",
                    "| Parameter | Value Tested | Status | Response Preview |",
                    "|-----------|--------------|:------:|------------------|",
                ]
                for ft in ep["fuzz_test_results"]:
                    preview = ft["body_preview"][:100].replace("\n", " ") if ft.get("body_preview") else "-"
                    lines.append(f"| `{ft['param']}` | `{ft['value']}` | {ft['status_code']} | `{preview}` |")

                # Detailed Fuzz Logs (Collapsible)
                lines += [
                    "",
                    "<details>",
                    "<summary><strong>View Full Fuzz Responses</strong></summary>",
                    ""
                ]
                for ft in ep["fuzz_test_results"]:
                    lines += [
                        f"**Parameter:** `{ft['param']}`",
                        f"**Value:** `{ft['value']}`",
                        "```json",
                        ft.get("body_preview", "N/A"),
                        "```",
                        "---",
                        ""
                    ]
                lines.append("</details>")

            # Parameter analysis
            if ep.get("param_results"):
                lines += [
                    "",
                    "#### Parameter Analysis",
                    "",
                    "| Parameter | Spec Required | Test Required | Status Without |",
                    "|-----------|:------------:|:------------:|:--------------:|",
                ]
                for p in ep["param_results"]:
                    lines.append(
                        f"| `{p['param']}` | {'Yes' if p['required_by_spec'] else 'No'} | "
                        f"{'Yes' if p['required_by_test'] else 'No'} | {p['status_without']} |"
                    )

            # Empty values
            if ep.get("empty_results"):
                warns = [p for p in ep["empty_results"] if not p["graceful"]]
                if warns:
                    lines += [
                        "",
                        "#### Empty Value Warnings",
                        "",
                    ]
                    for w in warns:
                        lines.append(f"- `{w['param']}` returned `{w['status_empty']}` (unexpected)")

            # Detailed Audit Log (New - Collapsible)
            lines += [
                "",
                "<details>",
                "<summary><strong>View Detailed Audit Log</strong></summary>",
                "",
                "**Request**",
                "```http",
                f"{ep['method']} {ep['path']}",
                "```",
                "",
                "**Request Headers**",
                "```json",
                json.dumps(ep.get("request_headers", {}), indent=2),
                "```",
                "",
                "**Response Headers**",
                "```json",
                json.dumps(ep.get("response_headers", {}), indent=2),
                "```",
                "",
                "**Response Body**",
                "```json",
                ep.get("body_preview", "N/A"),
                "```",
                "</details>",
                "",
                "---",
                ""
            ]

        # AI analysis for group
        if group_name in ai_analyses:
            lines += [
                f"## AI Analysis: {group_name}",
                "",
                ai_analyses[group_name],
                "",
                "---",
                "",
            ]

    lines += [
        "",
        f"*Report generated by Swagger-Driven API Test Suite - {now}*",
    ]

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return REPORT_PATH


# --- Public API for UI -------------------------------------------------------

def fetch_all_endpoints(config):
    """Fetch and parse all endpoints from all services/groups."""
    services = config.get("services", [])
    if not services:
        # Fallback to single base URL for backward compatibility
        base_url = config.get("swagger_base_url", "")
        if not base_url:
            return []
        services = [{"name": "Default", "url": base_url}]

    all_endpoints = []
    timeout = config.get("timeout_seconds", 10)
    
    for svc in services:
        svc_name = svc.get("name", "Unknown")
        svc_url = svc.get("url", "").rstrip("/")
        if not svc_url: continue
        
        try:
            print(f"[Discovery] Fetching configs for service: {svc_name} ({svc_url})")
            groups = fetch_swagger_config(svc_url, timeout=timeout)
            for group in groups:
                spec = fetch_openapi_spec(svc_url, group["url"], timeout=timeout)
                if spec:
                    endpoints = parse_endpoints(spec, group["name"])
                    # Add service context to each endpoint
                    for ep in endpoints:
                        ep["service_name"] = svc_name
                        ep["base_url"] = svc_url
                    all_endpoints.extend(endpoints)
        except Exception as e:
            print(f"[!] Warning: Failed to fetch endpoints for service '{svc_name}': {e}")
            
    return all_endpoints


def test_single_endpoint(endpoint, config, auth_token=None, username=None, password=None, 
                         param_overrides=None, random_overrides=None, custom_overrides=None, 
                         run_ai=False, combinatorial_mode="minimal", 
                         comb_offset=0, comb_limit=64, multi_params=None, include_params=None, isolated_params=None):
    """Run full test suite for a single endpoint."""
    base_url = endpoint.get("base_url") or config.get("swagger_base_url", "")
    
    # Auth headers
    auth_headers = {}
    if auth_token:
        auth_token = auth_token.strip()
        auth_type = config.get("auth_type", "Bearer")
        auth_header_key = config.get("auth_header", "Authorization")
        
        if auth_token.lower().startswith(auth_type.lower() + " "):
            auth_token = auth_token[len(auth_type)+1:].strip()
            
        auth_headers = {auth_header_key: f"{auth_type} {auth_token}"}
    elif username and password:
        # Basic Auth
        import base64
        creds = f"{username}:{password}"
        encoded = base64.b64encode(creds.encode()).decode()
        auth_headers = {"Authorization": f"Basic {encoded}"}

    # Merge Custom Params into the "Baseline" overrides
    if custom_overrides:
        if not param_overrides:
            param_overrides = {}
        param_overrides.update(custom_overrides)

    test_url, json_body = build_test_url(base_url, endpoint, param_overrides=param_overrides, include_params=include_params)
    
    # Run phases
    baseline = run_baseline(test_url, endpoint["method"], auth_headers, config, json_body=json_body, endpoint_def=endpoint)
    
    # Early Exit if Baseline fails with 401 Unauthorized
    if baseline.get("status_code") == 401:
        print("      [Auth] ⚠️ Baseline returned 401 Unauthorized. Halting additional tests.")
        return {
            "baseline": baseline,
            "enum_results": [],
            "combinatorial_result": {"results": [], "total_count": 0, "offset": comb_offset, "limit": comb_limit},
            "logic_findings": [],
            "granular_fuzz": [],
            "auth_findings": [],
            "ai_analysis": "Authentication failed (401). Please check your token/credentials." if run_ai else None
        }
    
    # Negative Tests
    neg_results = run_negative_tests(endpoint, base_url, auth_headers, config)

    # Deep QA (Phase 5)
    path_fuzz_results = run_path_fuzzing(endpoint, base_url, auth_headers, config, base_overrides=param_overrides)
    enum_results = run_enum_testing(endpoint, base_url, auth_headers, config, base_overrides=param_overrides)
    combinatorial_result = run_combinatorial_tests(endpoint, base_url, auth_headers, config, 
                                                   base_overrides=param_overrides, mode=combinatorial_mode,
                                                   offset=comb_offset, limit=comb_limit, 
                                                   multi_params=multi_params, include_params=include_params,
                                                   random_overrides=random_overrides,
                                                   isolated_params=isolated_params)
    logic_findings = run_logic_checks(endpoint, baseline, param_overrides, json_body=json_body)

    # Fuzz Test (Granular - One by One)
    fuzz_results_list = []
    if random_overrides:
        print("      [Fuzz] Testing Granular Random inputs...")
        # For each param with a random value, inject IT specifically while keeping others "Active" (valid)
        for param_name, random_val in random_overrides.items():
            # Start with Active credentials/defaults
            current_overrides = param_overrides.copy() if param_overrides else {}
            # Inject the FAILURE for this one parameter
            current_overrides[param_name] = random_val
            
            fuzz_url, fuzz_body = build_test_url(base_url, endpoint, param_overrides=current_overrides)
            res = call_endpoint(fuzz_url, endpoint["method"], auth_headers, json_body=fuzz_body, timeout=config["timeout_seconds"])
            
            # Attach context for reporting
            res["param"] = param_name
            res["value"] = random_val
            fuzz_results_list.append(res)
    
    # 2. Auth Tests
    # User wants separate tests for Token vs Credentials (if applicable)
    special_auth_results = {}
    
    # Check if endpoint has username/password params
    param_names = [p["name"] for p in endpoint["params"]]
    has_creds = "username" in param_names or "password" in param_names
    
    if has_creds:
        # Test A: Token Only (Skip username/password params)
        print("      [Auth] Testing Token Only (skipping username/password params)...")
        token_only_url, token_only_body = build_test_url(base_url, endpoint, 
                                      param_overrides=param_overrides,
                                      skip_params={"username", "password"})
        token_only_res = call_endpoint(token_only_url, endpoint["method"], auth_headers, 
                                     json_body=token_only_body, timeout=config["timeout_seconds"])
        special_auth_results["token_only"] = token_only_res
        
        # Test B: Credentials Only (No Token, ensure username/password sent)
        print("      [Auth] Testing Credentials Only (No Token)...")
        # We assume param_overrides has the credentials, or we fallback to examples
        creds_url, creds_body = build_test_url(base_url, endpoint, param_overrides=param_overrides)
        creds_res = call_endpoint(creds_url, endpoint["method"], headers={}, json_body=creds_body, timeout=config["timeout_seconds"])
        special_auth_results["creds_only"] = creds_res
        
        # Standard "No Auth" check (No Token, No Creds?) 
        # Actually user just wants to see if Token works separate from User/Pass. 
        # The standard run_auth_check uses the full URL (with user/pass) but NO token.
        # That is effectively "Credentials Only" if parameters are present.
        # So 'auth_result' (Phase 2) is basically Test B.
        auth_result = creds_res # Reuse
        
    else:
        # Standard Auth Check (No params to skip)
        auth_result = run_auth_check(test_url, endpoint["method"], config)
        special_auth_results["token_only"] = baseline # Baseline has token and all params
        
        # Test C: Invalid Auth (Malformed Token)
        print("      [Auth] Testing Invalid Token...")
        auth_header_key = config.get("auth_header", "Authorization")
        bad_token_header = {auth_header_key: "Bearer invalid_token_12345"}
        invalid_auth_res = call_endpoint(test_url, endpoint["method"], bad_token_header, timeout=config["timeout_seconds"])
        special_auth_results["invalid_token"] = invalid_auth_res
        
    
    # Params (only if query params exist)
    param_results = []
    empty_results = []
    query_params = [p for p in endpoint["params"] if p["in"] == "query"]
    
    if query_params:
        # Use user-provided params (or spec defaults) as the baseline for removal tests
        # This ensures that if the user issues a request with 5 valid params, we test removing 1 at a time from THAT set.
        
        # We need to construct the 'base_params' set that matches what build_test_url uses
        # build_test_url uses 'param_overrides' first, then 'p["example"]'
        
        # Let's run param removal using the overrides
        param_results = run_param_removal(endpoint, base_url, auth_headers, config, 
                                        base_overrides=param_overrides,
                                        include_params=include_params)
        empty_results = run_empty_values(endpoint, base_url, auth_headers, config,
                                       base_overrides=param_overrides,
                                       include_params=include_params)
    # Dictionary to return to UI
    result = {
        "endpoint": endpoint,
        "test_url": test_url,
        "baseline": baseline,
        "auth_test": auth_result,
        "special_auth": special_auth_results,
        "param_results": param_results,
        "empty_results": empty_results,
        "negative_results": neg_results,
        "fuzz_test_results": fuzz_results_list,
        "path_fuzz_results": path_fuzz_results,
        "enum_results": enum_results,
        "combinatorial_result": combinatorial_result,
        "logic_findings": logic_findings,
        "field_progression": run_field_progression_test(endpoint, base_url, auth_headers, config, base_overrides=param_overrides),
        "ai_analysis": None
    }

    if run_ai:
        # Improve AI prompt for single endpoint
        summary_text = f"Baseline: {baseline['status_code']}, Time: {baseline['response_time_ms']}ms\n"
        if baseline.get('body_preview'):
            summary_text += f"Response: {baseline['body_preview'][:500]}\n"
            
        prompt = f"Analyze this API endpoint: {endpoint['method']} {endpoint['path']}\n\n{summary_text}\n\nIs it working correctly?"
        result["ai_analysis"] = ask_gemini(prompt, config["gemini_api_key"])

    return result


# --- Main Orchestrator -------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Swagger-Driven API Test Suite")
    parser.add_argument("--group", type=str, default=None,
                        help="Test only this API group (e.g. 'api clients')")
    parser.add_argument("--tag", type=str, default=None,
                        help="Test only endpoints with this tag (e.g. 'history')")
    parser.add_argument("--list", action="store_true",
                        help="List all discovered endpoints without testing")
    parser.add_argument("--skip-ai", action="store_true",
                        help="Skip Gemini AI analysis (faster, no API calls)")
    parser.add_argument("--skip-params", action="store_true",
                        help="Skip parameter removal and empty value tests (faster)")
    args = parser.parse_args()

    config = load_config()
    base_url = config.get("swagger_base_url", "")
    if not base_url:
        print("[ERROR] swagger_base_url not set in config.json")
        sys.exit(1)

    # Auth headers
    if config.get("auth_token", "PASTE_YOUR_TOKEN_HERE") == "PASTE_YOUR_TOKEN_HERE":
        print("[WARN] auth_token not set in config.json. Testing without auth.\n")
        auth_headers = {}
    else:
        auth_type = config.get("auth_type", "Bearer")
        auth_key = config.get("auth_header", "Authorization")
        token = config['auth_token'].strip()
        if token.lower().startswith(auth_type.lower() + " "):
            token = token[len(auth_type)+1:].strip()
        auth_headers = {auth_key: f"{auth_type} {token}"}

    print(f"\n{'='*65}")
    print(f"  Swagger-Driven API Test Suite")
    print(f"  Base URL: {base_url}")
    print(f"{'='*65}")

    # Phase 0: Discover endpoints
    print(f"\n[Discovery] Fetching API specs...")
    groups = fetch_swagger_config(base_url, timeout=config["timeout_seconds"])
    if not groups:
        print("[ERROR] No API groups found.")
        sys.exit(1)

    # Filter groups if --group specified
    if args.group:
        groups = [g for g in groups if args.group.lower() in g["name"].lower()]
        if not groups:
            print(f"[ERROR] No group matching '{args.group}'")
            sys.exit(1)

    # Fetch and parse all specs
    all_endpoints = []
    for group in groups:
        spec = fetch_openapi_spec(base_url, group["url"],
                                  timeout=config["timeout_seconds"])
        if spec:
            endpoints = parse_endpoints(spec, group["name"])
            all_endpoints.extend(endpoints)
            print(f"    Parsed {len(endpoints)} endpoints from '{group['name']}'")

    # Filter by tag if specified
    if args.tag:
        all_endpoints = [ep for ep in all_endpoints
                         if any(args.tag.lower() in t.lower() for t in ep["tags"])]

    # Remove duplicates (same path+method across groups)
    seen = set()
    unique_endpoints = []
    for ep in all_endpoints:
        key = f"{ep['method']}:{ep['path']}"
        if key not in seen:
            seen.add(key)
            unique_endpoints.append(ep)
    all_endpoints = unique_endpoints

    print(f"\n  Total unique endpoints: {len(all_endpoints)}")

    if not all_endpoints:
        print("[WARN] No endpoints to test.")
        sys.exit(0)

    # --list mode: just print discovered endpoints and exit
    if args.list:
        print(f"\n{'='*65}")
        print(f"  Discovered Endpoints ({len(all_endpoints)})")
        print(f"{'='*65}\n")
        for i, ep in enumerate(all_endpoints, 1):
            tags_str = ", ".join(ep["tags"]) if ep["tags"] else "none"
            q_params = [p["name"] for p in ep["params"] if p["in"] == "query"]
            req_params = [p["name"] for p in ep["params"] if p["required"]]
            print(f"  {i:3d}. [{ep['method']:6s}] {ep['path']}")
            print(f"       Group: {ep['group']} | Tags: {tags_str}")
            print(f"       Params: {len(q_params)} query ({len(req_params)} required)")
            if ep["summary"]:
                print(f"       Summary: {ep['summary']}")
            print()
        return

    # Run tests
    print(f"\n{'='*65}")
    print(f"  Running Tests ({len(all_endpoints)} endpoints)")
    print(f"{'='*65}")

    all_results = []
    group_summaries = {}

    for i, ep in enumerate(all_endpoints, 1):
        print(f"\n  [{i}/{len(all_endpoints)}] {ep['method']} {ep['path']}")
        print(f"    Group: {ep['group']} | Tags: {', '.join(ep['tags'])}")

        test_url = build_test_url(base_url, ep)
        print(f"    URL: {test_url[:120]}{'...' if len(test_url) > 120 else ''}")

        # Phase 1: Baseline
        baseline = run_baseline(test_url, ep["method"], auth_headers, config)

        # Phase 2: Auth check
        auth_result = run_auth_check(test_url, ep["method"], config)

        # Phase 3 & 4: Parameter tests (optional)
        param_results = []
        empty_results = []
        if not args.skip_params:
            query_params = [p for p in ep["params"] if p["in"] == "query"]
            if query_params:
                param_results = run_param_removal(ep, base_url, auth_headers, config)
                empty_results = run_empty_values(ep, base_url, auth_headers, config)
            else:
                print("      No query params - skipping param tests")

        # Collect results
        ep_result = {
            "group": ep["group"],
            "path": ep["path"],
            "method": ep["method"],
            "tags": ep["tags"],
            "summary": ep["summary"],
            "baseline_status": baseline["status_code"],
            "baseline_json": baseline["is_json"],
            "baseline_time": baseline["response_time_ms"],
            "baseline_error": baseline.get("error"),
            "body_preview": baseline.get("body_preview"),
            "auth_status": auth_result["status_code"],
            "param_results": param_results,
            "empty_results": empty_results,
        }
        all_results.append(ep_result)

        # Group summaries for AI batch
        if ep["group"] not in group_summaries:
            group_summaries[ep["group"]] = []
        group_summaries[ep["group"]].append(ep_result)

        time.sleep(0.2)  # Be polite to the API

    # Phase 5: AI Analysis (one call per group)
    ai_analyses = {}
    if not args.skip_ai:
        print(f"\n{'='*65}")
        print(f"  Running AI Analysis")
        print(f"{'='*65}")
        for group_name, summaries in group_summaries.items():
            ai_analyses[group_name] = run_ai_analysis_batch(
                group_name, summaries, config
            )
            time.sleep(1)  # Respect rate limits between groups

    # Generate report
    print(f"\n{'='*65}")
    print(f"  Generating Report")
    print(f"{'='*65}")
    report_path = generate_report(all_results, ai_analyses, config)

    # Print final summary
    total = len(all_results)
    passed = sum(1 for ep in all_results
                 if ep["baseline_status"] == 200
                 and ep["baseline_json"]
                 and ep["baseline_time"] is not None
                 and ep["baseline_time"] < limit)
    limit = config["response_time_limit_ms"]

    print(f"\n  Results: {passed}/{total} passed")
    print(f"  Report: {report_path}")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
