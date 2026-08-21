"""
Turns a failed Google OAuth callback into something a person can actually act
on, instead of a bare 500 traceback or (when Google redirects back with
?error=... and no code - e.g. the account isn't an approved test user, or the
person hit Cancel) a generic FastAPI 422 for a "missing" code parameter.
"""
from fastapi.responses import HTMLResponse

_COMMON_CAUSES = """
<ul>
<li>The OAuth consent screen is in <b>Testing</b> mode and this Google account
hasn't been added as a test user yet (Google Cloud Console &rarr;
APIs &amp; Services &rarr; OAuth consent screen &rarr; Test users).</li>
<li>The redirect URI registered on the OAuth client doesn't <b>exactly</b>
match what this hub sent - check for http vs https, a trailing slash, or the
wrong hostname/port.</li>
<li><code>GOOGLE_CLIENT_ID</code> / <code>GOOGLE_CLIENT_SECRET</code> in
<code>.env</code> are missing or mistyped, or the hub wasn't restarted after
editing them.</li>
<li>The Gmail API or Drive API hasn't been enabled for this project
(APIs &amp; Services &rarr; Library).</li>
</ul>
"""


def error_page(title: str, message: str) -> HTMLResponse:
    html = f"""
    <html>
    <head><title>{title}</title></head>
    <body style="font-family: system-ui, sans-serif; max-width: 640px; margin: 60px auto; color: #222; line-height: 1.5;">
        <h2 style="color:#b3261e;">{title}</h2>
        <p>{message}</p>
        <p><b>Common causes:</b></p>
        {_COMMON_CAUSES}
        <p><a href="/connections">&larr; Back to Connections</a></p>
    </body>
    </html>
    """
    return HTMLResponse(content=html, status_code=400)
