"""URLs for Users app"""

from django.urls import path
from .views import (
    login_view, logout_view, profile_view,
    mfa_verify, mfa_toggle,
    update_email, update_password,
    forgot_password, reset_password,
    register_view,
)

urlpatterns = [
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('profile/', profile_view, name='profile'),
    path('me/', profile_view, name='me'),
    path('mfa/verify/', mfa_verify, name='mfa-verify'),
    path('mfa/toggle/', mfa_toggle, name='mfa-toggle'),
    path('update-email/', update_email, name='update-email'),
    path('update-password/', update_password, name='update-password'),
    path('forgot-password/', forgot_password, name='forgot-password'),
    path('reset-password/', reset_password, name='reset-password'),
    path('register/', register_view, name='register'),
]
