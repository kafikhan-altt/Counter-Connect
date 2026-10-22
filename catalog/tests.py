from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.db.utils import IntegrityError
from django.core.management import call_command
from django.urls import reverse
from catalog.models import Location, Business, MenuItem


class CatalogModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='test_vendor', password='password123')
        self.location = Location.objects.create(
            name='City Center Food Court',
            address='123 Market St',
            city='Durg',
            is_active=True
        )

    def test_location_slug_auto_generation(self):
        self.assertEqual(self.location.slug, 'city-center-food-court')

    def test_location_unique_name_city(self):
        with self.assertRaises(IntegrityError):
            Location.objects.create(
                name='City Center Food Court',
                address='Different address',
                city='Durg'
            )

    def test_business_creation_and_uniqueness(self):
        b1 = Business.objects.create(
            location=self.location,
            owner=self.user,
            name='Biryani Hub',
            category='Mughlai',
            avg_prep_minutes=15
        )
        self.assertEqual(str(b1), 'Biryani Hub — City Center Food Court')

        # Duplicate business name in same location must violate unique constraint
        with self.assertRaises(IntegrityError):
            Business.objects.create(
                location=self.location,
                owner=self.user,
                name='Biryani Hub',
                category='Different category'
            )

    def test_menu_item_non_negative_price(self):
        business = Business.objects.create(
            location=self.location,
            owner=self.user,
            name='Tea Corner',
            category='Beverages'
        )
        item = MenuItem.objects.create(
            business=business,
            name='Ginger Tea',
            price=Decimal('20.00'),
            is_veg=True
        )
        self.assertEqual(item.price, Decimal('20.00'))

        # Negative price must fail check constraint
        with self.assertRaises(IntegrityError):
            MenuItem.objects.create(
                business=business,
                name='Invalid Item',
                price=Decimal('-10.00')
            )

    def test_seed_demo_idempotence(self):
        call_command('seed_demo')
        location_count_1 = Location.objects.count()
        business_count_1 = Business.objects.count()
        menu_count_1 = MenuItem.objects.count()

        call_command('seed_demo')
        self.assertEqual(Location.objects.count(), location_count_1)
        self.assertEqual(Business.objects.count(), business_count_1)
        self.assertEqual(MenuItem.objects.count(), menu_count_1)


class CatalogBrowsingViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='v_south', password='pw')
        self.active_loc = Location.objects.create(
            name='Surya Mall',
            address='Junwani Road',
            city='Bhilai',
            is_active=True
        )
        self.inactive_loc = Location.objects.create(
            name='Ghost Mall',
            address='Nowhere',
            city='Nowhere City',
            is_active=False
        )
        self.counter = Business.objects.create(
            location=self.active_loc,
            owner=self.user,
            name='South Indian Corner',
            category='South Indian',
            is_open=True,
            avg_prep_minutes=10
        )
        self.item = MenuItem.objects.create(
            business=self.counter,
            name='Masala Dosa',
            price=Decimal('90.00'),
            is_veg=True,
            is_available=True
        )

    def test_home_page_shows_active_locations_only(self):
        response = self.client.get(reverse('catalog:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Surya Mall')
        self.assertNotContains(response, 'Ghost Mall')

    def test_search_by_name_and_city_case_insensitive(self):
        # Search by name lowercase
        res1 = self.client.get(reverse('catalog:search') + '?q=surya')
        self.assertEqual(res1.status_code, 200)
        self.assertContains(res1, 'Surya Mall')

        # Search by city uppercase
        res2 = self.client.get(reverse('catalog:search') + '?q=BHILAI')
        self.assertEqual(res2.status_code, 200)
        self.assertContains(res2, 'Surya Mall')

        # Search for non-existent or inactive
        res3 = self.client.get(reverse('catalog:search') + '?q=Ghost')
        self.assertEqual(res3.status_code, 200)
        self.assertContains(res3, 'No food court found')

    def test_location_detail_page(self):
        response = self.client.get(reverse('catalog:location_detail', kwargs={'slug': self.active_loc.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Surya Mall')
        self.assertContains(response, 'South Indian Corner')
        self.assertContains(response, 'Masala Dosa')

    def test_inactive_location_returns_404(self):
        response = self.client.get(reverse('catalog:location_detail', kwargs={'slug': self.inactive_loc.slug}))
        self.assertEqual(response.status_code, 404)
