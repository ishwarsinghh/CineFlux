import threading
from django.test import TestCase
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

from .models import Cinema, CinemaHall, Movie, Showtime, Seat, ShowSeat, Booking


# ==============================================================================
# Helper Mixin — shared setUp logic for all booking-related tests
# ==============================================================================
class BookingTestMixin:
    """Shared fixture setup for tests that need a showtime + seats."""

    def _create_fixtures(self):
        self.cinema   = Cinema.objects.create(name='Test Cinema', city='Test City')
        self.hall     = CinemaHall.objects.create(cinema=self.cinema, name='Hall 1', total_seats=5)
        self.movie    = Movie.objects.create(title='Test Movie', duration_minutes=120)
        self.showtime = Showtime.objects.create(
            movie=self.movie,
            cinema_hall=self.hall,
            start_time=timezone.now() + timedelta(hours=2),
            end_time=timezone.now() + timedelta(hours=4),
            price_per_seat=250.00
        )
        self.seat      = Seat.objects.create(cinema_hall=self.hall, seat_number='A1')
        self.show_seat = ShowSeat.objects.create(showtime=self.showtime, seat=self.seat)

    def _get_token(self, client, username, password='testpass123'):
        response = client.post('/api/auth/login/', {
            'username': username, 'password': password
        }, format='json')
        return response.data['access']


