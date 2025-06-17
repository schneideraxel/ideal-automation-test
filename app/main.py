from fastapi import FastAPI, Request
import pandas as pd
import os, requests, time, jwt

app = FastAPI()

# GitHub environment setup
APP_ID = os.getenv("GITHUB_APP_ID")
INSTALLATION_ID = os.getenv("GITHUB_INSTALLATION_ID")
REPO = os.getenv("GITHUB_REPO")

# === JWT + GitHub Setup ===
def generate_jwt():
    with open("private-key.pem", "r") as f:
        private_key = f.read()
    now = int(time.time())
    payload = {"iat": now, "exp": now + 600, "iss": APP_ID}
    return jwt.encode(payload, private_key, algorithm="RS256")

def get_install_token(jwt_token):
    url = f"https://api.github.com/app/installations/{INSTALLATION_ID}/access_tokens"
    headers = {"Authorization": f"Bearer {jwt_token}", "Accept": "application/vnd.github+json"}
    resp = requests.post(url, headers=headers)
    print("GitHub token response:", resp.status_code, resp.text)
    return resp.json()["token"]

def post_github_issue(token, title, body, labels):
    url = f"https://api.github.com/repos/{REPO}/issues"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    json = {"title": title, "body": body, "labels": labels}
    response = requests.post(url, headers=headers, json=json)
    print(f"Posted issue ({title}):", response.status_code)
    return response

# === Comment Handler ===
def post_github_comment(issue_number, message, token):
    url = f"https://api.github.com/repos/{REPO}/issues/{issue_number}/comments"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    response = requests.post(url, headers=headers, json={"body": message})
    print(f"Posted comment to issue #{issue_number}: {response.status_code}")
    return response

# === Message Generators ===
def generate_stage1_message(data):
    if data.get("X_correction") == "1":
        return f"<p>Stage 1 resubmission by {data['C_coder']} on {data['datetime']}. Corrected entry ID: <strong>{data['C_entryID']}</strong>. Awaiting review.</p>"
    else:
        return f"<p>Stage 1 completed by {data['C_coder']} on {data['datetime']}. Entry ID: <strong>{data['C_entryID']}</strong>. Awaiting review.</p>"

def generate_stage1_check_message(data):
    if data.get("entry_accepted") == "1":
        return f"<p>Entry <strong>{data['C_entryID']}</strong> reviewed by {data['C_supervisor']} on {data['datetime']}. <span style='color:green; font-weight:bold;'>Accepted.</span> Proceed to Stage 2.</p>"
    else:
        return f"<p>Entry <strong>{data['C_entryID']}</strong> reviewed by {data['C_supervisor']} on {data['datetime']}. <span style='color:red; font-weight:bold;'>Requires revision.</span> Please repeat Stage 1.</p>"

def generate_stage2_message(data):
    if data.get("X_correction") == "1":
        return f"<p>Stage 2 resubmission by {data['C_coder']} on {data['datetime']}. Corrected entry ID: <strong>{data['C_entryID']}</strong>. Awaiting review.</p>"
    else:
        return f"<p>Stage 2 completed by {data['C_coder']} on {data['datetime']}. Entry ID: <strong>{data['C_entryID']}</strong>. Awaiting review.</p>"

message_generators = {
    "ideal_stage_1": generate_stage1_message,
    "ideal_stage_1_check": generate_stage1_check_message,
    "ideal_stage_2": generate_stage2_message,
}

# === Find GitHub Issue Number by paper_id ===
def find_issue_number_by_paper_id(paper_id, token):
    url = f"https://api.github.com/repos/{REPO}/issues?state=open&per_page=100"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    response = requests.get(url, headers=headers)
    issues = response.json()
    for issue in issues:
        title = issue.get("title", "")
        if title.startswith(str(paper_id)):
            return issue["number"]
    return None

# === Webhook endpoint ===
@app.post("/webhook")
async def webhook_handler(request: Request):
    try:
        payload = await request.json()
        print("Webhook received:", payload)
    except Exception as e:
        print("Failed to parse webhook payload:", str(e))
        return {"error": "Invalid JSON"}

    form_id = payload.get("form_id")
    paper_id = payload.get("paper_id")

    if form_id not in message_generators:
        return {"error": "Unknown form_id"}

    message = message_generators[form_id](payload)

    jwt_token = generate_jwt()
    install_token = get_install_token(jwt_token)
    issue_number = find_issue_number_by_paper_id(paper_id, install_token)

    if issue_number is None:
        return {"error": f"No issue found for paper_id {paper_id}"}

    response = post_github_comment(issue_number, message, install_token)

    return {"status": "ok", "github_response": response.status_code}

# === Load and Post from CSV on Startup ===
@app.on_event("startup")
def create_issues_from_csv():
    print("Checking papers.csv and creating issues...")
    jwt_token = generate_jwt()
    install_token = get_install_token(jwt_token)

    # Load papers.csv
    df = pd.read_csv("app/papers.csv")

    # Get existing GitHub issue titles
    url = f"https://api.github.com/repos/{REPO}/issues"
    headers = {"Authorization": f"Bearer {install_token}", "Accept": "application/vnd.github+json"}
    existing_issues = requests.get(url, headers=headers).json()
    existing_titles = set(issue["title"] for issue in existing_issues if "title" in issue)

    for _, row in df.iterrows():
        title = f"{row['paper_id']}"
        if title in existing_titles:
            print(f"Skipping existing issue: {title}")
            continue

        body = f"""
<b>Paper:</b> {row['paper']} ({row['paper_id']})  <br>
<b>Coder:</b> {row['coder']} ({row['coder_id']})  <br>
<b>Supervisor:</b> {row['supervisor']} ({row['supervisor_id']})  <br>
<b>Case ID:</b> {row['paper_coder']}
"""
        labels = [str(row['paper_id']), str(row['coder_id']), str(row['supervisor_id']), str(row['coder']), str(row['supervisor'])]
        post_github_issue(install_token, title, body, labels)

