---
name: branch-impact-review
version: 1.0.0
description: >-
  Đánh giá xem các nhánh FE/BE có đáp ứng đủ yêu cầu không, phân tích phạm vi ảnh hưởng
  tới các tính năng khác, và đánh giá hiệu suất của các thay đổi.
  Triggers on: 'đánh giá nhánh', 'review branch', 'kiểm tra yêu cầu', 'branch review',
  'impact review', 'coverage review', 'đánh giá thay đổi', 'review thay đổi'.
  Requires: CONFLUENCE_PAT env var (nếu dùng Confluence URL); thông tin nhánh FE/BE.
---

# Branch Impact Review Skill

Nhận đầu vào là **yêu cầu thay đổi** (Confluence URL hoặc mô tả văn bản) + **thông tin nhánh** FE/BE, sau đó thực hiện 3 bước đánh giá:

1. **Đọc yêu cầu** — Nắm toàn bộ nội dung cần thay đổi/sửa chữa
2. **Phân tích thay đổi** — Pull master mới nhất, diff branch vs master để hiểu thực tế code thay đổi gì
3. **Đánh giá ba chiều** — Coverage (đã đủ yêu cầu chưa), Impact (ảnh hưởng tính năng khác), Performance (có vấn đề hiệu suất không)

## Core Principles

- **Yêu cầu + code là source of truth** — Không tự suy diễn, không bịa ra thay đổi không có trong diff
- **Mọi đánh giá phải có evidence** — Dẫn nguồn file:line cụ thể, không nhận xét chung chung
- **Viết bằng tiếng Việt** — Mọi phân tích tiếng Việt; giữ tiếng Anh cho: code identifiers, tên file, tên field
- **Hiệu suất đánh giá thực tế** — Chỉ flag vấn đề hiệu suất có khả năng gây hại thực tế ở production scale

---

## Phase 0: Setup & Context Loading

### 0.1 Giải thích input format

User sẽ cung cấp 2 thông tin:

**Yêu cầu** (một trong hai dạng):
- Confluence URL: `https://confluence.mymerchize.com/pages/viewpage.action?pageId=142541322`
- Mô tả văn bản: đoạn text mô tả thay đổi cần thực hiện

**Thông tin nhánh** (format chuẩn):
```
FE feature/FAC-1234 BE feature/FAC-5678
```
- Có thể chỉ có BE, chỉ có FE, hoặc cả hai
- Tên nhánh phân cách bằng khoảng trắng sau prefix `FE`/`BE`
- Ví dụ: `BE feature/FAC-1234` (chỉ BE), `FE feature/FAC-5678` (chỉ FE)

### 0.2 Parse nhánh và xác định ticket

```bash
# Parse từ input — ví dụ: "FE feature/FAC-1234 BE feature/FAC-5678"
INPUT="<nội dung input từ user>"

# Extract branch names (python inline)
python3 -c "
import re, sys
s = '''$INPUT'''
fe = re.search(r'FE\s+([\S]+)', s)
be = re.search(r'BE\s+([\S]+)', s)
print('FE_BRANCH=' + (fe.group(1) if fe else ''))
print('BE_BRANCH=' + (be.group(1) if be else ''))
"
```

Đặt biến:
```bash
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Lấy ticket ID từ tên nhánh (ưu tiên BE branch, fallback FE)
# Ví dụ: feature/FAC-1234 → FAC-1234
TICKET_ID=$(echo "$BE_BRANCH $FE_BRANCH" | grep -oE 'FAC-[0-9]+' | head -1 || echo "no-ticket")
OUTPUT_DIR="ai-review/$TICKET_ID"
```

### 0.3 Load memory bank

Kiểm tra và đọc nếu tồn tại:

**erp (backend)**:
- `erp/.memory-bank/brief.md`
- `erp/.memory-bank/architecture.md`
- `erp/.memory-bank/tech.md`
- `erp/AGENTS.md` hoặc `erp/CLAUDE.md`

**erp-webapp (frontend)**:
- `erp-webapp/.memory-bank/brief.md`
- `erp-webapp/.memory-bank/architecture.md`
- `erp-webapp/.memory-bank/tech.md`
- `erp-webapp/AGENTS.md` hoặc `erp-webapp/CLAUDE.md`

Ghi header:
```
[Memory Bank: erp ✓/✗ | erp-webapp ✓/✗]
```

---

## Phase 1: Đọc yêu cầu

