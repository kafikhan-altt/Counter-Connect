import uuid
from decimal import Decimal
from datetime import timedelta
from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils import timezone

phone_validator = RegexValidator(
    regex=r'^[6-9]\d{9}$',
    message="Enter a valid 10-digit Indian phone number starting with 6-9."
)


class Order(models.Model):
    """
    Parent order placed by a customer at one Location.
    Spans one or more counters (VendorOrders).
    """
    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True
    )
    location = models.ForeignKey(
        'catalog.Location',
        on_delete=models.PROTECT,
        related_name='orders'
    )
    customer_name = models.CharField(max_length=50)
    customer_phone = models.CharField(max_length=10, validators=[phone_validator])
    customer_email = models.EmailField(max_length=254, blank=True, default='')
    pickup_code = models.CharField(max_length=4)
    order_date = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['location', 'order_date', 'pickup_code'],
                name='unique_location_date_pickup_code'
            )
        ]

    def __str__(self):
        return f"Order #{self.pickup_code} ({self.customer_name}) - {self.location.name}"

    def clean(self):
        super().clean()
        if self.customer_name:
            self.customer_name = self.customer_name.strip()
            if len(self.customer_name) < 2 or len(self.customer_name) > 50:
                raise ValidationError({'customer_name': "Customer name must be between 2 and 50 characters."})

    # --- Derived Properties (Core Invariant 6: Never stored in DB) ---

    @property
    def status(self):
        """
        Computed status across all child VendorOrders.
        Rules (Spec Section 7):
        - All parts REJECTED/CANCELLED -> CANCELLED
        - All active parts COLLECTED -> COMPLETED
        - All active parts READY or COLLECTED -> READY
        - At least one active part PREPARING, READY or COLLECTED -> IN_PROGRESS
        - Otherwise -> PLACED
        """
        vos = list(self.vendor_orders.all())
        if not vos:
            return 'PLACED'

        active_parts = [vo for vo in vos if vo.status not in ('REJECTED', 'CANCELLED')]
        if not active_parts:
            return 'CANCELLED'

        if all(vo.status == 'COLLECTED' for vo in active_parts):
            return 'COMPLETED'

        if all(vo.status in ('READY', 'COLLECTED') for vo in active_parts):
            return 'READY'

        if any(vo.status in ('PREPARING', 'READY', 'COLLECTED') for vo in active_parts):
            return 'IN_PROGRESS'

        return 'PLACED'

    @property
    def is_fully_ready(self):
        return self.status == 'READY'

    @property
    def is_cancellable(self):
        """
        Cancellable only if every non-terminal part is still PLACED,
        and at least one part is currently PLACED.
        If any counter has started preparing, ready, or collected, cancel is forbidden.
        """
        vos = list(self.vendor_orders.all())
        placed_parts = [vo for vo in vos if vo.status == 'PLACED']
        non_terminal = [vo for vo in vos if vo.status not in ('REJECTED', 'CANCELLED', 'COLLECTED')]
        return bool(placed_parts) and (len(placed_parts) == len(non_terminal))

    @property
    def total_amount(self):
        """Total price of non-rejected, non-cancelled parts."""
        total = Decimal('0.00')
        for vo in self.vendor_orders.all():
            if vo.status not in ('REJECTED', 'CANCELLED'):
                total += vo.subtotal
        return total

    @property
    def estimated_ready_at(self):
        """created_at + max(avg_prep_minutes) over active parts."""
        active_parts = [vo for vo in self.vendor_orders.all() if vo.status not in ('REJECTED', 'CANCELLED')]
        if not active_parts:
            return self.created_at
        max_prep = max((vo.business.avg_prep_minutes for vo in active_parts), default=10)
        return self.created_at + timedelta(minutes=max_prep)


class VendorOrder(models.Model):
    """Sub-order for a specific counter within an Order."""

    STATUS_PLACED = 'PLACED'
    STATUS_PREPARING = 'PREPARING'
    STATUS_READY = 'READY'
    STATUS_COLLECTED = 'COLLECTED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_CANCELLED = 'CANCELLED'

    STATUS_CHOICES = [
        (STATUS_PLACED, 'Placed'),
        (STATUS_PREPARING, 'Preparing'),
        (STATUS_READY, 'Ready'),
        (STATUS_COLLECTED, 'Collected'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='vendor_orders'
    )
    business = models.ForeignKey(
        'catalog.Business',
        on_delete=models.PROTECT,
        related_name='vendor_orders'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PLACED
    )
    reject_reason = models.CharField(max_length=140, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['order', 'business'],
                name='unique_vendororder_order_business'
            )
        ]

    def __str__(self):
        return f"{self.business.name} sub-order #{self.order.pickup_code} ({self.status})"

    @property
    def subtotal(self):
        """Sum of items (unit_price * quantity)."""
        return sum(item.line_total for item in self.items.all()) or Decimal('0.00')

    def transition_to(self, new_status, actor_role='vendor', reason=None):
        """
        Enforce state machine transitions strictly (Spec Section 7).
        actor_role: 'vendor' or 'customer'
        """
        current = self.status

        # Allowed transitions mapping: (current, new_status) -> allowed_role
        allowed = {
            (self.STATUS_PLACED, self.STATUS_PREPARING): 'vendor',
            (self.STATUS_PLACED, self.STATUS_REJECTED): 'vendor',
            (self.STATUS_PLACED, self.STATUS_CANCELLED): 'customer',
            (self.STATUS_PREPARING, self.STATUS_READY): 'vendor',
            (self.STATUS_PREPARING, self.STATUS_REJECTED): 'vendor',
            (self.STATUS_READY, self.STATUS_COLLECTED): 'vendor',
        }

        pair = (current, new_status)
        if pair not in allowed:
            raise ValidationError(
                f"Invalid status transition from {current} to {new_status}."
            )

        expected_role = allowed[pair]
        if actor_role != expected_role:
            raise ValidationError(
                f"Actor role '{actor_role}' is not authorized to transition from {current} to {new_status}."
            )

        if new_status == self.STATUS_REJECTED:
            if not reason or not str(reason).strip():
                raise ValidationError("A rejection reason is required when rejecting an order.")
            self.reject_reason = str(reason).strip()[:140]

        self.status = new_status
        self.save(update_fields=['status', 'reject_reason', 'updated_at'])
        return self


class OrderItem(models.Model):
    """Line item snapshot in a VendorOrder."""
    vendor_order = models.ForeignKey(
        VendorOrder,
        on_delete=models.CASCADE,
        related_name='items'
    )
    menu_item = models.ForeignKey(
        'catalog.MenuItem',
        on_delete=models.PROTECT,
        related_name='order_items'
    )
    item_name = models.CharField(max_length=100)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    quantity = models.PositiveSmallIntegerField(default=1)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gte=1, quantity__lte=10),
                name='check_orderitem_quantity_bounds'
            ),
            models.UniqueConstraint(
                fields=['vendor_order', 'menu_item'],
                name='unique_orderitem_vendororder_menuitem'
            )
        ]

    def __str__(self):
        return f"{self.quantity}x {self.item_name} @ ₹{self.unit_price}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity
