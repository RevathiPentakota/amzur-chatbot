# Run the external MCP research server.
# Execute from the repo root:
#   powershell -File run_mcp_server.ps1

Set-Location "$PSScriptRoot"
uvicorn mcp_server.server:app --host 0.0.0.0 --port 8001 --reload