Phát hiện loại input và xử lý tương ứng.

### 1.1 Nếu input là Confluence URL

**Bước 1.1a** — Kiểm tra CONFLUENCE_PAT:
```bash
echo ${CONFLUENCE_PAT:0:8}...
```
Nếu không có PAT → dừng:
> "Cần `CONFLUENCE_PAT` trong env. Chạy: `export CONFLUENCE_PAT=<your-token>`"

**Bước 1.1b** — Fetch nội dung trang (ưu tiên theo thứ tự):

**Ưu tiên 1 — Python tool**:
```bash
CONFLUENCE_TOOL="/Users/cuongvu/workspace/merchize/maintain/tools/confluence_fetch.py"
python3 "$CONFLUENCE_TOOL" \
  --url "<URL>" \
  --token "$CONFLUENCE_PAT" \
  --children \
  --output /tmp/confluence_req.md

cat /tmp/confluence_req.md
```

**Ưu tiên 2 — curl fallback**:
```bash
PAGE_ID="<extracted_page_id>"
curl -s -H "Authorization: Bearer $CONFLUENCE_PAT" \
  "https://confluence.mymerchize.com/rest/api/content/$PAGE_ID?expand=body.storage,children.page" \
  | python3 -c "
import json,sys,re
d=json.load(sys.stdin)
title=d.get('title','')
body=d.get('body',{}).get('storage',{}).get('value','')
body=re.sub(r'<[^>]+>',' ',body)
print(f'# {title}\n\n{body}')
"
```

**Bước 1.1c** — Nếu có child pages, hỏi user:
> "Trang này có [N] child pages. Muốn tôi đọc thêm không? [danh sách child pages]"

### 1.2 Nếu input là văn bản mô tả

Đọc trực tiếp, bỏ qua bước fetch. Tiếp tục Phase 2 với nội dung đã có.

### 1.3 Trích xuất yêu cầu

Từ nội dung đã đọc, trích xuất **danh sách yêu cầu cụ thể**:

```markdown
## Danh sách yêu cầu (parsed)

| # | Yêu cầu | Loại | Phạm vi |
|---|---------|------|---------|
| R1 | [mô tả] | Tính năng mới / Sửa lỗi / Thay đổi nghiệp vụ | BE / FE / Cả hai |
| R2 | ... | ... | ... |
```

Đánh số từng yêu cầu (R1, R2...) để tham chiếu xuyên suốt các phase tiếp theo.

---

## Phase 2: Phân tích thay đổi từ các nhánh

### 2.1 Fetch code mới nhất từ remote

```bash
# Backend
cd erp
git fetch origin 2>&1 | tail -5
echo "Master hiện tại: $(git log origin/master -1 --oneline)"

# Frontend
cd ../erp-webapp
git fetch origin 2>&1 | tail -5
echo "Master hiện tại: $(git log origin/master -1 --oneline)"
```

### 2.2 Kiểm tra branch tồn tại

```bash
# Cho mỗi branch cần review
git ls-remote --heads origin <branch-name>
```

Nếu branch không tồn tại → ghi chú `[KHÔNG TÌM THẤY]` và bỏ qua branch đó.

### 2.3 Lấy diff của từng branch

**Backend (nếu có BE_BRANCH)**:
```bash
cd erp

# Xem commit log của branch
git log origin/master..origin/$BE_BRANCH --oneline

# Diff đầy đủ (những gì sẽ thêm vào master khi merge)
git diff origin/master...origin/$BE_BRANCH > /tmp/be_diff.txt

# Thống kê nhanh
git diff --stat origin/master...origin/$BE_BRANCH

# Xem nội dung diff
cat /tmp/be_diff.txt
```

**Frontend (nếu có FE_BRANCH)**:
```bash
cd erp-webapp

git log origin/master..origin/$FE_BRANCH --oneline

git diff origin/master...origin/$FE_BRANCH > /tmp/fe_diff.txt

git diff --stat origin/master...origin/$FE_BRANCH

cat /tmp/fe_diff.txt
```

### 2.4 Tóm tắt thay đổi

Phân tích diff và trình bày dưới dạng cấu trúc:

