"""Views for Users app"""

import random
from datetime import timedelta

from django.contrib.auth import get_user_model, authenticate
from django.core.mail import send_mail
from django.conf import settings as django_settings
from django.utils import timezone
from rest_framework import serializers, viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.authtoken.models import Token

from .models import MfaOtp
from .serializers import UserSerializer

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


def _send_otp_email(user, code):
    subject = 'Kode Verifikasi Login PTMA'
    message = (
        f'Halo {user.get_full_name() or user.username},\n\n'
        f'Kode verifikasi login Anda: {code}\n\n'
        f'Kode berlaku selama 5 menit. Jangan bagikan kode ini kepada siapapun.\n\n'
        f'PTMA Monitoring System'
    )
    from_email = getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@ptma.id')
    send_mail(subject, message, from_email, [user.email], fail_silently=True)


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """Login dan dapatkan token. Jika MFA aktif, kembalikan mfa_required=True."""
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    user = authenticate(
        username=serializer.validated_data['username'],
        password=serializer.validated_data['password']
    )
    if not user:
        return Response(
            {'detail': 'Username atau password salah.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    # Jika MFA aktif dan user punya email
    if user.mfa_enabled and user.email:
        code = f'{random.randint(0, 999999):06d}'
        otp = MfaOtp.objects.create(
            user=user,
            code=code,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        _send_otp_email(user, code)
        return Response({
            'mfa_required': True,
            'mfa_token': str(otp.session_key),
            'email_hint': user.email[:3] + '***' + user.email[user.email.index('@'):],
        })

    token, _ = Token.objects.get_or_create(user=user)
    user.last_active = timezone.now()
    user.save(update_fields=['last_active'])

    return Response({
        'token': token.key,
        'user': UserSerializer(user).data
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def mfa_verify(request):
    """Verifikasi kode OTP dari email lalu kembalikan token."""
    mfa_token = request.data.get('mfa_token', '').strip()
    otp_code = request.data.get('otp_code', '').strip()

    try:
        otp = MfaOtp.objects.select_related('user').get(session_key=mfa_token)
    except (MfaOtp.DoesNotExist, Exception):
        return Response({'detail': 'Sesi tidak valid.'}, status=status.HTTP_400_BAD_REQUEST)

    if not otp.is_valid():
        return Response({'detail': 'Kode OTP sudah kadaluarsa atau sudah digunakan.'}, status=status.HTTP_400_BAD_REQUEST)

    if otp.code != otp_code:
        return Response({'detail': 'Kode OTP salah.'}, status=status.HTTP_400_BAD_REQUEST)

    otp.is_used = True
    otp.save(update_fields=['is_used'])

    user = otp.user
    token, _ = Token.objects.get_or_create(user=user)
    user.last_active = timezone.now()
    user.save(update_fields=['last_active'])

    return Response({
        'token': token.key,
        'user': UserSerializer(user).data,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mfa_toggle(request):
    """Aktifkan atau nonaktifkan MFA untuk user yang sedang login."""
    user = request.user
    enable = request.data.get('enable')

    if enable is None:
        return Response({'detail': 'Field "enable" diperlukan.'}, status=status.HTTP_400_BAD_REQUEST)

    if enable and not user.email:
        return Response({'detail': 'Akun Anda belum memiliki alamat email.'}, status=status.HTTP_400_BAD_REQUEST)

    user.mfa_enabled = bool(enable)
    user.save(update_fields=['mfa_enabled'])

    return Response({
        'mfa_enabled': user.mfa_enabled,
        'detail': 'MFA Email diaktifkan.' if user.mfa_enabled else 'MFA Email dinonaktifkan.',
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """Logout dan hapus token"""
    request.user.auth_token.delete()
    return Response({'detail': 'Berhasil logout.'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def profile_view(request):
    """Profil pengguna saat ini"""
    return Response(UserSerializer(request.user).data)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
