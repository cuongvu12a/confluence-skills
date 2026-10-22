---
name: confluence-research
version: 1.0.0
description: >-
  Đọc tài liệu Confluence (nội bộ Merchize) + phân tích code erp/erp-webapp,
  sinh bảng break task và bảng prompt gợi ý cho từng task.
  Triggers on: 'đọc confluence', 'confluence research', 'nghiên cứu yêu cầu',
  'phân tích tài liệu', 'read confluence', 'doc research'.
  Requires: CONFLUENCE_PAT env var, Confluence page URL or ID.
---

# Confluence Research Skill

Đọc tài liệu Confluence + đối chiếu code hiện tại (erp backend + erp-webapp frontend), sau đó sinh ra:
1. Danh sách câu hỏi để dev confirm với BA/PO
2. Bảng break task (backend / frontend)
3. Bảng prompt gợi ý cho từng task (tiếng Anh, role solution architect)

## Core Principles

- **Tài liệu Confluence + code là source of truth** — Không tự suy diễn nếu thiếu thông tin
- **Hỏi khi không rõ** — Nếu docs mơ hồ hoặc không tìm thấy phần tương ứng trong code, hỏi lại trước khi tiếp tục
- **Viết bằng tiếng Việt** — Mọi phân tích đều tiếng Việt; chỉ giữ tiếng Anh cho: code identifiers, tên field, file paths, và nội dung prompt trong bảng Prompt
- **Tất cả prompt sinh ra đều là tiếng Anh** với role "senior solution architect", response phân tích bằng tiếng Việt

---

## Phase 0: Setup & Context Loading

### 0.1 Resolve variables
```bash
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "no-git")
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
```

### 0.2 Load project memory-bank

Kiểm tra từng path sau và đọc nếu tồn tại. Báo cáo kết quả:

**erp (backend)**:
- `erp/.memory-bank/brief.md`
- `erp/.memory-bank/product.md`
- `erp/.memory-bank/architecture.md`
- `erp/.memory-bank/tech.md`
- `erp/AGENTS.md`
- `erp/CLAUDE.md`

**erp-webapp (frontend)**:
- `erp-webapp/.memory-bank/brief.md`
- `erp-webapp/.memory-bank/product.md`
- `erp-webapp/.memory-bank/architecture.md`
- `erp-webapp/.memory-bank/tech.md`
- `erp-webapp/AGENTS.md`
- `erp-webapp/CLAUDE.md`

Ghi vào header của output:
```
[Memory Bank: erp ✓/✗ | erp-webapp ✓/✗]
```

### 0.3 Verify Confluence access

Kiểm tra `CONFLUENCE_PAT` env var:
```bash
echo ${CONFLUENCE_PAT:0:8}...  # show first 8 chars only
```

Nếu không có PAT → dừng và yêu cầu user cung cấp:
> "Cần thiết lập `CONFLUENCE_PAT` trong env. Chạy: `export CONFLUENCE_PAT=<your-token>`"

---

## Phase 1: Fetch Confluence Document

### 1.1 Nhận input từ user

User cung cấp một trong:
- Full URL: `https://confluence.mymerchize.com/pages/viewpage.action?pageId=142541322`
- Page ID: `142541322`
- CQL search: `"title ~ \"tên tính năng\""`

### 1.2 Fetch nội dung trang

**Ưu tiên 1 — dùng Python tool** (output markdown sạch hơn):
```bash
CONFLUENCE_TOOL="/Users/cuongvu/workspace/merchize/maintain/tools/confluence_fetch.py"
python3 "$CONFLUENCE_TOOL" \
  --url "<URL hoặc --page-id ID>" \
  --token "$CONFLUENCE_PAT" \
  --children \
  --output /tmp/confluence_page.md

cat /tmp/confluence_page.md
```

**Ưu tiên 2 — dùng curl trực tiếp** (fallback nếu Python không available):
```bash
PAGE_ID="<extracted_page_id>"
BASE_URL="https://confluence.mymerchize.com"

curl -s -H "Authorization: Bearer $CONFLUENCE_PAT" \
  "$BASE_URL/rest/api/content/$PAGE_ID?expand=body.storage,ancestors,version,children.page" \
  | python3 -c "
import json,sys,re
d=json.load(sys.stdin)
title=d.get('title','')
body=d.get('body',{}).get('storage',{}).get('value','')
body=re.sub(r'<[^>]+>',' ',body)
print(f'# {title}\n\n{body}')
"
```

