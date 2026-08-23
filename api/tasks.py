import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


@shared_task(name='api.tasks.release_expired_locks', bind=True, max_retries=3)
def release_expired_locks(self):
    """
    Periodic Celery Beat task (every 5 minutes via CELERY_BEAT_SCHEDULE).

    Problem it solves — Cart Hoarder Problem:
        A user selects seats and locks them (status=LOCKED) but navigates away
        or closes the browser without completing payment. Those seats remain
        unavailable to everyone else indefinitely.

    Solution:
        Atomically release all ShowSeats locked more than 10 minutes ago
        back to AVAILABLE, and mark their associated PENDING Bookings as FAILED.

    Why .update() instead of per-row .save():
        .update() generates ONE SQL UPDATE statement — faster and avoids
        a race condition where a concurrent transaction modifies a seat
        between our read and write.
    """
    from .models import ShowSeat, Booking

    try:
        cutoff_time = timezone.now() - timedelta(minutes=10)

        # Step 1: Find all expired locked ShowSeats
        expired_seats = ShowSeat.objects.filter(
            status=ShowSeat.SeatStatus.LOCKED,
            locked_at__lt=cutoff_time
        ).select_related('booking')

        # Step 2: Collect their booking IDs before the update clears them
        expired_booking_ids = set(
            seat.booking_id for seat in expired_seats if seat.booking_id
        )

        # Step 3: Atomically release seats (single UPDATE statement)
        released_count = expired_seats.update(
            status=ShowSeat.SeatStatus.AVAILABLE,
            booking=None,
            locked_at=None
        )

        # Step 4: Mark the abandoned PENDING bookings as FAILED
        failed_count = 0
        if expired_booking_ids:
            failed_count = Booking.objects.filter(
                id__in=expired_booking_ids,
                status=Booking.BookingStatus.PENDING
            ).update(status=Booking.BookingStatus.FAILED)

        logger.info(
            f"[release_expired_locks] Released {released_count} seats, "
            f"failed {failed_count} bookings. Cutoff: {cutoff_time}"
        )
        return {'released_seats': released_count, 'failed_bookings': failed_count}

    except Exception as exc:
        logger.error(f"[release_expired_locks] Unexpected error: {exc}", exc_info=True)
        # Exponential backoff: 60s, 120s, 180s
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@shared_task(name='api.tasks.send_booking_confirmation', bind=True, max_retries=3)
def send_booking_confirmation(self, booking_id):
    """
    Async task triggered after a booking is CONFIRMED.

    Why offload to Celery:
        Email/SMS sending is I/O-bound and takes 1-3 seconds.
        Blocking the API response harms UX. With Celery, the API
        returns in ~50ms and this task runs in the background.

    Idempotency note:
        If this task runs twice (e.g., after a retry), the user gets
        a duplicate notification — acceptable. The booking itself is
        not duplicated. For strict idempotency, check a sent_at flag.
    """
    from .models import Booking

    try:
        booking = Booking.objects.select_related(
            'user',
            'showtime__movie',
            'showtime__cinema_hall__cinema'
        ).prefetch_related('seats__seat').get(id=booking_id)

        seat_numbers = ', '.join(
            seat.seat.seat_number for seat in booking.seats.all()
        )

        # In production: replace with send_mail() or push notification API
        logger.info(
            f"[send_booking_confirmation] "
            f"To: {booking.user.email} | "
            f"Movie: {booking.showtime.movie.title} | "
            f"Cinema: {booking.showtime.cinema_hall.cinema.name} | "
            f"Seats: {seat_numbers} | "
            f"Booking ID: {booking_id}"
        )
        return f"Confirmation sent for booking {booking_id}"

    except Exception as exc:
        logger.error(
            f"[send_booking_confirmation] Failed for booking {booking_id}: {exc}",
            exc_info=True
        )
        raise self.retry(exc=exc, countdown=30)
