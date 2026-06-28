from django.db import models
from django.contrib.auth.models import User

class Cinema(models.Model):
    name = models.CharField(max_length=100)
    city = models.CharField(max_length=100)

class CinemaHall(models.Model):
    cinema = models.ForeignKey(Cinema, on_delete=models.CASCADE, related_name='halls')
    name = models.CharField(max_length=50) # e.g., "IMAX Screen 1"
    total_seats = models.IntegerField()

class Movie(models.Model):
    title = models.CharField(max_length=200)
    duration_minutes = models.IntegerField()

class Showtime(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='showtimes')
    cinema_hall = models.ForeignKey(CinemaHall, on_delete=models.CASCADE, related_name='showtimes')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

class Seat(models.Model):
    """Represents a physical seat in a specific hall."""
    cinema_hall = models.ForeignKey(CinemaHall, on_delete=models.CASCADE, related_name='seats')
    seat_number = models.CharField(max_length=10) # e.g., A1, B2
    
    class Meta:
        unique_together = ('cinema_hall', 'seat_number')

class Booking(models.Model):
    class BookingStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        FAILED = 'FAILED', 'Failed'

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    showtime = models.ForeignKey(Showtime, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

class ShowSeat(models.Model):
    """Represents the temporal state of a seat for a specific showtime."""
    class SeatStatus(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available'
        LOCKED = 'LOCKED', 'Locked'     # Locked while in user's cart
        BOOKED = 'BOOKED', 'Booked'     # Paid and confirmed

    showtime = models.ForeignKey(Showtime, on_delete=models.CASCADE, related_name='show_seats')
    seat = models.ForeignKey(Seat, on_delete=models.CASCADE)
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='seats')
    status = models.CharField(max_length=20, choices=SeatStatus.choices, default=SeatStatus.AVAILABLE)
    
    class Meta:
        unique_together = ('showtime', 'seat')
