#!/usr/bin/env bash
# Đẩy dữ liệu hiện tại (./data/) lên nhánh `data` trên GitHub.
# Dùng force-push vì nhánh data chỉ lưu "trạng thái mới nhất", không cần lịch sử.
set -euo pipefail

REPO="${GITHUB_REPOSITORY:?Thieu GITHUB_REPOSITORY}"
TOKEN="${GITHUB_TOKEN:?Thieu GITHUB_TOKEN}"
AUTH_URL="https://x-access-token:${TOKEN}@github.com/${REPO}.git"

# Dam bao _data_repo ton tai
if [ ! -d _data_repo/.git ]; then
    rm -rf _data_repo
    if git ls-remote --exit-code "$AUTH_URL" refs/heads/data >/dev/null 2>&1; then
        git clone --depth 1 -b data "$AUTH_URL" _data_repo
    else
        mkdir -p _data_repo
        (cd _data_repo && git init -q && git checkout -q -b data && \
         git remote add origin "$AUTH_URL")
    fi
fi

# Xoa noi dung cu trong _data_repo (giu .git) roi copy ./data/ vao
(cd _data_repo && find . -mindepth 1 ! -path './.git*' -delete 2>/dev/null || true)
cp -rf data/. _data_repo/

cd _data_repo
git add -A
if git diff --cached --quiet; then
    echo "==> Khong co thay doi, bo qua push."
    exit 0
fi

# Tao commit goc moi (khong ke thua lich su) de nhanh data luon gon nhe.
TREE=$(git write-tree)
STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
export GIT_COMMITTER_NAME="Codi Data Bot"
export GIT_COMMITTER_EMAIL="codi-data-bot@users.noreply.github.com"
export GIT_AUTHOR_NAME="Codi Data Bot"
export GIT_AUTHOR_EMAIL="codi-data-bot@users.noreply.github.com"
COMMIT=$(git commit-tree "$TREE" -m "chore(data): sync $STAMP")
git update-ref refs/heads/data "$COMMIT"
git push -f -q origin data
echo "==> Da push du lieu len nhanh data."