```markdown
## Tóm tắt thay đổi

### Backend (erp) — branch: <BE_BRANCH>
- **Files changed**: X files (Y insertions, Z deletions)
- **Commits**: [danh sách commit oneline]

**Thay đổi theo nhóm**:
| File/Module | Loại thay đổi | Mô tả ngắn |
|-------------|---------------|------------|
| path/to/file.ts | Sửa đổi | Thêm field X vào DTO, sửa logic Y |
| path/to/service.ts | Sửa đổi | Cập nhật business logic tính toán Z |

### Frontend (erp-webapp) — branch: <FE_BRANCH>
- **Files changed**: X files (Y insertions, Z deletions)
- **Commits**: [danh sách commit oneline]

**Thay đổi theo nhóm**:
| File/Module | Loại thay đổi | Mô tả ngắn |
|-------------|---------------|------------|
| src/pages/... | Sửa đổi | Thêm column X vào bảng, sửa form Y |
```

---

## Phase 3: Đánh giá Coverage — Đã đủ yêu cầu chưa?

Đối chiếu từng yêu cầu (R1, R2...) với code thay đổi thực tế.

### 3.1 Mapping yêu cầu → thay đổi

Với mỗi yêu cầu Ri, tìm trong diff:
- BE: tìm controller, service, DTO, entity, migration liên quan
- FE: tìm page, component, hook, API service call liên quan

Ghi nhận evidence cụ thể (file:line).

### 3.2 Bảng đánh giá coverage

```markdown
## Đánh giá Coverage

| Yêu cầu | Mô tả | BE Status | FE Status | Evidence | Ghi chú |
|---------|-------|-----------|-----------|----------|---------|
| R1 | ... | ✅ Đủ | ✅ Đủ | be: service.ts:45, fe: Page.tsx:23 | |
| R2 | ... | ⚠️ Một phần | ✅ Đủ | be: controller.ts:12 | Thiếu validation trường hợp X |
| R3 | ... | ❌ Chưa có | ❌ Chưa có | — | Không tìm thấy thay đổi tương ứng |
| R4 | ... | ➖ N/A | ✅ Đủ | fe: Component.tsx:67 | Chỉ liên quan FE |
```

**Legends**:
- ✅ Đủ — thay đổi code cover toàn bộ yêu cầu này
- ⚠️ Một phần — có thay đổi nhưng thiếu một số edge case hoặc điều kiện
- ❌ Chưa có — không tìm thấy thay đổi nào liên quan
- ➖ N/A — yêu cầu không áp dụng cho phía này

### 3.3 Kết luận Coverage

```markdown
### Kết luận Coverage

| Metric | Số lượng |
|--------|---------|
| Tổng yêu cầu | N |
| ✅ Đã đáp ứng đủ | X |
| ⚠️ Đáp ứng một phần | Y |
| ❌ Chưa đáp ứng | Z |

**Verdict**: ✅ Sẵn sàng merge / ⚠️ Cần bổ sung / ❌ Chưa đủ để merge
```

---

## Phase 4: Đánh giá Scope Impact — Ảnh hưởng tính năng khác

Xác định các tính năng hiện có bị ảnh hưởng bởi những thay đổi này.

### 4.1 Tìm caller/consumer của code bị sửa

Với mỗi function/class/component được sửa trong diff:

**Backend**:
```bash
cd erp
# Tìm nơi gọi service/function đã bị sửa
grep -r "<TênService>\|<TênMethod>" erp/src/ --include="*.ts" -l

# Tìm module nào import file đã thay đổi
grep -r "from.*<path-đã-thay-đổi>" erp/src/ --include="*.ts" -l
```

**Frontend**:
```bash
cd erp-webapp
# Tìm component/hook được import ở đâu
grep -r "import.*<TênComponent>" erp-webapp/src/ --include="*.tsx" --include="*.ts" -l

# Tìm API service method được dùng ở đâu
grep -r "<tênMethod>" erp-webapp/src/ --include="*.tsx" --include="*.ts" -l
```

### 4.2 Phân loại ảnh hưởng

```markdown
## Đánh giá Scope Impact

### 🔴 Ảnh hưởng cao — Cần test kỹ

| File/Module thay đổi | Tính năng bị ảnh hưởng | Loại ảnh hưởng | Khuyến nghị |
|----------------------|------------------------|----------------|-------------|
| service.ts:calcFee() | Module thanh toán, Báo cáo doanh thu | Logic tính phí thay đổi | Test regression cho cả 2 module |

### 🟡 Ảnh hưởng trung bình — Kiểm tra lại

| File/Module thay đổi | Tính năng bị ảnh hưởng | Loại ảnh hưởng | Khuyến nghị |
|----------------------|------------------------|----------------|-------------|
| dto.ts: thêm field | Import ở X nơi | Thêm field mới (non-breaking) | Xác nhận các consumer không bị break |

### 🟢 Không ảnh hưởng — An toàn

- [Danh sách thay đổi được đánh giá là isolated, chỉ ảnh hưởng phần đang làm]
```

