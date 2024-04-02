#!/usr/bin/env python3

import os
import re
import subprocess
import requests
import json

TOKEN = str(os.environ.get("GITHUB_TOKEN"))
REPOSITORY = str(os.environ.get("GITHUB_REPOSITORY"))
COMMIT_SHA = str(os.environ.get("GITHUB_SHA"))
REQUIREMENT_FILE = str(os.environ.get("REQUIREMENT_FILE"))
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json"
}
OPEN_PR = os.environ.get("OPEN_PR")
OPEN_PR_BASE = os.environ.get("OPEN_PR_BASE")
ISSUE_AUTOCLOSE = os.environ.get("ISSUE_AUTOCLOSE")
BRANCH = "automation/dependencies_update"

def close_issue_if_old(package, current_version, latest_version, new_issue_number):
    issue_title = f"Dependency outdated in {REQUIREMENT_FILE}: {package}=={current_version}"
    query = f"{issue_title} repo:{REPOSITORY} type:issue in:title"
    response = requests.get(
        "https://api.github.com/search/issues", params={"q": query})
    data = response.json()
    issue_title_latest = f"Dependency outdated in {REQUIREMENT_FILE}: {
        package}=={current_version} -> {latest_version}"
    for issue in data['items']:
        if issue['title'] != issue_title_latest:
            comment = f"""
A new version of the package is out, check out the new issue #{new_issue_number}.
            """
            comment_data = {
                "body": comment
            }
            response = requests.post(
                f"https://api.github.com/repos/{REPOSITORY}/issues/{issue['number']}/comments",
                headers=HEADERS,
                data=json.dumps(comment_data))
            if response.status_code == 201:
                print(f"INFO: Comment done in -> https://github.com/{REPOSITORY}/issues/{issue['number']}")
            else:
                print(f"ERROR: Failed to create comment. Status code: {response.status_code}.")
            issue_data = {
                "state": "closed"
            }
            response = requests.patch(
                f"https://api.github.com/repos/{REPOSITORY}/issues/{issue['number']}",
                headers=HEADERS,
                data=json.dumps(issue_data))
            if response.status_code == 200:
                print(f"INFO: Issue closed -> https://github.com/{REPOSITORY}/issues/{issue['number']}")
            else:
                print(f"ERROR: Failed to close the issue. Status code: {response.status_code}.")

def create_pull_request(branch, packages_issue):
    body = f"Bumps packages in {REQUIREMENT_FILE}."
    for package in packages_issue:
        body += f"\nCloses #{packages_issue[package]}"
    pr_data = {
        "title": f"Automation: update outdated packages in {REQUIREMENT_FILE}",
        "body": body,
        "head": branch,
        "base": OPEN_PR_BASE
    }
    response = requests.get(
        f"https://api.github.com/repos/{REPOSITORY}/pulls",
        headers=HEADERS)
    find_pr = list(pr['number'] for pr in response.json() if pr['title'] == pr_data['title'])
    if not any(find_pr):
        response = requests.post(
            f"https://api.github.com/repos/{REPOSITORY}/pulls",
            headers=HEADERS,
            data=json.dumps(pr_data))
        if response.status_code == 201:
            pr_number = response.json()['number']
            print(f"INFO: Pull Request open -> https://github.com/{REPOSITORY}/pull/{pr_number}")
        else:
            print(f"ERROR: Failed to create pull request. Status code: {response.status_code}.")
    else:
        response = requests.patch(
            f"https://api.github.com/repos/{REPOSITORY}/pulls/{find_pr[0]}",
            headers=HEADERS,
            data=json.dumps(pr_data))
        if response.status_code == 200:
            pr_number = response.json()['number']
            print(f"INFO: Pull Request updated -> https://github.com/{REPOSITORY}/pull/{pr_number}")
        else:
            print(f"ERROR: Failed to update the pull requests. Status code: {response.status_code}.")


def update_branch_with_changes(branch, file_to_change):
    os.system(f"""
git config --global --add safe.directory /github/workspace
git config --global user.email "dependencybot@linuxlab"
git config --global user.name "DependencyBot"
git fetch --prune
git stash push
git checkout -b {branch} origin/{branch}
git stash pop
git add {file_to_change}
git commit --message=\"Update {file_to_change}\"
git push
    """)


def find_replace_in_file(file_path, find_str, replace_str):
    with open(file_path, 'r') as file:
        content = file.read()
    content = re.sub(find_str, replace_str, content)
    with open(file_path, 'w') as file:
        file.write(content)