**Ưu tiên 3 — dùng WebFetch** nếu tool hỗ trợ custom headers:
Fetch URL: `https://confluence.mymerchize.com/rest/api/content/<PAGE_ID>?expand=body.storage`

### 1.3 Nếu fetch thất bại

Hỏi user:
> "Không thể fetch trang Confluence. Bạn có thể:
> 1. Copy-paste nội dung trang vào đây
> 2. Kiểm tra lại CONFLUENCE_PAT còn hiệu lực không
> 3. Thử với page ID khác"

### 1.4 Fetch child pages (nếu có)

Nếu trang có child pages (danh sách thấy trong output bước 1.2), hỏi user:
> "Trang này có [N] child pages. Bạn muốn tôi đọc thêm không?
> - [Danh sách tên + ID các child pages]"

---

## Phase 2: Parse & Understand Requirements

Đọc kỹ nội dung Confluence và trích xuất:

### 2.1 Thông tin cơ bản
- **Tên tính năng / yêu cầu**
- **Mục tiêu nghiệp vụ**
- **Đối tượng người dùng** (factory nào, role nào)
- **Luồng nghiệp vụ chính** (user story / flow)
- **Điều kiện tiền đề** (preconditions)
- **Tiêu chí chấp nhận** (acceptance criteria)

### 2.2 Chi tiết kỹ thuật (nếu có)
- API endpoints được đề cập
- UI screens / components được đề cập
- Data fields / entities được đề cập
- Tích hợp bên ngoài

### 2.3 Kiểm tra tính đầy đủ

Trước khi tiếp tục Phase 3, xác nhận đã hiểu:
- [ ] Mục tiêu nghiệp vụ rõ ràng
- [ ] Luồng chính được mô tả
- [ ] Scope backend / frontend phân biệt được

Nếu bất kỳ mục nào chưa rõ → ghi vào danh sách **GAP** để xử lý ở Phase 4.

---

## Phase 3: Code Research

Đối chiếu yêu cầu từ tài liệu với code hiện tại.

### 3.1 Backend research (erp/)

Tìm kiếm trong `erp/src/`:
```bash
# Tìm theo tên entity / domain
grep -r "<keyword từ docs>" erp/src/ --include="*.ts" -l

# Tìm controllers liên quan
find erp/src -name "*.controller.ts" | xargs grep -l "<keyword>" 2>/dev/null

# Tìm services liên quan
find erp/src -name "*.service.ts" | xargs grep -l "<keyword>" 2>/dev/null

# Tìm DTOs / schemas
find erp/src -name "*.dto.ts" -o -name "*.schema.ts" | xargs grep -l "<keyword>" 2>/dev/null
```

Ghi nhận:
- File controllers tương ứng
- Service methods liên quan
- Database schemas / entities
- API routes hiện có

### 3.2 Frontend research (erp-webapp/)

Tìm kiếm trong `erp-webapp/src/`:
```bash
# Tìm pages / components liên quan
grep -r "<keyword từ docs>" erp-webapp/src/ --include="*.tsx" --include="*.ts" -l

# Tìm routes
grep -r "<keyword>" erp-webapp/src/configs/ erp-webapp/src/routes/ 2>/dev/null -l

# Tìm API services
grep -r "<keyword>" erp-webapp/src/services/ -l 2>/dev/null

# Tìm query hooks
grep -r "<keyword>" erp-webapp/src/hooks/ -l 2>/dev/null
```

Ghi nhận:
- Pages / components tương ứng
- Route paths
- API service methods được dùng
- Query hooks hiện có

### 3.3 Ghi nhận kết quả research

Với mỗi phần trong tài liệu, ghi rõ:
```
Yêu cầu: [mô tả từ docs]
→ Backend: [file:line hoặc "Chưa có / Cần tạo mới"]
→ Frontend: [file:line hoặc "Chưa có / Cần tạo mới"]
→ Trạng thái: ✅ Đã có | 🔧 Cần sửa | ➕ Cần tạo mới
```

