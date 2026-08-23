import logging
from rest_framework import viewsets, status, generics
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db import transaction, IntegrityError, OperationalError
from django.core.cache import cache
from django.contrib.auth.models import User
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend

from .models import Showtime, ShowSeat, Booking
from .serializers import (
    ShowtimeSerializer, ShowSeatSerializer, BookingSerializer,
    UserSerializer, RegisterSerializer
)
from .filters import ShowtimeFilter

logger = logging.getLogger(__name__)


# =============================================================================
# WebSocket Broadcast Helper
# =============================================================================
def _broadcast_seat_update(showtime_id, seat_id, seat_number, new_status):
    """
    Broadcast a seat status change to every WebSocket client watching this showtime.

    Called via transaction.on_commit() so the broadcast fires only AFTER
    the database commit is durable. This ensures clients never receive a
    status update that could be rolled back.

    Gracefully degrades: if Redis/Channels is unavailable, the app continues
    to work normally — users just won't see real-time updates.
    """
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'showtime_{showtime_id}_seats',
                {
                    'type':        'seat_status_update',  # maps to consumer.seat_status_update()
                    'seat_id':     seat_id,
                    'seat_number': seat_number,
                    'status':      new_status,
                }
            )
    except Exception as e:
        logger.warning(f"[WS] Broadcast failed (non-critical): {e}")


# =============================================================================
# Authentication Views
# =============================================================================
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer


