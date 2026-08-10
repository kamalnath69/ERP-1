"""Inbox-safe transactional email templates for Edvatiq security flows."""
from html import escape


def render_auth_email(*, code: str, purpose: str, first_name: str, app_url: str, expires_minutes: int) -> tuple[str, str, str]:
    content = {
        "email_verification": {
            "subject": "Verify your email for Edvatiq",
            "eyebrow": "EMAIL VERIFICATION",
            "title": "Confirm it is really you",
            "intro": "Use the verification code below to finish setting up your Edvatiq workspace.",
            "action": "verify your email",
            "path": "/verify-email",
        },
        "password_reset": {
            "subject": "Reset your Edvatiq password",
            "eyebrow": "PASSWORD RECOVERY",
            "title": "Create a new password",
            "intro": "We received a request to reset your Edvatiq password. Use this secure code to continue.",
            "action": "reset your password",
            "path": "/forgot-password",
        },
        "platform_invite": {
            "subject": "Your Edvatiq platform invitation",
            "eyebrow": "PLATFORM INVITATION",
            "title": "You have been invited",
            "intro": "Your Edvatiq platform account is ready to activate. Use this one-time code to continue.",
            "action": "activate your account",
            "path": "/platform-invite",
        },
    }.get(purpose)
    if not content:
        raise ValueError(f"Unsupported authentication email purpose: {purpose}")

    greeting = f"Hi {first_name.strip()}," if first_name.strip() else "Hello,"
    action_url = f"{app_url.rstrip('/')}{content['path']}"
    subject = content["subject"]
    text = (
        f"{greeting}\n\n{content['title']}\n\n{content['intro']}\n\n"
        f"Your one-time code: {code}\n\n"
        f"This code expires in {expires_minutes} minutes and can be used once.\n"
        f"Continue: {action_url}\n\n"
        "If you did not request this, ignore this email. Never share this code with anyone.\n\n"
        "Edvatiq Security\nYour business, clearly managed."
    )

    safe = {key: escape(str(value)) for key, value in content.items()}
    safe_greeting = escape(greeting)
    safe_code = escape(code)
    safe_url = escape(action_url, quote=True)
    preheader = escape(f"Your Edvatiq code is {code}. It expires in {expires_minutes} minutes.")
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>{safe['subject']}</title>
  <style>
    @media only screen and (max-width:620px) {{
      .shell {{ width:100% !important; }}
      .content {{ padding:32px 22px !important; }}
      .code {{ font-size:30px !important; letter-spacing:7px !important; }}
      .headline {{ font-size:30px !important; line-height:36px !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:#f4f0e8;color:#17372d;font-family:Arial,Helvetica,sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">{preheader}</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f4f0e8;">
    <tr><td align="center" style="padding:36px 12px;">
      <table role="presentation" class="shell" width="600" cellspacing="0" cellpadding="0" border="0" style="width:600px;max-width:600px;background:#fffdf8;border:1px solid #ddd5c6;border-radius:20px;overflow:hidden;box-shadow:0 12px 40px rgba(24,55,45,.08);">
        <tr><td style="height:7px;background:#f28a22;font-size:0;line-height:0;">&nbsp;</td></tr>
        <tr><td class="content" style="padding:42px 48px 38px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
            <tr><td style="padding-bottom:36px;">
              <table role="presentation" cellspacing="0" cellpadding="0" border="0"><tr>
                <td width="46" height="46" align="center" valign="middle" style="width:46px;height:46px;border-radius:13px;background:#173f32;color:#ffffff;font-family:Georgia,serif;font-size:25px;font-weight:bold;">E</td>
                <td style="padding-left:13px;"><div style="font-family:Georgia,'Times New Roman',serif;font-size:23px;font-weight:bold;color:#17372d;line-height:25px;">Edvatiq</div><div style="font-size:10px;letter-spacing:2.4px;color:#73827c;margin-top:4px;">BUSINESS OS</div></td>
              </tr></table>
            </td></tr>
            <tr><td style="font-size:11px;letter-spacing:2px;font-weight:bold;color:#d96c0f;padding-bottom:13px;">{safe['eyebrow']}</td></tr>
            <tr><td class="headline" style="font-family:Georgia,'Times New Roman',serif;font-size:38px;line-height:44px;font-weight:bold;color:#17372d;padding-bottom:16px;">{safe['title']}</td></tr>
            <tr><td style="font-size:16px;line-height:26px;color:#52655e;padding-bottom:28px;">{safe_greeting}<br>{safe['intro']}</td></tr>
            <tr><td style="padding-bottom:28px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f7f2e8;border:1px solid #e7dcc8;border-radius:16px;">
                <tr><td align="center" style="padding:23px 16px 8px;font-size:11px;letter-spacing:1.8px;font-weight:bold;color:#718078;">YOUR ONE-TIME CODE</td></tr>
                <tr><td align="center" class="code" style="padding:5px 12px 13px;font-family:'Courier New',monospace;font-size:38px;line-height:48px;letter-spacing:10px;font-weight:bold;color:#17372d;">{safe_code}</td></tr>
                <tr><td align="center" style="padding:0 16px 22px;"><span style="display:inline-block;background:#e5efe9;color:#276347;border-radius:999px;padding:7px 12px;font-size:12px;font-weight:bold;">Valid for {expires_minutes} minutes</span></td></tr>
              </table>
            </td></tr>
            <tr><td align="center" style="padding-bottom:30px;"><a href="{safe_url}" style="display:inline-block;background:#173f32;color:#ffffff;text-decoration:none;font-size:15px;font-weight:bold;padding:14px 24px;border-radius:11px;">Continue to Edvatiq</a></td></tr>
            <tr><td style="background:#fff6e8;border-left:4px solid #f28a22;border-radius:8px;padding:15px 17px;font-size:13px;line-height:20px;color:#655746;"><strong style="color:#4d3b28;">Keep your account safe.</strong><br>Edvatiq staff will never ask for this code by phone, WhatsApp, or chat.</td></tr>
            <tr><td style="padding-top:30px;font-size:12px;line-height:19px;color:#83908b;">If you did not request this, you can safely ignore this email. The code can be used only once.</td></tr>
          </table>
        </td></tr>
        <tr><td style="background:#17372d;padding:24px 48px;color:#c9d6d0;font-size:12px;line-height:19px;">© Edvatiq &nbsp;·&nbsp; Your business, clearly managed.<br><span style="color:#91a59c;">This is an automated security message.</span></td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return subject, text, html