### 3.4 Đánh dấu điểm không rõ

Nếu gặp trường hợp:
- Tài liệu đề cập một tính năng nhưng không rõ tương ứng code nào
- Tìm được nhiều file có thể match, không chắc cái nào đúng
- Tài liệu dùng từ khác với code (terminology mismatch)

→ Ghi vào **GAP list** kèm câu hỏi cụ thể để hỏi lại.

---

## Phase 4: Interactive Clarification

**QUAN TRỌNG**: Không bỏ qua phase này nếu có gaps.

### 4.1 Trình bày findings

Trước khi tiếp tục, trình bày với developer:

```markdown
## Những điểm cần xác nhận trước khi lên kế hoạch

### 🔍 Không tìm thấy phần tương ứng trong code
[Danh sách các phần tài liệu không map được vào code]

### ❓ Tài liệu chưa rõ ràng
[Danh sách các điểm mơ hồ]

### ⚠️ Có thể ảnh hưởng tính năng hiện tại
[Danh sách các thay đổi có risk]
```

### 4.2 Hỏi từng vấn đề

Hỏi tối đa 3-4 câu mỗi lần. Ví dụ:

> **[1]** Tài liệu đề cập "màn hình quản lý X" — bạn có thể xác nhận đây là trang `/admin/x` trong frontend không, hay là trang khác?
>
> **[2]** Yêu cầu nói "cập nhật trạng thái Y" — trong code hiện tại, trạng thái Y được lưu ở `OrderStatus` enum. Tài liệu có nghĩa là thêm giá trị mới vào enum này không?

### 4.3 Exit condition

- Sau khi developer trả lời → cập nhật findings và tiếp tục Phase 5
- Nếu sau 2 vòng hỏi vẫn còn vấn đề chưa giải quyết → tiếp tục với `[GIẢ ĐỊNH — chờ xác nhận]` và ghi rõ assumption

---

## Phase 5: BA Confirmation Questions

Tổng hợp danh sách câu hỏi để developer/tech lead confirm với BA/PO.

Format:
```markdown
## Danh sách câu hỏi để confirm với BA/PO

| # | Câu hỏi (không dùng thuật ngữ kỹ thuật) | Lý do cần hỏi | Gợi ý trả lời |
|---|----------------------------------------|--------------|----------------|
| 1 | ... | ... | Option A / Option B (Ưu tiên: ...) |
| 2 | ... | ... | ... |
```

Nguyên tắc viết câu hỏi:
- Dùng ngôn ngữ nghiệp vụ (không dùng "schema", "enum", "middleware", "hook")
- Mỗi câu hỏi phải đủ để BA/PO hiểu và trả lời mà không cần biết code
- Đề xuất 2-3 lựa chọn trả lời và đánh dấu ưu tiên

---

## Phase 6: Task Breakdown Table

Sinh bảng break task dựa trên phân tích ở Phase 3.

### Nguyên tắc tách task theo module

**Ưu tiên nhóm theo tính năng / module**, không tách theo từng API hay từng file:

| ❌ Quá nhỏ (tránh) | ✅ Đúng mức |
|--------------------|------------|
| `[BE] API tạo đơn hàng` — 2h | `[BE] CRUD quản lý đơn hàng` — 6h |
| `[BE] API cập nhật đơn hàng` — 2h | (gộp create/update/detail/list vào 1 task) |
| `[BE] API lấy chi tiết đơn hàng` — 2h | |
| `[FE] Component filter trạng thái` — 1h | `[FE] Trang danh sách đơn hàng` — 6h |
| `[FE] Component bảng danh sách` — 2h | (gộp filter, bảng, phân trang vào 1 task) |

**Ngưỡng estimate hợp lý cho 1 task: 4h – 16h.** Ngoài khoảng này:
- Dưới 4h → xem xét gộp với task liên quan cùng module
- Trên 16h → tách thành 2 task độc lập theo ranh giới tự nhiên (ví dụ: data layer / API layer)

Các nguyên tắc khác:
- Backend và Frontend luôn tách riêng thành 2 bảng
- Sắp xếp theo thứ tự dependency (task A phải xong trước task B)
- Mỗi task phải có output kiểm chứng được (API có thể test, UI có thể demo)

