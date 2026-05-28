import json
from datetime import timedelta, date
from decimal import Decimal

from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.models import User, Group
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views import View
from django.conf import settings
from django.core.paginator import Paginator

from .models import RideBooking, Payment, SiteSettings


def dashboard_context_processor(request):
    is_viewer = (
        request.user.is_authenticated and
        not request.user.is_superuser and
        request.user.groups.filter(name='Viewer').exists()
    )
    return {'user_is_viewer': is_viewer}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dashboard_access(user):
    return user.is_authenticated and user.is_active and (user.is_staff or user.is_superuser)


def _can_edit(user):
    if not _dashboard_access(user):
        return False
    return user.is_superuser or (user.is_staff and not user.groups.filter(name='Viewer').exists())


def _require_dashboard(view_fn):
    def wrapper(self, request, *args, **kwargs):
        if not _dashboard_access(request.user):
            return redirect(f'/dashboard/login/?next={request.path}')
        return view_fn(self, request, *args, **kwargs)
    return wrapper


def _require_owner(view_fn):
    def wrapper(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            messages.error(request, 'Owner access required.')
            return redirect('dashboard:overview')
        return view_fn(self, request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Auth Views
# ---------------------------------------------------------------------------

class DashboardLoginView(View):
    template_name = 'dashboard/login.html'

    def get(self, request):
        if _dashboard_access(request.user):
            return redirect('dashboard:overview')
        return render(request, self.template_name)

    def post(self, request):
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_active:
            if user.is_staff or user.is_superuser:
                login(request, user)
                next_url = request.GET.get('next', '')
                return redirect(next_url if next_url else 'dashboard:overview')
            else:
                messages.error(request, 'You do not have dashboard access.')
        else:
            messages.error(request, 'Invalid username or password.')
        return render(request, self.template_name)


class DashboardLogoutView(View):
    def get(self, request):
        logout(request)
        return redirect('dashboard:login')

    def post(self, request):
        logout(request)
        return redirect('dashboard:login')


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

class DashboardOverviewView(View):
    @_require_dashboard
    def get(self, request):
        today = timezone.now().date()
        week_ago = today - timedelta(days=6)

        # Stat cards
        today_bookings = RideBooking.objects.filter(created_at__date=today).count()
        today_revenue = (
            RideBooking.objects.filter(created_at__date=today, status=RideBooking.STATUS_CONFIRMED)
            .aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        )
        pending_count = RideBooking.objects.filter(status=RideBooking.STATUS_PENDING).count()
        confirmed_count = RideBooking.objects.filter(status=RideBooking.STATUS_CONFIRMED).count()
        total_revenue = (
            RideBooking.objects.filter(status=RideBooking.STATUS_CONFIRMED)
            .aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        )

        # 7-day chart data
        chart_labels = []
        chart_data = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            chart_labels.append(d.strftime('%d %b'))
            chart_data.append(
                RideBooking.objects.filter(created_at__date=d).count()
            )

        # Recent 5 bookings
        recent_bookings = RideBooking.objects.select_related().order_by('-created_at')[:5]

        return render(request, 'dashboard/overview.html', {
            'today_bookings': today_bookings,
            'today_revenue': today_revenue,
            'pending_count': pending_count,
            'confirmed_count': confirmed_count,
            'total_revenue': total_revenue,
            'chart_labels': json.dumps(chart_labels),
            'chart_data': json.dumps(chart_data),
            'recent_bookings': recent_bookings,
            'can_edit': _can_edit(request.user),
        })


class DashboardChartDataView(View):
    @_require_dashboard
    def get(self, request):
        days = int(request.GET.get('days', 7))
        days = min(days, 365)
        today = timezone.now().date()
        labels = []
        data = []
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            labels.append(d.strftime('%d %b'))
            data.append(RideBooking.objects.filter(created_at__date=d).count())
        return JsonResponse({'labels': labels, 'data': data})


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------

class DashboardBookingsView(View):
    @_require_dashboard
    def get(self, request):
        qs = RideBooking.objects.order_by('-created_at')

        search = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '')
        date_filter = request.GET.get('date_range', '')

        if search:
            qs = qs.filter(
                Q(reference__icontains=search) |
                Q(passenger_full_name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search) |
                Q(pickup_address__icontains=search) |
                Q(dropoff_address__icontains=search)
            )

        if status_filter in (RideBooking.STATUS_PENDING, RideBooking.STATUS_CONFIRMED, RideBooking.STATUS_CANCELLED):
            qs = qs.filter(status=status_filter)

        today = timezone.now().date()
        if date_filter == '7days':
            qs = qs.filter(created_at__date__gte=today - timedelta(days=6))
        elif date_filter == '30days':
            qs = qs.filter(created_at__date__gte=today - timedelta(days=29))
        elif date_filter == 'today':
            qs = qs.filter(created_at__date=today)

        paginator = Paginator(qs, 20)
        page = paginator.get_page(request.GET.get('page', 1))

        return render(request, 'dashboard/bookings.html', {
            'page_obj': page,
            'search': search,
            'status_filter': status_filter,
            'date_filter': date_filter,
            'can_edit': _can_edit(request.user),
            'total_count': qs.count(),
        })


class DashboardBookingDetailView(View):
    @_require_dashboard
    def get(self, request, pk):
        booking = get_object_or_404(RideBooking, pk=pk)
        payments = booking.payments.order_by('-created_at')
        return render(request, 'dashboard/booking_detail.html', {
            'booking': booking,
            'payments': payments,
            'can_edit': _can_edit(request.user),
        })

    @_require_dashboard
    def post(self, request, pk):
        if not _can_edit(request.user):
            messages.error(request, 'You do not have permission to edit bookings.')
            return redirect('dashboard:booking_detail', pk=pk)
        booking = get_object_or_404(RideBooking, pk=pk)
        new_status = request.POST.get('status', '').strip()
        valid = (RideBooking.STATUS_PENDING, RideBooking.STATUS_CONFIRMED, RideBooking.STATUS_CANCELLED)
        if new_status in valid:
            booking.status = new_status
            booking.save()
            messages.success(request, f'Booking {booking.reference} status updated to {new_status}.')
        return redirect('dashboard:booking_detail', pk=pk)


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

class DashboardPaymentsView(View):
    @_require_dashboard
    def get(self, request):
        qs = Payment.objects.select_related('booking').order_by('-created_at')

        status_filter = request.GET.get('status', '')
        search = request.GET.get('q', '').strip()

        if status_filter in (Payment.STATUS_PENDING, Payment.STATUS_PAID, Payment.STATUS_FAILED):
            qs = qs.filter(status=status_filter)

        if search:
            qs = qs.filter(
                Q(paynow_reference__icontains=search) |
                Q(booking__reference__icontains=search) |
                Q(booking__email__icontains=search)
            )

        paginator = Paginator(qs, 20)
        page = paginator.get_page(request.GET.get('page', 1))

        total_paid = (
            Payment.objects.filter(status=Payment.STATUS_PAID)
            .aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        )

        return render(request, 'dashboard/payments.html', {
            'page_obj': page,
            'status_filter': status_filter,
            'search': search,
            'total_paid': total_paid,
        })


# ---------------------------------------------------------------------------
# Notifications (recent activity)
# ---------------------------------------------------------------------------

class DashboardNotificationsView(View):
    @_require_dashboard
    def get(self, request):
        recent_bookings = RideBooking.objects.order_by('-created_at')[:30]
        recent_payments = (
            Payment.objects.filter(status=Payment.STATUS_PAID)
            .select_related('booking')
            .order_by('-updated_at')[:20]
        )
        return render(request, 'dashboard/notifications.html', {
            'recent_bookings': recent_bookings,
            'recent_payments': recent_payments,
        })


# ---------------------------------------------------------------------------
# User Management (owner only)
# ---------------------------------------------------------------------------

class DashboardUsersView(View):
    @_require_dashboard
    @_require_owner
    def get(self, request):
        raw_users = User.objects.all().prefetch_related('groups').order_by('-date_joined')
        users = []
        for u in raw_users:
            if u.is_superuser:
                u.role_label = 'owner'
            elif u.groups.filter(name='Viewer').exists():
                u.role_label = 'viewer'
            else:
                u.role_label = 'manager'
            users.append(u)
        return render(request, 'dashboard/users.html', {'users': users})


class DashboardAddUserView(View):
    @_require_dashboard
    @_require_owner
    def get(self, request):
        return render(request, 'dashboard/user_form.html', {'action': 'Add'})

    @_require_dashboard
    @_require_owner
    def post(self, request):
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        role = request.POST.get('role', 'viewer')

        errors = []
        if not first_name:
            errors.append('First name is required.')
        if not email:
            errors.append('Email is required.')
        if User.objects.filter(email=email).exists():
            errors.append('A user with that email already exists.')
        if not password:
            errors.append('Password is required.')
        elif len(password) < 8:
            errors.append('Password must be at least 8 characters.')
        elif password != confirm_password:
            errors.append('Passwords do not match.')

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'dashboard/user_form.html', {
                'action': 'Add',
                'form_data': request.POST,
            })

        username = email.split('@')[0]
        base = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f'{base}{counter}'
            counter += 1

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_staff=True,
        )

        if role == 'manager':
            grp, _ = Group.objects.get_or_create(name='Manager')
            user.groups.add(grp)
        else:
            grp, _ = Group.objects.get_or_create(name='Viewer')
            user.groups.add(grp)

        messages.success(request, f'User {user.get_full_name()} added successfully.')
        return redirect('dashboard:users')


