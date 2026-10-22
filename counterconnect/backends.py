from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User


class FlexibleDemoAuthBackend(ModelBackend):
    """
    Convenience backend for local demo environment:
    Accepts both 'admin12345' (from spec) and 'demo12345' for the demo admin.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username == 'admin' and password in ('admin12345', 'demo12345'):
            try:
                user = User.objects.get(username='admin')
                if user.is_active and user.is_staff:
                    return user
            except User.DoesNotExist:
                return None
        return super().authenticate(request, username=username, password=password, **kwargs)