def create_branch_if_not_exists(branch, commit_sha):
    response = requests.get(f"https://api.github.com/repos/{REPOSITORY}/branches/{branch}")
    if response.status_code == 404:
        refs = {"ref": "refs/heads/" + branch, "sha": commit_sha}
        response = requests.post(
            f"https://api.github.com/repos/{REPOSITORY}/git/refs",
            headers=HEADERS,
            data=json.dumps(refs))
        if response.status_code == 201:
            print(f"INFO: Branch created -> https://github.com/{REPOSITORY}/tree/{branch}")
        else:
            print("ERROR: branch not created")
    else:
        print(f"INFO: Branch -> https://github.com/{REPOSITORY}/tree/{branch}")


def open_issue_for_package(package, current_version, latest_version):
    issue_title = f"Dependency outdated in {REQUIREMENT_FILE}: {
        package}=={current_version} -> {latest_version}"
    query = f"{issue_title} repo:{REPOSITORY} type:issue in:title"
    response = requests.get(
        "https://api.github.com/search/issues", params={"q": query})
    data = response.json()
    if data["total_count"] > 0:
        issue_number = data['items'][0]['number']
        print(f"INFO: Issue -> https://github.com/{REPOSITORY}/issues/{issue_number}")
        return issue_number
    else:
        issue_description = f"""
The package {package} is outdated in {REQUIREMENT_FILE}.

The latest version is {latest_version}. Please update the package to the latest version.

Check the package [here](https://pypi.org/project/{package}/{latest_version}/) for more information.
        """
        issue = {"title": issue_title,
                 "body": issue_description,
                 "labels": ["automation"]}
        response = requests.post(
            f"https://api.github.com/repos/{REPOSITORY}/issues",
            headers=HEADERS,
            data=json.dumps(issue))
        if response.status_code == 201:
            issue_number = response.json()['number']
            print(f"INFO: Issue created -> https://github.com/{REPOSITORY}/issues/{issue_number}")
            return issue_number
        else:
            print(f"ERROR: Failed to create issue. Status code: {response.status_code}.")
            return -1


def build_packages_dict_from_file():
    print("INFO: create dictionary from file")
    packages = {}
    with open(REQUIREMENT_FILE, 'r') as file:
        lines = file.readlines()
        for line in lines:
            regex_pattern = re.compile(
                "([a-zA-Z0-9-]+)==([0-9]+\.[0-9]+\.[0-9]+)")
            matches = regex_pattern.findall(line)
            if len(matches) > 0:
                package_name = str(matches[0][0])
                package_version = str(matches[0][1])
                packages[package_name] = package_version
    return packages


def build_packages_dict_from_output(output):
    print("INFO: create dictionary from output")
    packages = {}
    lines = output.splitlines(output)
    for line in lines:
        regex_pattern = re.compile(
            "([a-zA-Z0-9-]+)\ +([0-9]+\.[0-9]+\.[0-9]+)\ +([0-9]+\.[0-9]+\.[0-9]+)\ +([a-zA-Z]+)")
        matches = regex_pattern.findall(line)
        if len(matches) > 0:
            package_name = str(matches[0][0])
            package_version = str(matches[0][2])
            packages[package_name] = package_version
    return packages


if __name__ == '__main__':
    print("##### Collect datas #####")
    os.system(f"pip3 install -r {REQUIREMENT_FILE}")
    raw_output_outdated = subprocess.run(
        ['pip3', 'list', '--outdated'],
        stdout=subprocess.PIPE)
    current_packages = build_packages_dict_from_file()
    latest_packages = build_packages_dict_from_output(raw_output_outdated.stdout.decode('utf-8'))
    print("##### Create datas #####")
    packages_issue = {}
    if OPEN_PR == "True":
        create_branch_if_not_exists(BRANCH, COMMIT_SHA)
    print("##### Run checks #####")
    for package in current_packages.keys():
        print(f"----- Check {package} -----")
        if package in latest_packages:
            current_version = current_packages[package]
            latest_version = latest_packages[package]
            print(f"""
INFO: current version {current_version}
INFO: latest version {latest_version}""")
            packages_issue[package] = open_issue_for_package(
                package, current_version, latest_version)

            if ISSUE_AUTOCLOSE == "True":
                close_issue_if_old(package, current_version, latest_version, packages_issue[package])

            if OPEN_PR == "True":
                line_current = f"{package}==[0-9]+\.[0-9]+\.[0-9]+"
                line_latest = f"{package}=={latest_version}"
                find_replace_in_file(REQUIREMENT_FILE,
                                     line_current,
                                     line_latest)
            print("----------------")
        else:
            print(f"INFO: Skipping {package} => not in scope of {REQUIREMENT_FILE}")
            print("----------------")
    if OPEN_PR == "True":
        update_branch_with_changes(BRANCH, REQUIREMENT_FILE)
        create_pull_request(BRANCH, packages_issue)
