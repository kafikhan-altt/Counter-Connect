def cart_summary(request):
    """
    Provides quick cart info (count and total) to templates.
    Safe against empty or invalid sessions.
    """
    cart = request.session.get('cart', {})
    items = cart.get('items', {})
    total_qty = sum(items.values()) if isinstance(items, dict) else 0
    return {
        'cart_item_count': total_qty,
        'cart_location_id': cart.get('location_id'),
    }
