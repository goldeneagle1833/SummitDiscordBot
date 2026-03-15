#!/usr/bin/env python3
"""
Daily Log Report Script - Runs on the server

This script:
1. Analyzes the last 24 hours of Discord bot and web app logs
2. Finds errors, warnings, exceptions, and critical issues
3. Generates a summary report
4. Emails the report to configured recipients
5. Cleans up log archives older than 1 week

Designed to run as a daily cron job at 7 AM EST
"""

import json
import os
import re
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict, Counter


# Configuration paths
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "email_config.json"
BOT_LOG = Path("/root/Summit/SummitDiscordBot/discord-bot/bot.log")
WEB_APP_LOG = Path("/root/Summit/SummitDiscordBot/web-app/app.log")
LOG_ARCHIVE_DIR = Path("/root/Summit/log_archives")


class LogAnalyzer:
    """Analyzes log files for errors, warnings, and issues."""

    def __init__(self, hours: int = 24):
        self.hours = hours
        self.cutoff_time = datetime.now() - timedelta(hours=hours)

    def parse_log_entry(self, line: str) -> Tuple[datetime, str, str]:
        """
        Parse a log line to extract timestamp, level, and message.

        Returns:
            (timestamp, level, message) or (None, None, line) if parsing fails
        """
        # Common log patterns
        patterns = [
            # ISO format: 2026-03-14 12:34:56,789 - INFO - Message
            r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})[,.]?\d*\s*-\s*(\w+)\s*-\s*(.+)$',
            # Bracket format: [2026-03-14 12:34:56] INFO: Message
            r'^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]\s*(\w+):\s*(.+)$',
            # Discord.py format: discord.ext.commands: INFO: Message
            r'^[\w.]+:\s*(\w+):\s*(.+)$',
        ]

        for pattern in patterns:
            match = re.match(pattern, line)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    try:
                        timestamp = datetime.strptime(groups[0], '%Y-%m-%d %H:%M:%S')
                        return timestamp, groups[1].upper(), groups[2]
                    except ValueError:
                        pass
                elif len(groups) == 2:
                    # No timestamp in this pattern
                    return None, groups[0].upper(), groups[1]

        return None, None, line

    def analyze_file(self, log_file: Path) -> Dict:
        """Analyze a single log file."""
        if not log_file.exists():
            return {
                "file": str(log_file),
                "exists": False,
                "errors": [],
                "warnings": [],
                "critical": [],
                "exceptions": [],
                "stats": {}
            }

        errors = []
        warnings = []
        critical = []
        exceptions = []
        level_counts = Counter()
        error_types = defaultdict(int)

        current_exception = None

        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    timestamp, level, message = self.parse_log_entry(line)

                    # Count by level
                    if level:
                        level_counts[level] += 1

                    # Check if within time window (if timestamp available)
                    if timestamp and timestamp < self.cutoff_time:
                        continue

                    # Detect exceptions
                    if 'Traceback' in line or 'Exception' in line or 'Error:' in line:
                        if current_exception is None:
                            current_exception = []
                        current_exception.append(line)
                    elif current_exception:
                        if line.startswith('  ') or line.startswith('\t'):
                            current_exception.append(line)
                        else:
                            exceptions.append('\n'.join(current_exception))
                            current_exception = None

                    # Categorize by level
                    if level == 'ERROR' or 'ERROR' in line.upper():
                        errors.append(f"{timestamp or 'N/A'} | {message}")
                        # Extract error type
                        error_match = re.search(r'(\w+Error|\w+Exception)', message)
                        if error_match:
                            error_types[error_match.group(1)] += 1

                    elif level == 'WARNING' or 'WARNING' in line.upper():
                        warnings.append(f"{timestamp or 'N/A'} | {message}")

                    elif level == 'CRITICAL' or 'CRITICAL' in line.upper():
                        critical.append(f"{timestamp or 'N/A'} | {message}")

                # Add final exception if any
                if current_exception:
                    exceptions.append('\n'.join(current_exception))

        except Exception as e:
            errors.append(f"Failed to read log file: {e}")

        return {
            "file": str(log_file.name),
            "exists": True,
            "errors": errors[:50],  # Limit to 50 most recent
            "warnings": warnings[:50],
            "critical": critical[:50],
            "exceptions": exceptions[:10],  # Limit to 10 most recent
            "stats": {
                "total_errors": len(errors),
                "total_warnings": len(warnings),
                "total_critical": len(critical),
                "total_exceptions": len(exceptions),
                "level_counts": dict(level_counts),
                "error_types": dict(error_types)
            }
        }


