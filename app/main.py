from fastapi import FastAPI
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

# === Load and Post from CSV on Startup ===
@app.on_event("startup")
def create_issues_from_csv():
    print("🔁 Checking papers.csv and creating issues...")
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
        title = f"{row['paper_id']} {row['coder']} + {row['supervisor']}"
        if title in existing_titles:
            print(f"✅ Skipping existing issue: {title}")
            continue

        body = f"""
<b>Paper:</b> {row['paper']} ({row['paper_id']})  
<b>Coder:</b> {row['coder']} ({row['coder_id']})  
<b>Supervisor:</b> {row['supervisor']} ({row['supervisor_id']})  
<b>Case ID:</b> {row['paper_coder']}
"""
        labels = [str(row['paper_id']), str(row['coder_id']), str(row['supervisor_id'])]
        post_github_issue(install_token, title, body, labels)
