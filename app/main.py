from fastapi import FastAPI, Request
import requests, time, jwt, os, csv
from pathlib import Path

app = FastAPI()

APP_ID = os.getenv("GITHUB_APP_ID")
INSTALLATION_ID = os.getenv("GITHUB_INSTALLATION_ID")
REPO = os.getenv("GITHUB_REPO")

def generate_jwt():
    with open("private-key.pem", "r") as f:
        private_key = f.read()
    now = int(time.time())
    payload = {"iat": now, "exp": now + 600, "iss": APP_ID}
    return jwt.encode(payload, private_key, algorithm="RS256")

def get_install_token(jwt_token):
    url = f"https://api.github.com/app/installations/{INSTALLATION_ID}/access_tokens"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json"
    }
    resp = requests.post(url, headers=headers)
    print("GitHub token response:", resp.status_code, resp.text)
    data = resp.json()
    if "token" not in data:
        raise Exception(f"GitHub error: {data}")
    return data["token"]

def get_existing_issue_labels(token):
    url = f"https://api.github.com/repos/{REPO}/issues?state=all&per_page=100"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"Error fetching issues: {resp.status_code} {resp.text}")
    issues = resp.json()
    existing = set()
    for issue in issues:
        for label in issue.get("labels", []):
            name = label["name"]
            if name.startswith("paper_id="):
                existing.add(name.split("=")[1])
    return existing

def post_github_issue(token, title, body, labels):
    url = f"https://api.github.com/repos/{REPO}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }
    json_data = {
        "title": title,
        "body": body,
        "labels": labels
    }
    response = requests.post(url, headers=headers, json=json_data)
    print(f"Issue created: {response.status_code} {response.text}")
    return response

def create_issues_from_csv():
    csv_path = Path(__file__).parent / "papers.csv"
    if not csv_path.exists():
        print("papers.csv not found.")
        return

    jwt_token = generate_jwt()
    install_token = get_install_token(jwt_token)
    existing_ids = get_existing_issue_labels(install_token)

    with open(csv_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            paper_id = row['paper_id']
            if paper_id in existing_ids:
                print(f"Skipping existing issue for paper_id: {paper_id}")
                continue

            title = f"{paper_id} {row['coder']} + {row['supervisor']}"
            body = (
                f"<b>Paper:</b> {row['paper']} ({row['paper_id']})\n"
                f"<b>Coder:</b> {row['coder']} ({row['coder_id']})\n"
                f"<b>Supervisor:</b> {row['supervisor']} ({row['supervisor_id']})\n"
                f"<b>Case ID:</b> {row['paper_coder']}"
            )
            labels = [
                row['paper_id'],
                row['coder_id'],
                row['supervisor_id'],
                f"paper_id={paper_id}"
            ]
            post_github_issue(install_token, title, body, labels)

@app.on_event("startup")
def on_startup():
    create_issues_from_csv()

@app.post("/webhook")
async def receive_submission(request: Request):
    return {"status": "received"}
