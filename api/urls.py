from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import ShowtimeViewSet, BookingViewSet, RegisterView, UserProfileView

router = DefaultRouter()
router.register(r'showtimes', ShowtimeViewSet, basename='showtime')
router.register(r'bookings', BookingViewSet, basename='booking')

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='auth_register'),
    path('auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/profile/', UserProfileView.as_view(), name='auth_profile'),
    path('', include(router.urls)),
]
