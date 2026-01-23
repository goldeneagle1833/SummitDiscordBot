# Tailwind CSS Setup

This project uses Tailwind CSS for responsive styling. The build process is automated with scripts.

## Development (Local)

### Windows:
```powershell
cd web-app
.\build-tailwind.ps1
```

### Linux/Mac:
```bash
cd web-app
./build-tailwind.sh
```

### Watch Mode (auto-rebuild on changes):
```bash
# After building once, you can use watch mode for development
./tailwindcss -i ./static/css/tailwind.input.css -o ./static/css/tailwind.output.css --watch
```

## Deployment (Production)

The build script should be run during deployment:

```bash
cd /path/to/SummitDiscordBot/web-app
./build-tailwind.sh
```

This will:
1. Download the Tailwind CLI for your OS/architecture (if needed)
2. Build the minified CSS from `tailwind.input.css`
3. Output to `static/css/tailwind.output.css`

## Files

- `tailwind.config.js` - Tailwind configuration with custom theme
- `static/css/tailwind.input.css` - Input file with @tailwind directives
- `static/css/tailwind.output.css` - Generated CSS (gitignored, rebuilt on each deploy)
- `build-tailwind.sh` - Linux/Mac build script
- `build-tailwind.ps1` - Windows build script

## Customization

Edit `tailwind.config.js` to customize:
- Colors (primary, secondary, accent, backgrounds)
- Breakpoints (xs, sm, md, lg, xl, 2xl)
- Spacing, typography, shadows, etc.

After changes, rebuild with the build script or watch mode.

## Troubleshooting

**Build fails:** Make sure you're in the `web-app` directory and the script is executable:
```bash
chmod +x build-tailwind.sh
```

**CSS not loading:** Check that `tailwind.output.css` exists in `static/css/` and is loaded before other CSS files in your templates.

**Changes not appearing:** Force refresh in browser (Ctrl+F5) or clear browser cache.
