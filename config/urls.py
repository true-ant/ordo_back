"""ordo_backend URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path

from apps.auth.views import MyTokenObtainPairView, MyTokenVerifyView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.orders.urls")),
    path("api/", include("apps.notifications.urls")),
    path("_nested_admin/", include("nested_admin.urls")),
    path("api/auth/login/", MyTokenObtainPairView.as_view(), name="login"),
    path("api/token-verify/", MyTokenVerifyView.as_view(), name="verify-token"),
    path(
        "api/password_reset/",
        include("django_rest_passwordreset.urls", namespace="password_reset"),
    ),
    path("api/audit/", include("apps.audit.urls")),
]
