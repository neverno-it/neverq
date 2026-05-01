from requests_oauthlib import OAuth2Session
from django.conf import settings
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token as google_id_token


GOOGLE_AUTH_BASE_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://openidconnect.googleapis.com/v1/userinfo'
GOOGLE_SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
]


class GoogleOAuthError(Exception):
    pass


def get_google_auth_url(state, redirect_uri):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise GoogleOAuthError('Google OAuth credentials are missing.')

    oauth = OAuth2Session(
        client_id=settings.GOOGLE_CLIENT_ID,
        scope=GOOGLE_SCOPES,
        redirect_uri=redirect_uri,
        state=state,
    )
    auth_url, _ = oauth.authorization_url(
        GOOGLE_AUTH_BASE_URL,
        access_type='online',
        include_granted_scopes='true',
        prompt='select_account',
    )
    return auth_url


def exchange_code_for_user_info(code, redirect_uri):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise GoogleOAuthError('Google OAuth credentials are missing.')

    oauth = OAuth2Session(
        client_id=settings.GOOGLE_CLIENT_ID,
        scope=GOOGLE_SCOPES,
        redirect_uri=redirect_uri,
    )

    token = oauth.fetch_token(
        GOOGLE_TOKEN_URL,
        code=code,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        include_client_id=True,
    )

    raw_id_token = token.get('id_token')
    user_info = {}

    if raw_id_token:
        try:
            idinfo = google_id_token.verify_oauth2_token(
                raw_id_token,
                GoogleRequest(),
                settings.GOOGLE_CLIENT_ID,
            )
            user_info = {
                'email': idinfo.get('email', ''),
                'name': idinfo.get('name', ''),
                'google_id': idinfo.get('sub', ''),
                'picture': idinfo.get('picture', ''),
            }
        except Exception:
            user_info = {}

    if not user_info.get('email'):
        resp = oauth.get(GOOGLE_USERINFO_URL)
        if resp.status_code != 200:
            raise GoogleOAuthError('Failed to fetch Google user profile.')
        profile = resp.json()
        user_info = {
            'email': profile.get('email', ''),
            'name': profile.get('name', ''),
            'google_id': profile.get('sub', '') or profile.get('id', ''),
            'picture': profile.get('picture', ''),
        }

    if not user_info.get('email'):
        raise GoogleOAuthError('Google did not return an email address.')

    return user_info