from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.contrib import messages
from django.http import JsonResponse, Http404
from django.utils import timezone
from django.core.exceptions import ValidationError

from catalog.models import Business, MenuItem
from orders.models import VendorOrder, Order


def get_user_businesses(user):
    return Business.objects.filter(owner=user)


@login_required
def vendor_dashboard(request):
    """
    Vendor Dashboard:
    - Scoped strictly to businesses where business.owner == request.user
    - Displays today's orders in tabs: New, Preparing, Ready, Done
    - Collect by pickup code tool
    """
    businesses = get_user_businesses(request.user)
    if not businesses.exists():
        return render(request, 'orders/vendor/no_business.html')

    today = timezone.localdate()
    vendor_orders = (
        VendorOrder.objects.filter(
            business__in=businesses,
            order__order_date=today
        )
        .select_related('order', 'business')
        .prefetch_related('items')
        .order_by('-created_at')
    )

    new_orders = [vo for vo in vendor_orders if vo.status == VendorOrder.STATUS_PLACED]
    preparing_orders = [vo for vo in vendor_orders if vo.status == VendorOrder.STATUS_PREPARING]
    ready_orders = [vo for vo in vendor_orders if vo.status == VendorOrder.STATUS_READY]
    done_orders = [
        vo for vo in vendor_orders
        if vo.status in (VendorOrder.STATUS_COLLECTED, VendorOrder.STATUS_REJECTED, VendorOrder.STATUS_CANCELLED)
    ]

    return render(request, 'orders/vendor/dashboard.html', {
        'businesses': businesses,
        'new_orders': new_orders,
        'preparing_orders': preparing_orders,
        'ready_orders': ready_orders,
        'done_orders': done_orders,
        'new_count': len(new_orders),
        'preparing_count': len(preparing_orders),
        'ready_count': len(ready_orders),
        'done_count': len(done_orders),
    })


@login_required
@require_GET
def vendor_orders_json(request):
    """
    Live polling endpoint for vendor dashboard.
    Returns counts and lightweight order status list for today.
    """
    businesses = get_user_businesses(request.user)
    if not businesses.exists():
        return JsonResponse({'new_count': 0, 'preparing_count': 0, 'ready_count': 0, 'orders': []})

    today = timezone.localdate()
    vendor_orders = (
        VendorOrder.objects.filter(
            business__in=businesses,
            order__order_date=today
        )
        .select_related('order')
        .order_by('-created_at')
    )

    new_count = vendor_orders.filter(status=VendorOrder.STATUS_PLACED).count()
    preparing_count = vendor_orders.filter(status=VendorOrder.STATUS_PREPARING).count()
    ready_count = vendor_orders.filter(status=VendorOrder.STATUS_READY).count()

    orders_data = [
        {
            'id': vo.id,
            'pickup_code': vo.order.pickup_code,
            'status': vo.status,
            'updated_at': vo.updated_at.isoformat(),
        }
        for vo in vendor_orders[:20]
    ]

    return JsonResponse({
        'new_count': new_count,
        'preparing_count': preparing_count,
        'ready_count': ready_count,
        'orders': orders_data,
    })


@login_required
@require_POST
def vendor_order_transition(request, vendor_order_id):
    """
    Executes a status transition on a vendor's sub-order.
    Strictly verifies ownership: if not owned, raises 404 (Invariant 8).
    """
    # Verify ownership or 404 (do not leak existence with 403)
    vendor_order = VendorOrder.objects.filter(
        id=vendor_order_id,
        business__owner=request.user
    ).first()

    if not vendor_order:
        raise Http404("Order not found.")

    new_status = request.POST.get('new_status')
    reject_reason = request.POST.get('reject_reason', '').strip()

    try:
        vendor_order.transition_to(
            new_status=new_status,
            actor_role='vendor',
            reason=reject_reason
        )
        messages.success(request, f"Order #{vendor_order.order.pickup_code} updated to {vendor_order.get_status_display()}.")
    except ValidationError as e:
        messages.warning(request, f"Could not update order: {e.message}")

    return redirect('orders:vendor_dashboard')


@login_required
def vendor_collect_by_code(request):
    """
    Lookup order by 4-character pickup code for THIS vendor only.
    GET / POST: if code provided, finds matching sub-order.
    """
    businesses = get_user_businesses(request.user)
    if not businesses.exists():
        raise Http404("No counter linked to your account.")

    code = request.GET.get('code') or request.POST.get('code', '')
    code = code.strip().upper()
    sub_order = None
    lookup_done = False

    if code:
        lookup_done = True
        today = timezone.localdate()
        sub_order = VendorOrder.objects.filter(
            business__in=businesses,
            order__pickup_code=code,
            order__order_date=today
        ).select_related('order', 'business').prefetch_related('items').first()

        if request.method == 'POST' and request.POST.get('action') == 'collect' and sub_order:
            if sub_order.status == VendorOrder.STATUS_READY:
                sub_order.transition_to(VendorOrder.STATUS_COLLECTED, actor_role='vendor')
                messages.success(request, f"Order #{sub_order.order.pickup_code} successfully marked as COLLECTED!")
                return redirect('orders:vendor_dashboard')
            else:
                messages.error(request, f"Cannot collect: order is currently {sub_order.get_status_display()}, not READY.")

    return render(request, 'orders/vendor/collect_lookup.html', {
        'code': code,
        'sub_order': sub_order,
        'lookup_done': lookup_done,
    })


@login_required
def vendor_menu_manager(request):
    """
    Milestone 7: Vendor menu and counter availability manager.
    Vendors can:
    - Toggle counter is_open
    - Toggle menu item is_available (sold out)
    """
    businesses = get_user_businesses(request.user).prefetch_related('menu_items')
    if not businesses.exists():
        return render(request, 'orders/vendor/no_business.html')

    return render(request, 'orders/vendor/menu_manager.html', {
        'businesses': businesses,
    })


@login_required
@require_POST
def vendor_toggle_counter(request, business_id):
    """Toggle business is_open status."""
    business = Business.objects.filter(id=business_id, owner=request.user).first()
    if not business:
        raise Http404("Counter not found.")

    business.is_open = not business.is_open
    business.save(update_fields=['is_open', 'updated_at'])
    status_str = "OPEN" if business.is_open else "CLOSED"
    messages.info(request, f"{business.name} is now marked {status_str}.")
    return redirect('orders:vendor_menu_manager')


@login_required
@require_POST
def vendor_toggle_item(request, item_id):
    """Toggle MenuItem is_available status."""
    item = MenuItem.objects.filter(id=item_id, business__owner=request.user).first()
    if not item:
        raise Http404("Menu item not found.")

    item.is_available = not item.is_available
    item.save(update_fields=['is_available', 'updated_at'])
    status_str = "AVAILABLE" if item.is_available else "SOLD OUT"
    messages.info(request, f"'{item.name}' is now marked {status_str}.")
    return redirect('orders:vendor_menu_manager')
