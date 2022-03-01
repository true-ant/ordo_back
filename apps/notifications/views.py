from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from . import models as m
from . import serializers as s

# Create your views here.


class NotificationModelViewset(ModelViewSet):
    serializer_class = s.NotificationRecipientSerializer
    queryset = m.NotificationRecipient.objects.all()
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch"]

    def get_queryset(self):
        return self.queryset.filter(is_read=False, user=self.request.user)
