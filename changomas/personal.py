import json
import re
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.http import JsonResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .models import Product, Supermarket
from .payloads import loads_bounded
from .personal_forms import EmailLoginForm, RegistrationForm, SubscriptionForm
from .throttling import allow_auth, allow_attempt
from .personal_models import CartItem, NotificationPreference, ShoppingCart, Subscription

MAX_CART_ITEMS = 60
MAX_SUBSCRIPTIONS = 100
IMPORT_SALT = 'changomas.cart-import.v1'
EMAIL_SALT = 'changomas.email-verification.v1'
UNSUBSCRIBE_SALT = 'changomas.email-unsubscribe.v1'
EAN_RE = re.compile(r'^(?:\d{8}|\d{12}|\d{13}|\d{14}|listing-\d{1,18})$')


def private_no_store(response):
    response['Cache-Control'] = 'private, no-store, max-age=0'
    response['Pragma'] = 'no-cache'
    return response


def _json_body(request):
    try:
        data = loads_bounded(request.body or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
        raise ValueError('JSON inválido.')
    if not isinstance(data, dict):
        raise ValueError('Se esperaba un objeto JSON.')
    return data


def parse_items(items):
    """Validate guest cart rows; quantities are bounded to 99 on import."""
    if not isinstance(items, list):
        raise ValueError('items debe ser una lista.')
    parsed = {}
    for row in items:
        if not isinstance(row, dict):
            raise ValueError('Cada producto debe ser un objeto.')
        ean = str(row.get('ean', '')).strip()
        if not EAN_RE.fullmatch(ean):
            raise ValueError('EAN inválido.')
        try:
            quantity = int(row.get('qty', row.get('quantity')))
        except (TypeError, ValueError):
            raise ValueError('Cantidad inválida.')
        if quantity < 1:
            raise ValueError('La cantidad debe ser al menos 1.')
        parsed[ean] = min(99, parsed.get(ean, 0) + quantity)
    if len(parsed) > MAX_CART_ITEMS:
        raise ValueError(f'El carrito admite hasta {MAX_CART_ITEMS} productos.')
    return parsed


def _cart_for(user):
    try:
        return ShoppingCart.objects.get_or_create(user=user)[0]
    except IntegrityError:
        return ShoppingCart.objects.get(user=user)


def _cart_payload(cart):
    return {
        'items': [{'ean': item.ean, 'qty': item.quantity} for item in cart.items.all()],
        'version': cart.version,
    }


@never_cache
def register(request):
    if request.user.is_authenticated:
        return redirect('changomas:personal_subscriptions')
    if request.method == 'POST' and not allow_auth(request, 'registration', 5, 3600):
        return private_no_store(JsonResponse({'error': 'Demasiados intentos. Volvé a intentar más tarde.'}, status=429))
    form = RegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                user = get_user_model().objects.create_user(
                    email=form.cleaned_data['email'], password=form.cleaned_data['password1']
                )
        except IntegrityError:
            form.add_error('email', 'No pudimos completar el registro. Revisá los datos o intentá ingresar.')
            return private_no_store(render(request, 'changomas/personal/register.html', {'form': form}))
        login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
        _cart_for(user)
        return redirect(_safe_next(request, request.POST.get('next')) or 'changomas:personal_subscriptions')
    return private_no_store(render(request, 'changomas/personal/register.html', {'form': form, 'next': request.GET.get('next', '')}))


def _safe_next(request, value):
    if value and url_has_allowed_host_and_scheme(value, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return value
    return None


@never_cache
def login_view(request):
    if request.user.is_authenticated:
        return redirect('changomas:personal_subscriptions')
    if request.method == 'POST' and not allow_auth(request, 'login'):
        return private_no_store(JsonResponse({'error': 'Demasiados intentos. Volvé a intentar más tarde.'}, status=429))
    form = EmailLoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        target = _safe_next(request, request.POST.get('next'))
        return redirect(target or 'changomas:personal_subscriptions')
    return private_no_store(render(request, 'changomas/personal/login.html', {'form': form, 'next': request.GET.get('next', '')}))


@login_required(login_url='changomas:account_login')
@never_cache
def subscriptions_page(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'add')
        subscription = None
        if action != 'add':
            subscription = get_object_or_404(Subscription, pk=request.POST.get('subscription_id') if str(request.POST.get('subscription_id', '')).isdigit() else 0, user=request.user)
        if action == 'delete':
            subscription.delete()
            messages.success(request, 'Seguimiento eliminado.')
        elif action == 'pause':
            subscription.is_active = not subscription.is_active
            subscription.save(update_fields=['is_active'])
        elif action == 'edit':
            form = SubscriptionForm(request.POST)
            if form.is_valid():
                subscription.target_price = form.cleaned_data['target_price']
                subscription.promo_alert = form.cleaned_data['promo_alert']
                subscription.save(update_fields=['target_price', 'promo_alert'])
                subscription.stores.set(form.cleaned_data['stores'])
                messages.success(request, 'Seguimiento actualizado.')
            else:
                messages.error(request, 'Revisá los datos del seguimiento.')
        else:
            form = SubscriptionForm(request.POST)
            try:
                product = Product.objects.filter(pk=form.data.get('product_id'), supermarket__is_active=True).first()
            except (ValueError, TypeError):
                product = None
            if form.is_valid() and product:
                exists = Subscription.objects.filter(user=request.user, product=product).exists()
                if not exists and Subscription.objects.filter(user=request.user).count() >= MAX_SUBSCRIPTIONS:
                    messages.error(request, f'Podés seguir hasta {MAX_SUBSCRIPTIONS} productos.')
                else:
                    subscription, _ = Subscription.objects.update_or_create(
                        user=request.user, product=product,
                        defaults={
                            'target_price': form.cleaned_data['target_price'],
                            'promo_alert': form.cleaned_data['promo_alert'],
                            'is_active': True,
                        },
                    )
                    subscription.stores.set(form.cleaned_data['stores'])
                    messages.success(request, 'Producto agregado a tus seguimientos.')
            else:
                messages.error(request, 'Seleccioná un producto y al menos un tipo de alerta válido.')
        return redirect('changomas:personal_subscriptions')
    subscriptions = Subscription.objects.filter(user=request.user).select_related('product', 'product__supermarket').prefetch_related('stores')
    for subscription in subscriptions:
        subscription.edit_form = SubscriptionForm(initial={
            'product_id': subscription.product_id,
            'target_price': subscription.target_price,
            'promo_alert': subscription.promo_alert,
            'stores': list(subscription.stores.values_list('slug', flat=True)),
        })
    response = render(request, 'changomas/personal/subscriptions.html', {
        'subscriptions': subscriptions,
        'stores': Supermarket.objects.filter(is_active=True).order_by('name'),
    })
    return private_no_store(response)


@login_required(login_url='changomas:account_login')
@require_POST
def subscription_add(request, pk):
    # Product-specific form action used by cards in the catalog UI.
    if not Product.objects.filter(pk=pk).exists():
        return JsonResponse({'error': 'Producto inexistente.'}, status=404)
    request.POST = request.POST.copy()
    request.POST['product_id'] = str(pk)
    request.POST['action'] = 'add'
    return subscriptions_page(request)


@login_required(login_url='changomas:account_login')
@never_cache
def preferences(request):
    preference, _ = NotificationPreference.objects.get_or_create(user=request.user)
    email_is_verified = bool(
        preference.email_verified_at
        and preference.verified_email.lower() == request.user.email.lower()
    )
    if request.method == 'POST':
        preference.email_enabled = request.POST.get('email_enabled') == 'on'
        if preference.email_enabled and not email_is_verified:
            preference.email_enabled = False
            messages.error(request, 'Verificá tu email antes de activar las notificaciones.')
        elif preference.email_enabled:
            preference.unsubscribed_at = None
            messages.success(request, 'Notificaciones por email activadas.')
        else:
            preference.unsubscribed_at = timezone.now()
            messages.success(request, 'Notificaciones por email desactivadas.')
        preference.save(update_fields=['email_enabled', 'unsubscribed_at'])
        if request.POST.get('send_verification') == 'on' and not email_is_verified:
            sent = _send_verification(request, preference)
            messages.info(request, 'Te enviamos un enlace de verificación.' if sent else 'No se pudo enviar ahora; probá nuevamente más tarde.')
        return redirect('changomas:personal_preferences')
    response = render(request, 'changomas/personal/preferences.html', {
        'preference': preference, 'email_is_verified': email_is_verified,
    })
    return private_no_store(response)


def _send_verification(request, preference):
    if not allow_attempt('verify', request.user.pk, 1, 60) or not allow_attempt('verify-day', request.user.pk, 10, 86400):
        return False
    token = signing.dumps({'uid': request.user.pk, 'email': request.user.email}, salt=EMAIL_SALT)
    from urllib.parse import urljoin
    url = urljoin(settings.SUPERMARKET_PUBLIC_URL, reverse('changomas:personal_verify_email', kwargs={'token': token}))
    try:
        send_mail('Verificá tu email', f'Confirmá tu dirección desde este enlace: {url}', None, [request.user.email], fail_silently=False)
    except Exception:
        return False
    return True


@require_GET
@never_cache
def verify_email(request, token):
    try:
        payload = signing.loads(token, salt=EMAIL_SALT, max_age=60 * 60 * 24)
        user = get_user_model().objects.get(pk=payload['uid'], email__iexact=payload['email'])
    except (signing.BadSignature, signing.SignatureExpired, KeyError, get_user_model().DoesNotExist):
        return render(request, 'changomas/personal/verification_result.html', {'verified': False}, status=400)
    preference, _ = NotificationPreference.objects.get_or_create(user=user)
    if not preference.email_verified_at:
        preference.email_verified_at = timezone.now()
    preference.verified_email = user.email.strip().lower()
    preference.save(update_fields=['email_verified_at', 'verified_email'])
    return render(request, 'changomas/personal/verification_result.html', {'verified': True})


@require_http_methods(['GET', 'POST'])
@never_cache
def unsubscribe(request, token):
    try:
        payload = signing.loads(token, salt=UNSUBSCRIBE_SALT, max_age=60 * 60 * 24 * 30)
        user = get_user_model().objects.get(pk=payload['uid'], email__iexact=payload['email'])
    except (signing.BadSignature, signing.SignatureExpired, KeyError, get_user_model().DoesNotExist):
        return render(request, 'changomas/personal/unsubscribe.html', {'invalid': True}, status=400)
    if request.method == 'POST':
        preference, _ = NotificationPreference.objects.get_or_create(user=user)
        preference.email_enabled = False
        preference.unsubscribed_at = timezone.now()
        preference.save(update_fields=['email_enabled', 'unsubscribed_at'])
        return render(request, 'changomas/personal/unsubscribe.html', {'done': True})
    return render(request, 'changomas/personal/unsubscribe.html', {'token': token, 'done': False})


@login_required(login_url='changomas:account_login')
@require_GET
@ensure_csrf_cookie
@never_cache
def cart_api(request):
    return private_no_store(JsonResponse(_cart_payload(_cart_for(request.user))))


@login_required(login_url='changomas:account_login')
@require_http_methods(['PUT', 'DELETE'])
@never_cache
def cart_item_api(request, ean):
    if not EAN_RE.fullmatch(ean):
        return JsonResponse({'error': 'EAN inválido.'}, status=400)
    try:
        data = _json_body(request)
        version = int(data.get('version'))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'JSON y versión requeridos.'}, status=400)
    with transaction.atomic():
        cart = ShoppingCart.objects.select_for_update().filter(user=request.user).first()
        if cart is None:
            cart = _cart_for(request.user)
        if cart.version != version:
            return private_no_store(JsonResponse({'error': 'versión_conflictiva', **_cart_payload(cart)}, status=409))
        if request.method == 'DELETE':
            cart.items.filter(ean=ean).delete()
        else:
            try:
                quantity = int(data.get('qty', data.get('quantity')))
            except (TypeError, ValueError):
                return JsonResponse({'error': 'Cantidad inválida.'}, status=400)
            if quantity < 1:
                return JsonResponse({'error': 'La cantidad debe ser al menos 1.'}, status=400)
            quantity = min(99, quantity)
            if not cart.items.filter(ean=ean).exists() and cart.items.count() >= MAX_CART_ITEMS:
                return JsonResponse({'error': f'El carrito admite hasta {MAX_CART_ITEMS} productos.'}, status=400)
            CartItem.objects.update_or_create(cart=cart, ean=ean, defaults={'quantity': quantity})
        cart.version += 1
        cart.save(update_fields=['version'])
    return private_no_store(JsonResponse(_cart_payload(cart)))


