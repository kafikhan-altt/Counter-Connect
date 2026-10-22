from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from catalog.models import Location, Business, MenuItem


class Command(BaseCommand):
    help = "Seeds idempotent demo data for CounterConnect / Localo (Surya Mall & Central Market)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding demo data..."))

        # 1. Admin Superuser
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={'email': 'admin@counterconnect.local', 'is_staff': True, 'is_superuser': True}
        )
        admin_user.set_password('admin12345')
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.save()
        self.stdout.write(f"Admin user: admin / admin12345 ({'created' if created else 'updated'})")

        # 2. Vendor Users
        vendors_data = [
            ('vendor_south', 'vendor_south@counterconnect.local', 'Ramesh (South Indian)'),
            ('vendor_chinese', 'vendor_chinese@counterconnect.local', 'Lin (Chinese Wok)'),
            ('vendor_juice', 'vendor_juice@counterconnect.local', 'Sunil (Juice & Shakes)'),
            ('vendor_bakery', 'vendor_bakery@counterconnect.local', 'Ananya (Bakery & Desserts)'),
            ('vendor_raipur', 'vendor_raipur@counterconnect.local', 'Vikram (Raipur Chat)'),
        ]
        vendor_users = {}
        for username, email, first_name in vendors_data:
            u, _ = User.objects.get_or_create(
                username=username,
                defaults={'email': email, 'first_name': first_name}
            )
            u.set_password('demo12345')
            u.first_name = first_name
            u.save()
            vendor_users[username] = u

        # 3. Locations
        surya_mall, _ = Location.objects.update_or_create(
            name='Surya Mall',
            city='Bhilai',
            defaults={
                'address': 'Junwani Road, Bhilai, Chhattisgarh',
                'is_active': True,
            }
        )

        central_market, _ = Location.objects.update_or_create(
            name='Central Market Food Street',
            city='Raipur',
            defaults={
                'address': 'Pandri Main Road, Raipur, Chhattisgarh',
                'is_active': True,
            }
        )

        # 4. Surya Mall Counters
        # South Indian Corner
        c_south, _ = Business.objects.update_or_create(
            location=surya_mall,
            name='South Indian Corner',
            defaults={
                'owner': vendor_users['vendor_south'],
                'category': 'South Indian',
                'is_open': True,
                'avg_prep_minutes': 12,
                'display_order': 1,
            }
        )
        south_items = [
            ('Masala Dosa', 'Crispy fermented crepe stuffed with spiced potato masala', Decimal('90.00'), True, True),
            ('Ghee Roast Dosa', 'Golden buttery roast dosa served with sambar and 3 chutneys', Decimal('110.00'), True, True),
            ('Steamed Idli (2 pcs)', 'Fluffy steamed rice cakes with piping hot sambar', Decimal('50.00'), True, True),
            ('Medu Vada (2 pcs)', 'Crispy golden lentil fritters with coconut chutney', Decimal('60.00'), True, True),
            ('Onion Uttapam', 'Thick pancake topped with caramelized shallots and green chillies', Decimal('85.00'), True, True),
            ('Filter Coffee', 'Traditional South Indian froth-topped decoction brew', Decimal('35.00'), True, True),
            ('Rava Kesari', 'Semolina sweet halwa garnished with ghee cashews (Sold Out)', Decimal('55.00'), True, False),
        ]
        for name, desc, price, veg, avail in south_items:
            MenuItem.objects.update_or_create(
                business=c_south,
                name=name,
                defaults={'description': desc, 'price': price, 'is_veg': veg, 'is_available': avail}
            )

        # Chinese Wok
        c_chinese, _ = Business.objects.update_or_create(
            location=surya_mall,
            name='Chinese Wok',
            defaults={
                'owner': vendor_users['vendor_chinese'],
                'category': 'Chinese',
                'is_open': True,
                'avg_prep_minutes': 15,
                'display_order': 2,
            }
        )
        chinese_items = [
            ('Veg Hakka Noodles', 'Wok-tossed noodles with shredded cabbage, bell peppers & spring onion', Decimal('110.00'), True, True),
            ('Egg Hakka Noodles', 'Wok-tossed noodles with scrambled eggs and garden greens', Decimal('130.00'), False, True),
            ('Chicken Fried Rice', 'Fragrant basmati rice tossed with shredded chicken & soy garlic sauce', Decimal('160.00'), False, True),
            ('Veg Manchurian Dry', 'Crispy vegetable dumplings in spicy tangy ginger-coriander glaze', Decimal('120.00'), True, True),
            ('Chilli Paneer Gravy', 'Crisp paneer cubes simmered in spiced dark soya chilli gravy', Decimal('150.00'), True, True),
            ('Chicken Schezwan Momos (6 pcs)', 'Steamed chicken dumplings glazed in spicy Schezwan sauce', Decimal('140.00'), False, True),
            ('Crispy Corn Pepper Salt', 'Sweet corn kernels tossed with crushed peppercorn (Sold Out)', Decimal('95.00'), True, False),
        ]
        for name, desc, price, veg, avail in chinese_items:
            MenuItem.objects.update_or_create(
                business=c_chinese,
                name=name,
                defaults={'description': desc, 'price': price, 'is_veg': veg, 'is_available': avail}
            )

        # Juice & Shakes
        c_juice, _ = Business.objects.update_or_create(
            location=surya_mall,
            name='Juice & Shakes',
            defaults={
                'owner': vendor_users['vendor_juice'],
                'category': 'Juice',
                'is_open': True,
                'avg_prep_minutes': 7,
                'display_order': 3,
            }
        )
        juice_items = [
            ('Mango Shake', 'Rich Alphonso mango pulp blended with chilled milk and cream', Decimal('80.00'), True, True),
            ('Watermelon Juice', 'Freshly pressed cold watermelon with a pinch of black salt & mint', Decimal('60.00'), True, True),
            ('Oreo KitKat Shake', 'Thick chocolate shake layered with crushed Oreos and KitKat bars', Decimal('110.00'), True, True),
            ('Mosambi Sweet Lime Juice', 'Refreshing freshly squeezed sweet lime juice with rock salt', Decimal('50.00'), True, True),
            ('Cold Coffee with Ice Cream', 'Creamy espresso shake topped with a scoop of vanilla ice cream', Decimal('90.00'), True, True),
            ('Strawberry Banana Smoothie', 'Greek yogurt smoothie with real strawberry and banana', Decimal('100.00'), True, True),
        ]
        for name, desc, price, veg, avail in juice_items:
            MenuItem.objects.update_or_create(
                business=c_juice,
                name=name,
                defaults={'description': desc, 'price': price, 'is_veg': veg, 'is_available': avail}
            )

        # Bakery & Desserts
        c_bakery, _ = Business.objects.update_or_create(
            location=surya_mall,
            name='Bakery & Desserts',
            defaults={
                'owner': vendor_users['vendor_bakery'],
                'category': 'Bakery',
                'is_open': True,
                'avg_prep_minutes': 5,
                'display_order': 4,
            }
        )
        bakery_items = [
            ('Fudge Brownie', 'Warm gooey dark chocolate walnut brownie with chocolate drizzle', Decimal('70.00'), True, True),
            ('Red Velvet Pastry', 'Moist crimson sponge slice with smooth cream cheese frosting', Decimal('85.00'), True, True),
            ('Dutch Truffle Slice', 'Decadent multi-layered Belgian chocolate truffle cake', Decimal('95.00'), True, True),
            ('Garlic Cheese Toast (2 pcs)', 'Toasted artisanal baguette with garlic butter and melted mozzarella', Decimal('65.00'), True, True),
            ('Chicken Puff', 'Flaky golden puff pastry stuffed with spicy pepper chicken', Decimal('45.00'), False, True),
            ('Blueberry Cheesecake Slice', 'Baked New York style cheesecake with blueberry compote', Decimal('120.00'), True, True),
        ]
        for name, desc, price, veg, avail in bakery_items:
            MenuItem.objects.update_or_create(
                business=c_bakery,
                name=name,
                defaults={'description': desc, 'price': price, 'is_veg': veg, 'is_available': avail}
            )

        # 5. Central Market (Raipur) - include one open counter and one closed counter for edge-case testing
        c_raipur_open, _ = Business.objects.update_or_create(
            location=central_market,
            name='Raipur Chaat & Snacks',
            defaults={
                'owner': vendor_users['vendor_raipur'],
                'category': 'Street Food',
                'is_open': True,
                'avg_prep_minutes': 8,
                'display_order': 1,
            }
        )
        raipur_items = [
            ('Pani Puri (8 pcs)', 'Crispy puris with spicy mint water, tangy tamarind & potato chickpeas', Decimal('40.00'), True, True),
            ('Sev Puri', 'Flat crisp papdis topped with spiced potatoes, three chutneys & sev', Decimal('60.00'), True, True),
            ('Dahi Bhalla', 'Lentil dumplings soaked in sweet yogurt with roasted cumin and pomegranate', Decimal('70.00'), True, True),
        ]
        for name, desc, price, veg, avail in raipur_items:
            MenuItem.objects.update_or_create(
                business=c_raipur_open,
                name=name,
                defaults={'description': desc, 'price': price, 'is_veg': veg, 'is_available': avail}
            )

        # Closed counter at Raipur for testing "counter closed" edge cases
        Business.objects.update_or_create(
            location=central_market,
            name='Old City Biryani (Closed Counter)',
            defaults={
                'owner': vendor_users['vendor_raipur'],
                'category': 'Biryani',
                'is_open': False,  # Closed counter
                'avg_prep_minutes': 20,
                'display_order': 2,
            }
        )

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully!"))
        self.stdout.write("==================================================")
        self.stdout.write("DEMO LOGINS:")
        self.stdout.write("  Admin: admin / admin12345 (or demo12345)")
        self.stdout.write("  Vendors password: demo12345")
        self.stdout.write("  South Indian: vendor_south")
        self.stdout.write("  Chinese Wok: vendor_chinese")
        self.stdout.write("  Juice & Shakes: vendor_juice")
        self.stdout.write("  Bakery & Desserts: vendor_bakery")
        self.stdout.write("  Raipur Snacks: vendor_raipur")
        self.stdout.write("==================================================")
