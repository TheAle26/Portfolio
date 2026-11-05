from decimal import Decimal
import smtplib
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from changomas.alert_models import EmailDelivery, PriceAlertEvent
from changomas.alert_models import JobLease
from changomas.jobs import refresh_followed_products
from changomas.models import PriceObservation, Product, SourceRun, Supermarket
from changomas.notifications import dispatch_email_deliveries, enqueue_observation_alerts, evaluate_run
from changomas.personal_models import NotificationPreference, Subscription


class NotificationRulesTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username='buyer', email='buyer@example.test', password='unused')
        self.store = Supermarket.objects.get(pk='changomas')
        self.product = Product.objects.create(
            supermarket=self.store, reference_code='vtex-test-1', vtex_product_id='test-1',
            vtex_sku_id='sku-1', name='Producto de prueba',
        )
        self.subscription = Subscription.objects.create(
            user=self.user, product=self.product, target_price=Decimal('90.00'), promo_alert=True,
        )
        self.preference = NotificationPreference.objects.create(
            user=self.user, email_enabled=True, email_verified_at=timezone.now(), verified_email=self.user.email,
        )
        self.run = SourceRun.objects.create(supermarket=self.store, kind='followed', status='running')

    def observation(self, price, promo=None, text=''):
        return PriceObservation.objects.create(
            product=self.product, source_run=self.run, observed_at=timezone.now(),
            price=Decimal(price), list_price=None,
            promo_price=Decimal(promo) if promo is not None else None,
            promo_text=text, promotion={}, fingerprint=f'{price}:{promo}:{text}',
        )

    def test_repeated_condition_does_not_duplicate_and_target_rearms(self):
        first = self.observation('89')
        enqueue_observation_alerts(first)
        enqueue_observation_alerts(first)
        self.assertEqual(PriceAlertEvent.objects.filter(subscription=self.subscription).count(), 1)

        above = self.observation('95')
        enqueue_observation_alerts(above)
        below_again = self.observation('89')
        enqueue_observation_alerts(below_again)
        targets = PriceAlertEvent.objects.filter(subscription=self.subscription, payload__kind='target')
        self.assertEqual(targets.count(), 2)

    def test_promotion_signature_only_triggers_once(self):
        obs = self.observation('100', '80', '2 x 1')
        enqueue_observation_alerts(obs)
        enqueue_observation_alerts(obs)
        self.assertEqual(PriceAlertEvent.objects.filter(subscription=self.subscription, payload__kind='promotion').count(), 1)

    def test_reprocessing_a_run_does_not_duplicate_events_or_delivery(self):
        self.product.last_price_checked_at = timezone.now()
        self.product.save(update_fields=['last_price_checked_at'])
        self.observation('80')
        evaluate_run(self.run)
        evaluate_run(self.run)
        self.assertEqual(PriceAlertEvent.objects.filter(subscription=self.subscription).count(), 1)
        self.assertEqual(EmailDelivery.objects.count(), 1)

    def test_no_delivery_without_verified_opt_in_and_revocation_stops_pending(self):
        self.preference.email_enabled = False
        self.preference.save(update_fields=['email_enabled'])
        obs = self.observation('80')
        enqueue_observation_alerts(obs)
        self.assertEqual(EmailDelivery.objects.count(), 0)
        rearm = self.observation('95')
        enqueue_observation_alerts(rearm)

        # A later alert is queued when opted in, then a revocation is honored by the dispatcher.
        self.preference.email_enabled = True
        self.preference.save(update_fields=['email_enabled'])
        obs2 = self.observation('80')
        enqueue_observation_alerts(obs2)
        self.preference.unsubscribed_at = timezone.now()
        self.preference.save(update_fields=['unsubscribed_at'])
        with override_settings(SUPERMARKET_EMAILS_ENABLED=True):
            result = dispatch_email_deliveries(send=True)
        self.assertEqual(result['sent'], 0)
        self.assertEqual(EmailDelivery.objects.get().state, EmailDelivery.State.FAILED)

    @override_settings(SUPERMARKET_EMAILS_ENABLED=True)
    @patch('changomas.notifications.EmailMultiAlternatives.send', return_value=1)
    def test_successful_dispatch_is_not_retried(self, send):
        obs = self.observation('80')
        enqueue_observation_alerts(obs)
        result = dispatch_email_deliveries(send=True)
        self.assertEqual(result['sent'], 1)
        self.assertEqual(EmailDelivery.objects.get().state, EmailDelivery.State.SENT)
        dispatch_email_deliveries(send=True)
        send.assert_called_once()

    def test_smtp_4xx_retries_same_delivery_at_most_five_times(self):
        obs = self.observation('80')
        enqueue_observation_alerts(obs)
        delivery = EmailDelivery.objects.get()
        now = timezone.now()
        failure = smtplib.SMTPResponseException(451, b'temporary failure')

        with override_settings(SUPERMARKET_EMAILS_ENABLED=True), patch(
            'changomas.notifications.EmailMultiAlternatives.send', side_effect=failure,
        ) as send:
            for attempt in range(1, 6):
                result = dispatch_email_deliveries(send=True, now=now)
                self.assertEqual(result['sent'], 0)
                delivery.refresh_from_db()
                self.assertEqual(delivery.attempts, attempt)
                self.assertEqual(delivery.state, EmailDelivery.State.FAILED)
                if attempt < 5:
                    self.assertIsNotNone(delivery.next_attempt_at)
                    now = delivery.next_attempt_at
            dispatch_email_deliveries(send=True, now=now + timedelta(days=1))

        delivery.refresh_from_db()
        self.assertEqual(send.call_count, 5)
        self.assertIsNone(delivery.next_attempt_at)
        self.assertEqual(EmailDelivery.objects.count(), 1)
        self.assertEqual(PriceAlertEvent.objects.count(), 1)

    @override_settings(SUPERMARKET_EMAILS_ENABLED=True)
    @patch('changomas.notifications.EmailMultiAlternatives.send', side_effect=smtplib.SMTPServerDisconnected('connection lost'))
    def test_disconnect_is_uncertain_and_never_retried(self, send):
        enqueue_observation_alerts(self.observation('80'))
        delivery = EmailDelivery.objects.get()

        dispatch_email_deliveries(send=True)
        dispatch_email_deliveries(send=True, now=timezone.now() + timedelta(days=1))

        delivery.refresh_from_db()
        self.assertEqual(delivery.state, EmailDelivery.State.UNCERTAIN)
        self.assertEqual(delivery.attempts, 1)
        self.assertIsNone(delivery.next_attempt_at)
        send.assert_called_once()

    def test_target_change_does_not_repeat_same_promotion(self):
        obs = self.observation('100', '80', '2 x 1')
        enqueue_observation_alerts(obs)
        self.subscription.target_price = Decimal('95.00')
        self.subscription.save(update_fields=['target_price'])
        enqueue_observation_alerts(obs)

        self.assertEqual(
            PriceAlertEvent.objects.filter(subscription=self.subscription, payload__kind='promotion').count(), 1,
        )

    def test_different_verified_email_blocks_alert_delivery(self):
        self.preference.verified_email = 'other@example.test'
        self.preference.save(update_fields=['verified_email'])

        enqueue_observation_alerts(self.observation('80'))

        self.assertEqual(PriceAlertEvent.objects.count(), 1)
        self.assertEqual(EmailDelivery.objects.count(), 0)

    def test_store_filter_prevents_alert_for_unselected_store(self):
        self.subscription.stores.add(Supermarket.objects.get(pk='carrefour'))

        enqueue_observation_alerts(self.observation('80'))

        self.assertEqual(PriceAlertEvent.objects.count(), 0)
        self.assertEqual(EmailDelivery.objects.count(), 0)

    def test_evaluate_run_uses_latest_observation_even_when_it_predates_run(self):
        old_observation = self.observation('80')
        old_observation.observed_at = timezone.now() - timedelta(days=2)
        old_observation.save(update_fields=['observed_at'])
        self.subscription.delete()
        late_user = get_user_model().objects.create_user(
            username='late-buyer', email='late@example.test', password='unused',
        )
        NotificationPreference.objects.create(
            user=late_user, email_enabled=True, email_verified_at=timezone.now(), verified_email=late_user.email,
        )
        late_subscription = Subscription.objects.create(
            user=late_user, product=self.product, target_price=Decimal('90.00'),
        )
        self.product.last_price_checked_at = timezone.now()
        self.product.save(update_fields=['last_price_checked_at'])

        evaluate_run(self.run)

        event = PriceAlertEvent.objects.get(subscription=late_subscription)
        self.assertEqual(event.observation, old_observation)
        self.assertEqual(EmailDelivery.objects.filter(user=late_user).count(), 1)

    def test_old_pending_claim_is_not_uncertain_before_fifteen_minutes(self):
        enqueue_observation_alerts(self.observation('80'))
        delivery = EmailDelivery.objects.get()
        now = timezone.now()
        delivery.state = EmailDelivery.State.SENDING
        delivery.claimed_at = now - timedelta(minutes=14, seconds=59)
        delivery.save(update_fields=['state', 'claimed_at'])

        dispatch_email_deliveries(send=False, now=now)

        delivery.refresh_from_db()
        self.assertEqual(delivery.state, EmailDelivery.State.SENDING)

        dispatch_email_deliveries(send=False, now=now + timedelta(minutes=15, seconds=1))
        delivery.refresh_from_db()
        self.assertEqual(delivery.state, EmailDelivery.State.UNCERTAIN)

    @override_settings(SUPERMARKET_EMAILS_ENABLED=True)
    @patch('changomas.notifications.EmailMultiAlternatives.send', return_value=1)
    def test_paused_subscription_is_removed_from_batched_email_payload(self, _send):
        second_product = Product.objects.create(
            supermarket=self.store, reference_code='vtex-test-2', vtex_product_id='test-2',
            vtex_sku_id='sku-2', name='Otro producto',
        )
        second_subscription = Subscription.objects.create(
            user=self.user, product=second_product, target_price=Decimal('90.00'),
        )
        self.product.last_price_checked_at = timezone.now()
        self.product.save(update_fields=['last_price_checked_at'])
        second_product.last_price_checked_at = timezone.now()
        second_product.save(update_fields=['last_price_checked_at'])
        PriceObservation.objects.create(
            product=second_product, source_run=self.run, observed_at=timezone.now(),
            price=Decimal('80.00'), fingerprint='second-product-price',
        )
        self.observation('80')
        evaluate_run(self.run)
        delivery = EmailDelivery.objects.get(user=self.user)
        self.assertEqual(len(delivery.body_snapshot['events']), 2)
        second_subscription.is_active = False
        second_subscription.save(update_fields=['is_active'])
        rendered_contexts = []

        def render(_template, context):
            rendered_contexts.append(context)
            return 'rendered'

        with patch('changomas.notifications.render_to_string', side_effect=render):
            dispatch_email_deliveries(send=True)

        self.assertEqual(len(rendered_contexts[0]['events']), 1)
        self.assertEqual(
            rendered_contexts[0]['events'][0]['subscription_id'], self.subscription.pk,
        )

    def test_refresh_followed_products_records_changes_and_releases_leases(self):
        fake_client = MagicMock()
        from changomas.scraper import STORE_CONFIGS
        fake_client.config = STORE_CONFIGS['changomas']
        fake_client._get_json.return_value = [{'productId': 'test-1'}]
        parsed_product = {
            'vtex_product_id': 'test-1', 'vtex_sku_id': 'sku-1',
            'ean': '7790580146115', 'product_reference': 'new-ref',
            'measurement_unit': 'un', 'unit_multiplier': Decimal('1'),
            'name': 'Producto actualizado', 'brand': 'Marca', 'category': 'Almacén',
            'image_url': '', 'link': 'https://example.test/producto',
            'is_available': False, 'price': Decimal('80.00'),
            'list_price': None, 'promo_price': None, 'promo_text': '', 'promotion': {},
        }
        with patch('changomas.jobs.VtexClient', return_value=fake_client), patch(
            'changomas.jobs.parse_products', return_value=[parsed_product],
        ):
            stats = refresh_followed_products(delay=0)

        self.product.refresh_from_db()
        self.assertEqual(stats['products'], 1)
        self.assertEqual(stats['errors'], 0)
        self.assertEqual(stats['observations'], 1)
        self.assertFalse(self.product.is_available)
        self.assertTrue(self.product.is_comparable)
        self.assertFalse(JobLease.objects.exists())

    @override_settings(SUPERMARKET_EMAILS_ENABLED=True)
    @patch('changomas.notifications.EmailMultiAlternatives.send', return_value=1)
    def test_dispatch_limit_sends_oldest_deliveries_first(self, send):
        deliveries = []
        for index in range(3):
            deliveries.append(EmailDelivery.objects.create(
                user=self.user,
                batch_key=f'fifo-{index}',
                body_snapshot={'events': [{'subscription_id': self.subscription.pk}]},
            ))
        # The dispatcher's stable ordering is creation time then primary key.
        result = dispatch_email_deliveries(send=True, limit=2)

        self.assertEqual(result['sent'], 2)
        states = list(EmailDelivery.objects.order_by('created_at', 'pk').values_list('state', flat=True))
        self.assertEqual(states, [EmailDelivery.State.SENT, EmailDelivery.State.SENT, EmailDelivery.State.PENDING])
        self.assertEqual(send.call_count, 2)