@login_required(login_url='changomas:account_login')
@require_POST
@never_cache
def cart_import_api(request):
    try:
        data = _json_body(request)
        items = parse_items(data.get('items'))
        import_id = str(data.get('import_id', '')).strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', import_id):
            raise ValueError('import_id inválido.')
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    with transaction.atomic():
        cart = ShoppingCart.objects.select_for_update().filter(user=request.user).first()
        if cart is None:
            cart = _cart_for(request.user)
        if import_id in cart.imported_batches:
            return private_no_store(JsonResponse(_cart_payload(cart)))
        merged = {row.ean: row.quantity for row in cart.items.all()}
        for ean, quantity in items.items():
            merged[ean] = min(99, merged.get(ean, 0) + quantity)
        if len(merged) > MAX_CART_ITEMS:
            return JsonResponse({'error': f'El carrito admite hasta {MAX_CART_ITEMS} productos.'}, status=400)
        for ean, quantity in merged.items():
            CartItem.objects.update_or_create(cart=cart, ean=ean, defaults={'quantity': quantity})
        cart.imported_batches = (cart.imported_batches + [import_id])[-20:]
        cart.version += 1
        cart.save(update_fields=['imported_batches', 'version'])
    return private_no_store(JsonResponse(_cart_payload(cart)))


