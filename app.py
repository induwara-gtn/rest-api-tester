from flask import Flask, render_template, jsonify, request
import swagger_tester
import json
import os

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# Load config once on startup
CONFIG = swagger_tester.load_config()

# Cache endpoints in memory to avoid fetching on every request
CACHED_ENDPOINTS = []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    """Return public config lines (excluding sensitive keys if needed, but here we trust local user)."""
    return jsonify({
        "swagger_base_url": CONFIG.get("swagger_base_url"),
        "auth_token": CONFIG.get("auth_token"),
        "auth_header": CONFIG.get("auth_header", "Authorization"),
        "auth_type": CONFIG.get("auth_type", "Bearer")
    })

@app.route('/api/endpoints', methods=['GET'])
def get_endpoints():
    """Return all discovered endpoints."""
    global CACHED_ENDPOINTS
    if not CACHED_ENDPOINTS:
        try:
            from swagger_tester import fetch_all_endpoints
            CACHED_ENDPOINTS = fetch_all_endpoints(CONFIG)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    # Return endpoints with index for selection
    return jsonify([{"index": i, **ep} for i, ep in enumerate(CACHED_ENDPOINTS)])

@app.route('/api/run-test', methods=['POST'])
def run_test():
    """Run a test for a single endpoint using its cached index."""
    global CACHED_ENDPOINTS
    data = request.json
    endpoint_index = data.get('index')
    auth_token = data.get('auth_token')
    auth_mode = data.get('auth_mode', 'token') # 'token' or 'creds'
    username = data.get('username')
    password = data.get('password')
    params = data.get('params', {})
    random_params = data.get('random_params', {})
    custom_params = data.get('custom_params', {})
    run_ai = data.get('run_ai', False)
    comb_mode = data.get('combinatorial_mode', 'minimal')
    comb_offset = data.get('comb_offset', 0)
    comb_limit = data.get('comb_limit', 64)
    multi_params = data.get('multi_params', [])
    include_params = data.get('include_params')
    isolated_params = data.get('isolated_params', [])
    
    # Ensure cache is populated if empty
    if not CACHED_ENDPOINTS:
        try:
            from swagger_tester import fetch_all_endpoints
            CACHED_ENDPOINTS = fetch_all_endpoints(CONFIG)
        except Exception as e:
            return jsonify({"error": f"Failed to populate endpoints: {str(e)}"}), 500

    if endpoint_index is None or not (0 <= endpoint_index < len(CACHED_ENDPOINTS)):
        return jsonify({"error": "Invalid endpoint index"}), 400

    endpoint = CACHED_ENDPOINTS[endpoint_index]

    try:
        from swagger_tester import test_single_endpoint
        result = test_single_endpoint(
            endpoint, 
            CONFIG, 
            auth_token=auth_token if auth_mode == 'token' else None, 
            username=username if auth_mode == 'creds' else None,
            password=password if auth_mode == 'creds' else None,
            param_overrides=params,
            random_overrides=random_params,
            custom_overrides=custom_params,
            run_ai=run_ai,
            combinatorial_mode=comb_mode,
            comb_offset=comb_offset,
            comb_limit=comb_limit,
            multi_params=multi_params,
            include_params=include_params,
            isolated_params=isolated_params
        )
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/validate-token', methods=['POST'])
def validate_token():
    """Verify if the provided token/creds are valid by making a minimal request."""
    data = request.json
    auth_mode = data.get('auth_mode', 'token')
    auth_token = data.get('auth_token')
    username = data.get('username')
    password = data.get('password')
    
    # Try to fetch the swagger config of the first service to validate
    try:
        from swagger_tester import call_endpoint
        url = CONFIG.get("services", [{}])[0].get("url")
        if not url:
            return jsonify({"status": "success", "message": "No services defined to check, assuming valid structure."})
            
        # Mock auth headers
        headers = {}
        if auth_mode == 'token' and auth_token:
            headers = {CONFIG.get("auth_header", "Authorization"): f"{CONFIG.get('auth_type', 'Bearer')} {auth_token}"}
        elif auth_mode == 'creds' and username and password:
            import base64
            creds = f"{username}:{password}"
            encoded = base64.b64encode(creds.encode()).decode()
            headers = {"Authorization": f"Basic {encoded}"}
            
        # Make a HEAD or GET request to the service URL
        res = call_endpoint(url, method="GET", headers=headers, timeout=5)
        
        if res.get("status_code") == 401:
            return jsonify({"status": "error", "code": 401, "message": res.get("body_preview", "Unauthorized")}), 401
            
        return jsonify({"status": "success", "code": res.get("status_code")})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
