from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from . import vendor_views

app_name = 'orders'

urlpatterns = [
    # Cart routes
    path('cart/', views.cart_view, name='cart_view'),
    path('cart/add/', views.cart_add, name='cart_add'),
    path('cart/update/', views.cart_update, name='cart_update'),
    path('cart/remove/', views.cart_remove, name='cart_remove'),
    path('cart/clear/', views.cart_clear, name='cart_clear'),

    # Checkout & Customer Tracking
    path('checkout/', views.checkout_view, name='checkout_view'),
    path('o/<uuid:public_id>/', views.order_tracking, name='order_tracking'),
    path('o/<uuid:public_id>/status.json', views.order_status_json, name='order_status_json'),
    path('o/<uuid:public_id>/cancel/', views.order_cancel, name='order_cancel'),
    path('find-order/', views.find_order, name='find_order'),

    # Vendor Authentication
    path('vendor/login/', auth_views.LoginView.as_view(template_name='orders/vendor/login.html'), name='vendor_login'),
    path('vendor/logout/', auth_views.LogoutView.as_view(), name='vendor_logout'),

    # Vendor Dashboard & Operations
    path('vendor/', vendor_views.vendor_dashboard, name='vendor_dashboard'),
    path('vendor/orders.json', vendor_views.vendor_orders_json, name='vendor_orders_json'),
    path('vendor/order/<int:vendor_order_id>/transition/', vendor_views.vendor_order_transition, name='vendor_order_transition'),
    path('vendor/collect/', vendor_views.vendor_collect_by_code, name='vendor_collect'),

    # Vendor Menu & Counter Manager (Milestone 7)
    path('vendor/menu/', vendor_views.vendor_menu_manager, name='vendor_menu_manager'),
    path('vendor/counter/<int:business_id>/toggle/', vendor_views.vendor_toggle_counter, name='vendor_toggle_counter'),
    path('vendor/item/<int:item_id>/toggle/', vendor_views.vendor_toggle_item, name='vendor_toggle_item'),
]
