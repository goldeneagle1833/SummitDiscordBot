#!/usr/bin/env python3
"""
Pull log files from the cloud server to local machine.

Usage:
    python scripts/pull_logs.py [--config CONFIG_FILE]

Configuration:
    Create a config file at scripts/server_config.json with:
    {
        "server_host": "your-server-ip-or-domain",
        "server_user": "your-username",
        "server_key": "path/to/ssh/key",  # Optional, uses default SSH key if not set
        "remote_bot_path": "/path/to/discord-bot",
        "remote_web_path": "/path/to/web-app",
        "local_logs_dir": "logs"
    }
"""

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path


DEFAULT_CONFIG = {
    "server_host": "your-server-ip",
    "server_user": "your-username",
    "server_key": None,  # Uses default SSH key
    "remote_bot_path": "/home/ubuntu/SummitDiscordBot/discord-bot",
    "remote_web_path": "/home/ubuntu/SummitDiscordBot/web-app",
    "local_logs_dir": "logs"
}


def load_config(config_path: str) -> dict:
    """Load configuration from JSON file."""
    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}")
        print("Creating template config file...")
        with open(config_path, 'w') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        print(f"Please edit {config_path} with your server details and run again.")
        exit(1)

    with open(config_path, 'r') as f:
        return json.load(f)


def ensure_local_dir(local_dir: str) -> Path:
    """Ensure local logs directory exists."""
    path = Path(local_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_scp_command(server_user: str, server_host: str, remote_path: str,
                      local_path: str, ssh_key: str = None) -> list:
    """Build SCP command for pulling files."""
    cmd = ["scp"]

    if ssh_key:
        cmd.extend(["-i", ssh_key])

    # Add SSH options
    cmd.extend([
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null"
    ])

    cmd.append(f"{server_user}@{server_host}:{remote_path}")
    cmd.append(str(local_path))

    return cmd


def pull_log_file(config: dict, remote_file: str, local_subdir: str) -> bool:
    """Pull a single log file from the server."""
    local_logs_dir = ensure_local_dir(config["local_logs_dir"])
    local_file_dir = local_logs_dir / local_subdir
    local_file_dir.mkdir(parents=True, exist_ok=True)

    # Add timestamp to local filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = Path(remote_file).name
    name_parts = filename.rsplit('.', 1)
    if len(name_parts) == 2:
        local_filename = f"{name_parts[0]}_{timestamp}.{name_parts[1]}"
    else:
        local_filename = f"{filename}_{timestamp}"

    local_path = local_file_dir / local_filename

    cmd = build_scp_command(
        config["server_user"],
        config["server_host"],
        remote_file,
        local_path,
        config.get("server_key")
    )

    print(f"Pulling {remote_file}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  ✓ Saved to {local_path}")
            return True
        else:
            print(f"  ✗ Failed: {result.stderr}")
            return False
    except FileNotFoundError:
        print("  ✗ Error: scp command not found. Please install OpenSSH client.")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def pull_all_logs(config: dict, bot_only: bool = False, web_only: bool = False):
    """Pull all log files from the server."""
    success_count = 0
    total_count = 0

    # Discord bot logs
    if not web_only:
        print("\n=== Pulling Discord Bot Logs ===")
        bot_logs = [
            f"{config['remote_bot_path']}/bot.log",
        ]

        for log_file in bot_logs:
            total_count += 1
            if pull_log_file(config, log_file, "discord-bot"):
                success_count += 1

    # Web app logs
    if not bot_only:
        print("\n=== Pulling Web App Logs ===")
        web_logs = [
            f"{config['remote_web_path']}/app.log",
            f"{config['remote_web_path']}/error.log",
            f"{config['remote_web_path']}/access.log",
        ]

        for log_file in web_logs:
            total_count += 1
            if pull_log_file(config, log_file, "web-app"):
                success_count += 1

    print(f"\n=== Summary ===")
    print(f"Successfully pulled {success_count}/{total_count} log files")
    print(f"Logs saved to: {config['local_logs_dir']}")


def main():
    parser = argparse.ArgumentParser(description="Pull log files from the server")
    parser.add_argument(
        "--config",
        default="scripts/server_config.json",
        help="Path to server configuration file (default: scripts/server_config.json)"
    )
    parser.add_argument(
        "--bot-only",
        action="store_true",
        help="Pull only Discord bot logs"
    )
    parser.add_argument(
        "--web-only",
        action="store_true",
        help="Pull only web app logs"
    )

    args = parser.parse_args()

    config = load_config(args.config)
    pull_all_logs(config, bot_only=args.bot_only, web_only=args.web_only)


if __name__ == "__main__":
    main()
