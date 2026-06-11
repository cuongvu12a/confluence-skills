# Tools — AI Agent Middleware

Thư mục này chứa các công cụ và skill hỗ trợ AI agent đọc dữ liệu từ các hệ thống nội bộ.

## Claude Code Skills

Xem [skills/README.md](skills/README.md) để cài đặt và sử dụng các Claude Code skill:
- **confluence-research** — Đọc Confluence + sinh break task & prompt table
- **branch-impact-review** — Review nhánh FE/BE vs master (coverage, impact, performance)

---

## confluence_fetch.py

Fetch trang Confluence bằng Personal Access Token, output ra Markdown.  
Dùng khi AI platform không thể gửi custom `Authorization` header qua WebFetch.

### Cài đặt

```bash
# Tùy chọn — cải thiện chất lượng chuyển đổi HTML → Markdown
pip install requests html2text

# Không có pip? Script vẫn hoạt động với stdlib (urllib + regex)
```

### Setup PAT token

```bash
# Thêm vào ~/.zshrc hoặc ~/.bashrc
export CONFLUENCE_PAT="your-personal-access-token-here"
export CONFLUENCE_BASE_URL="https://confluence.mymerchize.com"
```

Lấy PAT token tại: Confluence → Profile → Personal Access Tokens

### Sử dụng

```bash
# Fetch theo URL đầy đủ
python3 tools/confluence_fetch.py \
  --url "https://confluence.mymerchize.com/pages/viewpage.action?pageId=142541322"

# Fetch theo page ID
python3 tools/confluence_fetch.py --page-id 142541322

# Fetch + child pages
python3 tools/confluence_fetch.py --page-id 142541322 --children

# Lưu ra file
python3 tools/confluence_fetch.py --page-id 142541322 --output /tmp/page.md

# Tìm kiếm bằng CQL
python3 tools/confluence_fetch.py --search 'title ~ "purchase order" AND space = "ERP"'

# Chỉ lấy metadata (không lấy body)
python3 tools/confluence_fetch.py --page-id 142541322 --no-body

# Output JSON thô
python3 tools/confluence_fetch.py --page-id 142541322 --json
```

### Dùng trong AI skill

Skill `confluence-research` tự động gọi tool này. Để dùng thủ công:

```bash
CONFLUENCE_PAT="$CONFLUENCE_PAT" python3 tools/confluence_fetch.py \
  --url "https://confluence.mymerchize.com/pages/viewpage.action?pageId=142541322" \
  --children
```
