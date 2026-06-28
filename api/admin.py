from django.contrib import admin
from .models import Cinema, CinemaHall, Movie, Showtime, Seat, Booking, ShowSeat

admin.site.register(Cinema)
admin.site.register(CinemaHall)
admin.site.register(Movie)
admin.site.register(Showtime)
admin.site.register(Seat)
admin.site.register(Booking)
admin.site.register(ShowSeat)