class DashboardEditUserView(View):
    @_require_dashboard
    @_require_owner
    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if user == request.user:
            messages.error(request, 'You cannot edit your own account here.')
            return redirect('dashboard:users')
        current_role = 'owner' if user.is_superuser else (
            'manager' if not user.groups.filter(name='Viewer').exists() else 'viewer'
        )
        return render(request, 'dashboard/user_form.html', {
            'action': 'Edit',
            'edit_user': user,
            'current_role': current_role,
        })

    @_require_dashboard
    @_require_owner
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if user == request.user:
            messages.error(request, 'You cannot edit your own account here.')
            return redirect('dashboard:users')

        role = request.POST.get('role', 'viewer')
        is_active = request.POST.get('is_active') == 'on'

        user.is_active = is_active
        user.groups.clear()

        if role == 'manager':
            grp, _ = Group.objects.get_or_create(name='Manager')
            user.groups.add(grp)
            user.is_staff = True
            user.is_superuser = False
        elif role == 'viewer':
            grp, _ = Group.objects.get_or_create(name='Viewer')
            user.groups.add(grp)
            user.is_staff = True
            user.is_superuser = False
        user.save()

        messages.success(request, f'User {user.get_full_name()} updated.')
        return redirect('dashboard:users')


class DashboardDeleteUserView(View):
    @_require_dashboard
    @_require_owner
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if user == request.user:
            messages.error(request, 'You cannot delete your own account.')
            return redirect('dashboard:users')
        name = user.get_full_name() or user.username
        user.delete()
        messages.success(request, f'User {name} has been removed.')
        return redirect('dashboard:users')


