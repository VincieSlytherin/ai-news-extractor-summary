import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import markdown

logger = logging.getLogger(__name__)


def send_email(summary_markdown: str, email_config: dict):
    """Send the summary as an HTML email via Gmail SMTP."""
    sender = email_config["sender"]
    password = email_config["password"]
    recipient = email_config["recipient"]
    smtp_server = email_config.get("smtp_server", "smtp.gmail.com")
    smtp_port = email_config.get("smtp_port", 587)

    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"AI Daily Digest / AI 每日速递 - {today}"

    # Convert Markdown to HTML
    html_body = markdown.markdown(
        summary_markdown,
        extensions=["tables", "fenced_code"],
    )

    # Wrap in a styled HTML template
    html_content = _wrap_html(html_body, today)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    # Attach both plain text and HTML versions
    msg.attach(MIMEText(summary_markdown, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    # Send with retry
    for attempt in range(2):
        try:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender, password)
                server.sendmail(sender, [recipient], msg.as_string())
            logger.info(f"Email sent successfully to {recipient}")
            return
        except Exception as e:
            logger.error(f"Email send attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                logger.info("Retrying...")

    logger.error("Failed to send email after 2 attempts")


def _wrap_html(body_html: str, date: str) -> str:
    """Wrap the HTML body in a clean email template."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.6;
    color: #333;
    max-width: 800px;
    margin: 0 auto;
    padding: 20px;
    background: #f9f9f9;
  }}
  h1 {{
    color: #1a1a2e;
    border-bottom: 2px solid #e94560;
    padding-bottom: 10px;
  }}
  h2 {{
    color: #16213e;
    margin-top: 30px;
  }}
  h3 {{
    color: #0f3460;
  }}
  a {{
    color: #e94560;
    text-decoration: none;
  }}
  a:hover {{
    text-decoration: underline;
  }}
  ul {{
    padding-left: 20px;
  }}
  li {{
    margin-bottom: 8px;
  }}
  strong {{
    color: #1a1a2e;
  }}
  .footer {{
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid #ddd;
    color: #888;
    font-size: 0.85em;
  }}
  blockquote {{
    border-left: 3px solid #e94560;
    margin-left: 0;
    padding-left: 15px;
    color: #555;
  }}
</style>
</head>
<body>
{body_html}
<div class="footer">
  <p>AI Daily Digest / AI 每日速递 | {date} | Generated automatically</p>
</div>
</body>
</html>"""