### Quy tắc đặt tên task

- Backend: tiền tố **`[BE]`** — ví dụ: `[BE] CRUD quản lý đơn hàng`
- Frontend: tiền tố **`[FE]`** — ví dụ: `[FE] Trang danh sách và chi tiết đơn hàng`
- Tên task phải đủ rõ khi đọc một mình, không cần đọc mô tả

### Quy tắc viết cột Mô tả (ngắn gọn, ngôn ngữ nghiệp vụ)

Cột **Mô tả** trong bảng break task ghi **ý chính** để người đọc — kể cả người không biết code — nắm được việc phải làm và những điểm cần chú ý:

**Ngôn ngữ**:
- Ưu tiên ngôn ngữ nghiệp vụ, không dùng thuật ngữ kỹ thuật
- Chỉ dùng thuật ngữ tech (tên module, tên service) khi nó phổ biến trong team **và** giúp câu ngắn hơn so với diễn đạt thông thường. Không list method names, tên file, tên function
- Mục tiêu: dev đọc hiểu ngay; BA/PO đọc cũng hiểu phạm vi

**Nội dung bắt buộc**:
- Phạm vi công việc (làm gì, cho module nào)
- **Ảnh hưởng trong module đang làm** — task này mở ra / làm tiền đề cho phần nào của tính năng
- **Ảnh hưởng đến module khác đang chạy** — nếu task này chạm vào code/data đang dùng ở chỗ khác, ghi rõ; nếu không ảnh hưởng, ghi "Không ảnh hưởng module hiện có"
- Điểm phụ thuộc quan trọng (cần task nào xong trước, cần ai ngoài dev như DevOps/PO)

**Không ghi vào đây**:
- Chi tiết từng bước thực hiện → để ở cột "Diễn giải chi tiết" trong bảng Prompt (Phase 7)
- Tên file, tên function, tên class cụ thể → để ở bảng Prompt

**Độ dài**: 2–4 câu ngắn.

Ví dụ mô tả tốt:
> Mở rộng tích hợp Google Sheets để hỗ trợ ghi dữ liệu (hiện chỉ đọc được). Tiền đề cho B2 và B3. Cần DevOps cấp thêm quyền ghi cho tài khoản dịch vụ. Không ảnh hưởng các tính năng đang dùng Google Sheets hiện tại (chỉ thêm mới, không sửa code cũ).

Ví dụ mô tả **sai** (ngôn ngữ tech thừa, thiếu thông tin ảnh hưởng):
> ~~Thêm write methods vào `GoogleSheetsService`: `writeValues`, `clearTab`, `ensureTabExists`, `applyFormatting`. Thêm 3 `ConfigKey` mới. DevOps cấp thêm scope `spreadsheets`.~~

### Format bảng

```markdown
## Bảng Break Task

### Backend (erp)

| # | Tên Task | Estimate | Mô tả |
|---|----------|----------|-------|
| B1 | [BE] [Tên module/tính năng] | [Xh] | [Phạm vi tổng quát. Liên kết task khác. Lưu ý chính.] |
| B2 | [BE] ... | ... | ... |

**Tổng estimate Backend**: Xh

### Frontend (erp-webapp)

| # | Tên Task | Estimate | Mô tả |
|---|----------|----------|-------|
| F1 | [FE] [Tên trang/tính năng] | [Xh] | [Phạm vi tổng quát. Liên kết task khác. Lưu ý chính.] |
| F2 | [FE] ... | ... | ... |

**Tổng estimate Frontend**: Xh

### Tổng cộng: ~Xd (Backend: Xh | Frontend: Xh)
```

### Estimate guidelines

| Loại công việc | Estimate gợi ý |
|----------------|----------------|
| CRUD module đơn giản (4 API) | 4–6h |
| CRUD module phức tạp (business logic, validation) | 6–10h |
| Module tích hợp bên ngoài / webhook | 8–12h |
| Trang UI đơn giản (list + filter) | 4–6h |
| Trang UI phức tạp (form nhiều bước, logic nghiệp vụ) | 8–12h |
| Trang UI có chart / report | 6–10h |
| Database schema + migration (cho 1 module) | 2–4h |
| Cấu hình / setup module mới (không có UI) | 2–4h |

