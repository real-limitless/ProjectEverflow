# Installation

Source: private kit TheFLOW. Family ritual: clone the product branch, then Compose.

This `CORE` branch is documentation only. Everflow does not use the shared campaign chrome. The runnable platform lives on `Development-Everflow`.

## Checkout

```sh
git clone -b Development-Everflow https://github.com/real-limitless/ProjectEverflow.git
cd ProjectEverflow
./scripts/everflow
./scripts/everflow setup-admin
```

UI: http://localhost:3000

If OpenFlow is already bound to 3000 on the same host, publish Everflow on 3001.

## One-liner

```sh
curl -fsSL https://raw.githubusercontent.com/real-limitless/ProjectEverflow/Development-Everflow/scripts/get-everflow.sh | bash
```

## Host needs

Linux, Docker or Podman plus Compose, and `/dev/kvm` for real microVMs (or mock mode for limited dev).

If you only see markdown, you are still on CORE:

```sh
git checkout Development-Everflow
```
