#!/usr/bin/env bash
set -euo pipefail

fabric_version="2.5.16"
nodeenv_version="2.5.8"
samples_commit="05edea01d4cf24dd4087bd3750c36e690dc4d6ff"
channel_name="fieldledgerchannel"
chaincode_name="fieldledger"

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runtime_dir="$project_dir/.runtime/fabric-samples"
network_dir="$runtime_dir/test-network"
chaincode_dir="$project_dir/blockchain/chaincode/fieldledger"

for command_name in docker git curl tar python3 jq; do
  command -v "$command_name" >/dev/null || {
    echo "Missing prerequisite: $command_name" >&2
    exit 1
  }
done

if [[ ! -d "$runtime_dir/.git" ]]; then
  mkdir -p "$(dirname "$runtime_dir")"
  git clone --filter=blob:none https://github.com/hyperledger/fabric-samples.git "$runtime_dir"
  git -C "$runtime_dir" checkout --detach "$samples_commit"
elif [[ "$(git -C "$runtime_dir" rev-parse HEAD)" != "$samples_commit" ]]; then
  echo "Unexpected fabric-samples revision in $runtime_dir; expected $samples_commit" >&2
  exit 1
fi

if [[ ! -x "$runtime_dir/bin/peer" ]]; then
  archive="$(mktemp)"
  trap 'rm -f "$archive"' EXIT
  curl -fL "https://github.com/hyperledger/fabric/releases/download/v${fabric_version}/hyperledger-fabric-linux-arm64-${fabric_version}.tar.gz" -o "$archive"
  tar -xzf "$archive" -C "$runtime_dir"
  rm -f "$archive"
  trap - EXIT
fi

export PATH="$runtime_dir/bin:$PATH"
export FABRIC_CFG_PATH="$runtime_dir/config"

python3 - "$network_dir" "$fabric_version" <<'PY'
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])
version = sys.argv[2]
files = [
    root / "compose" / "compose-test-net.yaml",
    root / "compose" / "docker" / "docker-compose-test-net.yaml",
    root / "addOrg3" / "compose" / "compose-org3.yaml",
    root / "addOrg3" / "compose" / "docker" / "docker-compose-org3.yaml",
]
for path in files:
    text = path.read_text()
    text = re.sub(r"(hyperledger/fabric-(?:peer|orderer)):latest", rf"\1:{version}", text)
    text = re.sub(r"(?m)^(\s*-\s*)(\d+):(\d+)\s*$", r'\1"127.0.0.1:\2:\3"', text)
    text = re.sub(
        r"(    labels:\n      service: hyperledger-fabric\n)(?!    logging:)",
        r'\1    logging:\n      driver: json-file\n      options:\n        max-size: "10m"\n        max-file: "3"\n',
        text,
    )
    path.write_text(text)
PY

for image in peer orderer tools ccenv baseos; do
  docker image inspect "hyperledger/fabric-${image}:${fabric_version}" >/dev/null 2>&1 || \
    docker pull "hyperledger/fabric-${image}:${fabric_version}"
  docker tag "hyperledger/fabric-${image}:${fabric_version}" "hyperledger/fabric-${image}:2.5"
done
docker image inspect "hyperledger/fabric-nodeenv:${nodeenv_version}" >/dev/null 2>&1 || \
  docker pull "hyperledger/fabric-nodeenv:${nodeenv_version}"
docker tag "hyperledger/fabric-nodeenv:${nodeenv_version}" hyperledger/fabric-nodeenv:2.5

docker run --rm -v "$chaincode_dir:/work" -w /work node:24.18.0-bookworm-slim \
  sh -c 'npm ci && npm test && rm -rf node_modules'

cd "$network_dir"
if ! docker container inspect peer0.org1.example.com >/dev/null 2>&1; then
  ./network.sh up createChannel -c "$channel_name" -i "$fabric_version"
else
  # shellcheck disable=SC1091
  set +u
  source scripts/envVar.sh
  setGlobals 1
  set -u
  if ! peer channel list 2>/dev/null | grep -Fxq "$channel_name"; then
    ./network.sh createChannel -c "$channel_name" -i "$fabric_version"
  fi
fi

if ! docker container inspect peer0.org3.example.com >/dev/null 2>&1; then
  (cd addOrg3 && ./addOrg3.sh up -c "$channel_name")
fi

# shellcheck disable=SC1091
set +u
source scripts/envVar.sh
setGlobals 1
set -u
if peer lifecycle chaincode querycommitted \
  --channelID "$channel_name" --name "$chaincode_name" >/dev/null 2>&1; then
  echo "Chaincode $chaincode_name is already committed"
else
  ./network.sh deployCC \
    -c "$channel_name" \
    -ccn "$chaincode_name" \
    -ccp "$chaincode_dir" \
    -ccl javascript \
    -ccv 1.0 \
    -ccs 1 \
    -ccep "AND('Org1MSP.peer','Org2MSP.peer')"
fi

docker update --restart unless-stopped \
  orderer.example.com peer0.org1.example.com peer0.org2.example.com peer0.org3.example.com \
  >/dev/null

echo "Fabric ${fabric_version} is ready on channel ${channel_name} with Org1, Org2, and Org3"
