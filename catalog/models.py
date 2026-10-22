from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User
from django.utils.text import slugify


class Location(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=150, unique=True, blank=True)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=80, db_index=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive locations are hidden from public search/listing."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['city', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'city'],
                name='unique_location_name_city'
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.city})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            if Location.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = slugify(f"{self.name}-{self.city}")
            counter = 1
            unique_slug = slug
            while Location.objects.filter(slug=unique_slug).exclude(pk=self.pk).exists():
                unique_slug = f"{slug}-{counter}"
                counter += 1
            self.slug = unique_slug
        super().save(*args, **kwargs)


class Business(models.Model):
    """A food court counter/stall."""
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name='businesses'
    )
    owner = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='owned_businesses'
    )
    name = models.CharField(max_length=100)
    category = models.CharField(
        max_length=50,
        help_text="e.g. South Indian, Chinese, Juice, Bakery"
    )
    is_open = models.BooleanField(
        default=True,
        help_text="Vendor can toggle counter open or closed."
    )
    avg_prep_minutes = models.PositiveSmallIntegerField(
        default=10,
        help_text="Estimated prep time (1-60 mins) used for order readiness."
    )
    display_order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Ordering sequence on the food court page."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name_plural = 'Businesses (Counters)'
        constraints = [
            models.UniqueConstraint(
                fields=['location', 'name'],
                name='unique_business_location_name'
            )
        ]

    def __str__(self):
        return f"{self.name} — {self.location.name}"


class MenuItem(models.Model):
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name='menu_items'
    )
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=200, blank=True, default='')
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Price in INR (>= 0)"
    )
    is_veg = models.BooleanField(
        default=True,
        help_text="True for Vegetarian (green dot), False for Non-veg (red dot)"
    )
    is_available = models.BooleanField(
        default=True,
        help_text="Vendor can mark sold out (False)."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gte=0),
                name='check_menuitem_price_non_negative'
            ),
            models.UniqueConstraint(
                fields=['business', 'name'],
                name='unique_menuitem_business_name'
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.business.name}) - ₹{self.price}"
