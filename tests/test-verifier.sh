#!/usr/bin/env bash
source "$(dirname "$0")/helpers.sh"

HOOK=hooks/post-tool-verify.sh

# Test: clean Python file → no block (empty output or non-block JSON)
CLEAN_PY=$(python3 -c "import tempfile,os; f=tempfile.NamedTemporaryFile(suffix='.py',dir='/tmp',delete=False,prefix='beton_v_'); print(f.name); f.close()")
printf 'x = 1\n' > "${CLEAN_PY}"
EVENT=$(python3 -c "import json,sys; print(json.dumps({'tool_name':'Write','tool_input':{'path':sys.argv[2]},'tool_response':{'output':'ok'}}))" -- "${CLEAN_PY}")
OUT=$(echo "${EVENT}" | bash "${HOOK}" 2>/dev/null)
EXIT=$?
check_eq "${EXIT}" "0" "clean python: exits 0"
# No block decision
if [ -n "${OUT}" ]; then
  DECISION=$(echo "${OUT}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('decision','allow'))" 2>/dev/null || echo "allow")
  check_eq "${DECISION}" "allow" "clean python: no block decision"
else
  ok "clean python: empty output (allow)"
fi

# Test: Python file with lint error → block decision with real error in payload
DIRTY_PY=$(python3 -c "import tempfile,os; f=tempfile.NamedTemporaryFile(suffix='.py',dir='/tmp',delete=False,prefix='beton_v_'); print(f.name); f.close()")
printf 'import unused_module\nx = 1\n' > "${DIRTY_PY}"  # F401 unused import
EVENT2=$(python3 -c "import json,sys; print(json.dumps({'tool_name':'Write','tool_input':{'path':sys.argv[2]},'tool_response':{'output':'ok'}}))" -- "${DIRTY_PY}")
OUT2=$(echo "${EVENT2}" | bash "${HOOK}" 2>/dev/null)
if [ -n "${OUT2}" ]; then
  DECISION2=$(echo "${OUT2}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('decision',''))" 2>/dev/null || echo "")
  check_eq "${DECISION2}" "block" "dirty python: decision=block"
  REASON=$(echo "${OUT2}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('reason',''))" 2>/dev/null || echo "")
  echo "${REASON}" | grep -qF "${DIRTY_PY}" \
    && ok "dirty python: reason contains file path" \
    || not_ok "dirty python: reason missing file path (got: '${REASON}')"
  AC=$(echo "${OUT2}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('additionalContext',''))" 2>/dev/null || echo "")
  echo "${AC}" | grep -q "F401" \
    && ok "dirty python: additionalContext contains real lint error (F401)" \
    || not_ok "dirty python: additionalContext missing real error"
else
  not_ok "dirty python: expected block JSON output, got empty"
fi

# Test: non-Python file (.md) → no block
MD_FILE=$(python3 -c "import tempfile,os; f=tempfile.NamedTemporaryFile(suffix='.md',dir='/tmp',delete=False,prefix='beton_v_'); print(f.name); f.close()")
printf '# hello\n' > "${MD_FILE}"
EVENT3=$(python3 -c "import json,sys; print(json.dumps({'tool_name':'Edit','tool_input':{'path':sys.argv[2]},'tool_response':{'output':'ok'}}))" -- "${MD_FILE}")
OUT3=$(echo "${EVENT3}" | bash "${HOOK}" 2>/dev/null)
check_eq "${OUT3}" "" "markdown file: no block (empty output)"

# Test: missing file path → exits 0 gracefully
EVENT4='{"tool_name":"Write","tool_input":{},"tool_response":{"output":"ok"}}'
echo "${EVENT4}" | bash "${HOOK}" > /dev/null 2>&1
check_eq "$?" "0" "missing file path: exits 0 gracefully"

