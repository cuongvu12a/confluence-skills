# Tự động tạo task Jira (FAC) bằng REST API

Áp dụng cho Jira Server `jira.mymerchize.com` (8.16.1). Đã dùng để tạo FAC-26395 → FAC-26398 ngày 2026-10-16.

## 1. Chuẩn bị

| Việc | Cách làm |
|---|---|
| Personal Access Token | Jira → avatar → Profile → **Personal Access Tokens** → Create token (nên đặt hạn ngắn) |
| Biến môi trường | `JIRA_URL=https://jira.mymerchize.com`, `JIRA_TOKEN=<PAT>`. Có thể khai trong `~/.claude/settings.json` mục `env`, hoặc `export` trong shell. **Không** commit token vào repo |
| Kiểm token | `curl -s -H "Authorization: Bearer $JIRA_TOKEN" "$JIRA_URL/rest/api/2/myself"` → trả `name`, `displayName` |

Header cho mọi request: `Authorization: Bearer $JIRA_TOKEN`, `Content-Type: application/json`.

## 2. Field cần thiết (project FAC, loại Task)

| Field (tên hiển thị) | Field id | Kiểu / giá trị gửi lên | Bắt buộc | Ví dụ |
|---|---|---|---|---|
| Project | `project` | `{"key": "FAC"}` | ✅ | |
| Issue Type | `issuetype` | `{"id": "10002"}` (Task) | ✅ | |
| Summary | `summary` | chuỗi | ✅ | `User Groups và ngưỡng Away` |
| Description | `description` | chuỗi **Jira wiki markup** (`*bold*`, `{{code}}`, `h3.`, `#` danh sách số) | | xem `jira-tasks.md` |
| Priority | `priority` | `{"name": "Medium"}` — Highest / High / Medium / Low / Lowest | | |
| Epic Link | `customfield_10102` | chuỗi key epic | | `"FAC-26380"` |
| Sprint | `customfield_10101` | **số** id sprint | | `1214` (FAC Sprint 152) |
| Story Points | `customfield_10106` | số | | `8` |
| Original Estimate | `timetracking` | `{"originalEstimate": "1d 6h"}` (1d = 8h) | | |
| Management Systems | `customfield_10804` | mảng `[{"value": "DFWUS"}]` — FFM / LAB / MCUS / TC / BM / DFWUS | | |
| Assignee | `assignee` | `{"name": "<username>"}`; bỏ trống thì **Jira tự gán default assignee của project** (FAC → Tùng Phạm) | | |
| Labels | `labels` | mảng chuỗi | | |

Tra lại field khi Jira đổi cấu hình:

```bash
curl -s -H "Authorization: Bearer $JIRA_TOKEN" \
  "$JIRA_URL/rest/api/2/issue/createmeta?projectKeys=FAC&issuetypeNames=Task&expand=projects.issuetypes.fields"
```

Tra id sprint hiện tại (board FAC `rapidViewId = 4`):

```bash
curl -s -H "Authorization: Bearer $JIRA_TOKEN" \
  "$JIRA_URL/rest/agile/1.0/board/4/sprint?state=active" | python3 -m json.tool
```

## 3. Các bước

1. **Soạn nội dung** từng task (summary, description wiki markup, SP, estimate) — ví dụ `jira-tasks.md`.
2. **Tạo issue**: `POST /rest/api/2/issue` với body `{"fields": {...}}` → trả `{"key": "FAC-xxxxx"}`.
3. **Bỏ assignee** (nếu muốn Unassigned — vì bước 2 bị gán default): `PUT /rest/api/2/issue/<KEY>/assignee` body `{"name": null}` → 204.
4. **Link phụ thuộc** (tuỳ chọn): `POST /rest/api/2/issueLink` body
   `{"type": {"name": "Blocks"}, "inwardIssue": {"key": "<KEY chặn>"}, "outwardIssue": {"key": "<KEY bị chặn>"}}` → 201.
   Loại link khác: `GET /rest/api/2/issueLinkType` (Relates, Duplicate, Cloners…).
5. **Kiểm lại**: `GET /rest/api/2/issue/<KEY>?fields=summary,assignee,customfield_10102,customfield_10101,customfield_10106,timetracking,customfield_10804,issuelinks`.

Ví dụ body bước 2:

```json
{
  "fields": {
    "project": {"key": "FAC"},
    "issuetype": {"id": "10002"},
    "summary": "User Groups và ngưỡng Away",
    "description": "*Hợp đồng bắt buộc* ...",
    "priority": {"name": "Medium"},
    "customfield_10102": "FAC-26380",
    "customfield_10101": 1214,
    "customfield_10106": 8,
    "timetracking": {"originalEstimate": "1d"},
    "customfield_10804": [{"value": "DFWUS"}]
  }
}
```

## 4. Script

`create_jira_tasks.py` (cùng thư mục) đọc file JSON danh sách task và làm đủ bước 2–5. Mặc định chỉ in thử (dry run); thêm `--apply` mới gửi lên Jira.

```bash
python3 create_jira_tasks.py tasks.json            # dry run: in payload
python3 create_jira_tasks.py tasks.json --apply    # tạo thật
```

`tasks.json`:

```json
{
  "defaults": {
    "epic": "FAC-26380", "sprint": 1214, "priority": "Medium",
    "management_systems": ["DFWUS"], "unassigned": true
  },
  "tasks": [
    {"id": "t1", "summary": "User Groups và ngưỡng Away", "description_file": "desc/t1.txt", "sp": 8, "estimate": "1d"},
    {"id": "t2", "summary": "Phiên làm việc và auto-logout", "description_file": "desc/t2.txt", "sp": 18, "estimate": "2d 2h", "blocked_by": ["t1"]}
  ]
}
```

## 5. Lưu ý

- `description` là wiki markup của Jira Server, **không** phải Markdown (Markdown sẽ hiện nguyên ký tự `**`, `` ` ``).
- `Sprint` gửi **id số**, không gửi tên.
- Story Points / Original Estimate có thể bị ẩn trên màn hình nếu screen của project không có field — API vẫn nhận.
- Token có quyền như chính user tạo ra nó: issue được ghi reporter là user đó.
- Tạo xong nên kiểm lại assignee — project FAC luôn tự gán default assignee.
