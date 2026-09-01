#!/usr/bin/env bash
# Kéo dữ liệu xuyên restart: đọc nhánh `data` trên GitHub vào ./data/
# Nhánh `data` là "cơ sở dữ liệu" riêng, giữ main sạch.
set -euo pipefail

REPO="${GITHUB_REPOSITORY:?Thieu GITHUB_REPOSITORY}"
TOKEN="${GITHUB_TOKEN:?Thieu GITHUB_TOKEN}"
AUTH_URL="https://x-access-token:${TOKEN}@github.com/${REPO}.git"

rm -rf _data_repo
mkdir -p data

if git ls-remote --exit-code "$AUTH_URL" refs/heads/data >/dev/null 2>&1; then
    echo "==> Tim thay nhanh data, dang clone..."
    git clone --depth 1 -b data "$AUTH_URL" _data_repo
    # Chep noi dung (bao gom transcripts/ va cac .json) vao ./data/
    cp -rf _data_repo/. data/
    rm -rf data/.git
    echo "==> Da pull du lieu tu nhanh data."
else
    echo "==> Nhanh data chua ton tai -> khoi tao du lieu rong."
fi
