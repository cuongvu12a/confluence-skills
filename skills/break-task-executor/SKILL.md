---
name: break-task-executor
version: 1.0.0
description: >-
  Thực thi tự động các task trong bảng Break Task của một plan (do confluence-research sinh ra):
  viết code qua subagent, review-tối-ưu lặp lại (chất lượng/hiệu suất/chức năng/impact),
  tách mỗi phía BE/FE thành một worktree với mỗi task một commit sạch để dev cherry-pick,
  và xuất test-plan cho phần thay đổi có impact.
  Triggers on: 'thực thi task', 'execute break task', 'chạy plan', 'code task backend',
  'code task frontend', 'thực thi plan', 'run break task', 'execute plan'.
  Requires: plan file (bảng Break Task + bảng Prompt); repo git erp và/hoặc erp-webapp sạch working tree.
---

# Break Task Executor Skill

Nhận đầu vào là **file plan** (output của skill `confluence-research`, chứa bảng Break Task `B*`/`F*` + bảng Prompt English) và **phạm vi thực thi**, sau đó:

1. **Thực thi code** từng task được chỉ định qua subagent, dùng chính prompt English trong plan làm brief
2. **Review + tối ưu lặp lại** mỗi task (chất lượng code, hiệu suất, chức năng) rồi impact toàn nhánh
3. **Tách worktree** mỗi phía BE/FE, **mỗi task một commit sạch** để dev so sánh và cherry-pick vào git gốc
4. **Xuất test-plan** cho phần thay đổi có impact

## Core Principles

- **Plan là source of truth cho việc cần làm** — cột "Prompt (English)" và "Diễn giải chi tiết" là brief giao cho subagent; không tự bịa scope ngoài plan
- **Thứ tự bắt buộc: toàn bộ Backend trước → contract request/response → Frontend** — FE task chỉ chạy sau khi contract BE đã chốt
- **Mỗi task = một commit sạch** — review-tối-ưu xong mới commit, để dev cherry-pick từng task hoặc một nhóm task liên quan
- **Không tự merge vào git gốc** — skill chỉ tạo worktree + commit; việc cherry-pick lên feature branch gốc để dev quyết định
- **Evidence-based review** — findings phải dẫn `file:line`; chỉ flag high/critical để lặp, còn lại report cho dev
- **Viết phân tích bằng tiếng Việt** — giữ tiếng Anh cho code, tên file/field, và nội dung prompt

## Skills phối hợp

Skill này **điều phối** (không tự viết code từng task). Nó dùng:
- `superpowers:subagent-driven-development` — pattern dispatch mỗi task cho một subagent implement
- `superpowers:dispatching-parallel-agents` — fan-out review nhiều góc song song
- `superpowers:receiving-code-review` — kỷ luật khi apply fix từ review
- `git-diff-review` — review correctness/perf/impact trên diff của task
- `branch-impact-review` — đánh giá coverage vs yêu cầu + impact toàn nhánh (cấp per-side)
- `test-plan` — sinh test-plan cuối cho phần impact

---

## Phase 0: Setup & Input Parsing

### 0.1 Nhận input từ user

Ba thông tin:

**Plan file** (mặc định tìm theo thứ tự nếu user không chỉ định):
- Đường dẫn user cung cấp
- `ai-plans/<branch>/confluence_research.md`
- File `.md` gần nhất trong `ai-plans/` có bảng Break Task

**Phạm vi** (bắt buộc): một trong `backend` | `frontend` | `both`

**Base branch** (tùy chọn): base để tạo worktree. Mặc định = HEAD hiện tại của mỗi repo.
- Backend base: HEAD của `erp/`
- Frontend base: HEAD của `erp-webapp/`

Nếu thiếu phạm vi → hỏi lại:
> "Bạn muốn thực thi phạm vi nào: `backend`, `frontend`, hay `both`?"

### 0.2 Resolve variables

