import django_filters
from .models import Showtime


class ShowtimeFilter(django_filters.FilterSet):
    """
    FilterSet for the Showtime model.

    Supported URL query params:
      ?movie=inception      -> case-insensitive title match
      ?city=Mumbai          -> case-insensitive city match
      ?date=2026-08-20      -> exact date match on start_time

    Example: GET /api/showtimes/?movie=interstellar&city=Metropolis
    """
    movie = django_filters.CharFilter(
        field_name='movie__title',
        lookup_expr='icontains',
        label='Movie title (partial, case-insensitive)'
    )
    city = django_filters.CharFilter(
        field_name='cinema_hall__cinema__city',
        lookup_expr='icontains',
        label='City (partial, case-insensitive)'
    )
    date = django_filters.DateFilter(
        field_name='start_time__date',
        label='Exact show date (YYYY-MM-DD)'
    )

    class Meta:
        model = Showtime
        fields = ['movie', 'city', 'date']
