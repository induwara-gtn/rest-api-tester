import requests
import json
from requests.auth import HTTPBasicAuth

def fetch_jira_issue(issue_id, config):
    """
    Fetch Jira issue details (Summary, Description, Comments).
    """
    jira_url = config.get("jira_url", "").strip().rstrip("/")
    # Remove common UI suffixes if user pasted browser URL
    if "/browse" in jira_url:
        jira_url = jira_url.split("/browse")[0]
    
    jira_email = config.get("jira_email")
    jira_api_token = config.get("jira_api_token")

    if not all([jira_url, jira_email, jira_api_token]):
        return {"error": "Jira configuration is incomplete (url, email, or token missing)."}

    # Extract issue key if issue_id is a full URL
    if "/browse/" in str(issue_id):
        issue_id = str(issue_id).split("/browse/")[1].split("?")[0].split("#")[0].strip("/")
    elif "http" in str(issue_id) and "/" in str(issue_id):
        issue_id = str(issue_id).rstrip("/").split("/")[-1]

    url = f"{jira_url}/rest/api/3/issue/{issue_id}"
    auth = HTTPBasicAuth(jira_email, jira_api_token)
    headers = {
        "Accept": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, auth=auth, timeout=10)
        if response.status_code == 200:
            data = response.json()
            fields = data.get("fields", {})
            
            # Extract plain text from Atlassian Document Format (ADF) if possible
            details = {
                "key": data.get("key"),
                "summary": fields.get("summary"),
                "description_raw": fields.get("description"), # ADF format
                "status": fields.get("status", {}).get("name"),
                "comments": []
            }
            
            # Simple ADF to text converter for the description
            details["description_text"] = adf_to_text(fields.get("description"))

            # Fetch comments
            comment_payload = fields.get("comment", {}).get("comments", [])
            for c in comment_payload:
                author = c.get("author", {}).get("displayName", "User")
                body = adf_to_text(c.get("body"))
                details["comments"].append(f"{author}: {body}")
            
            return details
        else:
            return {"error": f"Jira API returned {response.status_code}: {response.text}"}
    except Exception as e:
        return {"error": f"Failed to connect to Jira: {str(e)}"}

def adf_to_text(doc):
    """Very basic converter for Atlassian Document Format to plain text."""
    if not doc or not isinstance(doc, dict):
        return ""
    
    parts = []
    def traverse(node):
        if "text" in node:
            parts.append(node["text"])
        if "content" in node:
            for child in node["content"]:
                traverse(child)
                
    traverse(doc)
    return " ".join(parts)