def generate_html_report(bot_analysis: Dict, web_analysis: Dict, period_hours: int) -> str:
    """Generate an HTML email report."""

    total_errors = bot_analysis["stats"]["total_errors"] + web_analysis["stats"]["total_errors"]
    total_warnings = bot_analysis["stats"]["total_warnings"] + web_analysis["stats"]["total_warnings"]
    total_critical = bot_analysis["stats"]["total_critical"] + web_analysis["stats"]["total_critical"]
    total_exceptions = bot_analysis["stats"]["total_exceptions"] + web_analysis["stats"]["total_exceptions"]

    # Determine status
    if total_critical > 0:
        status = "🔴 CRITICAL"
        status_color = "#dc3545"
    elif total_errors > 10:
        status = "🟠 HIGH ERRORS"
        status_color = "#fd7e14"
    elif total_errors > 0:
        status = "🟡 WARNINGS"
        status_color = "#ffc107"
    else:
        status = "🟢 HEALTHY"
        status_color = "#28a745"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
            .container {{ max-width: 800px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            h1 {{ color: #333; border-bottom: 3px solid {status_color}; padding-bottom: 10px; }}
            .status {{ background-color: {status_color}; color: white; padding: 15px; border-radius: 5px; font-size: 18px; font-weight: bold; text-align: center; margin: 20px 0; }}
            .summary {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin: 20px 0; }}
            .stat-card {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; border-left: 4px solid #007bff; }}
            .stat-number {{ font-size: 32px; font-weight: bold; color: #007bff; }}
            .stat-label {{ color: #6c757d; font-size: 14px; }}
            .section {{ margin: 30px 0; }}
            .section h2 {{ color: #495057; font-size: 20px; border-bottom: 2px solid #dee2e6; padding-bottom: 5px; }}
            .log-entry {{ background-color: #f8f9fa; padding: 10px; margin: 5px 0; border-left: 3px solid #dc3545; font-family: monospace; font-size: 12px; overflow-x: auto; }}
            .warning {{ border-left-color: #ffc107; }}
            .critical {{ border-left-color: #dc3545; background-color: #fff5f5; }}
            .exception {{ background-color: #fff5f5; padding: 15px; margin: 10px 0; border: 1px solid #dc3545; border-radius: 5px; font-family: monospace; font-size: 11px; white-space: pre-wrap; }}
            .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6; color: #6c757d; font-size: 12px; text-align: center; }}
            .no-issues {{ color: #28a745; font-weight: bold; text-align: center; padding: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Summit Discord Bot - Daily Log Report</h1>
            <div class="status">{status}</div>

            <p><strong>Period:</strong> Last {period_hours} hours ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})</p>

            <div class="summary">
                <div class="stat-card">
                    <div class="stat-number">{total_errors}</div>
                    <div class="stat-label">Errors</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{total_warnings}</div>
                    <div class="stat-label">Warnings</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{total_critical}</div>
                    <div class="stat-label">Critical Issues</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{total_exceptions}</div>
                    <div class="stat-label">Exceptions</div>
                </div>
            </div>
    """

    # Discord Bot Section
    html += f"""
            <div class="section">
                <h2>📱 Discord Bot ({bot_analysis['file']})</h2>
    """

    if not bot_analysis['exists']:
        html += '<p class="no-issues">⚠️ Log file not found</p>'
    elif bot_analysis['stats']['total_errors'] == 0 and bot_analysis['stats']['total_warnings'] == 0:
        html += '<p class="no-issues">✅ No issues found</p>'
    else:
        if bot_analysis['critical']:
            html += '<h3>🔴 Critical Issues:</h3>'
            for entry in bot_analysis['critical'][:10]:
                html += f'<div class="log-entry critical">{entry}</div>'

        if bot_analysis['exceptions']:
            html += '<h3>💥 Exceptions:</h3>'
            for exc in bot_analysis['exceptions'][:5]:
                html += f'<div class="exception">{exc}</div>'

        if bot_analysis['errors']:
            html += f'<h3>❌ Errors ({len(bot_analysis["errors"])} total):</h3>'
            for entry in bot_analysis['errors'][:20]:
                html += f'<div class="log-entry">{entry}</div>'

        if bot_analysis['warnings']:
            html += f'<h3>⚠️ Warnings ({len(bot_analysis["warnings"])} total, showing first 10):</h3>'
            for entry in bot_analysis['warnings'][:10]:
                html += f'<div class="log-entry warning">{entry}</div>'

    html += '</div>'

    # Web App Section
    html += f"""
            <div class="section">
                <h2>🌐 Web Application ({web_analysis['file']})</h2>
    """

    if not web_analysis['exists']:
        html += '<p class="no-issues">⚠️ Log file not found</p>'
    elif web_analysis['stats']['total_errors'] == 0 and web_analysis['stats']['total_warnings'] == 0:
        html += '<p class="no-issues">✅ No issues found</p>'
    else:
        if web_analysis['critical']:
            html += '<h3>🔴 Critical Issues:</h3>'
            for entry in web_analysis['critical'][:10]:
                html += f'<div class="log-entry critical">{entry}</div>'

        if web_analysis['exceptions']:
            html += '<h3>💥 Exceptions:</h3>'
            for exc in web_analysis['exceptions'][:5]:
                html += f'<div class="exception">{exc}</div>'

        if web_analysis['errors']:
            html += f'<h3>❌ Errors ({len(web_analysis["errors"])} total):</h3>'
            for entry in web_analysis['errors'][:20]:
                html += f'<div class="log-entry">{entry}</div>'

        if web_analysis['warnings']:
            html += f'<h3>⚠️ Warnings ({len(web_analysis["warnings"])} total, showing first 10):</h3>'
            for entry in web_analysis['warnings'][:10]:
                html += f'<div class="log-entry warning">{entry}</div>'

    html += '</div>'

    html += """
            <div class="footer">
                This is an automated report from Summit Discord Bot.<br>
                Generated by daily_log_report.py
            </div>
        </div>
    </body>
    </html>
    """

    return html


def send_email(subject: str, html_content: str, config: Dict):
    """Send email via SMTP."""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = config['smtp_user']
        msg['To'] = ', '.join(config['recipients'])

        # Attach HTML
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)

        # Connect and send
        with smtplib.SMTP(config['smtp_server'], config['smtp_port']) as server:
            server.starttls()
            server.login(config['smtp_user'], config['smtp_password'])
            server.send_message(msg)

        print(f"✓ Email sent successfully to {', '.join(config['recipients'])}")
        return True

    except Exception as e:
        print(f"✗ Failed to send email: {e}")
        return False


def cleanup_old_logs(archive_dir: Path, days: int = 7):
    """Delete log archives older than specified days."""
    if not archive_dir.exists():
        return

    cutoff = datetime.now() - timedelta(days=days)
    deleted_count = 0

    for log_file in archive_dir.glob("*.log"):
        try:
            file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
            if file_time < cutoff:
                log_file.unlink()
                deleted_count += 1
        except Exception as e:
            print(f"Warning: Could not delete {log_file}: {e}")

    if deleted_count > 0:
        print(f"✓ Cleaned up {deleted_count} old log file(s)")


def main():
    """Main execution function."""
    print("=" * 60)
    print("Summit Discord Bot - Daily Log Report")
    print("=" * 60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Load email configuration
    if not CONFIG_FILE.exists():
        print(f"✗ Error: Email config not found at {CONFIG_FILE}")
        print("Create email_config.json from the template first.")
        return 1

    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)

    # Analyze logs
    print("\nAnalyzing logs...")
    analyzer = LogAnalyzer(hours=24)

    bot_analysis = analyzer.analyze_file(BOT_LOG)
    web_analysis = analyzer.analyze_file(WEB_APP_LOG)

    # Generate report
    print("Generating report...")
    html_report = generate_html_report(bot_analysis, web_analysis, 24)

    # Determine subject based on severity
    total_errors = bot_analysis["stats"]["total_errors"] + web_analysis["stats"]["total_errors"]
    total_critical = bot_analysis["stats"]["total_critical"] + web_analysis["stats"]["total_critical"]

    if total_critical > 0:
        subject = f"🔴 CRITICAL - Summit Bot Daily Report ({total_errors} errors)"
    elif total_errors > 10:
        subject = f"🟠 Summit Bot Daily Report ({total_errors} errors)"
    elif total_errors > 0:
        subject = f"🟡 Summit Bot Daily Report ({total_errors} errors)"
    else:
        subject = "🟢 Summit Bot Daily Report (All Clear)"

    # Send email
    print("Sending email...")
    send_email(subject, html_report, config)

    # Cleanup old logs
    print("\nCleaning up old logs...")
    cleanup_old_logs(LOG_ARCHIVE_DIR, days=7)

    print("\n" + "=" * 60)
    print("Report completed successfully")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    exit(main())
