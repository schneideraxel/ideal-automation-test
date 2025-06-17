from fastapi import FastAPI, Request
import requests, time, jwt, os, csv, pandas as pd

app = FastAPI()

# Load from environment
APP_ID = os.getenv("GITHUB_APP_ID")
INSTALLATION_ID = os.getenv("GITHUB_INSTALLATION_ID")
REPO = os.getenv("GITHUB_REPO")  # e.g., "username/repo"
POSTED_IDS_FILE = "posted_issues.txt"

# === Step 1: Create GitHub App JWT ===
def generate_jwt():
    with open("private-key.pem", "r") as f:
        private_key = f.read()
    now = int(time.time())
    payload = {"iat": now, "exp": now + 600, "iss": APP_ID}
    return jwt.encode(payload, private_key, algorithm="RS256")

# === Step 2: Get Installation Token ===
def get_install_token(jwt_token):
    url = f"https://api.github.com/app/installations/{INSTALLATION_ID}/access_tokens"
    headers = {"Authorization": f"Bearer {jwt_token}", "Accept": "application/vnd.github+json"}
    resp = requests.post(url, headers=headers)
    return resp.json()["token"]

# === Step 3: Post GitHub Issue (with retries) ===
def post_github_issue(token, title, body, labels):
    url = f"https://api.github.com/repos/{REPO}/issues"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    payload = {"title": title, "body": body, "labels": labels}

    attempt = 0
    while True:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 201:
            print(f"Issue created: {title}")
            return True
        else:
            attempt += 1
            print(f"[Attempt {attempt}] Failed to post issue: {title}, status {response.status_code}")
            print("Retrying in 60 seconds...")
            time.sleep(60)

# === Track Already Posted Issues ===
def load_posted_ids():
    if not os.path.exists(POSTED_IDS_FILE):
        return set()
    with open(POSTED_IDS_FILE, "r") as f:
        return set(line.strip() for line in f.readlines())

def save_posted_id(paper_id):
    with open(POSTED_IDS_FILE, "a") as f:
        f.write(paper_id + "\n")

# === On Startup: Create Issues from CSV ===
@app.on_event("startup")
def create_issues_from_csv():
    print("Checking papers.csv and creating issues...")
    df = pd.read_csv("app/papers.csv")
    posted_ids = load_posted_ids()

    jwt_token = generate_jwt()
    install_token = get_install_token(jwt_token)

    for _, row in df.iterrows():
        paper_id = str(row["paper_id"])
        if paper_id in posted_ids:
            continue

        title = f"{row['paper_id']} {row['coder']} + {row['supervisor']}"
        body = (
            f"<b>Paper:</b> {row['paper']} ({row['paper_id']})\n"
            f"<b>Coder:</b> {row['coder']} ({row['coder_id']})\n"
            f"<b>Supervisor:</b> {row['supervisor']} ({row['supervisor_id']})\n"
            f"<b>Case ID:</b> {row['paper_coder']}"
        )
        labels = [row["paper_id"], row["coder_id"], row["supervisor_id"]]

        success = post_github_issue(install_token, title, body, labels)
        if success:
            save_posted_id(paper_id)

# === Webhook Endpoint ===
@app.post("/webhook")
async def receive_submission(request: Request):
    data = await request.json()
    issue_name = data.get("issue_name")
    issue_message = data.get("issue_message")

    if not issue_name or not issue_message:
        return {"status": "error", "message": "Missing issue_name or issue_message"}

    jwt_token = generate_jwt()
    install_token = get_install_token(jwt_token)

    # Post comment to existing issue
    url = f"https://api.github.com/repos/{REPO}/issues/{issue_name}/comments"
    headers = {
        "Authorization": f"Bearer {install_token}",
        "Accept": "application/vnd.github+json"
    }
    response = requests.post(url, headers=headers, json={"body": issue_message})

    return {"status": "posted", "response": response.status_code, "text": response.text}