```bash
ERP="/Users/cuongvu/workspace/merchize/maintain/erp"
WEBAPP="/Users/cuongvu/workspace/merchize/maintain/erp-webapp"
WORKTREE_ROOT="/Users/cuongvu/workspace/merchize/maintain/.worktrees"

TICKET="<extract từ tên plan file hoặc branch, ví dụ FAC-23965>"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

BE_BASE=$(git -C "$ERP" rev-parse --abbrev-ref HEAD)
FE_BASE=$(git -C "$WEBAPP" rev-parse --abbrev-ref HEAD)
```

### 0.3 Pre-flight checks

Trước khi chạm code, kiểm tra và **dừng nếu fail**:

```bash
# Working tree phải sạch (tránh trộn thay đổi đang dở của dev vào worktree base)
git -C "$ERP" status --porcelain
git -C "$WEBAPP" status --porcelain
```

- Working tree bẩn ở repo thuộc phạm vi → dừng, báo user commit/stash trước
- Plan file không tồn tại hoặc không parse được bảng Break Task → dừng, yêu cầu chỉ định đúng file
- Worktree/branch tên trùng đã tồn tại → hỏi user (reuse / xoá tạo mới / đổi tên)

### 0.4 Load memory-bank

Đọc nếu tồn tại (giao cho subagent implement làm context):
- `erp/.memory-bank/*.md`, `erp/AGENTS.md`, `erp/CLAUDE.md`
- `erp-webapp/.memory-bank/*.md`, `erp-webapp/AGENTS.md`, `erp-webapp/CLAUDE.md`

---

## Phase 1: Parse Plan → Task List

Đọc plan file, trích xuất **cả 2 bảng** và ghép theo task id:

Cho mỗi task lấy: `id` (B1/F1...), `hệ thống` (Backend/Frontend), `tên task`, `mô tả`, `diễn giải chi tiết` (acceptance criteria + edge case + dependencies), `prompt English`.

Ghi nhận **dependency** từ mô tả/diễn giải (ví dụ "Cần B1 xong trước", "Phụ thuộc B3 + B2").

### 1.1 Lọc theo phạm vi và sắp thứ tự

- `backend` → chỉ task `B*`
- `frontend` → chỉ task `F*`
- `both` → tất cả

**Thứ tự thực thi (bất biến):**
1. Toàn bộ task Backend, sắp topo theo dependency (task không phụ thuộc trước)
2. Contract handoff (Phase 4)
3. Toàn bộ task Frontend, sắp topo theo dependency

Nếu phạm vi = `frontend` mà plan có task BE liên quan **chưa** được thực thi trong repo → cảnh báo và hỏi:
> "Phạm vi frontend nhưng contract BE ([các task B*]) chưa chắc đã có trong `erp/`. Bạn muốn: (a) tôi rút contract từ spec API trong plan, hay (b) chỉ định branch BE đã có sẵn contract?"

### 1.2 Trình bày kế hoạch thực thi

Trước khi tạo worktree, in ra cho user xác nhận:
```
Phạm vi: <backend|frontend|both>
Backend (base: <BE_BASE>): B1 → B2 → B3 → B4
Frontend (base: <FE_BASE>): F1 → F2 → F3
Worktree: .worktrees/erp-<TICKET>-be, .worktrees/erp-webapp-<TICKET>-fe
Điều kiện dừng review mỗi task: hết finding high/critical hoặc tối đa 3 vòng.
```

---

## Phase 2: Prepare Worktrees

**Mỗi phía một branch + một worktree.** Base = HEAD hiện tại (hoặc base user chỉ định).

```bash
mkdir -p "$WORKTREE_ROOT"

# Backend (chỉ khi phạm vi gồm backend)
BE_BRANCH="${TICKET}-be-exec"
git -C "$ERP" worktree add -b "$BE_BRANCH" \
  "$WORKTREE_ROOT/erp-${TICKET}-be" "$BE_BASE"

# Frontend (tạo ở Phase 5, sau khi contract BE chốt — không tạo sớm)
```

Ghi lại đường dẫn worktree tuyệt đối để truyền cho subagent.

**Lưu ý:** không dùng `--detach`; cần branch thật để commit và cherry-pick. Worktree **không tự xoá** sau khi xong — để dev inspect/cherry-pick.

---

## Phase 3: Execute Backend Tasks

Lặp tuần tự từng task BE theo thứ tự dependency. Với **mỗi task**:

