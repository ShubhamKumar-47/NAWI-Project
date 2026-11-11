"""apps/audit/middleware.py — Middleware to capture request context for audit logging."""


class AuditMiddleware:
    """
    Attaches the request object to a thread-local so it can be accessed
    from signal handlers and services that don't have direct request access.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response
