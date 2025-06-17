import os
import time
import requests
import pandas as pd
from fastapi import FastAPI
from github import Auth, Github

app = FastAPI()

REPO_NAME = "schneideraxel/ideal-automation-test"
CSV_FILE = "papers.csv"
POSTED_IDS_FILE = "posted_ids.txt"

def get_github_client():
    app_id = os.getenv("GITHUB_APP_ID")
    installation_id = os.getenv("GITHUB_INSTALLATION_ID")
    pem_key = os.getenv("GITHUB_PRIVATE_KEY")

    auth = Auth.AppAuth(app_id, installation_id, pem_key)
    gh = Github(auth=auth)
    return gh.get_repo(REPO_NAME)

def read_posted_ids():
    if os.path.exists(POSTED_IDS_FILE):
        with open(POSTED_IDS_FILE, "r") as f:
            return set(line.strip() for line in f)
    return set()

def write_posted_id(paper_id):
    with open(POSTED_IDS_FILE, "a") as f:
        f.write(paper_id + "\n")

def create_issue_with_retry(repo, title, body, labels, paper_id, max_retries=5, delay=60):
    for attempt in range(max_retries):
        try:
            issue = repo.create_issue(title=title, body=body, labels=labels)
            print(f"Issue posted: {title}")
            write_posted_id(paper_id)
            return
        except Exception as e:
            print(f"Failed to post issue '{title}' (Attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print(f"Gave up on '{title}' after {max_retries} attempts.")

@app.on_event("startup")
def create_issues_from_csv():
    print("Checking papers.csv and creating issues...")
    df = pd.read_csv(CSV_FILE)
    repo = get_github_client()
    posted_ids = read_posted_ids()

    for _, row in df.iterrows():
        paper_id = str(row["paper_id"])
        if paper_id in posted_ids:
            continue

        title = f"{paper_id} {row['coder']} + {row['supervisor']}"
        body = (
            f"<b>Paper:</b> {row['paper']} ({row['paper_id']})\n"
            f"<b>Coder:</b> {row['coder']} ({row['coder_id']})\n"
            f"<b>Supervisor:</b> {row['supervisor']} ({row['supervisor_id']})\n"
            f"<b>Case ID:</b> {row['paper_coder']}"
        )
        labels = [str(row['paper_id']), str(row['coder_id']), str(row['supervisor_id'])]

        create_issue_with_retry(repo, title, body, labels, paper_id)
