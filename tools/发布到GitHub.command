#!/bin/zsh
# ============================================================
# 利润断层 · 一键推送到 GitHub（用于云端 GitHub Actions 部署）
#
# 前置：先在 github.com 上建一个**空**仓库（不要勾选 README/.gitignore），
#       复制它的地址，例如 https://github.com/你的用户名/利润断层.git
#
# 用法：双击本文件，按提示粘贴仓库地址即可。
# ============================================================
set -u

DIR="/Users/jason/Desktop/利润断层"
cd "$DIR" || { echo "找不到项目目录 $DIR"; read -r "?回车关闭…"; exit 1; }

echo "============================================"
echo " 利润断层 · 推送到 GitHub"
echo "============================================"
echo

if git rev-parse --git-dir >/dev/null 2>&1; then
  :
else
  echo "✗ 当前不是 git 仓库，先初始化…"
  git init
fi

REMOTE="$(git remote get-url origin 2>/dev/null || true)"
if [ -z "$REMOTE" ]; then
  echo "请输入 GitHub 仓库地址（形如 https://github.com/用户名/利润断层.git）："
  read -r "URL?"
  if [ -z "$URL" ]; then
    echo "✗ 未输入地址，已取消"
    read -r "?回车关闭…"
    exit 1
  fi
  git remote add origin "$URL"
  echo "→ 已设置远端 origin = $URL"
else
  echo "→ 已存在远端 origin = $REMOTE"
fi

echo
echo "→ 确保分支名为 main 并推送…"
git branch -M main
if git push -u origin main; then
  echo
  echo "✔ 推送成功！"
  echo
  echo "接下来在浏览器里做两件事（各 1 分钟）："
  echo "  1) 仓库 Settings → Pages → Source 选「Deploy from a branch」"
  echo "     → Branch 选 main / (root) → Save"
  echo "  2) 仓库 Actions 页 → 左侧「利润断层每日扫描」→ Run workflow"
  echo "     （手动触发第一次，验证云端能抓到数据；成功后再改回自动即可）"
  echo
  echo "站点地址（等 Pages 显示绿色后可用）："
  echo "  https://<你的用户名>.github.io/<仓库名>/"
else
  echo
  echo "✗ 推送失败。通常是鉴权问题："
  echo "   HTTPS 方式首次推送会要你输入 GitHub 用户名 + Personal Access Token"
  echo "   （不是密码）。没有 Token 的话去 github.com → Settings →"
  echo "   Developer settings → Personal access tokens 生成一个，勾 repo 权限。"
fi
echo
read -r "?回车关闭…"