### 3.1 Implement (subagent)

Dispatch một subagent implement với brief:
- **Prompt English của task** (nguyên văn từ bảng Prompt) làm yêu cầu chính
- Working directory = **worktree path** (`$WORKTREE_ROOT/erp-${TICKET}-be`) — subagent chỉ được sửa file trong worktree này
- Context: memory-bank đã đọc; output của các task phụ thuộc đã hoàn thành trước đó (đã có trong worktree vì commit tuần tự cùng branch)
- Yêu cầu subagent: chỉ implement scope của task này, không đụng scope task khác; không commit (main agent commit)

### 3.2 Review + tối ưu (lặp, tối đa 3 vòng)

Trên **diff của task** (`git -C <worktree> diff` so với commit trước / base), lặp cho đến khi **hết finding high/critical** hoặc **đủ 3 vòng**:

1. **Fan-out review song song** (`dispatching-parallel-agents`):
   - **Code quality** — clean code, convention repo, đúng pattern (dùng góc nhìn `git-diff-review`)
   - **Performance** — N+1 query, unbounded query, thiếu index, vòng lặp tốn kém
   - **Functionality** — đối chiếu diff với acceptance criteria + edge case trong cột "Diễn giải chi tiết" của task
2. **Gộp findings**, xếp theo severity.
3. Còn **high/critical** → apply fix (kỷ luật `receiving-code-review`: verify từng finding trước khi sửa, không sửa mù) → **re-review** (vòng tiếp).
4. Hết high/critical hoặc đủ 3 vòng → dừng. Nếu sau 3 vòng vẫn còn → **ghi residual findings vào report**, không tiếp tục lặp.

### 3.3 Commit một task = một commit sạch

Sau khi review pass, commit toàn bộ thay đổi của task thành **đúng một commit**:

```bash
git -C "$WORKTREE_ROOT/erp-${TICKET}-be" add -A
git -C "$WORKTREE_ROOT/erp-${TICKET}-be" commit -m "[<TASK_ID>] <tên task> (<TICKET>)

<mô tả ngắn scope task>
Skill: break-task-executor"
```

Ghi lại commit hash + task id vào bảng mapping (dùng ở Phase 7).

### 3.4 Sau khi xong toàn bộ BE — impact review cấp nhánh

Dùng `branch-impact-review` trên toàn nhánh BE (`$BE_BRANCH` vs `$BE_BASE`):
- Coverage: đã đủ các yêu cầu BE trong plan chưa
- Impact: ảnh hưởng tính năng/module khác đang chạy
- Performance: vấn đề ở quy mô production

Finding high/critical → apply fix, commit fix (gắn vào task tương ứng nếu rõ ràng, hoặc commit `[BE][impact-fix]` riêng). Ghi report.

---

## Phase 4: BE → FE Contract Handoff

**Chỉ chạy khi phạm vi gồm frontend.** Sinh artifact contract để làm tiền đề cho FE.

Rút từ diff BE (hoặc từ spec API trong plan nếu BE không thực thi ở đây):
- Endpoint mới/đổi: method + path
- Request shape (query/body/params) + validation
- Response shape (fields, kiểu, pagination meta như `alertCount`...)
- Breaking change với API cũ (nếu có)

Ghi vào `ai-plans/<branch>/be-fe-contract.md`. Nội dung này được **inject vào brief của từng subagent implement FE** ở Phase 5.

---

## Phase 5: Execute Frontend Tasks

Tạo worktree FE (giờ mới tạo, để base FE phản ánh đúng thời điểm bắt đầu FE):

```bash
FE_BRANCH="${TICKET}-fe-exec"
git -C "$WEBAPP" worktree add -b "$FE_BRANCH" \
  "$WORKTREE_ROOT/erp-webapp-${TICKET}-fe" "$FE_BASE"
```

Lặp từng task FE **giống Phase 3** (implement → review 3.2 → commit 3.3), với khác biệt:
- Working directory = worktree `erp-webapp`
- Brief mỗi task **kèm `be-fe-contract.md`** làm prerequisite context
- Functionality review đối chiếu thêm với contract (gọi đúng endpoint, đúng request/response shape)

