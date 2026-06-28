from rest_framework import serializers
from .models import Movie, Showtime, ShowSeat, Booking
from django.contrib.auth.models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password']
        )
        return user

class MovieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Movie
        fields = ['id', 'title', 'duration_minutes']

class ShowtimeSerializer(serializers.ModelSerializer):
    movie_title = serializers.CharField(source='movie.title', read_only=True)
    cinema_name = serializers.CharField(source='cinema_hall.cinema.name', read_only=True)
    hall_name = serializers.CharField(source='cinema_hall.name', read_only=True)

    class Meta:
        model = Showtime
        fields = ['id', 'movie_title', 'cinema_name', 'hall_name', 'start_time']

class ShowSeatSerializer(serializers.ModelSerializer):
    seat_number = serializers.CharField(source='seat.seat_number', read_only=True)

    class Meta:
        model = ShowSeat
        fields = ['id', 'seat_number', 'status']

class BookingSerializer(serializers.ModelSerializer):
    seats = ShowSeatSerializer(many=True, read_only=True)
    movie_title = serializers.CharField(source='showtime.movie.title', read_only=True)
    start_time = serializers.DateTimeField(source='showtime.start_time', read_only=True)
    cinema_name = serializers.CharField(source='showtime.cinema_hall.cinema.name', read_only=True)
    
    class Meta:
        model = Booking
        fields = ['id', 'showtime', 'movie_title', 'cinema_name', 'start_time', 'status', 'created_at', 'seats']
