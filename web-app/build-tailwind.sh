#!/bin/bash
# Tailwind CSS Build Script for Deployment
# This script downloads Tailwind CLI and builds the CSS for production

set -e  # Exit on any error

echo "🎨 Building Tailwind CSS..."

# Detect OS and architecture
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

# Map architecture names
if [ "$ARCH" = "x86_64" ]; then
    ARCH="x64"
elif [ "$ARCH" = "aarch64" ]; then
    ARCH="arm64"
fi

# Determine Tailwind CLI filename
TAILWIND_VERSION="v3.4.1"
if [ "$OS" = "linux" ]; then
    TAILWIND_FILE="tailwindcss-linux-${ARCH}"
elif [ "$OS" = "darwin" ]; then
    TAILWIND_FILE="tailwindcss-macos-${ARCH}"
else
    echo "❌ Unsupported OS: $OS"
    exit 1
fi

# Download Tailwind CLI if not present
if [ ! -f "tailwindcss" ]; then
    echo "📥 Downloading Tailwind CLI for ${OS}-${ARCH}..."
    curl -sLO "https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/${TAILWIND_FILE}"

    # Make executable
    chmod +x "${TAILWIND_FILE}"

    # Rename to simple 'tailwindcss'
    mv "${TAILWIND_FILE}" tailwindcss

    echo "✅ Tailwind CLI downloaded"
else
    echo "✅ Tailwind CLI already present"
fi

# Build Tailwind CSS
echo "🔨 Building Tailwind CSS (minified)..."
./tailwindcss -i ./static/css/tailwind.input.css -o ./static/css/tailwind.output.css --minify

# Check if build was successful
if [ -f "./static/css/tailwind.output.css" ]; then
    SIZE=$(du -h ./static/css/tailwind.output.css | cut -f1)
    echo "✅ Tailwind CSS built successfully! (${SIZE})"
else
    echo "❌ Failed to build Tailwind CSS"
    exit 1
fi

echo "🎉 Tailwind build complete!"