def smart_ai_test():
    """Run AI-suggested tests based on a baseline response."""
    global CACHED_ENDPOINTS
    data = request.json
    endpoint_index = data.get('index')
    baseline_result = data.get('baseline')
    
    # Ensure cache is populated if empty
    if not CACHED_ENDPOINTS:
        try:
            from swagger_tester import fetch_all_endpoints
            CACHED_ENDPOINTS = fetch_all_endpoints(CONFIG)
        except Exception as e:
            return jsonify({"error": f"Failed to populate endpoints: {str(e)}"}), 500

    if endpoint_index is None or not baseline_result or not (0 <= endpoint_index < len(CACHED_ENDPOINTS)):
        return jsonify({"error": "Invalid endpoint index or missing baseline"}), 400

    endpoint = CACHED_ENDPOINTS[endpoint_index]
    
    try:
        from swagger_tester import run_ai_smart_tests
        
        # Build headers based on mode
        auth_mode = data.get('auth_mode', 'token')
        if auth_mode == 'creds':
            import base64
            username = data.get('username')
            password = data.get('password')
            creds = f"{username}:{password}"
            encoded = base64.b64encode(creds.encode()).decode()
            headers = {"Authorization": f"Basic {encoded}"}
        else:
            token = data.get('token') or data.get('auth_token') or CONFIG.get('auth_token')
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            
        results = run_ai_smart_tests(
            endpoint, 
            endpoint.get("base_url") or CONFIG.get("swagger_base_url"), 
            headers, 
            CONFIG, 
            baseline_result
        )
        return jsonify(results)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/ai-suggest-tests', methods=['POST'])
def ai_suggest_tests():
    """Analyze baseline and suggest tests (no execution)."""
    global CACHED_ENDPOINTS
    data = request.json
    endpoint_index = data.get('index')
    baseline_result = data.get('baseline')
    
    # Ensure cache is populated if empty
    if not CACHED_ENDPOINTS:
        try:
            from swagger_tester import fetch_all_endpoints
            CACHED_ENDPOINTS = fetch_all_endpoints(CONFIG)
        except Exception as e:
            return jsonify({"error": f"Failed to populate endpoints: {str(e)}"}), 500

    if endpoint_index is None or not baseline_result or not (0 <= endpoint_index < len(CACHED_ENDPOINTS)):
        return jsonify({"error": "Invalid endpoint index or missing baseline"}), 400
    
    endpoint = CACHED_ENDPOINTS[endpoint_index]
    cr_description = data.get('cr_description')
    try:
        from swagger_tester import generate_ai_smart_tests
        test_plan = generate_ai_smart_tests(endpoint, baseline_result, CONFIG.get("gemini_api_key"), cr_description=cr_description)
        return jsonify(test_plan)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/ai-execute-and-verify', methods=['POST'])
def ai_execute_and_verify():
    """Run a specific AI suggestion and verify its logic."""
    global CACHED_ENDPOINTS
    data = request.json
    endpoint_index = data.get('index')
    baseline_result = data.get('baseline')
    test_case = data.get('test_case') # {param, value, reason}
    
    # Ensure cache is populated if empty
    if not CACHED_ENDPOINTS:
        try:
            from swagger_tester import fetch_all_endpoints
            CACHED_ENDPOINTS = fetch_all_endpoints(CONFIG)
        except Exception as e:
            return jsonify({"error": f"Failed to populate endpoints: {str(e)}"}), 500

    if endpoint_index is None or not baseline_result or not test_case or not (0 <= endpoint_index < len(CACHED_ENDPOINTS)):
        return jsonify({"error": "Missing required data or invalid index"}), 400

    endpoint = CACHED_ENDPOINTS[endpoint_index]
    try:
        from swagger_tester import run_single_smart_test, analyze_test_logic
        
        # Build headers based on mode
        auth_mode = data.get('auth_mode', 'token')
        if auth_mode == 'creds':
            import base64
            username = data.get('username')
            password = data.get('password')
            creds = f"{username}:{password}"
            encoded = base64.b64encode(creds.encode()).decode()
            headers = {"Authorization": f"Basic {encoded}"}
        else:
            token = data.get('token') or data.get('auth_token') or CONFIG.get('auth_token')
            headers = {"Authorization": f"Bearer {token}"} if token else {}

        # 1. Run the test
        test_res = run_single_smart_test(
            endpoint, 
            endpoint.get("base_url") or CONFIG.get("swagger_base_url"), 
            headers, 
            CONFIG, 
            test_case['param'], 
            test_case['value']
        )
        
        # 2. Verify logic via AI
        analysis = analyze_test_logic(
            endpoint, 
            baseline_result, 
            test_res, 
            test_case, 
            CONFIG.get("gemini_api_key")
        )
        
        return jsonify({
            "status_code": test_res["status_code"],
            "body_preview": test_res["body_preview"],
            "body_full": test_res.get("body_full"),
            "analysis": analysis
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/jira-scope', methods=['POST'])
def jira_scope():
    """Fetch Jira issue and suggest test scope via AI."""
    global CACHED_ENDPOINTS
    data = request.json
    issue_id = data.get('issue_id')
    
    if not issue_id:
        return jsonify({"error": "Missing Jira Issue ID"}), 400

    # Ensure cache is populated
    if not CACHED_ENDPOINTS:
        try:
            from swagger_tester import fetch_all_endpoints
            CACHED_ENDPOINTS = fetch_all_endpoints(CONFIG)
        except Exception as e:
            return jsonify({"error": f"Failed to populate endpoints: {str(e)}"}), 500

    try:
        from jira_client import fetch_jira_issue
        jira_issue = fetch_jira_issue(issue_id, CONFIG)
        if "error" in jira_issue:
            return jsonify(jira_issue), 400

        from swagger_tester import suggest_test_scope_from_jira
        scoping_result = suggest_test_scope_from_jira(jira_issue, CACHED_ENDPOINTS, CONFIG.get("gemini_api_key"))
        
        return jsonify({
            "jira": jira_issue,
            "scoping": scoping_result
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("Starting API Tester UI at http://localhost:5000")
    app.run(debug=True, port=5000)
