#!/usr/bin/env bash
# test_step4_failfast.sh — step4 の exit code 伝播を検証する受入テスト
# workflow-gate.sh step4 が bin/quality-gate verify の exit code を正しく伝播するか検証する。
# 手法: tmpdir に疑似プロジェクト構造を作成し、bin/quality-gate スタブを配置する。
set -u

PASS=0
FAIL=0
TESTS_RUN=0

_assert_exit() {
  local desc="$1" expected="$2" actual="$3"
  TESTS_RUN=$((TESTS_RUN + 1))
  if [[ "$actual" -eq "$expected" ]]; then
    echo "  PASS: $desc (exit=$actual)"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: $desc — expected exit $expected, got $actual"
    FAIL=$((FAIL + 1))
  fi
}

# --- セットアップ: 疑似プロジェクト構造 ---
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

# workflow-gate.sh の ROOT_DIR 解決: SCRIPT_DIR/../../../..
# 構造: $TMPDIR/.cursor/skills/session-handover/scripts/workflow-gate.sh
GATE_DIR="$TMPDIR/.cursor/skills/session-handover/scripts"
mkdir -p "$GATE_DIR"
mkdir -p "$TMPDIR/bin"

# 生成物の workflow-gate.sh をコピー
REAL_SCRIPT_DIR="$(cd "$(dirname "$0")/../../session-handover/scripts" && pwd)"
cp "$REAL_SCRIPT_DIR/workflow-gate.sh" "$GATE_DIR/workflow-gate.sh"
chmod +x "$GATE_DIR/workflow-gate.sh"

# --- bin/quality-gate スタブ ---
# 環境変数 STUB_VERIFY_EXIT で verify の exit code を制御
cat > "$TMPDIR/bin/quality-gate" << 'EOF'
#!/usr/bin/env bash
SUBCMD="${1:-}"
case "$SUBCMD" in
  verify)
    exit "${STUB_VERIFY_EXIT:-0}"
    ;;
  gen)
    exit "${STUB_GEN_EXIT:-0}"
    ;;
  *)
    exit 0
    ;;
esac
EOF
chmod +x "$TMPDIR/bin/quality-gate"

# --- テスト実行 ---
echo "=== test_step4_failfast ==="

# Test 1: verify が exit 0 → step4 が exit 0
echo "[Test 1] verify exit 0 → step4 exit 0"
STUB_VERIFY_EXIT=0 "$GATE_DIR/workflow-gate.sh" step4 >/dev/null 2>&1
_assert_exit "verify exit 0 propagates as step4 exit 0" 0 $?

# Test 2: verify が exit 1 → step4 が exit 1
echo "[Test 2] verify exit 1 → step4 exit 1"
STUB_VERIFY_EXIT=1 "$GATE_DIR/workflow-gate.sh" step4 >/dev/null 2>&1
_assert_exit "verify exit 1 propagates as step4 exit 1" 1 $?

# Test 3: verify が exit 2 → step4 が exit 2
echo "[Test 3] verify exit 2 → step4 exit 2"
STUB_VERIFY_EXIT=2 "$GATE_DIR/workflow-gate.sh" step4 >/dev/null 2>&1
_assert_exit "verify exit 2 propagates as step4 exit 2" 2 $?

# --- 結果サマリ ---
echo ""
echo "=== Results: $TESTS_RUN tests, $PASS passed, $FAIL failed ==="

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
exit 0