class UserProfileView(generics.RetrieveAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


# =============================================================================
# Showtime Views
# =============================================================================
class ShowtimeViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (AllowAny,)
    queryset = Showtime.objects.select_related('movie', 'cinema_hall__cinema')
    serializer_class = ShowtimeSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ShowtimeFilter

    def list(self, request, *args, **kwargs):
        # Only cache unfiltered listings — filtered results vary per query param
        if not request.query_params:
            cache_key = 'all_showtimes_list'
            cached_data = cache.get(cache_key)
            if cached_data:
                return Response(cached_data)
            response = super().list(request, *args, **kwargs)
            cache.set(cache_key, response.data, timeout=300)
            return response
        return super().list(request, *args, **kwargs)

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


# =============================================================================
# Booking Views
# =============================================================================
class BookingViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def my_dashboard(self, request):
        """Fetch all bookings for the authenticated user, newest first."""
        bookings = Booking.objects.filter(user=request.user).select_related(
            'showtime__movie', 'showtime__cinema_hall__cinema'
        ).prefetch_related('seats__seat').order_by('-created_at')
        serializer = BookingSerializer(bookings, many=True)
        return Response(serializer.data)

    # -------------------------------------------------------------------------
    @action(detail=False, methods=['post'])
    def lock_seats(self, request):
        """
        Phase 1 of two-phase booking — Cart / Seat Hold.

        Transitions selected AVAILABLE seats → LOCKED and creates a PENDING
        booking. A Celery Beat task auto-releases locks after 10 minutes if
        the user never calls confirm_booking (Cart Hoarder fix).

        Deadlock prevention: seat_ids are sorted ascending so all concurrent
        transactions acquire row-level locks in the same order.

        WebSocket: broadcasts LOCKED status to all clients on this showtime.
        """
        showtime_id = request.data.get('showtime_id')
        seat_ids    = request.data.get('seat_ids', [])

        if not showtime_id or not seat_ids:
            return Response({"error": "showtime_id and seat_ids are required"},
                            status=status.HTTP_400_BAD_REQUEST)

        seat_ids = sorted(seat_ids)  # Deterministic lock order prevents deadlocks

        try:
            seat_data = []
            with transaction.atomic():
                available_seats = ShowSeat.objects.select_for_update()\
                    .select_related('seat').filter(
                        id__in=seat_ids,
                        showtime_id=showtime_id,
                        status=ShowSeat.SeatStatus.AVAILABLE
                    )

                if len(available_seats) != len(seat_ids):
                    return Response(
                        {"error": "One or more seats are no longer available."},
                        status=status.HTTP_409_CONFLICT
                    )

                booking = Booking.objects.create(
                    user=request.user,
                    showtime_id=showtime_id,
                    status=Booking.BookingStatus.PENDING
                )

                now = timezone.now()
                for show_seat in available_seats:
                    show_seat.status    = ShowSeat.SeatStatus.LOCKED
                    show_seat.booking   = booking
                    show_seat.locked_at = now
                    show_seat.save()
                    seat_data.append((showtime_id, show_seat.id,
                                      show_seat.seat.seat_number, 'LOCKED'))

                # Invalidate cache + broadcast AFTER commit (guaranteed ordering)
                transaction.on_commit(lambda: cache.delete(f'showtime_{showtime_id}_seats'))
                transaction.on_commit(lambda: [_broadcast_seat_update(*d) for d in seat_data])

            # Schedule Celery auto-release after 10 minutes
            from .tasks import release_expired_locks
            release_expired_locks.apply_async(countdown=600)

            logger.info(f"Seats LOCKED: user={request.user.id}, "
                        f"showtime={showtime_id}, seats={seat_ids}")
            return Response(BookingSerializer(booking).data,
                            status=status.HTTP_201_CREATED)

        except IntegrityError:
            logger.warning(f"IntegrityError on lock: user={request.user.id}, seats={seat_ids}")
            return Response({"error": "Seat conflict — please select different seats."},
                            status=status.HTTP_409_CONFLICT)
        except Exception as e:
            logger.error(f"Unexpected error in lock_seats: {e}", exc_info=True)
            return Response({"error": "Internal server error."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # -------------------------------------------------------------------------
    @action(detail=False, methods=['post'])
    def confirm_booking(self, request):
        """
        Phase 2 of two-phase booking — Payment Simulation.

        Accepts a booking_id (from lock_seats) and a simulate_success flag.

        simulate_success=True  → Payment approved
            PENDING  booking → CONFIRMED
            LOCKED   seats   → BOOKED
            Triggers: send_booking_confirmation Celery task (async email)
            Broadcasts: BOOKED status via WebSocket

        simulate_success=False → Payment declined
            PENDING  booking → FAILED
            LOCKED   seats   → AVAILABLE (released immediately)
            Broadcasts: AVAILABLE status via WebSocket

        In a real system, simulate_success would be replaced by verifying
        a payment gateway webhook signature (idempotent processing).
        """
        booking_id       = request.data.get('booking_id')
        simulate_success = request.data.get('simulate_success', True)

        if not booking_id:
            return Response({"error": "booking_id is required"},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            seat_data = []
            with transaction.atomic():
                booking = Booking.objects.select_for_update().get(
                    id=booking_id,
                    user=request.user
                )

                if booking.status != Booking.BookingStatus.PENDING:
                    return Response(
                        {"error": f"Booking is already {booking.status}. "
                                  f"Cannot process payment again."},
                        status=status.HTTP_409_CONFLICT
                    )

                locked_seats = ShowSeat.objects.select_for_update()\
                    .select_related('seat').filter(
                        booking=booking,
                        status=ShowSeat.SeatStatus.LOCKED
                    )

                if not locked_seats.exists():
                    return Response(
                        {"error": "No locked seats found. Lock may have expired."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if simulate_success:
                    # ---- PAYMENT APPROVED ----
                    booking.status = Booking.BookingStatus.CONFIRMED
                    booking.save()

                    for seat in locked_seats:
                        seat.status    = ShowSeat.SeatStatus.BOOKED
                        seat.locked_at = None
                        seat.save()
                        seat_data.append((booking.showtime_id, seat.id,
                                          seat.seat.seat_number, 'BOOKED'))

                    transaction.on_commit(
                        lambda: cache.delete(f'showtime_{booking.showtime_id}_seats'))
                    transaction.on_commit(
                        lambda: [_broadcast_seat_update(*d) for d in seat_data])

                    # Fire async confirmation email (non-blocking)
                    from .tasks import send_booking_confirmation
                    booking_id_captured = booking.id
                    transaction.on_commit(
                        lambda: send_booking_confirmation.delay(booking_id_captured))

                    logger.info(f"Payment CONFIRMED: user={request.user.id}, "
                                f"booking={booking.id}")
                    return Response(BookingSerializer(booking).data,
                                    status=status.HTTP_200_OK)

                else:
                    # ---- PAYMENT DECLINED ----
                    booking.status = Booking.BookingStatus.FAILED
                    booking.save()

                    for seat in locked_seats:
                        seat.status    = ShowSeat.SeatStatus.AVAILABLE
                        seat.booking   = None
                        seat.locked_at = None
                        seat.save()
                        seat_data.append((booking.showtime_id, seat.id,
                                          seat.seat.seat_number, 'AVAILABLE'))

                    transaction.on_commit(
                        lambda: cache.delete(f'showtime_{booking.showtime_id}_seats'))
                    transaction.on_commit(
                        lambda: [_broadcast_seat_update(*d) for d in seat_data])

                    logger.warning(f"Payment DECLINED: user={request.user.id}, "
                                   f"booking={booking.id}")
                    return Response(
                        {"error": "Payment declined. Seats have been released."},
                        status=status.HTTP_402_PAYMENT_REQUIRED
                    )

        except Booking.DoesNotExist:
            return Response({"error": "Booking not found."},
                            status=status.HTTP_404_NOT_FOUND)
        except IntegrityError:
            return Response({"error": "Conflict — please try again."},
                            status=status.HTTP_409_CONFLICT)
        except OperationalError as e:
            logger.error(f"DB error in confirm_booking: {e}", exc_info=True)
            return Response({"error": "Database temporarily unavailable."},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            logger.error(f"Unexpected error in confirm_booking: {e}", exc_info=True)
            return Response({"error": "Internal server error."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # -------------------------------------------------------------------------
    @action(detail=False, methods=['post'])
    def book_seats(self, request):
        """
        Direct booking — Phase 1 + Phase 2 combined (no payment hold).

        Kept for backward compatibility with the existing frontend.
        For the new two-phase flow, use lock_seats + confirm_booking.
        """
        showtime_id = request.data.get('showtime_id')
        seat_ids    = request.data.get('seat_ids', [])

        if not showtime_id or not seat_ids:
            return Response({"error": "showtime_id and seat_ids are required"},
                            status=status.HTTP_400_BAD_REQUEST)

        seat_ids = sorted(seat_ids)

        try:
            seat_data = []
            with transaction.atomic():
                available_seats = ShowSeat.objects.select_for_update()\
                    .select_related('seat').filter(
                        id__in=seat_ids,
                        showtime_id=showtime_id,
                        status=ShowSeat.SeatStatus.AVAILABLE
                    )

                if len(available_seats) != len(seat_ids):
                    return Response(
                        {"error": "One or more seats are no longer available."},
                        status=status.HTTP_409_CONFLICT
                    )

                booking = Booking.objects.create(
                    user=request.user,
                    showtime_id=showtime_id,
                    status=Booking.BookingStatus.CONFIRMED
                )

                for show_seat in available_seats:
                    show_seat.status  = ShowSeat.SeatStatus.BOOKED
                    show_seat.booking = booking
                    show_seat.save()
                    seat_data.append((showtime_id, show_seat.id,
                                      show_seat.seat.seat_number, 'BOOKED'))

                transaction.on_commit(lambda: cache.delete(f'showtime_{showtime_id}_seats'))
                transaction.on_commit(lambda: [_broadcast_seat_update(*d) for d in seat_data])

            from .tasks import send_booking_confirmation
            booking_id_captured = booking.id
            transaction.on_commit(
                lambda: send_booking_confirmation.delay(booking_id_captured))

            logger.info(f"Booking CONFIRMED: user={request.user.id}, "
                        f"showtime={showtime_id}, seats={seat_ids}")
            return Response(BookingSerializer(booking).data,
                            status=status.HTTP_201_CREATED)

        except IntegrityError:
            logger.warning(f"IntegrityError in book_seats: user={request.user.id}, seats={seat_ids}")
            return Response({"error": "Seat conflict — already booked by another user."},
                            status=status.HTTP_409_CONFLICT)
        except OperationalError as e:
            logger.error(f"DB error in book_seats: {e}", exc_info=True)
            return Response({"error": "Database temporarily unavailable."},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            logger.error(f"Unexpected error in book_seats: {e}", exc_info=True)
            return Response({"error": "Internal server error."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
