#!/usr/bin/env bash
set -eu
root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$root"
make -n logs | grep -q 'docker compose logs --tail'
make -n logs SERVICE=flow-ui FOLLOW=1 | grep -q 'docker compose logs --tail.*-f.*flow-ui'
output=$(make -n generate-all)
printf '%s\n' "$output" | grep -q 'scenario'
python3 - "$root" <<'PY'
import os
from pathlib import Path
import subprocess
import sys
import tempfile
root = Path(sys.argv[1])
with tempfile.TemporaryDirectory() as tmp:
    work = Path(tmp)
    (work / '.env').write_text('FLOW_UI_HOST_PORT=18080\n')
    result = subprocess.run(['make', '-s', '-f', str(root / 'Makefile'), 'help'], cwd=work, text=True, capture_output=True, check=True)
    assert 'FLOW_UI_HOST_PORT=18080' in result.stdout
    result = subprocess.run(['make', '-s', '-f', str(root / 'Makefile'), 'help', 'FLOW_UI_HOST_PORT=18081'], cwd=work, text=True, capture_output=True, check=True)
    assert 'FLOW_UI_HOST_PORT=18081' in result.stdout
    fakebin = work / 'bin'
    fakebin.mkdir()
    fake = fakebin / 'docker'
    fake.write_text('#!/bin/sh\ntouch "' + str(work / 'docker-called') + '"\n')
    fake.chmod(0o755)
    env = dict(os.environ, PATH=str(fakebin) + os.pathsep + os.environ['PATH'])
    result = subprocess.run(['make', '-s', '-f', str(root / 'Makefile'), 'reset'], cwd=work, env=env, capture_output=True)
    assert result.returncode != 0 and not (work / 'docker-called').exists()
    setup = root / 'scripts/local-setup.sh'
    env.pop('SENTINEL_DEV_PASSWORD', None)
    subprocess.run(['bash', str(setup)], cwd=work, env=env, check=True)
    service = (work / 'infra/secrets/ch_password').read_bytes()
    dev = (work / 'infra/secrets/dev_password').read_bytes()
    subprocess.run(['bash', str(setup)], cwd=work, env=env, check=True)
    assert (work / 'infra/secrets/ch_password').read_bytes() == service
    assert (work / 'infra/secrets/dev_password').read_bytes() == dev
PY
echo 'make workflow checks passed'
