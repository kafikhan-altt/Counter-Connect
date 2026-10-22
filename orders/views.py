import re
from collections import defaultdict
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST, require_GET
from django.contrib import messages
from django.http import JsonResponse, HttpResponseNotAllowed
from django.db import transaction
from django.utils import timezone
from django.urls import reverse
from django.core.mail import send_mail

from .cart import Cart
from .models import Order, VendorOrder, OrderItem, phone_validator
from .utils import (
    generate_pickup_code,
    generate_qr_svg_data_uri,
    generate_qr_svg_inline,
    get_local_lan_ip,
)
from catalog.models import MenuItem, Location


def cart_view(request):
    """Renders the cross-counter cart with live DB validation."""
    cart = Cart(request)
    cart_details = cart.get_details()
    return render(request, 'orders/cart.html', {
        'cart_details': cart_details,
    })


@require_POST
def cart_add(request):
    """Adds a menu item to the cross-counter session cart (POST only)."""
    menu_item_id = request.POST.get('menu_item_id')
    try:
        quantity = int(request.POST.get('quantity', 1))
        if quantity <= 0:
            quantity = 1
    except (ValueError, TypeError):
        quantity = 1

    force_switch = request.POST.get('confirm_switch') == 'true'
    cart = Cart(request)

    success, error_code, message, meta = cart.add(
        menu_item_id=menu_item_id,
        quantity=quantity,
        force_switch=force_switch
    )

    if not success and error_code == 'LOCATION_MISMATCH':
        item = get_object_or_404(MenuItem, pk=menu_item_id)
        return render(request, 'orders/cart_switch_confirm.html', {
            'current_location_name': meta.get('current_location_name'),
            'new_location_name': meta.get('new_location_name'),
            'item': item,
            'quantity': quantity,
        })

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('orders:cart_view')


@require_POST
def cart_update(request):
    """Updates quantity of an item in the cart (POST only)."""
    menu_item_id = request.POST.get('menu_item_id')
    try:
        quantity = int(request.POST.get('quantity', 1))
    except (ValueError, TypeError):
        quantity = 1

    cart = Cart(request)
    success, message = cart.update(menu_item_id, quantity)
    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)
    return redirect('orders:cart_view')


@require_POST
def cart_remove(request):
    """Removes an item from the cart (POST only)."""
    menu_item_id = request.POST.get('menu_item_id')
    cart = Cart(request)
    success, message = cart.remove(menu_item_id)
    if success:
        messages.info(request, message)
    return redirect('orders:cart_view')


@require_POST
def cart_clear(request):
    """Clears the session cart completely (POST only)."""
    cart = Cart(request)
    cart.clear()
    messages.info(request, "Your cart has been cleared.")
    return redirect('orders:cart_view')