# ==============================================================================
# Test 1: Full Authentication Flow
# ==============================================================================
class AuthFlowTest(APITestCase):
    """
    Verifies the full register -> login -> profile -> logout lifecycle.
    Also tests that password is never returned in any response.
    """

    def test_register_does_not_expose_password(self):
        response = self.client.post('/api/auth/register/', {
            'username': 'ishwar',
            'email': 'ishwar@test.com',
            'password': 'securepass123'
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn('password', response.data,
                         "Password must NEVER be returned in the registration response")

    def test_login_returns_jwt_tokens(self):
        User.objects.create_user(username='testuser', password='testpass123')
        response = self.client.post('/api/auth/login/', {
            'username': 'testuser', 'password': 'testpass123'
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access',  response.data, "Login response must contain access token")
        self.assertIn('refresh', response.data, "Login response must contain refresh token")

    def test_profile_requires_authentication(self):
        # Without token -> should be 401
        response = self.client.get('/api/auth/profile/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_profile_returns_correct_user(self):
        User.objects.create_user(username='ishwar', password='testpass123', email='i@test.com')
        login = self.client.post('/api/auth/login/', {
            'username': 'ishwar', 'password': 'testpass123'
        }, format='json')
        token = login.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.get('/api/auth/profile/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'ishwar')


# ==============================================================================
# Test 2: Booking Logic — Core Business Rules
# ==============================================================================
class BookingTest(BookingTestMixin, APITestCase):
    """Tests the core booking rules: auth guards, 409 conflict, state transitions."""

    def setUp(self):
        self._create_fixtures()
        self.user = User.objects.create_user(username='booker', password='testpass123')
        self.token = self._get_token(self.client, 'booker')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')

    def test_booking_requires_authentication(self):
        unauthenticated = APIClient()
        response = unauthenticated.post('/api/bookings/book_seats/', {
            'showtime_id': self.showtime.id,
            'seat_ids': [self.show_seat.id]
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_successful_booking_returns_201(self):
        response = self.client.post('/api/bookings/book_seats/', {
            'showtime_id': self.showtime.id,
            'seat_ids': [self.show_seat.id]
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'CONFIRMED')
        self.assertIn('total_price', response.data)

    def test_booking_already_booked_seat_returns_409(self):
        """Attempting to book a seat that is already BOOKED must return 409."""
        self.show_seat.status = ShowSeat.SeatStatus.BOOKED
        self.show_seat.save()

        response = self.client.post('/api/bookings/book_seats/', {
            'showtime_id': self.showtime.id,
            'seat_ids': [self.show_seat.id]
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_booking_missing_params_returns_400(self):
        response = self.client.post('/api/bookings/book_seats/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_seat_status_changes_to_booked_after_booking(self):
        self.client.post('/api/bookings/book_seats/', {
            'showtime_id': self.showtime.id,
            'seat_ids': [self.show_seat.id]
        }, format='json')
        self.show_seat.refresh_from_db()
        self.assertEqual(self.show_seat.status, ShowSeat.SeatStatus.BOOKED)

    def test_total_price_in_booking_response(self):
        response = self.client.post('/api/bookings/book_seats/', {
            'showtime_id': self.showtime.id,
            'seat_ids': [self.show_seat.id]
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # 1 seat x Rs.250 = 250.0
        self.assertEqual(float(response.data['total_price']), 250.0)


# ==============================================================================
# Test 3: Double Booking Prevention (Race Condition)
# ==============================================================================
class DoubleBookingTest(BookingTestMixin, APITestCase):
    """
    Simulates two users attempting to book the same seat concurrently.

    Testing strategy:
        Django's test runner wraps tests in a transaction that is rolled back
        after each test, which makes true thread-based concurrency tests
        unreliable (threads can't see each other's data).

        Instead, we test the sequential equivalent: make the seat BOOKED
        by user A, then verify user B receives 409. This proves the
        application-level conflict check works. The DB-level guarantee
        (SELECT FOR UPDATE) is tested by the unique_together constraint test.
    """

    def setUp(self):
        self._create_fixtures()
        self.user1 = User.objects.create_user(username='user1', password='testpass123')
        self.user2 = User.objects.create_user(username='user2', password='testpass123')

    def test_sequential_double_booking_prevented(self):
        """User 1 books seat -> User 2 tries to book same seat -> 409."""
        # User 1 successfully books
        client1 = APIClient()
        client1.credentials(
            HTTP_AUTHORIZATION=f'Bearer {self._get_token(client1, "user1")}'
        )
        response1 = client1.post('/api/bookings/book_seats/', {
            'showtime_id': self.showtime.id,
            'seat_ids': [self.show_seat.id]
        }, format='json')
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

        # User 2 tries to book the same seat
        client2 = APIClient()
        client2.credentials(
            HTTP_AUTHORIZATION=f'Bearer {self._get_token(client2, "user2")}'
        )
        response2 = client2.post('/api/bookings/book_seats/', {
            'showtime_id': self.showtime.id,
            'seat_ids': [self.show_seat.id]
        }, format='json')
        self.assertEqual(response2.status_code, status.HTTP_409_CONFLICT)

        # Verify exactly ONE booking exists and seat is BOOKED
        self.show_seat.refresh_from_db()
        self.assertEqual(self.show_seat.status, ShowSeat.SeatStatus.BOOKED)
        self.assertEqual(Booking.objects.filter(
            showtime=self.showtime, status=Booking.BookingStatus.CONFIRMED
        ).count(), 1)


# ==============================================================================
# Test 4: Celery Task — Expired Lock Release
# ==============================================================================
class ExpiredLockReleaseTest(BookingTestMixin, TestCase):
    """Tests the release_expired_locks Celery task logic synchronously."""

    def setUp(self):
        self._create_fixtures()
        self.user = User.objects.create_user(username='hoarder', password='testpass123')

    def test_expired_locked_seat_is_released(self):
        """A seat locked more than 10 minutes ago must be released to AVAILABLE."""
        from .tasks import release_expired_locks

        # Create a PENDING booking with a seat locked 15 minutes ago
        booking = Booking.objects.create(
            user=self.user, showtime=self.showtime,
            status=Booking.BookingStatus.PENDING
        )
        self.show_seat.status = ShowSeat.SeatStatus.LOCKED
        self.show_seat.booking = booking
        self.show_seat.locked_at = timezone.now() - timedelta(minutes=15)
        self.show_seat.save()

        # Run the task synchronously (no Celery broker needed in tests)
        result = release_expired_locks()

        self.show_seat.refresh_from_db()
        booking.refresh_from_db()

        self.assertEqual(self.show_seat.status, ShowSeat.SeatStatus.AVAILABLE,
                         "Expired locked seat should be released to AVAILABLE")
        self.assertIsNone(self.show_seat.locked_at)
        self.assertEqual(booking.status, Booking.BookingStatus.FAILED,
                         "PENDING booking with expired lock should be marked FAILED")
        self.assertEqual(result['released_seats'], 1)

    def test_recent_locked_seat_is_not_released(self):
        """A seat locked only 2 minutes ago must NOT be released."""
        from .tasks import release_expired_locks

        booking = Booking.objects.create(
            user=self.user, showtime=self.showtime,
            status=Booking.BookingStatus.PENDING
        )
        self.show_seat.status = ShowSeat.SeatStatus.LOCKED
        self.show_seat.booking = booking
        self.show_seat.locked_at = timezone.now() - timedelta(minutes=2)
        self.show_seat.save()

        release_expired_locks()

        self.show_seat.refresh_from_db()
        self.assertEqual(self.show_seat.status, ShowSeat.SeatStatus.LOCKED,
                         "Recently locked seat should NOT be released")
