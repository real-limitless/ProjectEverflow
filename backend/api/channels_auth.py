"""
Channels middleware to authenticate WebSocket connections using JWT (SimpleJWT).
Extracts the `Authorization: Bearer <token>` header or `token` query param and
attaches `scope['user']` accordingly.
Fallback to Django session auth for same-origin WebSocket connections (e.g., from iframes).
"""
from urllib.parse import parse_qs
from typing import Callable
from asgiref.sync import sync_to_async


class JWTAuthMiddleware:
    """Basic JWT auth middleware for Channels websockets."""

    def __init__(self, inner: Callable):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # Import here to avoid AppRegistryNotReady
        from django.contrib.auth.models import AnonymousUser
        from django.contrib.auth import get_user_model
        from rest_framework_simplejwt.authentication import JWTAuthentication
        
        user = AnonymousUser()

        try:
            # Try Authorization header
            headers = dict(scope.get('headers') or [])
            auth_header = None
            if headers:
                # headers are bytes; look for b'authorization'
                auth_header = headers.get(b'authorization')

            token = None
            if auth_header:
                # Expect: b'Bearer <token>'
                try:
                    parts = auth_header.decode().split()
                    if len(parts) == 2 and parts[0].lower() == 'bearer':
                        token = parts[1]
                        print(f"[JWTAuth] Found token in Authorization header")
                except Exception as e:
                    print(f"[JWTAuth] Error parsing Authorization header: {e}")
                    token = None

            # Fallback to token passed via query string (e.g., ws://...?token=...)
            if not token:
                query_string = scope.get('query_string') or b''
                qs = parse_qs(query_string.decode())
                token = (qs.get('token') or [None])[0]
                if token:
                    print(f"[JWTAuth] Found token in query string: {token[:20]}...")
                else:
                    print(f"[JWTAuth] No token in query string. Query: {query_string.decode() if query_string else 'None'}")

            if token:
                authenticator = JWTAuthentication()
                # Build DRF-like request with header
                class DummyReq:
                    META = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
                # Use sync_to_async for database operations
                from asgiref.sync import sync_to_async
                auth_result = await sync_to_async(authenticator.authenticate)(DummyReq())
                if auth_result:
                    user, _ = auth_result
                    print(f"[JWTAuth] Successfully authenticated user: {user}")
                else:
                    print(f"[JWTAuth] Token validation failed")
            else:
                print(f"[JWTAuth] No token found; checking Django session")
                # Fallback: check Django session cookies for same-origin WebSocket
                cookie_header = headers.get(b'cookie')
                if cookie_header:
                    from django.contrib.sessions.models import Session
                    from http.cookies import SimpleCookie
                    cookies = SimpleCookie()
                    cookies.load(cookie_header.decode())
                    session_cookie_name = 'sessionid'  # Django default
                    if session_cookie_name in cookies:
                        session_id = cookies[session_cookie_name].value
                        try:
                            session = await sync_to_async(Session.objects.get)(session_key=session_id)
                            user_id = session.get_decoded().get('_auth_user_id')
                            if user_id:
                                User = get_user_model()
                                user = await sync_to_async(User.objects.get)(pk=user_id)
                                print(f"[JWTAuth] Authenticated via Django session: {user}")
                        except (Session.DoesNotExist, User.DoesNotExist):
                            print(f"[JWTAuth] Session authentication failed")
                            pass
        except Exception as e:
            # On any failure, leave as Anonymous
            print(f"[JWTAuth] Exception during auth: {e}")
            import traceback
            traceback.print_exc()
            user = AnonymousUser()

        scope['user'] = user
        return await self.inner(scope, receive, send)


def JWTAuthMiddlewareStack(inner: Callable):
    return JWTAuthMiddleware(inner)