@login_required(login_url='changomas:account_login')
@require_http_methods(['GET', 'POST'])
@never_cache
def subscriptions_api(request):
    if request.method == 'GET':
        rows = Subscription.objects.filter(user=request.user).select_related('product')
        data = [{'id': row.pk, 'product_id': row.product_id, 'name': row.product.name,
                 'target_price': str(row.target_price) if row.target_price is not None else None,
                 'promo_alert': row.promo_alert, 'is_active': row.is_active,
                 'stores': list(row.stores.values_list('slug', flat=True)),
                 'all_stores': not row.stores.exists()} for row in rows]
        return private_no_store(JsonResponse({'subscriptions': data}))
    try:
        data = _json_body(request)
        form = SubscriptionForm(data)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors.get_json_data()}, status=400)
    product = Product.objects.filter(pk=form.cleaned_data['product_id'], supermarket__is_active=True).first()
    if not product:
        return JsonResponse({'error': 'Producto inexistente.'}, status=404)
    if not Subscription.objects.filter(user=request.user, product=product).exists() and Subscription.objects.filter(user=request.user).count() >= MAX_SUBSCRIPTIONS:
        return JsonResponse({'error': f'Podés seguir hasta {MAX_SUBSCRIPTIONS} productos.'}, status=400)
    row, _ = Subscription.objects.update_or_create(user=request.user, product=product, defaults={
        'target_price': form.cleaned_data['target_price'], 'promo_alert': form.cleaned_data['promo_alert'], 'is_active': True,
    })
    row.stores.set(form.cleaned_data['stores'])
    return private_no_store(JsonResponse({
        'id': row.pk, 'product_id': row.product_id, 'is_active': row.is_active,
        'stores': list(row.stores.values_list('slug', flat=True)),
        'all_stores': not row.stores.exists(),
    }, status=201))


from django.contrib.auth.views import PasswordResetView


class TrackerPasswordResetView(PasswordResetView):
    def post(self, request, *args, **kwargs):
        if not allow_auth(request, 'password-reset', 5, 3600):
            return private_no_store(JsonResponse({'error': 'Volvé a intentarlo más tarde.'}, status=429))
        return super().post(request, *args, **kwargs)
