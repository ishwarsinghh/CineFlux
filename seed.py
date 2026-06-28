import os
import django
from datetime import timedelta
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cineflux.settings')
django.setup()

from api.models import Cinema, CinemaHall, Movie, Showtime, Seat, ShowSeat
from django.contrib.auth.models import User

def seed_db():
    print("Clearing old data...")
    User.objects.all().delete()
    Cinema.objects.all().delete()
    Movie.objects.all().delete()

    
    print("Creating Movie...")
    movie = Movie.objects.create(title="Inception: IMAX Re-release", duration_minutes=148)
    movie2 = Movie.objects.create(title="Interstellar", duration_minutes=169)

    print("Creating Cinema & Hall...")
    cinema = Cinema.objects.create(name="Starlight Cinemas", city="Metropolis")
    hall1 = CinemaHall.objects.create(cinema=cinema, name="IMAX Screen 1", total_seats=20)
    hall2 = CinemaHall.objects.create(cinema=cinema, name="Screen 2", total_seats=20)

    print("Creating Seats...")
    seats1 = []
    for row in ['A', 'B', 'C', 'D']:
        for col in range(1, 6):
            seats1.append(Seat(cinema_hall=hall1, seat_number=f"{row}{col}"))
    Seat.objects.bulk_create(seats1)

    seats2 = []
    for row in ['A', 'B', 'C', 'D']:
        for col in range(1, 6):
            seats2.append(Seat(cinema_hall=hall2, seat_number=f"{row}{col}"))
    Seat.objects.bulk_create(seats2)

    print("Creating Showtimes & ShowSeats...")
    now = timezone.now()
    
    # Showtime 1
    st1 = Showtime.objects.create(
        movie=movie,
        cinema_hall=hall1,
        start_time=now + timedelta(days=1, hours=19), # Tomorrow 7 PM
        end_time=now + timedelta(days=1, hours=21, minutes=28)
    )
    show_seats = [ShowSeat(showtime=st1, seat=s) for s in Seat.objects.filter(cinema_hall=hall1)]
    ShowSeat.objects.bulk_create(show_seats)

    # Showtime 2
    st2 = Showtime.objects.create(
        movie=movie2,
        cinema_hall=hall2,
        start_time=now + timedelta(days=2, hours=20),
        end_time=now + timedelta(days=2, hours=23)
    )
    show_seats2 = [ShowSeat(showtime=st2, seat=s) for s in Seat.objects.filter(cinema_hall=hall2)]
    ShowSeat.objects.bulk_create(show_seats2)

    print("Database seeded successfully! 🎉")

if __name__ == "__main__":
    seed_db()
