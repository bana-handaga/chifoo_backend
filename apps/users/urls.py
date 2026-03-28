"""URLs for Users app"""

from django.urls import path
from .views import login_view, logout_view, profile_view, mfa_verify, mfa_toggle

urlpatterns = [
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('profile/', profile_view, name='profile'),
    path('me/', profile_view, name='me'),
    path('mfa/verify/', mfa_verify, name='mfa-verify'),
    path('mfa/toggle/', mfa_toggle, name='mfa-toggle'),
]
