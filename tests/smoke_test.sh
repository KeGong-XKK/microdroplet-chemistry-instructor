#!/usr/bin/env bash
# Minimal smoke test — runs every tool once and checks output is non-empty.
# Total runtime: < 15 seconds. Exits non-zero on first failure.
#
# Used by:
#   - new users to verify their install works end-to-end
#   - .github/workflows/ci.yml to gate every push/PR
#
# Run from the repo root:  bash tests/smoke_test.sh

set -euo pipefail

# Always operate from the repo root regardless of where the script was invoked
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Use a project-local scratch directory (works identically on Linux/macOS
# and Git Bash on Windows; portable across mktemp implementations).
TMP="$ROOT/tests/.scratch"
rm -rf "$TMP"
mkdir -p "$TMP"
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0

assert_nonempty() {
    local label="$1"
    local file="$2"
    if [[ -s "$file" ]]; then
        echo "  [PASS] $label  ($(wc -c < "$file") bytes)"
        pass=$((pass + 1))
    else
        echo "  [FAIL] $label  (empty / missing: $file)"
        fail=$((fail + 1))
    fi
}

assert_contains() {
    local label="$1"
    local file="$2"
    local needle="$3"
    if grep -q "$needle" "$file"; then
        echo "  [PASS] $label  (contains '$needle')"
        pass=$((pass + 1))
    else
        echo "  [FAIL] $label  ('$needle' not found in $file)"
        fail=$((fail + 1))
    fi
}

echo
echo "=== 1. Corpus & taxonomy ==="
python -m tools.filter classify-query "CO2 reduction in microdroplets" --taxonomy reaction \
    > "$TMP/01.json"
assert_contains  "filter.classify-query"  "$TMP/01.json"  "Redox chemistry"

echo
echo "=== 2. Search (keyword mode, no embeddings needed) ==="
python -m tools.search "CO2 reduction water microdroplet" --k 5 --alpha 0.0 \
    > "$TMP/02.json"
assert_contains  "search returns hits"  "$TMP/02.json"  "row_id"

echo
echo "=== 3. Combine (parameter aggregation) ==="
python -m tools.search "CO2 reduction water microdroplet" --k 10 --alpha 0.0 \
    | python -m tools.combine --top-n 3  > "$TMP/03.json"
assert_contains  "combine returns digest"  "$TMP/03.json"  "droplet_type"

echo
echo "=== 4. Citation rendering ==="
ROW_ID="$(python -c "import json, sys; print(json.load(sys.stdin)[0]['row_id'])" < "$TMP/02.json")"
python -m tools.cite "$ROW_ID" --style numbered  > "$TMP/04.txt"
assert_contains  "cite renders bibliography"  "$TMP/04.txt"  "\[1\]"

echo
echo "=== 5. Geometry builder (water cluster) ==="
python -m tools.build_model cluster --solute-smiles "O" --n-waters 4 \
    -o "$TMP/05_cluster.xyz"
assert_nonempty  "build_model cluster"  "$TMP/05_cluster.xyz"

echo
echo "=== 6. Geometry builder (interface slab) ==="
python -m tools.build_model slab --solute-smiles "O=C=O" --n-waters-per-layer 8 --n-layers 2 \
    -o "$TMP/06_slab.xyz"
assert_nonempty  "build_model slab"  "$TMP/06_slab.xyz"
assert_nonempty  "slab .cell sidecar"  "$TMP/06_slab.cell"

echo
echo "=== 7. Input writer — Gaussian ==="
python -m tools.write_input --xyz "$TMP/05_cluster.xyz" --code gaussian \
    -o "$TMP/07.gjf"
assert_contains  "Gaussian input has %NProcShared"  "$TMP/07.gjf"  "%NProcShared"

echo
echo "=== 8. Input writer — ORCA ==="
python -m tools.write_input --xyz "$TMP/05_cluster.xyz" --code orca \
    -o "$TMP/08.inp"
assert_contains  "ORCA input has ! method line"  "$TMP/08.inp"  "wB97X"

echo
echo "=== 9. Input writer — CP2K AIMD ==="
python -m tools.write_input --xyz "$TMP/06_slab.xyz" --code cp2k \
    --cell "$TMP/06_slab.cell" --xc BLYP --steps 100 \
    -o "$TMP/09.inp"
assert_contains  "CP2K input has &MOTION block"  "$TMP/09.inp"  "&MOTION"
assert_contains  "CP2K input has GTH potential"  "$TMP/09.inp"  "GTH-BLYP"

echo
echo "===================="
echo "smoke test results"
echo "===================="
echo "  passed: $pass"
echo "  failed: $fail"
echo

if [[ $fail -gt 0 ]]; then
    exit 1
fi
echo "OK"
