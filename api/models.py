from django.db import models
from django.contrib.auth.models import User


class Cinema(models.Model):
    name = models.CharField(max_length=100)
    city = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} ({self.city})"


class CinemaHall(models.Model):
    cinema = models.ForeignKey(Cinema, on_delete=models.CASCADE, related_name='halls')
    name = models.CharField(max_length=50)  # e.g., "IMAX Screen 1"
    total_seats = models.IntegerField()

    def __str__(self):
        return f"{self.cinema.name} — {self.name}"


class Movie(models.Model):
    title = models.CharField(max_length=200)
    duration_minutes = models.IntegerField()

    def __str__(self):
        return self.title


class Showtime(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.PROTECT, related_name='showtimes')
    cinema_hall = models.ForeignKey(CinemaHall, on_delete=models.CASCADE, related_name='showtimes')
    start_time = models.DateTimeField(db_index=True)   # Indexed for fast date filtering
    end_time = models.DateTimeField()
    price_per_seat = models.DecimalField(max_digits=6, decimal_places=2, default=250.00)

    def __str__(self):
        return f"{self.movie.title} @ {self.cinema_hall.name} — {self.start_time}"


class Seat(models.Model):
    """Represents a physical, permanent seat in a specific CinemaHall."""
    cinema_hall = models.ForeignKey(CinemaHall, on_delete=models.CASCADE, related_name='seats')
    seat_number = models.CharField(max_length=10)  # e.g., A1, B2

    class Meta:
        unique_together = ('cinema_hall', 'seat_number')

    def __str__(self):
        return f"{self.cinema_hall.name} — Seat {self.seat_number}"


class Booking(models.Model):
    class BookingStatus(models.TextChoices):
        PENDING   = 'PENDING',   'Pending'    # Seats locked, awaiting payment
        CONFIRMED = 'CONFIRMED', 'Confirmed'  # Payment received
        FAILED    = 'FAILED',    'Failed'     # Expired lock or payment failure

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    showtime = models.ForeignKey(Showtime, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=20,
        choices=BookingStatus.choices,
        default=BookingStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Booking #{self.id} — {self.user.username} — {self.status}"


class ShowSeat(models.Model):
    """
    Represents the temporal state of a physical Seat for a specific Showtime.

    Key design decision:
        A Seat (e.g., A1 in Hall 1) exists permanently. But its availability
        changes per-showtime. This model tracks that per-show state.
        unique_together('showtime', 'seat') is the DB-level guard against
        double booking — even if application logic fails.
    """
    class SeatStatus(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available'
        LOCKED    = 'LOCKED',    'Locked'   # Held while user is in checkout
        BOOKED    = 'BOOKED',    'Booked'   # Confirmed and paid

    showtime = models.ForeignKey(Showtime, on_delete=models.CASCADE, related_name='show_seats')
    seat = models.ForeignKey(Seat, on_delete=models.CASCADE)
    booking = models.ForeignKey(
        Booking, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='seats'
    )
    status = models.CharField(
        max_length=20,
        choices=SeatStatus.choices,
        default=SeatStatus.AVAILABLE,
        db_index=True    # Indexed for fast WHERE status='AVAILABLE' queries
    )
    locked_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Timestamp when seat entered LOCKED state. Used by Celery to release expired locks."
    )

    class Meta:
        unique_together = ('showtime', 'seat')

    def __str__(self):
        return f"ShowSeat: {self.seat.seat_number} @ Showtime#{self.showtime_id} — {self.status}"

# =============================================================================
# SIGNALS: Automating Cache Invalidation & Seat Generation
# =============================================================================
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

@receiver([post_save, post_delete], sender=Showtime)
def invalidate_showtime_cache(sender, instance, **kwargs):
    """
    Cache Invalidation: 
    Whenever a Showtime is added, edited, or deleted (e.g. from the Admin panel),
    we immediately delete the 'all_showtimes_list' from Redis. 
    This ensures the frontend instantly reflects the new schedule!
    """
    cache.delete('all_showtimes_list')


@receiver(post_save, sender=Showtime)
def generate_show_seats(sender, instance, created, **kwargs):
    """
    Auto-generation:
    When you create a new Showtime in the Django Admin, this signal automatically
    generates all the physical ShowSeat records for that specific showtime based 
    on the CinemaHall's capacity. Without this, the seating chart would be empty!
    """
    if created:
        # Get all physical seats belonging to this hall
        seats = Seat.objects.filter(cinema_hall=instance.cinema_hall)
        
        # Bulk create the ShowSeat records mapped to this new showtime
        show_seats = [ShowSeat(showtime=instance, seat=seat) for seat in seats]
        ShowSeat.objects.bulk_create(show_seats)
