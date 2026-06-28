from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render

# Simple view to serve the frontend single-page application
def frontend_view(request):
    return render(request, 'index.html')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('', frontend_view, name='home'),
]
