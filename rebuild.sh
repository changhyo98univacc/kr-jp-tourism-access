#!/usr/bin/env bash
# 코드를 고친 뒤 이것만 돌리면 된다.
# 파이프라인은 결정적이므로, 끝나고 git status 가 비어 있으면 결과물이 코드와 이미 일치한다는 뜻이다.
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python}"
for s in build_data build_grid build_scenarios analyze; do
  echo "── src/$s.py"
  PYTHONUTF8=1 PYTHONIOENCODING=utf-8 "$PY" "src/$s.py"
done
echo
echo "── 바뀐 산출물"
git status --porcelain -- data/processed || true
echo "(비어 있으면 커밋할 것이 없다는 뜻)"
