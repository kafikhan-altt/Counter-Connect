from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from catalog.models import Location, Business, MenuItem
from orders.models import Order, VendorOrder, OrderItem
from orders.cart import Cart


class CartTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.vendor = User.objects.create_user(username='v_test', password='pw')
        
        self.loc1 = Location.objects.create(
            name='Surya Mall', address='Junwani Road', city='Bhilai', is_active=True
        )
        self.loc2 = Location.objects.create(
            name='Central Market', address='Pandri', city='Raipur', is_active=True
        )

        self.b1 = Business.objects.create(
            location=self.loc1, owner=self.vendor, name='South Indian Corner',
            category='South Indian', is_open=True, avg_prep_minutes=10
        )
        self.b2 = Business.objects.create(
            location=self.loc1, owner=self.vendor, name='Juice & Shakes',
            category='Beverages', is_open=True, avg_prep_minutes=5
        )
        self.b_closed = Business.objects.create(
            location=self.loc1, owner=self.vendor, name='Closed Stall',
            category='Snacks', is_open=False, avg_prep_minutes=5
        )
        self.b_loc2 = Business.objects.create(
            location=self.loc2, owner=self.vendor, name='Raipur Stall',
            category='Snacks', is_open=True, avg_prep_minutes=5
        )

        self.item1 = MenuItem.objects.create(
            business=self.b1, name='Masala Dosa', price=Decimal('90.00'), is_available=True
        )
        self.item2 = MenuItem.objects.create(
            business=self.b2, name='Mango Shake', price=Decimal('80.00'), is_available=True
        )
        self.item_soldout = MenuItem.objects.create(
            business=self.b1, name='Special Sweet', price=Decimal('50.00'), is_available=False
        )
        self.item_closed = MenuItem.objects.create(
            business=self.b_closed, name='Samosa', price=Decimal('20.00'), is_available=True
        )
        self.item_loc2 = MenuItem.objects.create(
            business=self.b_loc2, name='Kachori', price=Decimal('25.00'), is_available=True
        )

    def test_add_items_from_multiple_counters_same_location(self):
        self.client.post(reverse('orders:cart_add'), {'menu_item_id': self.item1.id, 'quantity': 2})
        self.client.post(reverse('orders:cart_add'), {'menu_item_id': self.item2.id, 'quantity': 1})

        session = self.client.session
        cart = session.get('cart')
        self.assertEqual(cart['location_id'], self.loc1.id)
        self.assertEqual(cart['items'][str(self.item1.id)], 2)
        self.assertEqual(cart['items'][str(self.item2.id)], 1)

        self.assertNotIn('price', str(cart))
        self.assertNotIn('Masala Dosa', str(cart))

    def test_one_location_invariant_switch_confirm(self):
        self.client.post(reverse('orders:cart_add'), {'menu_item_id': self.item1.id, 'quantity': 1})
        self.assertEqual(self.client.session['cart']['location_id'], self.loc1.id)

        res = self.client.post(reverse('orders:cart_add'), {'menu_item_id': self.item_loc2.id, 'quantity': 1})
        self.assertContains(res, 'Switch Food Court?')
        self.assertEqual(self.client.session['cart']['location_id'], self.loc1.id)
        self.assertEqual(self.client.session['cart']['items'], {str(self.item1.id): 1})

        res_confirm = self.client.post(reverse('orders:cart_add'), {
            'menu_item_id': self.item_loc2.id,
            'quantity': 1,
            'confirm_switch': 'true'
        })
        self.assertEqual(self.client.session['cart']['location_id'], self.loc2.id)
        self.assertEqual(self.client.session['cart']['items'], {str(self.item_loc2.id): 1})

    def test_cannot_add_soldout_or_closed_counter_item(self):
        res1 = self.client.post(reverse('orders:cart_add'), {'menu_item_id': self.item_soldout.id, 'quantity': 1})
        self.assertNotIn(str(self.item_soldout.id), self.client.session.get('cart', {}).get('items', {}))

        res2 = self.client.post(reverse('orders:cart_add'), {'menu_item_id': self.item_closed.id, 'quantity': 1})
        self.assertNotIn(str(self.item_closed.id), self.client.session.get('cart', {}).get('items', {}))

    def test_update_and_remove_cart_items(self):
        self.client.post(reverse('orders:cart_add'), {'menu_item_id': self.item1.id, 'quantity': 2})
        self.client.post(reverse('orders:cart_update'), {'menu_item_id': self.item1.id, 'quantity': 4})
        self.assertEqual(self.client.session['cart']['items'][str(self.item1.id)], 4)

        self.client.post(reverse('orders:cart_update'), {'menu_item_id': self.item1.id, 'quantity': 0})
        self.assertNotIn(str(self.item1.id), self.client.session['cart']['items'])

    def test_state_changing_cart_endpoints_reject_get(self):
        res = self.client.get(reverse('orders:cart_add'))
        self.assertEqual(res.status_code, 405)
        res2 = self.client.get(reverse('orders:cart_update'))
        self.assertEqual(res2.status_code, 405)
        res3 = self.client.get(reverse('orders:cart_remove'))
        self.assertEqual(res3.status_code, 405)
        res4 = self.client.get(reverse('orders:cart_clear'))
        self.assertEqual(res4.status_code, 405)

    def test_cart_view_flags_items_that_become_sold_out_or_closed(self):
        self.client.post(reverse('orders:cart_add'), {'menu_item_id': self.item1.id, 'quantity': 1})
        self.item1.is_available = False
        self.item1.save()

        response = self.client.get(reverse('orders:cart_view'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Checkout Blocked')
        self.assertContains(response, 'sold out')


class CheckoutAndOrderTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.v1 = User.objects.create_user(username='v1', password='pw')
        self.v2 = User.objects.create_user(username='v2', password='pw')
        self.v3 = User.objects.create_user(username='v3', password='pw')

        self.loc = Location.objects.create(
            name='Surya Mall', address='Junwani Road', city='Bhilai', is_active=True
        )

        self.b1 = Business.objects.create(
            location=self.loc, owner=self.v1, name='South Indian',
            category='South Indian', is_open=True, avg_prep_minutes=12
        )
        self.b2 = Business.objects.create(
            location=self.loc, owner=self.v2, name='Chinese Wok',
            category='Chinese', is_open=True, avg_prep_minutes=15
        )
        self.b3 = Business.objects.create(
            location=self.loc, owner=self.v3, name='Juice & Shakes',
            category='Juice', is_open=True, avg_prep_minutes=7
        )

        self.item1 = MenuItem.objects.create(
            business=self.b1, name='Masala Dosa', price=Decimal('90.00'), is_available=True
        )
        self.item2 = MenuItem.objects.create(
            business=self.b2, name='Veg Hakka Noodles', price=Decimal('110.00'), is_available=True
        )
        self.item3 = MenuItem.objects.create(
            business=self.b3, name='Mango Shake', price=Decimal('80.00'), is_available=True
        )

    def test_successful_checkout_across_three_counters(self):
        self.client.post(reverse('orders:cart_add'), {'menu_item_id': self.item1.id, 'quantity': 2})
        self.client.post(reverse('orders:cart_add'), {'menu_item_id': self.item2.id, 'quantity': 1})
        self.client.post(reverse('orders:cart_add'), {'menu_item_id': self.item3.id, 'quantity': 1})

        checkout_res = self.client.post(reverse('orders:checkout_view'), {
            'customer_name': 'Riya Sharma',
            'customer_phone': '9876543210'
        }, follow=True)

        self.assertEqual(checkout_res.status_code, 200)
        self.assertContains(checkout_res, 'Pre-Order Status')
        self.assertContains(checkout_res, 'South Indian')
        self.assertContains(checkout_res, 'Chinese Wok')
        self.assertContains(checkout_res, 'Juice &amp; Shakes')

        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.first()
        self.assertEqual(order.customer_name, 'Riya Sharma')
        self.assertEqual(order.customer_phone, '9876543210')
        self.assertEqual(order.vendor_orders.count(), 3)
        self.assertEqual(order.status, 'PLACED')
        self.assertEqual(order.total_amount, Decimal('370.00'))
        self.assertEqual(self.client.session.get('cart', {}).get('items', {}), {})

    def test_price_snapshot_invariant(self):
        self.client.post(reverse('orders:cart_add'), {'menu_item_id': self.item1.id, 'quantity': 1})
        self.client.post(reverse('orders:checkout_view'), {
            'customer_name': 'Ramesh',
            'customer_phone': '9123456789'
        })
        order = Order.objects.first()
        item_ordered = OrderItem.objects.filter(vendor_order__order=order).first()
        self.assertEqual(item_ordered.unit_price, Decimal('90.00'))

        self.item1.price = Decimal('150.00')
        self.item1.save()

        item_ordered.refresh_from_db()
        self.assertEqual(item_ordered.unit_price, Decimal('90.00'))
        self.assertEqual(order.total_amount, Decimal('90.00'))

    def test_checkout_validation_failures(self):
        self.client.post(reverse('orders:cart_add'), {'menu_item_id': self.item1.id, 'quantity': 1})
        res1 = self.client.post(reverse('orders:checkout_view'), {
            'customer_name': 'Riya',
            'customer_phone': '12345'
        })
        self.assertContains(res1, 'valid 10-digit Indian phone number')
        self.assertEqual(Order.objects.count(), 0)

        res2 = self.client.post(reverse('orders:checkout_view'), {
            'customer_name': 'R',
            'customer_phone': '9876543210'
        })
        self.assertContains(res2, 'between 2 and 50 characters')
        self.assertEqual(Order.objects.count(), 0)

    def test_double_submit_safety(self):
        self.client.post(reverse('orders:cart_add'), {'menu_item_id': self.item1.id, 'quantity': 1})
        self.client.post(reverse('orders:checkout_view'), {
            'customer_name': 'Riya',
            'customer_phone': '9876543210'
        })
        self.assertEqual(Order.objects.count(), 1)

        res = self.client.post(reverse('orders:checkout_view'), {
            'customer_name': 'Riya',
            'customer_phone': '9876543210'
        }, follow=True)
        self.assertEqual(Order.objects.count(), 1)
        self.assertContains(res, 'Your cart is empty')

    def test_abuse_guard_max_3_active_orders_today(self):
        for i in range(3):
            self.client.post(reverse('orders:cart_add'), {'menu_item_id': self.item1.id, 'quantity': 1})
            self.client.post(reverse('orders:checkout_view'), {
                'customer_name': 'Riya',
                'customer_phone': '9876543210'
            })
        self.assertEqual(Order.objects.count(), 3)

        self.client.post(reverse('orders:cart_add'), {'menu_item_id': self.item1.id, 'quantity': 1})
        res4 = self.client.post(reverse('orders:checkout_view'), {
            'customer_name': 'Riya',
            'customer_phone': '9876543210'
        })
        self.assertContains(res4, 'You already have 3 active orders at this food court today')
        self.assertEqual(Order.objects.count(), 3)

    def test_order_tracking_and_status_json_endpoints(self):
        self.client.post(reverse('orders:cart_add'), {'menu_item_id': self.item1.id, 'quantity': 1})
        self.client.post(reverse('orders:checkout_view'), {
            'customer_name': 'Riya',
            'customer_phone': '9876543210'
        })
        order = Order.objects.first()

        res = self.client.get(reverse('orders:order_tracking', kwargs={'public_id': order.public_id}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, order.pickup_code)

        json_res = self.client.get(reverse('orders:order_status_json', kwargs={'public_id': order.public_id}))
        self.assertEqual(json_res.status_code, 200)
        data = json_res.json()
        self.assertEqual(data['status'], 'PLACED')
        self.assertEqual(data['total_amount'], '90.00')
        self.assertEqual(len(data['vendor_orders']), 1)


class StateMachineAndVendorTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.v_south = User.objects.create_user(username='vendor_south', password='password123')
        self.v_chinese = User.objects.create_user(username='vendor_chinese', password='password123')

        self.loc = Location.objects.create(name='Surya Mall', address='Junwani Road', city='Bhilai')
        self.b_south = Business.objects.create(
            location=self.loc, owner=self.v_south, name='South Indian', category='South Indian', is_open=True
        )
        self.b_chinese = Business.objects.create(
            location=self.loc, owner=self.v_chinese, name='Chinese Wok', category='Chinese', is_open=True
        )

        self.item_dosa = MenuItem.objects.create(
            business=self.b_south, name='Dosa', price=Decimal('90.00'), is_available=True
        )
        self.item_noodles = MenuItem.objects.create(
            business=self.b_chinese, name='Noodles', price=Decimal('110.00'), is_available=True
        )

        # Create multi-counter order
        self.order = Order.objects.create(
            location=self.loc, customer_name='Riya', customer_phone='9876543210',
            pickup_code='K7M2', order_date=timezone.localdate()
        )
        self.vo_south = VendorOrder.objects.create(order=self.order, business=self.b_south)
        self.vo_chinese = VendorOrder.objects.create(order=self.order, business=self.b_chinese)

        OrderItem.objects.create(vendor_order=self.vo_south, menu_item=self.item_dosa, item_name='Dosa', unit_price=Decimal('90.00'), quantity=1)
        OrderItem.objects.create(vendor_order=self.vo_chinese, menu_item=self.item_noodles, item_name='Noodles', unit_price=Decimal('110.00'), quantity=1)

    def test_state_machine_transitions_and_validation(self):
        # 1. PLACED -> PREPARING (by vendor)
        self.vo_south.transition_to(VendorOrder.STATUS_PREPARING, actor_role='vendor')
        self.assertEqual(self.vo_south.status, VendorOrder.STATUS_PREPARING)

        # Disallowed transition: PREPARING -> PLACED
        with self.assertRaises(ValidationError):
            self.vo_south.transition_to(VendorOrder.STATUS_PLACED, actor_role='vendor')

        # 2. PREPARING -> READY (by vendor)
        self.vo_south.transition_to(VendorOrder.STATUS_READY, actor_role='vendor')
        self.assertEqual(self.vo_south.status, VendorOrder.STATUS_READY)

        # 3. READY -> COLLECTED (by vendor)
        self.vo_south.transition_to(VendorOrder.STATUS_COLLECTED, actor_role='vendor')
        self.assertEqual(self.vo_south.status, VendorOrder.STATUS_COLLECTED)

        # Terminal state: cannot transition out of COLLECTED
        with self.assertRaises(ValidationError):
            self.vo_south.transition_to(VendorOrder.STATUS_READY, actor_role='vendor')

    def test_rejection_requires_reason(self):
        # Rejection without reason must raise ValidationError
        with self.assertRaises(ValidationError):
            self.vo_chinese.transition_to(VendorOrder.STATUS_REJECTED, actor_role='vendor', reason=None)

        with self.assertRaises(ValidationError):
            self.vo_chinese.transition_to(VendorOrder.STATUS_REJECTED, actor_role='vendor', reason='   ')

        # With reason should succeed
        self.vo_chinese.transition_to(VendorOrder.STATUS_REJECTED, actor_role='vendor', reason='Ran out of noodles')
        self.assertEqual(self.vo_chinese.status, VendorOrder.STATUS_REJECTED)
        self.assertEqual(self.vo_chinese.reject_reason, 'Ran out of noodles')

    def test_derived_order_status_progression(self):
        # Initial: both PLACED -> Order status PLACED
        self.assertEqual(self.order.status, 'PLACED')
        self.assertTrue(self.order.is_cancellable)

        # South starts PREPARING -> Order status IN_PROGRESS
        self.vo_south.transition_to(VendorOrder.STATUS_PREPARING, actor_role='vendor')
        self.assertEqual(self.order.status, 'IN_PROGRESS')
        # Not cancellable once prep starts
        self.assertFalse(self.order.is_cancellable)

        # South READY, Chinese REJECTED -> active parts all READY -> Order status READY
        self.vo_south.transition_to(VendorOrder.STATUS_READY, actor_role='vendor')
        self.vo_chinese.transition_to(VendorOrder.STATUS_REJECTED, actor_role='vendor', reason='Out of stock')
        self.assertEqual(self.order.status, 'READY')

        # Total amount excludes rejected parts (only 90.00)
        self.assertEqual(self.order.total_amount, Decimal('90.00'))

        # South COLLECTED -> all active parts COLLECTED -> Order status COMPLETED
        self.vo_south.transition_to(VendorOrder.STATUS_COLLECTED, actor_role='vendor')
        self.assertEqual(self.order.status, 'COMPLETED')

    def test_all_rejected_or_cancelled_gives_cancelled_order_status(self):
        self.vo_south.transition_to(VendorOrder.STATUS_REJECTED, actor_role='vendor', reason='Gas leak')
        self.vo_chinese.transition_to(VendorOrder.STATUS_REJECTED, actor_role='vendor', reason='Power cut')
        self.assertEqual(self.order.status, 'CANCELLED')
        self.assertEqual(self.order.total_amount, Decimal('0.00'))

    def test_vendor_isolation_invariant(self):
        # Core Invariant 8: Vendor A cannot view or modify Vendor B's sub-order (must return 404)
        self.client.login(username='vendor_south', password='password123')

        # Vendor South attempts to transition Chinese stall's sub-order -> 404
        res = self.client.post(
            reverse('orders:vendor_order_transition', kwargs={'vendor_order_id': self.vo_chinese.id}),
            {'new_status': 'PREPARING'}
        )
        self.assertEqual(res.status_code, 404)

        # Vendor South cannot toggle Chinese menu items -> 404
        res2 = self.client.post(
            reverse('orders:vendor_toggle_item', kwargs={'item_id': self.item_noodles.id})
        )
        self.assertEqual(res2.status_code, 404)

    def test_collect_by_code_vendor_isolation(self):
        self.client.login(username='vendor_south', password='password123')

        # Lookup with pickup code K7M2
        res = self.client.get(reverse('orders:vendor_collect') + '?code=K7M2')
        self.assertEqual(res.status_code, 200)
        # Should see South Indian items
        self.assertContains(res, 'Dosa')
        # Must NEVER see Chinese Wok items
        self.assertNotContains(res, 'Noodles')

    def test_vendor_menu_manager_toggles(self):
        self.client.login(username='vendor_south', password='password123')

        # Toggle item availability (Dosa is_available=True -> False)
        self.client.post(reverse('orders:vendor_toggle_item', kwargs={'item_id': self.item_dosa.id}))
        self.item_dosa.refresh_from_db()
        self.assertFalse(self.item_dosa.is_available)

        # Toggle stall is_open (b_south is_open=True -> False)
        self.client.post(reverse('orders:vendor_toggle_counter', kwargs={'business_id': self.b_south.id}))
        self.b_south.refresh_from_db()
        self.assertFalse(self.b_south.is_open)

    def test_customer_cancel_order_flow(self):
        # Order is PLACED -> customer cancels
        res = self.client.post(reverse('orders:order_cancel', kwargs={'public_id': self.order.public_id}))
        self.assertEqual(res.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'CANCELLED')

    def test_find_order_by_phone_and_code(self):
        # Valid search
        res = self.client.post(reverse('orders:find_order'), {
            'phone': '9876543210',
            'pickup_code': 'K7M2'
        })
        self.assertRedirects(res, reverse('orders:order_tracking', kwargs={'public_id': self.order.public_id}))

        # Invalid code
        res_bad = self.client.post(reverse('orders:find_order'), {
            'phone': '9876543210',
            'pickup_code': 'ZZZZ'
        })
        self.assertContains(res_bad, 'No matching order found for today')
