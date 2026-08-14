#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo"

python3 scripts/verify-public-source.py

node --check skills/engineering/gpt-squad-installer/scripts/gpt-squad-runtime.mjs
node --check skills/engineering/gpt-squad-orchestrator/scripts/gpt-squad-context.mjs
node --check skills/engineering/gpt-squad-orchestrator/scripts/gpt-squad-cooperation.mjs
node --check skills/engineering/gpt-squad-orchestrator/scripts/gpt-squad-runtime-policy.mjs
python3 -m py_compile skills/engineering/gpt-squad-orchestrator/scripts/gpt_squad_context.py
python3 -m py_compile skills/engineering/gpt-squad-orchestrator/scripts/operational_hardening_test.py

node --test skills/engineering/gpt-squad-installer/scripts/gpt-squad.test.mjs
node --test skills/engineering/gpt-squad-orchestrator/scripts/context-synchronization.test.mjs
node --test skills/engineering/gpt-squad-orchestrator/scripts/context-hub-wrapper.test.mjs
node --test skills/engineering/gpt-squad-orchestrator/scripts/cooperation.test.mjs
node --test skills/engineering/gpt-squad-orchestrator/scripts/runtime-policy.test.mjs
node --test skills/engineering/gpt-squad-orchestrator/scripts/operational-contract.test.mjs
python3 -W error::ResourceWarning skills/engineering/gpt-squad-orchestrator/scripts/context_hub_test.py -v
python3 -W error::ResourceWarning skills/engineering/gpt-squad-orchestrator/scripts/operational_hardening_test.py -v

python3 -m compileall -q skills scripts
python3 -m tabnanny skills scripts
