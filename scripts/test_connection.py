#!/usr/bin/env python3
"""
Test SSH connection to the server before running automated log pulls.

Usage:
    python scripts/test_connection.py [--config CONFIG_FILE]
"""

import argparse
import json
import os
import subprocess
from pathlib import Path


def load_config(config_path: str) -> dict:
    """Load configuration from JSON file."""
    if not os.path.exists(config_path):
        print(f"❌ Config file not found: {config_path}")
        print("Run pull_logs.py first to create the config template.")
        return None

    with open(config_path, 'r') as f:
        config = json.load(f)

    # Validate config
    if config.get("server_host") == "your-server-ip":
        print(f"❌ Please configure {config_path} with your actual server details")
        return None

    return config


def test_ssh_connection(config: dict) -> bool:
    """Test basic SSH connection to the server."""
    print("\n=== Testing SSH Connection ===")

    cmd = ["ssh"]

    if config.get("server_key"):
        cmd.extend(["-i", config["server_key"]])

    cmd.extend([
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "BatchMode=yes",  # No interactive prompts
        f"{config['server_user']}@{config['server_host']}",
        "echo 'Connection successful'"
    ])

    print(f"Connecting to {config['server_user']}@{config['server_host']}...")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            print("✓ SSH connection successful!")
            return True
        else:
            print(f"✗ SSH connection failed:")
            print(f"  {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("✗ Connection timed out (10 seconds)")
        return False
    except FileNotFoundError:
        print("✗ Error: ssh command not found")
        print("  Install OpenSSH client first")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_log_files_exist(config: dict) -> bool:
    """Test if log files exist on the server."""
    print("\n=== Testing Log File Access ===")

    log_files = [
        (f"{config['remote_bot_path']}/bot.log", "Discord Bot"),
        (f"{config['remote_web_path']}/app.log", "Web App"),
    ]

    cmd_base = ["ssh"]

    if config.get("server_key"):
        cmd_base.extend(["-i", config["server_key"]])

    cmd_base.extend([
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "BatchMode=yes",
        f"{config['server_user']}@{config['server_host']}"
    ])

    all_success = True

    for log_file, description in log_files:
        cmd = cmd_base + [f"test -r '{log_file}' && echo 'OK' || echo 'NOT_FOUND'"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            output = result.stdout.strip()

            if output == "OK":
                print(f"  ✓ {description} log found: {log_file}")
            else:
                print(f"  ✗ {description} log not accessible: {log_file}")
                all_success = False
        except Exception as e:
            print(f"  ✗ Error checking {description}: {e}")
            all_success = False

    return all_success


def test_scp_capability(config: dict) -> bool:
    """Test if SCP is available and working."""
    print("\n=== Testing SCP Capability ===")

    # Try to get a small file
    cmd = ["scp"]

    if config.get("server_key"):
        cmd.extend(["-i", config["server_key"]])

    cmd.extend([
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        f"{config['server_user']}@{config['server_host']}:/etc/hostname",
        os.devnull  # Discard output
    ])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            print("✓ SCP is working correctly")
            return True
        else:
            print(f"✗ SCP test failed:")
            print(f"  {result.stderr}")
            return False
    except FileNotFoundError:
        print("✗ Error: scp command not found")
        print("  Install OpenSSH client first")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test server connection for log pulling")
    parser.add_argument(
        "--config",
        default="scripts/server_config.json",
        help="Path to server configuration file"
    )

    args = parser.parse_args()

    print("Summit Discord Bot - Server Connection Test")
    print("=" * 50)

    config = load_config(args.config)
    if not config:
        return

    print(f"\nConfiguration:")
    print(f"  Server: {config['server_user']}@{config['server_host']}")
    print(f"  SSH Key: {config.get('server_key', 'default')}")
    print(f"  Bot Path: {config['remote_bot_path']}")
    print(f"  Web Path: {config['remote_web_path']}")

    # Run tests
    tests_passed = 0
    tests_total = 3

    if test_ssh_connection(config):
        tests_passed += 1

        if test_scp_capability(config):
            tests_passed += 1

        if test_log_files_exist(config):
            tests_passed += 1
    else:
        print("\n⚠️  Skipping remaining tests due to connection failure")

    # Summary
    print("\n" + "=" * 50)
    print(f"Tests Passed: {tests_passed}/{tests_total}")

    if tests_passed == tests_total:
        print("✓ All tests passed! You can now run pull_logs scripts.")
    else:
        print("✗ Some tests failed. Please fix the issues above before running automated pulls.")
        print("\nCommon fixes:")
        print("  - Verify server_host and server_user in config")
        print("  - Check SSH key permissions (should be 600)")
        print("  - Ensure SSH key is added to server's authorized_keys")
        print("  - Verify remote paths exist on the server")


if __name__ == "__main__":
    main()
