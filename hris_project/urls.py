from django.urls import path, include

urlpatterns = [
    path("", include("hris_app.urls")),
]
