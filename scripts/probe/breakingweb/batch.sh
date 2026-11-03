#!/bin/bash
# All environments x all kinds; each run restores the sources afterwards.
cd ~/.workspace/_refsrc/BreakingWeb
export PATH=$HOME/.local/share/mise/installs/node/24.20.0/bin:$HOME/.local/bin:$PATH BREAKINGWEB_AUTO_BUILD_FRONTENDS=0 PYTHONPATH=$PWD
for e in gmail reddit robinhood booking lms pp amazon; do
  for k in none landmarks headings names labels alt tableheads; do
    [ -f /tmp/amt-syn/bw-variants/$( [ $e = pp ] && echo patient_portal || ([ $e = rh ] && echo robinhood || echo $e))/$k.report.json ] && continue
    echo "=== $e $k $(date +%T)"
    timeout 1800 .venv/bin/python /tmp/amt-syn/bw-probe/variant_run.py $e $k 2 /tmp/amt-syn/bw-variants 2>&1 | grep -v Warning | tail -3
  done
done
git status --short
echo BATCH DONE