def checkout_view(request):
    """
    Guest checkout view:
    GET: review cart, enter name and phone.
    POST: executes Section 9 order placement algorithm atomically.
    """
    cart = Cart(request)
    cart_details = cart.get_details()

    # Step 1: Double-submit & empty cart guard
    if not cart_details['location'] or cart_details['total_quantity'] == 0:
        messages.info(request, "Your cart is empty. Please add items to begin.")
        return redirect('catalog:home')

    # Step 1b: If cart has sold-out items or closed stalls, redirect back to cart
    if cart_details['has_issues']:
        messages.error(request, "Some items in your cart cannot be ordered. Please resolve them first.")
        return redirect('orders:cart_view')

    if request.method == 'POST':
        customer_name = request.POST.get('customer_name', '').strip()
        customer_phone = request.POST.get('customer_phone', '').strip()
        customer_email = request.POST.get('customer_email', '').strip()

        # Step 2: Validate customer inputs
        errors = []
        if len(customer_name) < 2 or len(customer_name) > 50:
            errors.append("Name must be between 2 and 50 characters.")

        if not re.match(r'^[6-9]\d{9}$', customer_phone):
            errors.append("Enter a valid 10-digit Indian phone number starting with 6, 7, 8, or 9.")

        location = cart_details['location']
        items_dict = cart.cart.get('items', {})
        today = timezone.localdate()

        # Step 3 & 4: Load and verify items from DB with select_related
        item_ids = [int(k) for k in items_dict.keys()]
        menu_items = list(
            MenuItem.objects.filter(id__in=item_ids)
            .select_related('business', 'business__location')
        )
        items_map = {item.id: item for item in menu_items}

        if len(menu_items) != len(item_ids):
            errors.append("One or more items in your cart no longer exist. Please review your cart.")

        for item_id_str, qty in items_dict.items():
            item_id = int(item_id_str)
            item = items_map.get(item_id)
            if item:
                if not item.is_available:
                    errors.append(f"'{item.name}' has just sold out.")
                if not item.business.is_open:
                    errors.append(f"Counter '{item.business.name}' is closed.")
                if item.business.location_id != location.id:
                    errors.append(f"'{item.name}' does not belong to {location.name}.")
                if qty < 1 or qty > 10:
                    errors.append(f"Invalid quantity ({qty}) for '{item.name}'.")

        # Step 5: Abuse guard (max 3 active orders per phone at this location today)
        active_orders_today = Order.objects.filter(
            location=location,
            customer_phone=customer_phone,
            order_date=today
        ).prefetch_related('vendor_orders')

        uncompleted_count = 0
        for ord_obj in active_orders_today:
            if ord_obj.status not in ('COMPLETED', 'CANCELLED'):
                uncompleted_count += 1

        if uncompleted_count >= 3:
            errors.append(
                "You already have 3 active orders at this food court today. "
                "Please collect or cancel them before placing a new one."
            )

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, 'orders/checkout.html', {
                'cart_details': cart_details,
                'customer_name': customer_name,
                'customer_phone': customer_phone,
                'customer_email': customer_email,
            })

        # Step 6-9: Atomic order creation
        with transaction.atomic():
            pickup_code = generate_pickup_code(location, today)

            order = Order.objects.create(
                location=location,
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_email=customer_email,
                pickup_code=pickup_code,
                order_date=today
            )

            # Group items by business
            business_items_map = defaultdict(list)
            for item_id_str, qty in items_dict.items():
                item = items_map[int(item_id_str)]
                business_items_map[item.business].append((item, qty))

            for business, b_items in business_items_map.items():
                vendor_order = VendorOrder.objects.create(
                    order=order,
                    business=business,
                    status=VendorOrder.STATUS_PLACED
                )
                for item, qty in b_items:
                    OrderItem.objects.create(
                        vendor_order=vendor_order,
                        menu_item=item,
                        item_name=item.name,  # Price & Name Snapshot
                        unit_price=item.price,
                        quantity=qty
                    )

            # Clear session cart
            cart.clear()

        # Optional Email Notification
        if customer_email:
            try:
                tracking_url = request.build_absolute_uri(
                    reverse('orders:order_tracking', kwargs={'public_id': order.public_id})
                )
                items_summary_lines = []
                for vo in order.vendor_orders.all():
                    items_summary_lines.append(f"[{vo.business.name}]")
                    for itm in vo.items.all():
                        items_summary_lines.append(f"  • {itm.quantity}x {itm.item_name} — ₹{itm.line_total}")
                    items_summary_lines.append(f"  Subtotal: ₹{vo.subtotal}\n")

                items_text = "\n".join(items_summary_lines)
                subject = f"Thanks for ordering! Pre-Order #{order.pickup_code} at {order.location.name}"
                body = (
                    f"Hi {order.customer_name},\n\n"
                    f"Thanks for your pre-order at {order.location.name}!\n\n"
                    f"SINGLE PICKUP CODE: {order.pickup_code}\n\n"
                    f"Order Details:\n{items_text}\n"
                    f"Total Payable at Counters: ₹{order.total_amount}\n\n"
                    f"Track Live Order Status:\n{tracking_url}\n\n"
                    f"Simply show your 4-character pickup code ({order.pickup_code}) or the QR code at each counter to collect your food!\n\n"
                    f"— CounterConnect"
                )
                send_mail(
                    subject=subject,
                    message=body,
                    from_email=None,
                    recipient_list=[customer_email],
                    fail_silently=True
                )
            except Exception:
                pass

        messages.success(request, f"Order placed successfully! Pickup code: {order.pickup_code}")
        return redirect('orders:order_tracking', public_id=order.public_id)

    return render(request, 'orders/checkout.html', {
        'cart_details': cart_details,
    })


