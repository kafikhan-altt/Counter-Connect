from django.shortcuts import render, get_object_or_404
from django.db.models import Q
from .models import Location, Business, MenuItem


def home(request):
    """Home view showing active food courts and search bar."""
    locations = Location.objects.filter(is_active=True).prefetch_related('businesses')
    return render(request, 'catalog/home.html', {
        'locations': locations,
    })


def search_locations(request):
    """Search active locations by name or city (case-insensitive)."""
    query = request.GET.get('q', '').strip()
    results = Location.objects.none()

    if query:
        results = Location.objects.filter(
            Q(name__icontains=query) | Q(city__icontains=query),
            is_active=True
        ).distinct()

    return render(request, 'catalog/search_results.html', {
        'query': query,
        'results': results,
    })


def location_detail(request, slug):
    """
    Core page: 'One location, every counter, one page'.
    Renders every business and its menu items for the location.
    """
    location = get_object_or_404(Location, slug=slug, is_active=True)
    businesses = location.businesses.all().order_by('display_order', 'name').prefetch_related('menu_items')

    # Calculate cart total if current session cart is for this location
    cart = request.session.get('cart', {})
    cart_for_this_location = (cart.get('location_id') == location.id)
    cart_items = cart.get('items', {}) if cart_for_this_location else {}
    cart_item_count = sum(cart_items.values())

    return render(request, 'catalog/location_detail.html', {
        'location': location,
        'businesses': businesses,
        'cart_for_this_location': cart_for_this_location,
        'cart_item_count': cart_item_count,
    })
