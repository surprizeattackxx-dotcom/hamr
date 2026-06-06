#!/usr/bin/env bash
# Smoke-test the bundled stdio plugins: send a representative request to each
# handler and assert it emits a single valid JSON object of the expected type.
# Offline plugins only (network plugins are skipped unless --net is passed).
#
# Usage: scripts/smoke-test-plugins.sh [--net]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGINS="$ROOT/plugins"
NET=0
[ "${1:-}" = "--net" ] && NET=1

pass=0
fail=0

# check <plugin> <expected-type> <json-request>
check() {
    local plugin="$1" want="$2" req="$3"
    local out
    out=$(printf '%s\n' "$req" | timeout 15 python3 "$PLUGINS/$plugin/handler.py" 2>/dev/null | head -1)
    local got
    got=$(printf '%s' "$out" | python3 -c "import sys,json;print(json.loads(sys.stdin.read()).get('type','?'))" 2>/dev/null)
    if [ "$got" = "$want" ]; then
        printf '  \033[0;32mok\033[0m   %-12s %s\n' "$plugin" "$want"
        pass=$((pass + 1))
    else
        printf '  \033[0;31mFAIL\033[0m %-12s expected %s, got %s\n' "$plugin" "$want" "${got:-<none>}"
        fail=$((fail + 1))
    fi
}

echo "Offline plugins:"
check devtools   match   '{"step":"match","query":"base64 hello"}'
check units      match   '{"step":"match","query":"100 km to mi"}'
check passgen    results '{"step":"search","query":"pass 20"}'
check qrcode     card    '{"step":"search","query":"hello"}'
check random     match   '{"step":"match","query":"roll 2d6"}'
check worldclock match   '{"step":"match","query":"time tokyo"}'
check websearch  match   '{"step":"match","query":"g rust"}'
check kill       results '{"step":"search","query":"init"}'
check sysinfo    card    '{"step":"initial","query":""}'
check unicode    match   '{"step":"match","query":"char A"}'

if [ "$NET" = 1 ]; then
    echo "Network plugins:"
    check weather   card    '{"step":"initial","query":"weather london"}'
    check translate match   '{"step":"match","query":"tr hola"}'
    check units     match   '{"step":"match","query":"100 usd to eur"}'
else
    echo "(skipping network plugins; pass --net to include weather/translate/currency)"
fi

echo
echo "Passed: $pass  Failed: $fail"
[ "$fail" -eq 0 ]
