from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from apps.accounts.models import PortalSession
from apps.accounts.sessions import IDLE_LIMIT, session_for


class SessionActivityView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        session = session_for(request.auth, request.user.pk)
        if session:
            session.last_active_at = timezone.now()
            session.save(update_fields=['last_active_at'])
            refresh = RefreshToken.for_user(request.user)
            refresh['sid'] = str(session.pk)
            return Response({'idle_seconds': int(IDLE_LIMIT.total_seconds()), 'access': str(refresh.access_token), 'refresh': str(refresh)})
        return Response({'idle_seconds': int(IDLE_LIMIT.total_seconds())})


class SessionLogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.auth.get('sid'):
            PortalSession.objects.filter(pk=request.auth['sid'], customer=request.user).update(revoked=True)
        return Response(status=204)