### 4.3 Đặc biệt chú ý

Luôn kiểm tra các loại thay đổi sau vì có nguy cơ ảnh hưởng cao:

| Loại thay đổi | Rủi ro | Cách kiểm tra |
|---------------|--------|---------------|
| Database schema / migration | Thay đổi cấu trúc dữ liệu ảnh hưởng toàn bộ module dùng entity đó | `grep -r "TênEntity" erp/src/ -l` |
| Shared utility / helper function | Logic dùng ở nhiều nơi | Tìm tất cả caller |
| Config key / Enum value thay đổi | Có thể break các flow đang dùng giá trị cũ | Kiểm tra enum usage |
| API response structure thay đổi | FE đang consume API này có bị break không | Kiểm tra FE API service types |
| Middleware / interceptor | Chạy cho mọi request, thay đổi có thể ảnh hưởng toàn bộ | Đọc kỹ scope áp dụng |

---

## Phase 5: Đánh giá Performance — Hiệu suất hệ thống

Tập trung vào các vấn đề hiệu suất **có khả năng gây hại thực tế** ở production scale, không flag lý thuyết.

### 5.1 Ngưỡng flag hiệu suất

Chỉ flag khi thỏa mãn ít nhất một trong các điều kiện:

| Pattern | Ngưỡng flag |
|---------|-------------|
| Database query trong vòng lặp | Vòng lặp N >= 10 bản ghi hoặc không giới hạn N |
| Unbounded query (không có limit) | Bảng có thể có > 1000 bản ghi |
| Sync/blocking I/O trong hot path | Xảy ra với mỗi request hoặc mỗi item |
| Memory accumulation | Tích lũy data không giải phóng trong vòng lặp |
| Re-render không cần thiết | Component re-render toàn bộ khi chỉ cần cập nhật một phần |
| Large payload (FE) | API trả về > 500 items không phân trang |
| Heavy computation trong render | Tính toán phức tạp không memo hóa, chạy mỗi render |

### 5.2 Checklist Backend

Với mỗi service/function bị sửa, kiểm tra:

```
□ N+1 query: có query trong vòng lặp không?
□ Unbounded query: findMany/find() không có limit có không?
□ Transaction scope: transaction có bao quá nhiều operation không?
□ Async/await: có await trong vòng lặp sequential khi có thể dùng Promise.all không?
□ Memory: có build array lớn trong memory không (ví dụ: load toàn bộ bảng vào RAM)?
□ Index: câu query filter theo field có index không?
□ Recursive logic: có đệ quy không giới hạn depth không?
□ Cron job / batch: job có xử lý từng item một thay vì batch không?
```

### 5.3 Checklist Frontend

```
□ useEffect dependency: có gây infinite loop không?
□ Memo: component có render lại không cần thiết khi parent re-render không?
□ Large list: có render danh sách dài không có virtualization không?
□ API waterfall: có gọi API tuần tự khi có thể song song không?
□ State update trong loop: có setState trong vòng lặp không?
□ Event listener: có addEventListener mà không removeEventListener không?
□ Large bundle: có import cả thư viện khi chỉ cần một hàm không?
```

### 5.4 Bảng đánh giá Performance

```markdown
## Đánh giá Performance

### 🔴 Vấn đề nghiêm trọng — Có thể gây chậm/đơ production

| Vị trí | Pattern | Mô tả vấn đề | Đề xuất fix |
|--------|---------|--------------|-------------|
| service.ts:78-95 | N+1 query | Gọi DB trong forEach orders, nếu 1000 đơn = 1000 queries | Dùng eager loading hoặc bulk query trước vòng lặp |

### 🟡 Cần cải thiện — Chưa gây vấn đề ngay nhưng sẽ scale kém

| Vị trí | Pattern | Mô tả | Gợi ý |
|--------|---------|-------|-------|
| Component.tsx:45 | Missing memo | Re-render mỗi lần parent update | Thêm React.memo hoặc useMemo |

### 🟢 Không có vấn đề hiệu suất

[Xác nhận logic thay đổi đã được đánh giá và không có vấn đề hiệu suất đáng lo ngại]
```