---

## Phase 7: Prompt Table

Bảng này mở rộng bảng break task với 2 cột bổ sung. Đây là nơi tập trung **tất cả thông tin kỹ thuật** — những gì cố ý không ghi ở cột Mô tả của Phase 6:
- **Diễn giải chi tiết** — liệt kê đầy đủ công việc con, tên file/class/API, acceptance criteria, edge case, dependencies cụ thể
- **Prompt (English)** — prompt tiếng Anh dùng để giao task cho AI agent, bao gồm đủ context kỹ thuật để agent không cần hỏi lại

### Quy tắc viết cột Diễn giải chi tiết

Đây là phần **khai triển chi tiết** của cột Mô tả. Viết bằng tiếng Việt, có thể dùng danh sách gạch đầu dòng:
- Liệt kê đủ các công việc con bên trong task (API nào, entity nào, component nào...)
- Ghi rõ acceptance criteria cụ thể (điều kiện nào thì task được coi là done)
- Nêu edge case và cách xử lý kỳ vọng
- Ghi dependencies cụ thể (task nào, field nào, API nào cần sẵn trước)

### Format bảng

```markdown
## Bảng Prompt Gợi Ý

| Task | Hệ thống | Diễn giải chi tiết | Prompt (English) |
|------|----------|--------------------|-----------------|
| B1: [BE] [Tên task] | Backend | [Chi tiết công việc + acceptance criteria + edge case + dependencies] | [Full prompt in English] |
| F1: [FE] [Tên task] | Frontend | [Chi tiết công việc + acceptance criteria + edge case + dependencies] | [Full prompt in English] |
```

### Template prompt cho từng loại task

**Backend — API endpoint mới:**
```
As a senior solution architect with 10+ years of ERP system experience,
analyze the [feature name] requirement for the Merchize ERP backend (NestJS/TypeORM).

Context:
- Codebase: erp/src/
- Related existing code: [file paths]
- Requirement: [1-2 sentence summary]

Goal: Implement [specific goal].

Please provide:
1. The exact files to create or modify (with file paths)
2. Controller, Service, DTO, and Entity changes
3. Any database migration needed
4. Validation rules and error handling
5. Code examples for the key changes

Respond with analysis in Vietnamese, code in English.
```

**Frontend — UI component/page:**
```
As a senior solution architect with 10+ years of ERP system experience,
design the implementation for [feature name] in the Merchize ERP frontend (React/TypeScript).

Context:
- Codebase: erp-webapp/src/
- Related existing pages/components: [file paths]
- API endpoint: [endpoint if known]
- Requirement: [1-2 sentence summary]

Goal: [specific UI goal].

Please provide:
1. Component structure and file locations
2. TanStack Query hooks needed
3. Form schema (Zod) if applicable
4. State management approach
5. i18n keys to add (Vietnamese + English)
6. Feature flag considerations (factory-specific behavior)

Respond with analysis in Vietnamese, code in English.
```

**Chung — Backend + Frontend cùng một tính năng:**
```
As a senior solution architect with 10+ years of ERP system experience,
provide an end-to-end implementation plan for [feature name] in the Merchize ERP system.

Context:
- Backend: NestJS + TypeORM (erp/)
- Frontend: React + TypeScript + TanStack Query (erp-webapp/)
- Related existing code: [file paths]
- Requirement: [full requirement summary]

Goal: [goal].

Please provide:
1. Backend changes (API design, service logic, DB schema)
2. Frontend changes (pages, components, hooks)
3. Data flow diagram (Backend ↔ Frontend)
4. Integration points and API contract
5. Implementation order (what to build first)

Respond with analysis in Vietnamese, code in English.
```

---

## Phase 8: Synthesize & Write Output

### 8.1 Tạo output file

```bash
mkdir -p ai-plans/$BRANCH
OUTPUT_FILE="ai-plans/$BRANCH/confluence_research.md"
```

### 8.2 Cấu trúc file output

