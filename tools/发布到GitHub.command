#!/bin/zsh
# ============================================================
# 利润断层 · 一键推送到 GitHub（用于云端 GitHub Actions 部署）
#
# 前置（只需做一次）：在浏览器打开 https://github.com/new 建一个空仓库，
#   名字随便填（比如 profit-gap），**不要**勾选 README/.gitignore，点 Create。
#   然后复制它的地址（形如 https://github.com/你的用户名/profit-gap.git）。
#
# 用法：双击本文件，粘贴仓库地址回车即可。首次推送若弹「允许钥匙串」，
#       点一下「允许」即可（那是 macOS 在调你之前存好的 GitHub 登录凭证）。
# ============================================================
set -u

DIR="/Users/jason/Desktop/利润断层"
cd "$DIR" || { echo "找不到项目目录 $DIR"; read -r "?回车关闭…"; exit 1; }

echo "============================================"
echo " 利润断层 · 推送到 GitHub"
echo "============================================"
echo

[ -d .git ] || git init

REMOTE="$(git remote get-url origin 2>/dev/null || true)"
if [ -z "$REMOTE" ]; then
  echo "粘贴 GitHub 仓库地址（形如 https://github.com/用户名/profit-gap.git）："
  read -r "URL?"
  [ -z "$URL" ] && { echo "✗ 未输入地址，已取消"; read -r "?回车关闭…"; exit 1; }
  git remote add origin "$URL"
  echo "→ 已设置远端 origin = $URL"
else
  echo "→ 已存在远端 origin = $REMOTE"
fi

# 从远端地址解析 owner/repo（兼容 https 与 ssh 两种写法）
URL="$(git remote get-url origin)"
OWNER=""; REPO=""
case "$URL" in
  *github.com:*/*) OWNER="${URL##*github.com:}"; OWNER="${OWNER%%/*}"; REPO="${URL##*/}"; REPO="${REPO%.git}" ;;
  *github.com/*)   OWNER="${URL#*github.com/}"; OWNER="${OWNER%%/*}"; REPO="${URL##*/}"; REPO="${REPO%.git}" ;;
esac

echo
echo "→ 推送 main 分支到远端…"
git branch -M main
if git push -u origin main; then
  echo
  echo "✔ 推送成功！"
  echo
  if [ -n "$OWNER" ] && [ -n "$REPO" ]; then
    echo "→ 正在打开仓库设置页（Pages + Actions）…"
    open "https://github.com/$OWNER/$REPO/settings/pages"
    open "https://github.com/$OWNER/$REPO/actions/workflows/daily-scan.yml"
    echo
    echo "剩下两下点击（各 5 秒）："
    echo "  ① 刚打开的 Pages 页 → Build and deployment → Source 选"
    echo "     「Deploy from a branch」→ Branch 选 main /(root) → Save"
    echo "  ② 刚打开的 Actions 页 → 右侧「Run workflow」→ 绿色 Run workflow"
    echo "     （手动跑第一次，验证云端能抓到数据；以后每天 22:00 全自动）"
    echo
    echo "网站地址（①保存后约 1 分钟可用）："
    echo "  https://$OWNER.github.io/$REPO/"
  else
    echo "未能从远端地址解析出用户名/仓库名，请手动打开仓库的 Settings→Pages 和 Actions 页。"
  fi
else
  echo
  echo "✗ 推送失败。通常是鉴权问题："
  echo "   首次推送会要 GitHub 用户名 + 访问令牌（不是密码）。"
  echo "   本机已存过 GitHub 登录凭证，若弹出「允许钥匙串」请点允许；"
  echo "   若确实没有令牌，去 github.com → Settings → Developer settings →"
  echo "   Personal access tokens 生成一个（勾 repo、workflow），再把令牌当密码粘贴。"
fi
echo
read -r "?回车关闭…"