# Test: parser handles all tool_input path shapes (file_path, path, edits[].file_path, edits[].path)
DIRTY_PARSER=$(python3 -c "import tempfile,os; f=tempfile.NamedTemporaryFile(suffix='.py',dir='/tmp',delete=False,prefix='beton_v_parser_'); print(f.name); f.close()")
printf 'import unused\nx = 1\n' > "${DIRTY_PARSER}"
for shape in \
    "{\"tool_input\":{\"file_path\":\"${DIRTY_PARSER}\"}}" \
    "{\"tool_input\":{\"path\":\"${DIRTY_PARSER}\"}}" \
    "{\"tool_input\":{\"edits\":[{\"file_path\":\"${DIRTY_PARSER}\"}]}}" \
    "{\"tool_input\":{\"edits\":[{\"path\":\"${DIRTY_PARSER}\"}]}}"; do
  OUT=$(echo "$shape" | bash "${HOOK}" 2>/dev/null)
  if [ -n "$OUT" ]; then
    DEC=$(echo "$OUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('decision',''))" 2>/dev/null)
    [ "$DEC" = "block" ] \
      && ok "parser shape ${shape:14:25}...: blocks correctly" \
      || not_ok "parser shape ${shape:14:25}...: decision=${DEC}"
  else
    not_ok "parser shape ${shape:14:25}...: got empty output"
  fi
done
rm -f "${DIRTY_PARSER}"

# Test: huge error output (1000+ lint errors) — must not SIGPIPE, must truncate cleanly
FLOOD_PY=$(python3 -c "import tempfile,os; f=tempfile.NamedTemporaryFile(suffix='.py',dir='/tmp',delete=False,prefix='beton_v_flood_'); print(f.name); f.close()")
python3 -c "
import sys
out = sys.argv[1]
with open(out, 'w') as f:
    for i in range(1000):
        f.write(f'import unused_{i}\n')
    f.write('x = 1\n')
" "${FLOOD_PY}"
EVENT5=$(python3 -c "import json,sys; print(json.dumps({'tool_name':'Write','tool_input':{'path':sys.argv[2]},'tool_response':{'output':'ok'}}))" -- "${FLOOD_PY}")
OUT5=$(echo "${EVENT5}" | bash "${HOOK}" 2>/dev/null)
EXIT5=$?
check_eq "${EXIT5}" "0" "1000-error flood: exits 0 (no SIGPIPE)"
if [ -n "${OUT5}" ]; then
  AC5=$(echo "${OUT5}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('additionalContext',''))" 2>/dev/null)
  AC_LEN=${#AC5}
  [ "${AC_LEN}" -lt 3000 ] \
    && ok "1000-error flood: additionalContext is truncated (${AC_LEN} bytes)" \
    || not_ok "1000-error flood: additionalContext too large (${AC_LEN} bytes, expected <3000)"
  echo "${AC5}" | grep -q "truncated" \
    && ok "1000-error flood: truncation marker present" \
    || not_ok "1000-error flood: missing truncation marker"
else
  not_ok "1000-error flood: expected block JSON, got empty"
fi
rm -f "${FLOOD_PY}"

# --- Edge: file paths with spaces, symlinks, missing files, no extension ---

# File with spaces in the path: must not break shell quoting downstream.
SPACE_FILE='/tmp/beton_v_file with space.py'
printf 'x = 1\n' > "${SPACE_FILE}"
EVT=$(python3 -c "import json,sys; print(json.dumps({'tool_name':'Edit','tool_input':{'file_path':sys.argv[1]}}))" "${SPACE_FILE}")
OUT=$(echo "${EVT}" | bash "${HOOK}" 2>/dev/null)
check_eq "${OUT}" "" "file path with spaces: handled, no block"
rm -f "${SPACE_FILE}"

# Nonexistent file: hook exits 0 silently rather than crashing.
EVT='{"tool_name":"Edit","tool_input":{"file_path":"/tmp/beton_v_does_not_exist.py"}}'
OUT=$(echo "${EVT}" | bash "${HOOK}" 2>/dev/null)
EXIT=$?
check_eq "${EXIT}" "0" "nonexistent file: exits 0"
check_eq "${OUT}" "" "nonexistent file: silent"

# File with no extension: lint/typecheck have no language to dispatch to,
# so the hook must stay silent rather than guessing.
NOEXT=$(mktemp -p /tmp beton_v_noext_XXXX)
printf 'x = 1\n' > "${NOEXT}"
EVT=$(python3 -c "import json,sys; print(json.dumps({'tool_name':'Edit','tool_input':{'file_path':sys.argv[1]}}))" "${NOEXT}")
OUT=$(echo "${EVT}" | bash "${HOOK}" 2>/dev/null)
check_eq "${OUT}" "" "file without extension: no block"
rm -f "${NOEXT}"

rm -f "${CLEAN_PY}" "${DIRTY_PY}" "${MD_FILE}"
report
