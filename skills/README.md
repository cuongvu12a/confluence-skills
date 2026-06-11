# Claude Code Skills

Thư mục này chứa các Claude Code global skill dùng trong workflow phân tích và review của team Merchize.

## Skills có sẵn

| Skill | Mô tả | Trigger |
|-------|-------|---------|
| `confluence-research` | Đọc trang Confluence + đối chiếu code → sinh break task và prompt table | `đọc confluence`, `confluence research`, `nghiên cứu yêu cầu` |
| `branch-impact-review` | So sánh nhánh FE/BE vs master → đánh giá coverage, scope impact, performance | `đánh giá nhánh`, `review branch`, `branch review` |

## Cài đặt (máy mới)

```bash
# 1. Clone hoặc pull repo về
git clone <repo-url> ~/workspace/merchize/maintain
cd ~/workspace/merchize/maintain

# 2. Cài đặt skills vào ~/.claude/skills/
bash tools/skills/install.sh

# 3. Cài dependency Python (nếu chưa có)
pip install requests html2text

# 4. Thiết lập Confluence PAT trong shell profile (~/.zshrc hoặc ~/.bashrc)
echo 'export CONFLUENCE_PAT="your-personal-access-token-here"' >> ~/.zshrc
source ~/.zshrc
```

Lấy PAT token tại: **Confluence → Profile (góc trên phải) → Personal Access Tokens**

> **Lưu ý**: Script install tự động thay thế đường dẫn hardcoded `confluence_fetch.py` bằng đường dẫn thực tế trên máy của bạn.

## Xem trước khi cài (dry-run)

```bash
bash tools/skills/install.sh --dry-run
```

## Cập nhật skill

Khi skill được cập nhật trong repo, chạy lại:

```bash
git pull
bash tools/skills/install.sh
```

## Cách dùng

### confluence-research

```
đọc confluence https://confluence.mymerchize.com/pages/viewpage.action?pageId=142541322
```

Hoặc:
```
confluence research pageId=142541322
```

Skill sẽ:
1. Fetch nội dung trang (và child pages nếu cần)
2. Đối chiếu với code trong `erp/` và `erp-webapp/`
3. Sinh danh sách câu hỏi confirm với BA/PO
4. Sinh bảng break task (BE + FE riêng)
5. Sinh bảng prompt cho từng task

Output lưu tại: `ai-plans/<branch>/confluence_research.md`

**Yêu cầu**: `CONFLUENCE_PAT` env var

---

### branch-impact-review

```
review branch FE feature/FAC-1234 BE feature/FAC-5678
```

Hoặc chỉ một phía:
```
đánh giá nhánh BE feature/FAC-1234
```

Skill sẽ:
1. Đọc yêu cầu từ Confluence URL hoặc text mô tả
2. Fetch diff của nhánh vs `origin/master`
3. Đánh giá coverage (đã đủ yêu cầu chưa?)
4. Đánh giá scope impact (ảnh hưởng tính năng khác)
5. Đánh giá performance (N+1 query, unbounded query, re-render...)

Output lưu tại: `ai-review/<ticket-id>/requirement_review.md`

**Yêu cầu**: `CONFLUENCE_PAT` env var (nếu dùng Confluence URL)

## Cấu trúc thư mục

```
tools/skills/
├── README.md                          # File này
├── install.sh                         # Script cài đặt vào ~/.claude/skills/
├── confluence-research/
│   └── SKILL.md                       # Skill definition
└── branch-impact-review/
    └── SKILL.md                       # Skill definition
```

Skills được cài vào `~/.claude/skills/` (global) nên hoạt động từ bất kỳ project nào.
