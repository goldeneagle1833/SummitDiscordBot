# Tailwind CSS Build Script for Windows
# This script downloads Tailwind CLI and builds the CSS

Write-Host "🎨 Building Tailwind CSS..." -ForegroundColor Cyan

$TAILWIND_VERSION = "v3.4.1"
$TAILWIND_FILE = "tailwindcss-windows-x64.exe"
$TAILWIND_URL = "https://github.com/tailwindlabs/tailwindcss/releases/download/$TAILWIND_VERSION/$TAILWIND_FILE"

# Download Tailwind CLI if not present
if (-Not (Test-Path "tailwindcss.exe")) {
    Write-Host "📥 Downloading Tailwind CLI for Windows..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $TAILWIND_URL -OutFile "tailwindcss.exe"
    Write-Host "✅ Tailwind CLI downloaded" -ForegroundColor Green
} else {
    Write-Host "✅ Tailwind CLI already present" -ForegroundColor Green
}

# Build Tailwind CSS
Write-Host "🔨 Building Tailwind CSS (minified)..." -ForegroundColor Yellow
.\tailwindcss.exe -i .\static\css\tailwind.input.css -o .\static\css\tailwind.output.css --minify

# Check if build was successful
if (Test-Path ".\static\css\tailwind.output.css") {
    $size = (Get-Item ".\static\css\tailwind.output.css").Length / 1KB
    Write-Host "✅ Tailwind CSS built successfully! ($([math]::Round($size, 2)) KB)" -ForegroundColor Green
    Write-Host "🎉 Tailwind build complete!" -ForegroundColor Cyan
} else {
    Write-Host "❌ Failed to build Tailwind CSS" -ForegroundColor Red
    exit 1
}