---

## Phase 6: Tổng hợp & Viết Output

### 6.1 Tạo thư mục output

```bash
mkdir -p "ai-review/$TICKET_ID"
OUTPUT_FILE="ai-review/$TICKET_ID/requirement_review.md"
```

### 6.2 Cấu trúc file output

```markdown
# Branch Impact Review: <TICKET_ID>

[Memory Bank: erp ✓/✗ | erp-webapp ✓/✗]
Generated: {TIMESTAMP} | Ticket: {TICKET_ID} | Skill: branch-impact-review v{VERSION}
Requirement: {CONFLUENCE_URL hoặc "Text description"}
BE Branch: {BE_BRANCH hoặc "N/A"} | FE Branch: {FE_BRANCH hoặc "N/A"}

---

## Tóm tắt yêu cầu

[2-3 câu tóm tắt yêu cầu và scope]

## Danh sách yêu cầu

[Bảng R1, R2... từ Phase 1]

## Tóm tắt thay đổi

[Kết quả Phase 2: số file thay đổi, commits, nhóm thay đổi]

## Đánh giá Coverage

[Bảng từ Phase 3 — coverage matrix + verdict]

## Đánh giá Scope Impact

[Bảng từ Phase 4 — ảnh hưởng tính năng khác]

## Đánh giá Performance

[Bảng từ Phase 5 — vấn đề hiệu suất]

## Kết luận & Khuyến nghị

[Verdict tổng thể + action items ưu tiên]

---
*Generated by branch-impact-review skill v{VERSION} | {AGENT_NAME} {MODEL_NAME}*
```

### 6.3 Kết luận tổng thể

```markdown
## Kết luận & Khuyến nghị

### Verdict tổng thể
| Chiều đánh giá | Kết quả |
|----------------|---------|
| Coverage | ✅ Đủ / ⚠️ Một phần / ❌ Thiếu |
| Scope Impact | ✅ An toàn / ⚠️ Cần test thêm / 🔴 Có nguy cơ |
| Performance | ✅ Ổn / ⚠️ Cần cải thiện / 🔴 Có vấn đề |

**Quyết định**: ✅ Sẵn sàng merge / ⚠️ Cần xử lý trước khi merge / ❌ Chưa thể merge

### Action Items (ưu tiên xử lý trước)

| # | Ưu tiên | Mô tả | Phạm vi |
|---|---------|-------|---------|
| 1 | 🔴 Bắt buộc | [việc phải làm] | BE/FE |
| 2 | 🟡 Nên làm | [việc nên làm] | BE/FE |
| 3 | 🟢 Tùy chọn | [cải thiện không bắt buộc] | BE/FE |
```

### 6.4 Thông báo hoàn thành

> "Đã lưu kết quả đánh giá vào `{OUTPUT_FILE}`.
> - Coverage: {X}/{N} yêu cầu đã đáp ứng đủ
> - Scope Impact: {N} điểm cần chú ý
> - Performance: {N} vấn đề phát hiện
> - Verdict: [kết quả]"

---

## Quality Checklist

Trước khi finalize output:

✅ Memory bank của cả 2 projects đã được kiểm tra  
✅ Tất cả yêu cầu đã được đánh số R1, R2... và tracking xuyên suốt  
✅ Diff đã được fetch từ remote (không dùng local state có thể stale)  
✅ Mỗi assessment trong bảng coverage có evidence (file:line)  
✅ Scope impact search thực sự đã chạy grep/find, không đoán mò  
✅ Performance chỉ flag vấn đề có evidence thực tế trong diff  
✅ Action items được sắp xếp theo mức ưu tiên  
✅ Output file đã được lưu vào `ai-review/$TICKET_ID/requirement_review.md`  

## What NOT to Do

❌ Tự bịa ra "thiếu yêu cầu" mà không có evidence trong diff  
❌ Flag performance issue chỉ vì "lý thuyết có thể chậm" — phải có pattern cụ thể  
❌ Bỏ qua scope impact search — phải thực sự chạy grep  
❌ Review chỉ dựa trên diff stat (số dòng thay đổi) mà không đọc nội dung  
❌ Đánh giá "không ảnh hưởng gì" mà không kiểm tra caller/consumer  
❌ Viết action items mơ hồ ("cần cải thiện code") — phải cụ thể file và vấn đề  
❌ Dùng local branch state thay vì `origin/master` làm baseline  
