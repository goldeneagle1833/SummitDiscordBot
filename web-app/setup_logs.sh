#!/bin/bash
# Setup script for Summit Web Application log directories
# Run this script on the server before starting the application

echo "Setting up log directories for Summit Web Application..."

# Create log directory
mkdir -p /var/log/summit-web

# Create log files
touch /var/log/summit-web/error.log
touch /var/log/summit-web/access.log

# Set proper permissions
chmod 755 /var/log/summit-web
chmod 644 /var/log/summit-web/error.log
chmod 644 /var/log/summit-web/access.log

echo "✓ Created /var/log/summit-web directory"
echo "✓ Created error.log and access.log files"
echo "✓ Set proper permissions"
echo ""
echo "Log directory setup complete!"
echo "Logs will be written to:"
echo "  - /var/log/summit-web/error.log"
echo "  - /var/log/summit-web/access.log"
