from django.urls import path
from django.contrib.auth import views as auth_views
from . import dashboard_views

app_name = 'dashboard'

urlpatterns = [
    # Auth
    path('login/', dashboard_views.DashboardLoginView.as_view(), name='login'),
    path('logout/', dashboard_views.DashboardLogoutView.as_view(), name='logout'),
    path(
        'password-reset/',
        auth_views.PasswordResetView.as_view(
            template_name='dashboard/forgot_password.html',
            email_template_name='dashboard/email/password_reset_email.txt',
            html_email_template_name='dashboard/email/password_reset_email.html',
            subject_template_name='dashboard/email/password_reset_subject.txt',
        ),
        name='password_reset',
    ),
    path(
        'password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(template_name='dashboard/password_reset_done.html'),
        name='password_reset_done',
    ),
    path(
        'password-reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(template_name='dashboard/password_reset_confirm.html'),
        name='password_reset_confirm',
    ),
    path(
        'password-reset/complete/',
        auth_views.PasswordResetCompleteView.as_view(template_name='dashboard/password_reset_complete.html'),
        name='password_reset_complete',
    ),

    # Dashboard pages
    path('', dashboard_views.DashboardOverviewView.as_view(), name='overview'),
    path('bookings/', dashboard_views.DashboardBookingsView.as_view(), name='bookings'),
    path('bookings/<uuid:pk>/', dashboard_views.DashboardBookingDetailView.as_view(), name='booking_detail'),
    path('payments/', dashboard_views.DashboardPaymentsView.as_view(), name='payments'),
    path('notifications/', dashboard_views.DashboardNotificationsView.as_view(), name='notifications'),

    # User management (owner only)
    path('users/', dashboard_views.DashboardUsersView.as_view(), name='users'),
    path('users/add/', dashboard_views.DashboardAddUserView.as_view(), name='add_user'),
    path('users/<int:pk>/edit/', dashboard_views.DashboardEditUserView.as_view(), name='edit_user'),
    path('users/<int:pk>/delete/', dashboard_views.DashboardDeleteUserView.as_view(), name='delete_user'),

    # Settings (owner only)
    path('settings/', dashboard_views.DashboardSettingsView.as_view(), name='settings'),

    # Chart AJAX
    path('api/chart-data/', dashboard_views.DashboardChartDataView.as_view(), name='chart_data'),
]
