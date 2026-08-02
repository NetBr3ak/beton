#!/usr/bin/env bash
source "$(dirname "$0")/helpers.sh"

# Set up a fake project tree
PROJ=$(mktemp -d /tmp/beton_proj_XXXX)
mkdir -p "${PROJ}/src" "${PROJ}/tests"
touch "${PROJ}/src/auth.py"
touch "${PROJ}/tests/test_auth.py"
touch "${PROJ}/tests/test_utils.py"
touch "${PROJ}/src/utils.py"

# Test: Python file → finds test file by naming convention
FOUND=$(bash bin/run-affected-tests "${PROJ}/src/auth.py" --dry-run 2>/dev/null)
check_contains "${FOUND}" "test_auth.py" "auth.py → test_auth.py discovered"

# Test: Python file with no matching test → exits 0 with empty output
touch "${PROJ}/src/orphan.py"
FOUND2=$(bash bin/run-affected-tests "${PROJ}/src/orphan.py" --dry-run 2>/dev/null)
check_eq "${FOUND2}" "" "orphan.py → no tests found (empty output)"

# Test: exits 0 regardless
bash bin/run-affected-tests "${PROJ}/src/auth.py" --dry-run 2>/dev/null
check_eq "$?" "0" "exits 0 regardless"

# Test: monorepo isolation — editing app1/src/foo.py must not find app2/tests/
MONO=$(mktemp -d /tmp/beton_mono_XXXX)
mkdir -p "${MONO}/app1/src" "${MONO}/app1/tests" "${MONO}/app2/src" "${MONO}/app2/tests"
# Each subproject has its own pyproject.toml so they're separate project roots
echo "[project]" > "${MONO}/app1/pyproject.toml"
echo "[project]" > "${MONO}/app2/pyproject.toml"
touch "${MONO}/app1/src/foo.py" "${MONO}/app1/tests/test_foo.py"
touch "${MONO}/app2/src/foo.py" "${MONO}/app2/tests/test_foo.py"
FOUND_M=$(bash bin/run-affected-tests "${MONO}/app1/src/foo.py" --dry-run 2>/dev/null)
echo "${FOUND_M}" | grep -q "app1/tests" && echo "${FOUND_M}" | grep -qv "app2/tests" \
  && ok "monorepo isolation: app1 edit doesn't find app2 tests" \
  || not_ok "monorepo isolation: leak detected (got: ${FOUND_M})"

rm -rf "${PROJ}" "${MONO}"
report
