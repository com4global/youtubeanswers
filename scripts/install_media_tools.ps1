Write-Host "Installing yt-dlp and ffmpeg via winget..."

try {
    winget --version | Out-Null
} catch {
    Write-Host "winget not found. Please install App Installer from Microsoft Store."
    exit 1
}

winget install -e --id yt-dlp.yt-dlp
winget install -e --id Gyan.FFmpeg
winget install -e --id OpenJS.NodeJS.LTS

Write-Host "Done. Restart your terminal to refresh PATH."
