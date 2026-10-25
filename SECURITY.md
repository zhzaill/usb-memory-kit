# Security

- Do not commit `memory-kit/config/secret.ps1`.
- Do not commit `memory-kit/corpus/`, `memory-kit/index/`, `memory-kit/state/`
  or `我的文件/`.
- Do not publish real machine names, personal paths, logs or API credentials.
- The HTTP service is designed for `127.0.0.1`; do not expose it directly to the
  public internet without authentication and a reverse proxy.
- Before lending a USB stick, remove private data, model caches, sessions and any
  local credential file.
