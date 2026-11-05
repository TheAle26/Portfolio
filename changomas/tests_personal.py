import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail, signing
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Product, Supermarket
from .personal import EMAIL_SALT, UNSUBSCRIBE_SALT
from .personal_models import CartItem, NotificationPreference, ShoppingCart, Subscription


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', DEBUG=False)
class PersonalFeaturesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email='person@example.com', password='Strong-pass-1357')
        self.other = get_user_model().objects.create_user(email='other@example.com', password='Strong-pass-1357')
        self.store = Supermarket.objects.get(slug='changomas')
        self.product = Product.objects.create(
            supermarket=self.store, reference_code='12345678', ean='12345678',
            vtex_product_id='vtex-1', name='Arroz',
        )

    def api_login(self, client=None, user=None):
        client = client or self.client
        user = user or self.user
        client.force_login(user)
        return client

    def test_registration_normalizes_email_and_logs_user_in(self):
        response = self.client.post(reverse('changomas:account_register'), {
            'email': '  New.User@Example.com ', 'password1': 'Another-Strong-2468',
            'password2': 'Another-Strong-2468',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.filter(email='new.user@example.com').exists())
        self.assertIn('_auth_user_id', self.client.session)

    def test_duplicate_email_is_case_insensitive(self):
        response = self.client.post(reverse('changomas:account_register'), {
            'email': 'PERSON@example.com', 'password1': 'Another-Strong-2468',
            'password2': 'Another-Strong-2468',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(get_user_model().objects.filter(email__iexact='person@example.com').count(), 1)

    def test_login_normalizes_email_and_rejects_external_next(self):
        response = self.client.post(reverse('changomas:account_login'), {
            'username': 'PERSON@EXAMPLE.COM', 'password': 'Strong-pass-1357',
            'next': 'https://attacker.invalid/path',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('changomas:personal_subscriptions'))
        self.assertIn('_auth_user_id', self.client.session)

    def test_private_account_pages_redirect_to_named_login(self):
        response = self.client.get(reverse('changomas:account_settings'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response['Location'],
            f"{reverse('changomas:account_login')}?next={reverse('changomas:account_settings')}",
        )

    def test_cart_is_private_and_updates_use_version(self):
        client = self.api_login()
        url = reverse('changomas:personal_cart_api')
        payload = client.get(url).json()
        self.assertEqual(payload, {'items': [], 'version': 1})
        update = client.put(
            reverse('changomas:personal_cart_item_api', kwargs={'ean': '12345678'}),
            data=json.dumps({'qty': 3, 'version': 1}), content_type='application/json',
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.json()['items'], [{'ean': '12345678', 'qty': 3}])
        stale = client.put(
            reverse('changomas:personal_cart_item_api', kwargs={'ean': '12345678'}),
            data=json.dumps({'qty': 4, 'version': 1}), content_type='application/json',
        )
        self.assertEqual(stale.status_code, 409)
        self.api_login(user=self.other)
        self.assertEqual(self.client.get(url).json()['items'], [])

    def test_cart_put_requires_csrf_for_logged_in_users(self):
        client = Client(enforce_csrf_checks=True)
        self.api_login(client)
        client.get(reverse('changomas:personal_cart_api'))
        url = reverse('changomas:personal_cart_item_api', kwargs={'ean': '12345678'})
        body = json.dumps({'qty': 2, 'version': 1})
        denied = client.put(url, data=body, content_type='application/json')
        self.assertEqual(denied.status_code, 403)
        token = client.cookies['csrftoken'].value
        allowed = client.put(
            url, data=body, content_type='application/json', HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json()['items'], [{'ean': '12345678', 'qty': 2}])

    def test_cart_merge_is_idempotent_and_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.api_login(client)
        url = reverse('changomas:personal_cart_import')
        body = json.dumps({'items': [{'ean': '12345678', 'qty': 2}], 'import_id': 'batch_12345678'})
        denied = client.post(url, data=body, content_type='application/json')
        self.assertEqual(denied.status_code, 403)
        client.get(reverse('changomas:personal_cart_api'))
        token = client.cookies['csrftoken'].value
        first = client.post(url, data=body, content_type='application/json', HTTP_X_CSRFTOKEN=token)
        second = client.post(url, data=body, content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.json()['items'], [{'ean': '12345678', 'qty': 2}])
        self.assertEqual(CartItem.objects.filter(cart__user=self.user).get().quantity, 2)

    def test_subscription_endpoints_are_scoped_to_current_user(self):
        row = Subscription.objects.create(user=self.other, product=self.product)
        carrefour = Supermarket.objects.get(slug='carrefour')
        self.api_login()
        list_url = reverse('changomas:personal_subscriptions_api')
        response = self.client.post(list_url, data=json.dumps({
            'product_id': self.product.pk, 'target_price': '123.45', 'promo_alert': False,
            'stores': [carrefour.slug],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Subscription.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Subscription.objects.filter(pk=row.pk, user=self.other).count(), 1)
        payload = self.client.get(list_url).json()['subscriptions'][0]
        self.assertEqual(payload['product_id'], self.product.pk)
        self.assertEqual(payload['stores'], [carrefour.slug])
        self.assertFalse(payload['all_stores'])

        response = self.client.post(list_url, data=json.dumps({
            'product_id': self.product.pk, 'target_price': '123.45',
            'promo_alert': False, 'stores': [],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Subscription.objects.get(user=self.user, product=self.product).stores.count(), 0)
        self.assertTrue(self.client.get(list_url).json()['subscriptions'][0]['all_stores'])

    def test_html_subscription_edit_saves_selected_stores(self):
        carrefour = Supermarket.objects.get(slug='carrefour')
        subscription = Subscription.objects.create(user=self.user, product=self.product)
        subscription.stores.add(carrefour)
        self.api_login()
        response = self.client.get(reverse('changomas:personal_subscriptions'))
        self.assertContains(response, 'Sin seleccionar ninguno equivale a todas las cadenas activas.')
        self.assertContains(response, f'<option value="{carrefour.slug}" selected')
        self.client.post(reverse('changomas:personal_subscriptions'), {
            'action': 'edit', 'subscription_id': subscription.pk,
            'product_id': self.product.pk, 'target_price': '', 'promo_alert': 'on',
            'stores': ['changomas'],
        })
        subscription.refresh_from_db()
        self.assertEqual(list(subscription.stores.values_list('slug', flat=True)), ['changomas'])

    def test_subscription_store_choices_only_include_active_stores(self):
        inactive = Supermarket.objects.get(slug='vea')
        inactive.is_active = False
        inactive.save(update_fields=['is_active'])
        self.api_login()
        response = self.client.post(reverse('changomas:personal_subscriptions_api'), data=json.dumps({
            'product_id': self.product.pk, 'promo_alert': True, 'stores': [inactive.slug],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_database_constraints_bound_cart_quantity_and_target_price(self):
        cart = ShoppingCart.objects.create(user=self.user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CartItem.objects.create(cart=cart, ean='12345678', quantity=100)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Subscription.objects.create(user=self.user, product=self.product, target_price=0)

    def test_preferences_require_email_verification_and_unsubscribe_is_post_only(self):
        preference = NotificationPreference.objects.create(user=self.user)
        self.api_login()
        page = reverse('changomas:personal_preferences')
        response = self.client.post(page, {'email_enabled': 'on'})
        preference.refresh_from_db()
        self.assertFalse(preference.email_enabled)

        token = signing.dumps({'uid': self.user.pk, 'email': self.user.email}, salt=UNSUBSCRIBE_SALT)
        unsubscribe_url = reverse('changomas:personal_unsubscribe', kwargs={'token': token})
        self.assertEqual(self.client.get(unsubscribe_url).status_code, 200)
        preference.email_verified_at = timezone.now()
        preference.email_enabled = True
        preference.save()
        self.client.post(unsubscribe_url)
        preference.refresh_from_db()
        self.assertFalse(preference.email_enabled)
        self.assertIsNotNone(preference.unsubscribed_at)

    def test_verification_email_is_explicit_and_token_marks_only_verified(self):
        self.api_login()
        page = reverse('changomas:personal_preferences')
        response = self.client.post(page, {'send_verification': 'on'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.client.post(page, {'send_verification': 'on'})
        self.assertEqual(len(mail.outbox), 1)
        token = signing.dumps({'uid': self.user.pk, 'email': self.user.email}, salt=EMAIL_SALT)
        verify_url = reverse('changomas:personal_verify_email', kwargs={'token': token})
        self.client.get(verify_url)
        preference = NotificationPreference.objects.get(user=self.user)
        self.assertIsNotNone(preference.email_verified_at)
        self.assertEqual(preference.verified_email, self.user.email.lower())
        self.assertFalse(preference.email_enabled)

    def test_verified_old_email_cannot_enable_alerts_for_changed_address(self):
        preference = NotificationPreference.objects.create(
            user=self.user, email_verified_at=timezone.now(), verified_email='old@example.com',
        )
        self.api_login()
        self.client.post(reverse('changomas:personal_preferences'), {'email_enabled': 'on'})
        preference.refresh_from_db()
        self.assertFalse(preference.email_enabled)
        self.assertContains(self.client.get(reverse('changomas:personal_preferences')), 'Sin verificar')


class PersonalThrottleTests(TestCase):
    def test_login_rejects_attempt_21_from_same_client(self):
        url = reverse('changomas:account_login')
        responses = [self.client.post(url, {'username': 'nobody@example.com', 'password': 'wrong'})
                     for _ in range(21)]
        self.assertTrue(all(response.status_code == 200 for response in responses[:20]))
        self.assertEqual(responses[-1].status_code, 429)

    def test_verification_rate_limit_allows_ten_per_day(self):
        from .throttling import allow_attempt

        start = 1_900_000_000
        with mock.patch('changomas.throttling.time.time', side_effect=[start + 61 * n for n in range(10)]):
            for _ in range(10):
                self.assertTrue(allow_attempt('verify-day', 123, 10, 86400))
        with mock.patch('changomas.throttling.time.time', return_value=start + 700):
            self.assertFalse(allow_attempt('verify-day', 123, 10, 86400))

    def test_verification_minute_window_allows_only_one(self):
        from .throttling import allow_attempt

        with mock.patch('changomas.throttling.time.time', return_value=1_900_000_000):
            self.assertTrue(allow_attempt('verify', 123, 1, 60))
            self.assertFalse(allow_attempt('verify', 123, 1, 60))
