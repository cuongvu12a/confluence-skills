#!/usr/bin/env python3
"""Tạo task Jira (project FAC) hàng loạt từ tasks.json.

Mặc định chạy dry-run (không gọi API tạo issue). Thêm --apply mới tạo thật.
Xem jira-create-guide.md để biết chi tiết field.
"""
import argparse
import json
import math
import os
import sys
import urllib.error
import urllib.request

ISSUETYPE_TASK = "10002"
FIELD_EPIC = "customfield_10102"
FIELD_SPRINT = "customfield_10101"
FIELD_STORY_POINTS = "customfield_10106"
FIELD_MANAGEMENT_SYSTEMS = "customfield_10804"


def jira_request(base_url, token, method, path, body=None):
    url = f"{base_url}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Jira API lỗi {e.code} {method} {path}: {e.read().decode()}")


def get_myself(base_url, token):
    return jira_request(base_url, token, "GET", "/rest/api/2/myself")


def get_active_sprint(base_url, token, board_id):
    data = jira_request(base_url, token, "GET", f"/rest/agile/1.0/board/{board_id}/sprint?state=active")
    values = data.get("values") or []
    if not values:
        raise SystemExit(f"Không tìm thấy sprint active trên board {board_id}")
    return values[0]


def round_up_hours(hours):
    return math.ceil(float(hours))


def build_fields(task, defaults, project_key, sprint_id, assignee_name):
    hours = round_up_hours(task["estimate_hours"])
    fields = {
        "project": {"key": project_key},
        "issuetype": {"id": ISSUETYPE_TASK},
        "summary": task["summary"],
        "description": task.get("description", ""),
        "priority": {"name": defaults.get("priority", "Medium")},
        FIELD_SPRINT: sprint_id,
        FIELD_STORY_POINTS: hours,
        "timetracking": {"originalEstimate": f"{hours}h"},
        "assignee": {"name": assignee_name},
    }
    epic = task.get("epic", defaults.get("epic"))
    if epic:
        fields[FIELD_EPIC] = epic
    mgmt = task.get("management_systems", defaults.get("management_systems"))
    if mgmt and mgmt != ["None"] and mgmt != "None":
        fields[FIELD_MANAGEMENT_SYSTEMS] = [{"value": v} for v in mgmt]
    return fields, hours


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks_file", help="File tasks.json")
    parser.add_argument("--apply", action="store_true", help="Tạo thật lên Jira (mặc định chỉ dry-run)")
    parser.add_argument("--project", default="FAC", help="Project key (mặc định FAC)")
    args = parser.parse_args()

    base_url = os.environ.get("JIRA_URL")
    token = os.environ.get("JIRA_TOKEN")
    if not base_url or not token:
        raise SystemExit("Thiếu JIRA_URL hoặc JIRA_TOKEN trong env")

    with open(args.tasks_file) as f:
        data = json.load(f)
    defaults = data.get("defaults", {})
    tasks = data["tasks"]

    me = get_myself(base_url, token)
    assignee_name = defaults.get("assignee") or me["name"]

    sprint_id = defaults.get("sprint")
    board_id = defaults.get("board_id", 4)
    sprint_label = sprint_id
    if not sprint_id:
        sprint = get_active_sprint(base_url, token, board_id)
        sprint_id = sprint["id"]
        sprint_label = f"{sprint_id} ({sprint['name']})"

    epic = defaults.get("epic")
    mgmt = defaults.get("management_systems")

    print(f"Jira: {base_url}  Project: {args.project}")
    print(f"Assignee mặc định: {assignee_name} ({me['displayName']})")
    print(f"Sprint: {sprint_label}")
    print(f"Epic Link mặc định: {epic or '(chưa set)'}")
    print(f"Management Systems mặc định: {mgmt or '(chưa set)'}")
    print(f"Mode: {'APPLY (tạo thật)' if args.apply else 'DRY-RUN (không tạo gì)'}")
    print("-" * 72)

    total_hours = 0
    results = []
    for task in tasks:
        fields, hours = build_fields(task, defaults, args.project, sprint_id, assignee_name)
        total_hours += hours
        print(f"[{task['id']}] {fields['summary']}")
        print(f"    Estimate: {hours}h  |  Story Points: {hours}  |  Epic: {fields.get(FIELD_EPIC, '-')}"
              f"  |  Management Systems: {fields.get(FIELD_MANAGEMENT_SYSTEMS, '-')}")
        desc_preview = (fields["description"] or "").splitlines()[0][:100] if fields["description"] else ""
        print(f"    Mô tả: {desc_preview}...")

        if args.apply:
            created = jira_request(base_url, token, "POST", "/rest/api/2/issue", {"fields": fields})
            key = created["key"]
            print(f"    -> Đã tạo {key}")
            results.append({"id": task["id"], "key": key, "summary": fields["summary"]})
        print()

    print("-" * 72)
    print(f"Tổng: {len(tasks)} task, tổng estimate {total_hours}h = tổng Story Points {total_hours}")

    if args.apply:
        out_file = args.tasks_file.replace(".json", "_created.json")
        with open(out_file, "w") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"Đã lưu danh sách key vừa tạo vào {out_file}")
    else:
        print("Đây là DRY-RUN — chưa tạo gì trên Jira. Thêm --apply để tạo thật.")


if __name__ == "__main__":
    sys.exit(main())
