# exploration

Research notebooks (carmax, meta, roblox, ...) sharing one Python environment.

## Environment

```powershell
uv sync                      # builds .venv from pyproject.toml / uv.lock
.\.venv\Scripts\Activate.ps1
```

In VS Code / Jupyter, pick the kernel **Python (exploration)**. To re-register it:
`.\.venv\Scripts\python.exe -m ipykernel install --user --name exploration --display-name "Python (exploration)"`

## Snowflake login

Notebooks call `snowflake.connector.connect(connection_name="default")`, defined in
`~\.snowflake\connections.toml`:

- `[default]` uses key-pair JWT (`SNOWFLAKE_JWT`) with `~\.snowflake\keys\fin_creedon_rsa_key.p8`.
  No browser prompt. `[keypair]` is an identical alias.
- `[oauth]` uses browser OAuth (`OAUTH_AUTHORIZATION_CODE`) as a fallback. The browser opens on the
  first connect, then the token is cached until it expires. To use it, set
  `$env:SNOWFLAKE_CONNECTION = "oauth"` (notebooks that read that variable only).

The OAuth token cache below only applies to the `[oauth]` connection.

The token cache needs `tools\dpapi_keyring.py`. Windows Credential Manager rejects OAuth
tokens because they are too large (WinError 1783), so this keyring backend stores them as
DPAPI-encrypted files in `%LOCALAPPDATA%\exploration-keyring\` instead. It is enabled by
`.venv\Lib\site-packages\exploration-keyring.pth`. **If you recreate `.venv`, recreate that file**:

```
C:\Users\fintan.creedon\code\exploration\tools
import os; os.environ.setdefault("PYTHON_KEYRING_BACKEND", "dpapi_keyring.DpapiKeyring")
```

To force a fresh login, delete the files in `%LOCALAPPDATA%\exploration-keyring\`.