def order_tracking(request, public_id):
    """
    Customer order tracking page:
    Shows pickup code BIG, QR code (segno), live status of each counter.
    Automatically formats QR URL with local Wi-Fi IP so phone cameras can open it.
    """
    order = get_object_or_404(
        Order.objects.select_related('location').prefetch_related(
            'vendor_orders__business',
            'vendor_orders__items'
        ),
        public_id=public_id
    )

    tracking_url = request.build_absolute_uri(
        reverse('orders:order_tracking', kwargs={'public_id': order.public_id})
    )

    # For scanning from smartphone camera over local Wi-Fi:
    # If the user accessed via 127.0.0.1 or localhost, rewrite host in QR to LAN IP
    host = request.get_host()
    qr_url = tracking_url
    if host.startswith('127.0.0.1') or host.startswith('localhost'):
        lan_ip = get_local_lan_ip()
        port = host.split(':')[1] if ':' in host else '8000'
        qr_url = tracking_url.replace(f"http://{host}", f"http://{lan_ip}:{port}").replace(f"https://{host}", f"https://{lan_ip}:{port}")

    qr_svg_uri = generate_qr_svg_data_uri(qr_url)
    qr_svg_inline = generate_qr_svg_inline(qr_url)

    return render(request, 'orders/tracking.html', {
        'order': order,
        'qr_svg_uri': qr_svg_uri,
        'qr_svg_inline': qr_svg_inline,
        'tracking_url': tracking_url,
        'qr_url': qr_url,
    })


@require_GET
def order_status_json(request, public_id):
    """
    JSON API for live polling order status every 5s.
    """
    order = get_object_or_404(
        Order.objects.prefetch_related('vendor_orders__business'),
        public_id=public_id
    )

    vos = []
    for vo in order.vendor_orders.all():
        vos.append({
            'business_name': vo.business.name,
            'status': vo.status,
            'reject_reason': vo.reject_reason,
            'subtotal': str(vo.subtotal),
        })

    return JsonResponse({
        'public_id': str(order.public_id),
        'status': order.status,
        'is_fully_ready': order.is_fully_ready,
        'is_cancellable': order.is_cancellable,
        'total_amount': str(order.total_amount),
        'estimated_ready_at': order.estimated_ready_at.strftime('%I:%M %p') if order.estimated_ready_at else '',
        'vendor_orders': vos,
    })


@require_POST
def order_cancel(request, public_id):
    """
    Allows customer to cancel order while all parts are PLACED.
    Transitions all PLACED parts to CANCELLED atomically.
    """
    order = get_object_or_404(Order, public_id=public_id)

    if not order.is_cancellable:
        messages.error(request, "Too late to cancel — one or more counters have already started preparing your food.")
        return redirect('orders:order_tracking', public_id=order.public_id)

    with transaction.atomic():
        for vo in order.vendor_orders.all():
            if vo.status == VendorOrder.STATUS_PLACED:
                vo.transition_to(VendorOrder.STATUS_CANCELLED, actor_role='customer')

    messages.info(request, "Your order has been cancelled.")
    return redirect('orders:order_tracking', public_id=order.public_id)


def find_order(request):
    """
    Find order by phone number and 4-character pickup code.
    Scopes to today's date for privacy and speed.
    """
    if request.method == 'POST':
        phone = request.POST.get('phone', '').strip()
        pickup_code = request.POST.get('pickup_code', '').strip().upper()
        today = timezone.localdate()

        order = Order.objects.filter(
            customer_phone=phone,
            pickup_code=pickup_code,
            order_date=today
        ).first()

        if order:
            return redirect('orders:order_tracking', public_id=order.public_id)
        else:
            messages.error(request, "No matching order found for today. Please verify your phone number and pickup code.")

    return render(request, 'orders/find_order.html')
