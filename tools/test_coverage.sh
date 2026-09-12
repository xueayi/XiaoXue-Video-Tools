#!/bin/bash
# 稳定的测试 + 覆盖率入口: 每个测试文件独立进程运行, 覆盖率合并统计。
# 用法: bash tools/test_coverage.sh [测试目录或文件...]  (默认 tests/)
set -u
cd "$(dirname "$0")/.."

TARGETS=("$@")
[ ${#TARGETS[@]} -eq 0 ] && TARGETS=(tests)

rm -f .coverage
find . -name "__pycache__" -type d -not -path "./wiki/*" \
    -not -path "./.git/*" | xargs rm -rf 2>/dev/null

files=$(find "${TARGETS[@]}" -name "test_*.py" 2>/dev/null | tr -d '\r' | sort)
overall=0
for f in $files; do
    echo "=== $f ==="
    timeout 300 python -m pytest "$f" -q -p no:cacheprovider \
        --cov=src --cov-append --cov-report= > /tmp/pytest_one.log 2>&1
    code=$?
    if [ $code -ne 0 ]; then
        echo "FAILED (exit $code): $f"
        tail -20 /tmp/pytest_one.log
        overall=1
    fi
done

echo "=== coverage ==="
python -m coverage report --show-missing
python -m coverage report --fail-under=100 > /dev/null 2>&1
cov=$?
if [ $cov -ne 0 ]; then
    echo "!! 覆盖率未达 100%"
    overall=1
else
    echo "OK: 覆盖率 100%"
fi
exit $overall