Sau khi xong toàn bộ FE → `branch-impact-review` cấp nhánh FE (giống 3.4).

---

## Phase 6: Test Plan cho phần Impact

Gọi skill `test-plan` để sinh test-plan cho **phần thay đổi có impact**:
- Chạy trên diff của worktree BE và/hoặc FE so với base (không phải master của repo, mà base đã dùng để tạo worktree)
- Output: `ai-plans/<branch>/test_plan.md`
- Ưu tiên cover: các endpoint/màn hình đã đổi, edge case từ "Diễn giải chi tiết", và các điểm impact mà `branch-impact-review` nêu ở 3.4/Phase 5

Nếu phạm vi `both`, test-plan cover cả luồng BE↔FE end-to-end theo contract.

---

## Phase 7: Handoff Summary (cho dev cherry-pick)

In ra tóm tắt cuối để dev thao tác git gốc:

```markdown
## Kết quả thực thi — <TICKET>

### Backend — branch `<BE_BRANCH>` @ worktree `.worktrees/erp-<TICKET>-be`
| Task | Commit | Tóm tắt |
|------|--------|---------|
| B1 | <hash> | ... |
| B2 | <hash> | ... |

### Frontend — branch `<FE_BRANCH>` @ worktree `.worktrees/erp-webapp-<TICKET>-fe`
| Task | Commit | Tóm tắt |
| F1 | <hash> | ... |

### Cách đưa vào git gốc
- Cherry-pick một task:      `git cherry-pick <hash>`
- Cherry-pick nhóm liên quan: `git cherry-pick <hash_from>^..<hash_to>`
- Xem diff một task:          `git show <hash>`

### Artifacts
- Contract BE↔FE: ai-plans/<branch>/be-fe-contract.md
- Test plan:       ai-plans/<branch>/test_plan.md
- Review report:   ai-plans/<branch>/execution_report.md

### Dọn worktree khi xong
git -C erp worktree remove .worktrees/erp-<TICKET>-be
git -C erp-webapp worktree remove .worktrees/erp-webapp-<TICKET>-fe
```

Ghi report chi tiết (findings mỗi vòng, residual sau 3 vòng, impact) vào `ai-plans/<branch>/execution_report.md`.

---

## Quality Checklist

Trước khi kết thúc, kiểm tra:

✅ Pre-flight: working tree sạch, plan parse được, không trùng worktree
✅ Thứ tự đúng: toàn bộ BE → contract → FE (không xen kẽ)
✅ Mỗi task đúng **một commit sạch**, message có task id + ticket
✅ Mỗi task đã qua review 3 góc (quality/perf/functional) và lặp đến khi hết high/critical hoặc 3 vòng
✅ Impact review cấp nhánh đã chạy cho mỗi phía đã thực thi
✅ Contract BE↔FE đã sinh (khi phạm vi gồm frontend)
✅ Test-plan đã sinh cho phần impact
✅ Handoff summary có mapping task→commit + lệnh cherry-pick
✅ Worktree **không** bị auto-merge/auto-xoá; để dev inspect
✅ Report residual findings (nếu còn sau 3 vòng) đã ghi rõ

## What NOT to Do

❌ Thực thi FE trước khi BE + contract xong (phá thứ tự bất biến)
❌ Gộp nhiều task vào một commit, hoặc để một task rải nhiều commit lộn xộn → dev không cherry-pick sạch được
❌ Tự merge/rebase/push worktree lên feature branch gốc hoặc remote — chỉ dev làm
❌ Sửa code ngoài worktree (đụng thẳng vào repo base)
❌ Apply fix mù theo review mà không verify (bỏ kỷ luật receiving-code-review)
❌ Lặp review vô hạn — tối đa 3 vòng rồi report residual
❌ Chạy khi working tree bẩn (trộn thay đổi dở của dev vào base worktree)
❌ Bịa scope ngoài plan; bỏ qua acceptance criteria trong "Diễn giải chi tiết"
❌ Bỏ qua memory-bank khi đã có file `.memory-bank/`

---
*break-task-executor v1.0.0 — tiêu thụ output của confluence-research, xuất worktree + test-plan*