```markdown
# Confluence Research: [Tên tính năng]

[Memory Bank: erp ✓/✗ | erp-webapp ✓/✗]
Generated: {TIMESTAMP} | Branch: {BRANCH} | Skill: confluence-research v{VERSION}
Confluence: {PAGE_URL}

---

## Tóm tắt yêu cầu

[2-3 câu tóm tắt ngắn gọn mục tiêu và scope]

## Nội dung tài liệu gốc (Confluence)

[Nội dung đã fetch, giữ nguyên bố cục]

## Đối chiếu với code hiện tại

[Kết quả research Phase 3 — mapping requirement → code]

## Danh sách câu hỏi confirm với BA/PO

[Bảng từ Phase 5]

## Bảng Break Task

[Bảng từ Phase 6]

## Bảng Prompt Gợi Ý

[Bảng từ Phase 7]

---
*Generated by confluence-research skill v{VERSION} | {AGENT_NAME} {MODEL_NAME}*
```

### 8.3 Thông báo hoàn thành

Sau khi write file:
> "Đã lưu kết quả phân tích vào `{OUTPUT_FILE}`.
> - [N] câu hỏi cần confirm với BA/PO
> - [N] task backend | [N] task frontend
> - Tổng estimate: ~X ngày"

---

## Quality Checklist

Trước khi finalize, kiểm tra:

✅ Memory bank của cả 2 projects đã được đọc  
✅ Nội dung Confluence đã được fetch đầy đủ (kể cả child pages nếu cần)  
✅ Mọi điểm không rõ đã được hỏi ở Phase 4 trước khi tiếp tục  
✅ Câu hỏi BA/PO viết bằng ngôn ngữ nghiệp vụ (không dùng thuật ngữ kỹ thuật)  
✅ Task backend dùng tiền tố `[BE]`, frontend dùng `[FE]`  
✅ Task được nhóm theo module/tính năng, không tách từng API riêng lẻ  
✅ Estimate mỗi task nằm trong khoảng 4h–16h  
✅ Cột Mô tả viết bằng ngôn ngữ nghiệp vụ (không dùng tên file/method/class), đủ 4 ý: phạm vi + ảnh hưởng trong module + ảnh hưởng module khác + phụ thuộc  
✅ Cột Diễn giải chi tiết trong bảng Prompt đủ acceptance criteria + edge case  
✅ Task backend và frontend tách riêng, có estimate  
✅ Mỗi task trong bảng Prompt có prompt tiếng Anh đầy đủ  
✅ Tất cả prompt bắt đầu bằng role "senior solution architect"  
✅ Phân tích viết bằng tiếng Việt, prompt viết bằng tiếng Anh  
✅ Output file đã được lưu vào `ai-plans/$BRANCH/confluence_research.md`  

## What NOT to Do

❌ Bỏ qua Phase 4 khi có gaps — luôn hỏi trước khi lên kế hoạch  
❌ Để task quá to (> 2 ngày) — phải tách nhỏ hơn  
❌ Viết prompt tiếng Việt — tất cả prompt trong bảng Prompt phải là tiếng Anh  
❌ Tên task thiếu tiền tố `[BE]` / `[FE]`  
❌ Tách mỗi API endpoint thành 1 task riêng (phải nhóm theo module)  
❌ Task estimate dưới 4h hoặc vượt 16h mà không có lý do rõ ràng  
❌ Cột Mô tả dùng thuật ngữ tech thừa (tên file, method, class) khi có thể diễn đạt bằng ngôn ngữ thông thường  
❌ Cột Mô tả thiếu phần ảnh hưởng đến module khác đang chạy (phải luôn ghi rõ, kể cả khi "Không ảnh hưởng")  
❌ Bỏ cột Diễn giải chi tiết trong bảng Prompt  
❌ Gộp backend và frontend vào cùng bảng task  
❌ Đưa ra estimate khi chưa đọc code tương ứng  
❌ Bỏ qua memory-bank khi đã có file `.memory-bank/`  

## Sau khi có Bảng Break Task

Sau khi file plan đã lưu xong và có Bảng Break Task, hỏi user có muốn tạo task Jira từ bảng này không. Nếu có, chuyển sang skill `jira-task-creator` (không tự ý gọi API Jira trong skill này) — skill đó sẽ hỏi Epic Link + Management Systems và luôn dry-run trước khi tạo thật.
