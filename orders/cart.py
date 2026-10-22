from decimal import Decimal
from django.shortcuts import get_object_or_404
from catalog.models import MenuItem, Location, Business


class Cart:
    """
    Session-backed cart satisfying Core Invariants:
    1. Stores IDs and quantities only, never prices or names.
    2. Scoped to exactly ONE Location.
    3. Re-reads and re-validates against DB on every retrieval.
    """

    def __init__(self, request):
        self.session = request.session
        cart = self.session.get('cart')
        if not cart or not isinstance(cart, dict):
            cart = {'location_id': None, 'items': {}}
            self.session['cart'] = cart
        self.cart = cart

    def save(self):
        self.session.modified = True

    def clear(self):
        self.cart['location_id'] = None
        self.cart['items'] = {}
        self.save()

    @property
    def location_id(self):
        return self.cart.get('location_id')

    @property
    def total_quantity(self):
        return sum(int(qty) for qty in self.cart.get('items', {}).values())

    def add(self, menu_item_id, quantity=1, force_switch=False):
        """
        Add an item to cart.
        Returns: (success: bool, error_code: str or None, message: str, meta: dict)
        """
        menu_item = get_object_or_404(
            MenuItem.objects.select_related('business', 'business__location'),
            pk=menu_item_id
        )
        item_location = menu_item.business.location

        # Check location scoping
        current_loc_id = self.cart.get('location_id')
        if current_loc_id and current_loc_id != item_location.id:
            if not force_switch:
                current_loc = Location.objects.filter(id=current_loc_id).first()
                current_loc_name = current_loc.name if current_loc else "another food court"
                return False, 'LOCATION_MISMATCH', (
                    f"Your cart contains items from {current_loc_name}. "
                    f"Would you like to clear your cart and start a new order at {item_location.name}?"
                ), {
                    'current_location_id': current_loc_id,
                    'current_location_name': current_loc_name,
                    'new_location_id': item_location.id,
                    'new_location_name': item_location.name,
                    'menu_item_id': menu_item_id,
                }
            else:
                self.clear()

        # Check counter open & item availability
        if not menu_item.business.is_open:
            return False, 'COUNTER_CLOSED', f"{menu_item.business.name} is currently closed.", {}
        if not menu_item.is_available:
            return False, 'ITEM_UNAVAILABLE', f"'{menu_item.name}' is currently sold out.", {}

        # Validate line quantity
        item_id_str = str(menu_item.id)
        current_qty = self.cart['items'].get(item_id_str, 0)
        new_qty = current_qty + quantity

        if new_qty > 10:
            return False, 'QTY_LIMIT_EXCEEDED', f"Maximum 10 of '{menu_item.name}' allowed per order.", {}

        if (self.total_quantity + quantity) > 30:
            return False, 'TOTAL_LIMIT_EXCEEDED', "Maximum 30 items allowed across all counters in one pre-order.", {}

        self.cart['location_id'] = item_location.id
        self.cart['items'][item_id_str] = new_qty
        self.save()
        return True, None, f"Added {menu_item.name} to cart.", {}

    def update(self, menu_item_id, quantity):
        """Update or remove item quantity."""
        item_id_str = str(menu_item_id)
        if quantity <= 0:
            self.cart['items'].pop(item_id_str, None)
            if not self.cart['items']:
                self.cart['location_id'] = None
            self.save()
            return True, "Item removed from cart."

        if quantity > 10:
            return False, "Maximum 10 quantity per item."

        other_items_total = sum(
            qty for k, qty in self.cart['items'].items() if k != item_id_str
        )
        if (other_items_total + quantity) > 30:
            return False, "Maximum 30 total items allowed per order."

        self.cart['items'][item_id_str] = quantity
        self.save()
        return True, "Cart updated."

    def remove(self, menu_item_id):
        return self.update(menu_item_id, 0)

    def get_details(self):
        """
        Re-reads all items from database and validates live availability.
        Groups items by Business / Counter.
        Computes subtotals per counter and grand total.
        Flags any lines that are sold out or belonging to closed counters.
        """
        location_id = self.cart.get('location_id')
        items_dict = self.cart.get('items', {})

        if not location_id or not items_dict:
            return {
                'location': None,
                'groups': [],
                'grand_total': Decimal('0.00'),
                'total_quantity': 0,
                'has_issues': False,
                'issue_messages': [],
            }

        location = Location.objects.filter(id=location_id).first()
        item_ids = [int(k) for k in items_dict.keys()]
        menu_items = MenuItem.objects.filter(id__in=item_ids).select_related('business', 'business__location')
        menu_items_map = {item.id: item for item in menu_items}

        groups_map = {}
        grand_total = Decimal('0.00')
        total_quantity = 0
        has_issues = False
        issue_messages = []

        for item_id_str, qty in list(items_dict.items()):
            item_id = int(item_id_str)
            item = menu_items_map.get(item_id)

            if not item:
                # Item was deleted from DB
                has_issues = True
                issue_messages.append(f"An item in your cart is no longer available. Please remove it.")
                continue

            business = item.business
            unit_price = item.price
            line_total = unit_price * qty
            total_quantity += qty

            # Live checks
            is_blocked = False
            block_reason = None
            if not business.is_open:
                is_blocked = True
                block_reason = f"Counter '{business.name}' is currently closed"
                has_issues = True
                issue_messages.append(f"{business.name} is closed. Please remove its items.")
            elif not item.is_available:
                is_blocked = True
                block_reason = f"'{item.name}' is sold out"
                has_issues = True
                issue_messages.append(f"'{item.name}' is sold out. Please remove it.")
            elif business.location_id != location_id:
                is_blocked = True
                block_reason = "Location mismatch"
                has_issues = True
                issue_messages.append(f"'{item.name}' does not belong to {location.name}.")

            if not is_blocked:
                grand_total += line_total

            if business.id not in groups_map:
                groups_map[business.id] = {
                    'business': business,
                    'items': [],
                    'subtotal': Decimal('0.00'),
                    'has_blocked_item': False,
                }

            groups_map[business.id]['items'].append({
                'item': item,
                'quantity': qty,
                'unit_price': unit_price,
                'line_total': line_total,
                'is_blocked': is_blocked,
                'block_reason': block_reason,
            })
            if not is_blocked:
                groups_map[business.id]['subtotal'] += line_total
            else:
                groups_map[business.id]['has_blocked_item'] = True

        return {
            'location': location,
            'groups': list(groups_map.values()),
            'grand_total': grand_total,
            'total_quantity': total_quantity,
            'has_issues': has_issues,
            'issue_messages': list(set(issue_messages)),
        }
