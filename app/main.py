from fastapi import FastAPI, Request
import requests, time, jwt, os

app = FastAPI()

# Load from environment
APP_ID = os.getenv("GITHUB_APP_ID")
INSTALLATION_ID = os.getenv("GITHUB_INSTALLATION_ID")
REPO = os.getenv("GITHUB_REPO")  # e.g., "schneideraxel/ideal-automation-test"

# === Step 1: Create GitHub App JWT ===
def generate_jwt():
    with open("private-key.pem", "r") as f:
        private_key = f.read()

    now = int(time.time())
    payload = {
        "iat": now,
        "exp": now + 600,
        "iss": APP_ID
    }

    return jwt.encode(payload, private_key, algorithm="RS256")

# === Step 2: Get Installation Token ===
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

# === Step 3: Post GitHub Issue ===
def post_github_issue(token, title, body):
    url = f"https://api.github.com/repos/{REPO}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }
    json = {"title": title, "body": body}
    return requests.post(url, headers=headers, json=json)

# === Webhook Endpoint ===
@app.post("/webhook")
async def receive_submission(request: Request):
    data = await request.json()

    issue_name = data["issue_name"]
    issue_message = data["issue_message"]

    title = issue_name
    body = issue_message

    jwt_token = generate_jwt()
    install_token = get_install_token(jwt_token)
    response = post_github_issue(install_token, title, body)

    return {"status": "created", "github_response": response.json()}
