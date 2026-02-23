# Windows Deployment Guide: context7-local

This guide explains how to set up and run the `context7-local` MCP server on a Windows environment.

## 1. Prerequisites

- **Python 3.12+**: Download from [python.org](https://www.python.org/).
- **uv**: It is highly recommended to use `uv` for dependency management.

  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

## 2. Installation

1. **Clone the repository**:

   ```powershell
   git clone https://github.com/your-repo/context7-local.git
   cd context7-local
   ```

2. **Synchronize dependencies**:

   ```powershell
   uv sync
   ```

## 3. Environment Configuration

### GitHub Token (Recommended)

To avoid rate limiting, set a GitHub Personal Access Token (PAT):

**PowerShell (Current Session)**:

```powershell
$env:GITHUB_TOKEN = "your_token_here"
```

**Permanent (User Profile)**:

```powershell
[System.Environment]::SetEnvironmentVariable("GITHUB_TOKEN", "your_token_here", "User")
```

### Custom Cache Directory (Optional)

On Windows, the default cache is `~\.cache\context7-local`. To change it:

```powershell
$env:CACHE_DIR = "C:\Data\context7_cache"
```

## 4. Cline Configuration

Add the following to your `cline_mcp_settings.json` (usually located in `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json`):

> [!IMPORTANT]
> Use double backslashes `\\` for paths in the JSON configuration.

```json
{
  "mcpServers": {
    "context7-local": {
      "command": "uv",
      "args": [
        "--directory", 
        "C:\\path\\to\\context7-local", 
        "run", 
        "context7-local"
      ],
      "env": {
        "GITHUB_TOKEN": "your_token_here"
      },
      "disabled": false
    }
  }
}
```

## 5. Troubleshooting

- **Path with Spaces**: If your path contains spaces, ensure it is properly quoted in the `args` list.
- **Execution Policy**: If `uv` fails to run, ensure your PowerShell execution policy allows it: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`.
- **UTF-8 Encoding**: The server uses UTF-8. If logs show encoding issues, ensure your terminal is set to 65001: `chcp 65001`.
