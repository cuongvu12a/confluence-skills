---
name: jira-task-creator
version: 1.0.0
description: >-
  Tạo task Jira (team/project FAC) hàng loạt từ bảng Break Task do skill
  confluence-research sinh ra.
  Triggers on: 'tạo task jira', 'tạo jira từ plan', 'push break task lên jira',
  'create jira tasks'.
  Requires: JIRA_URL, JIRA_TOKEN env var; file plan có bảng "Bảng Break Task".
---

# Jira Task Creator

Chuyển **Bảng Break Task** (cột: `#`, `Tên Task`, `Estimate`, `Độ khó`, `Mô tả`) từ một research plan (`ai-plans/**/confluence_research.md` hoặc tương đương) thành task thật trên Jira, team **FAC** (team không đổi, luôn dùng FAC bất kể module/tenant nào — kể cả LAB, FFM...).

Xem thêm `jira-create-guide.md` (cùng thư mục với repo này) để biết chi tiết field Jira và cách tra lại field id/sprint khi Jira đổi cấu hình.

Script dùng: `/Users/cuongvu/workspace/merchize/maintain/confluence-skills/create_jira_tasks.py` (đường dẫn này được `install.sh` tự thay bằng path thực tế trên máy bạn, không cần sửa tay).

## Quy tắc chuyển đổi (đã chốt với user — không tự suy diễn khác)

| Bảng Break Task | Jira field | Quy tắc |
|---|---|---|
| Tên Task | `summary` | Giữ nguyên nguyên văn (kể cả tiền tố `[BE+FE]`/`[BE]`/`[FE]`/`🔶`/`[T1]`). Không bỏ, không viết lại. |
| Estimate (`10.5h`) | `timetracking.originalEstimate` + `customfield_10106` (Story Points) | **Làm tròn lên** số nguyên giờ (`math.ceil`), dùng **cùng con số đó** làm cả Estimate (`Nh`) và Story Points. Độ khó (1–10) **không** dùng để tính SP. |
| Mô tả | `description` | Chuyển sang Jira wiki markup (`*bold*` thay cho `**bold**`, v.v.) nhưng **giữ nguyên câu "Cần T1, T2..."** y như trong bảng — đây là ghi chú phụ thuộc, không phải issueLink. |
| "Cần T1, T2" | — | **Không** gọi `issueLink`/Blocks. Chỉ là text trong description. |
| Management Systems | `customfield_10804` | Giá trị hợp lệ: `None`, `FFM`, `LAB`, `BM`, `DFWUS`. **Bắt buộc hỏi user xác nhận giá trị trước mỗi lần chốt `--apply`** — không suy ra từ nội dung plan, kể cả khi có vẻ rõ ràng là LAB. |
| Epic Link | `customfield_10102` | User **tự gửi link/key epic** mỗi lần — không tự tạo epic mới, không đoán epic từ plan. Nếu user chưa gửi, phải hỏi trước khi build tasks.json. |
| Assignee | `assignee` | Mặc định = chính người tạo (chủ sở hữu `JIRA_TOKEN`, script tự lấy qua `/rest/api/2/myself`). Không bỏ trống/Unassigned trừ khi user nói khác. |
| Sprint | `customfield_10101` | Không hỏi — script tự lấy sprint **active** của board FAC (`board_id=4`) tại thời điểm chạy. |
| Project | `project` | Luôn `FAC` — team cố định, không hỏi lại. |

## Các bước

1. **Đọc bảng Break Task** từ file plan user chỉ định (hoặc hỏi đường dẫn nếu chưa rõ).
2. **Hỏi user** (nếu chưa có trong message): Epic Link, giá trị Management Systems áp dụng cho batch này.
3. **Build `tasks.json`** (lưu vào scratchpad, không commit) theo schema:
   ```json
   {
     "defaults": {"epic": "FAC-xxxxx", "management_systems": ["LAB"], "board_id": 4},
     "tasks": [
       {"id": "T1", "summary": "...", "estimate_hours": 11, "description": "..."}
     ]
   }
   ```
   `estimate_hours` = số giờ gốc trong bảng (chưa làm tròn — script tự `ceil`).
4. **Chạy dry-run trước, luôn luôn**:
   ```bash
   python3 /Users/cuongvu/workspace/merchize/maintain/confluence-skills/create_jira_tasks.py <tasks.json>
   ```
   In ra: project, assignee mặc định, sprint active, epic, management systems, rồi từng task với Estimate/SP đã làm tròn + preview mô tả, và tổng cuối bảng.
5. **Đưa output dry-run cho user xem nguyên văn**, hỏi xác nhận rõ ràng (đặc biệt giá trị Management Systems) trước khi tạo thật. Đây là hành động visible tới cả team (issue hiện trên board FAC) — không tự ý `--apply`.
6. Sau khi user xác nhận, chạy lại với `--apply`:
   ```bash
   python3 /Users/cuongvu/workspace/merchize/maintain/confluence-skills/create_jira_tasks.py <tasks.json> --apply
   ```
   Script in ra từng key vừa tạo (`FAC-xxxxx`) và lưu `*_created.json` cạnh file tasks.json để tra cứu/đối chiếu sau.
7. Báo lại cho user danh sách Txx → FAC-key vừa tạo.

## Khi nào dừng hỏi lại user

- Chưa có Epic Link.
- Chưa xác nhận Management Systems cho batch này (luôn hỏi lại mỗi lần, kể cả nếu plan trước dùng LAB).
- Token lỗi/hết hạn (`/rest/api/2/myself` trả lỗi) → báo user tạo PAT mới theo `jira-create-guide.md` mục 1.

## What NOT to Do

❌ Tự đoán Management Systems từ nội dung plan thay vì hỏi user.
❌ Tạo `issueLink` Blocks cho các dòng "Cần Txx".
❌ Để Unassigned — mặc định luôn là người tạo (token owner).
❌ Gọi `--apply` khi chưa cho user xem dry-run và chưa được xác nhận.
❌ Hardcode sprint id cũ — luôn để script tự fetch sprint active.
❌ Hỏi lại project/team — luôn là FAC.
