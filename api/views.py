from rest_framework import viewsets, status, generics
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db import transaction
from django.core.cache import cache
from django.contrib.auth.models import User
from .models import Showtime, ShowSeat, Booking
from .serializers import (
    ShowtimeSerializer, ShowSeatSerializer, BookingSerializer, 
    UserSerializer, RegisterSerializer
)

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

class UserProfileView(generics.RetrieveAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

class ShowtimeViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (AllowAny,)
    queryset = Showtime.objects.select_related('movie', 'cinema_hall__cinema')
    serializer_class = ShowtimeSerializer

    def list(self, request, *args, **kwargs):
        cache_key = 'all_showtimes_list'
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return Response(cached_data)

        response = super().list(request, *args, **kwargs)
        cache.set(cache_key, response.data, timeout=300) # 5 minutes TTL
        return response

    @action(detail=True, methods=['get'])
    def seats(self, request, pk=None):
        cache_key = f'showtime_{pk}_seats'
        cached_seats = cache.get(cache_key)
        if cached_seats:
            return Response(cached_seats)

        showtime = self.get_object()
        seats = ShowSeat.objects.filter(showtime=showtime).select_related('seat')
        serializer = ShowSeatSerializer(seats, many=True)
        cache.set(cache_key, serializer.data, timeout=60)
        return Response(serializer.data)

class BookingViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def my_dashboard(self, request):
        """Fetch all bookings for the logged-in user"""
        bookings = Booking.objects.filter(user=request.user).select_related(
            'showtime__movie', 'showtime__cinema_hall__cinema'
        ).prefetch_related('seats__seat').order_by('-created_at')
        serializer = BookingSerializer(bookings, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def book_seats(self, request):
        showtime_id = request.data.get('showtime_id')
        seat_ids = request.data.get('seat_ids', [])

        if not showtime_id or not seat_ids:
            return Response({"error": "Missing parameters"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                available_seats = ShowSeat.objects.select_for_update().filter(
                    id__in=seat_ids,
                    showtime_id=showtime_id,
                    status=ShowSeat.SeatStatus.AVAILABLE
                )

                if len(available_seats) != len(seat_ids):
                    return Response(
                        {"error": "One or more selected seats are no longer available."},
                        status=status.HTTP_409_CONFLICT
                    )

                booking = Booking.objects.create(
                    user=request.user,
                    showtime_id=showtime_id,
                    status=Booking.BookingStatus.CONFIRMED
                )

                for show_seat in available_seats:
                    show_seat.status = ShowSeat.SeatStatus.BOOKED
                    show_seat.booking = booking
                    show_seat.save()

            cache.delete(f'showtime_{showtime_id}_seats')

            serializer = BookingSerializer(booking)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