# ---------------------------------------------------------------------------
# Settings (owner only)
# ---------------------------------------------------------------------------

class DashboardSettingsView(View):
    @_require_dashboard
    @_require_owner
    def get(self, request):
        from rides.services.pricing import DEFAULT_PRICING, DEFAULT_LONG_DISTANCE
        site_settings = SiteSettings.get_settings()
        brackets = site_settings.pricing_brackets or DEFAULT_PRICING['BRACKETS']
        last_bracket_max = max((float(b.get('max', 0)) for b in brackets), default=35) if brackets else 35
        return render(request, 'dashboard/settings.html', {
            'site_settings': site_settings,
            'django_email': settings.TAXI_OWNER_EMAIL,
            'django_phone': settings.TAXI_OWNER_PHONE,
            'pricing_brackets': brackets,
            'last_bracket_max': last_bracket_max,
            'ld_default_threshold': DEFAULT_LONG_DISTANCE['THRESHOLD_KM'],
            'ld_default_per_km': DEFAULT_LONG_DISTANCE['PER_KM'],
            'ld_default_base_pax': DEFAULT_LONG_DISTANCE['BASE_PASSENGERS'],
            'ld_default_extra_pax': DEFAULT_LONG_DISTANCE['EXTRA_PAX_FEE'],
            'ld_default_free_luggage': DEFAULT_LONG_DISTANCE['FREE_LUGGAGE_ITEMS'],
            'ld_default_luggage_fee': DEFAULT_LONG_DISTANCE['LUGGAGE_FEE'],
        })

    @_require_dashboard
    @_require_owner
    def post(self, request):
        site_settings = SiteSettings.get_settings()
        form_type = request.POST.get('form_type', 'contact')

        if form_type == 'pricing':
            try:
                site_settings.pricing_min_km = float(request.POST.get('pricing_min_km', 13))
                site_settings.pricing_above_35_per_km = float(request.POST.get('pricing_above_35_per_km', 1.0))
                site_settings.pricing_base_passengers = int(request.POST.get('pricing_base_passengers', 3))
                site_settings.pricing_extra_adult_fee = float(request.POST.get('pricing_extra_adult_fee', 10.0))
                site_settings.pricing_free_luggage = int(request.POST.get('pricing_free_luggage', 5))
                site_settings.pricing_luggage_fee = float(request.POST.get('pricing_luggage_fee', 3.0))

                brackets = []
                mins = request.POST.getlist('bracket_min')
                maxs = request.POST.getlist('bracket_max')
                prices = request.POST.getlist('bracket_price')
                for b_min, b_max, b_price in zip(mins, maxs, prices):
                    if b_min and b_max and b_price:
                        brackets.append({
                            "min": float(b_min),
                            "max": float(b_max),
                            "price": float(b_price),
                        })
                site_settings.pricing_brackets = brackets
                site_settings.save()
                messages.success(request, 'City pricing updated successfully.')
            except (ValueError, TypeError) as e:
                messages.error(request, f'Invalid pricing value: {e}')

        elif form_type == 'long_distance':
            try:
                site_settings.long_distance_threshold_km = float(request.POST.get('ld_threshold_km', 80))
                site_settings.long_distance_per_km = float(request.POST.get('ld_per_km', 1.40))
                site_settings.long_distance_base_passengers = int(request.POST.get('ld_base_passengers', 3))
                site_settings.long_distance_extra_pax_fee = float(request.POST.get('ld_extra_pax_fee', 40.0))
                site_settings.long_distance_free_luggage = int(request.POST.get('ld_free_luggage', 5))
                site_settings.long_distance_luggage_fee = float(request.POST.get('ld_luggage_fee', 5.0))
                site_settings.save()
                messages.success(request, 'Long distance pricing updated successfully.')
            except (ValueError, TypeError) as e:
                messages.error(request, f'Invalid long distance pricing value: {e}')

        else:
            email = request.POST.get('taxi_owner_email', '').strip()
            phone = request.POST.get('taxi_owner_phone', '').strip()
            if email:
                site_settings.taxi_owner_email = email
            if phone:
                site_settings.taxi_owner_phone = phone
            site_settings.save()
            messages.success(request, 'Settings saved successfully.')

        return redirect('dashboard:settings')
