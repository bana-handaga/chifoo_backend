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

from .models import MfaOtp, PasswordResetToken
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

    username = serializer.validated_data['username']
    password = serializer.validated_data['password']

    # Cek dulu apakah user ada dan password benar, tapi belum aktif
    try:
        user_obj = User.objects.get(username=username)
        if not user_obj.check_password(password):
            return Response(
                {'detail': 'Username atau password salah.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        if not user_obj.is_active:
            return Response(
                {'detail': 'Akun Anda belum diaktifkan. Hubungi administrator.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
    except User.DoesNotExist:
        return Response(
            {'detail': 'Username atau password salah.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    user = authenticate(username=username, password=password)
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
def update_email(request):
    """Update alamat email user yang sedang login."""
    email = request.data.get('email', '').strip()
    password = request.data.get('password', '').strip()

    if not email or not password:
        return Response({'detail': 'Email dan password diperlukan.'}, status=status.HTTP_400_BAD_REQUEST)

    if not request.user.check_password(password):
        return Response({'detail': 'Password salah.'}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(email=email).exclude(pk=request.user.pk).exists():
        return Response({'detail': 'Email sudah digunakan oleh akun lain.'}, status=status.HTTP_400_BAD_REQUEST)

    request.user.email = email
    # Jika MFA aktif tapi email lama tidak valid, tetap pertahankan
    request.user.save(update_fields=['email'])

    return Response({'detail': 'Email berhasil diperbarui.', 'user': UserSerializer(request.user).data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_password(request):
    """Ganti password user yang sedang login."""
    old_password = request.data.get('old_password', '').strip()
    new_password = request.data.get('new_password', '').strip()
    confirm_password = request.data.get('confirm_password', '').strip()

    if not old_password or not new_password or not confirm_password:
        return Response({'detail': 'Semua field diperlukan.'}, status=status.HTTP_400_BAD_REQUEST)

    if not request.user.check_password(old_password):
        return Response({'detail': 'Password lama salah.'}, status=status.HTTP_400_BAD_REQUEST)

    if new_password != confirm_password:
        return Response({'detail': 'Konfirmasi password tidak cocok.'}, status=status.HTTP_400_BAD_REQUEST)

    if len(new_password) < 8:
        return Response({'detail': 'Password baru minimal 8 karakter.'}, status=status.HTTP_400_BAD_REQUEST)

    request.user.set_password(new_password)
    request.user.save()
    # Perbarui token agar sesi tetap valid
    Token.objects.filter(user=request.user).delete()
    token = Token.objects.create(user=request.user)

    return Response({'detail': 'Password berhasil diperbarui.', 'token': token.key})


@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    """Registrasi akun baru. Akun tidak aktif sampai disetujui admin."""
    data = request.data
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    password = data.get('password', '').strip()
    confirm_password = data.get('confirm_password', '').strip()
    nomor_telepon = data.get('nomor_telepon', '').strip()

    errors = {}
    if not username:
        errors['username'] = 'Username wajib diisi.'
    elif User.objects.filter(username=username).exists():
        errors['username'] = 'Username sudah digunakan.'
    if not email:
        errors['email'] = 'Email wajib diisi.'
    elif User.objects.filter(email=email).exists():
        errors['email'] = 'Email sudah terdaftar.'
    if not first_name:
        errors['first_name'] = 'Nama depan wajib diisi.'
    if not password:
        errors['password'] = 'Password wajib diisi.'
    elif len(password) < 8:
        errors['password'] = 'Password minimal 8 karakter.'
    elif password != confirm_password:
        errors['confirm_password'] = 'Konfirmasi password tidak cocok.'

    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.create_user(
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        password=password,
        nomor_telepon=nomor_telepon,
        is_active=False,
        role=User.Role.VIEWER,
    )

    # Notifikasi ke semua superadmin
    admin_emails = list(User.objects.filter(
        role=User.Role.SUPERADMIN, email__isnull=False, is_active=True
    ).exclude(email='').values_list('email', flat=True))
    fallback = getattr(django_settings, 'DEFAULT_FROM_EMAIL', '')
    notify_list = admin_emails if admin_emails else ([fallback] if fallback else [])

    if notify_list:
        send_mail(
            subject='Permintaan Registrasi Baru — PTMA Monitor',
            message=(
                f'Ada permintaan registrasi akun baru:\n\n'
                f'Nama     : {user.get_full_name()}\n'
                f'Username : {user.username}\n'
                f'Email    : {user.email}\n\n'
                f'Silakan aktifkan akun melalui halaman admin Django jika disetujui.\n\n'
                f'PTMA Monitoring System'
            ),
            from_email=getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@ptma.id'),
            recipient_list=notify_list,
            fail_silently=True,
        )

    return Response({
        'detail': (
            'Pendaftaran berhasil! Akun Anda sedang menunggu persetujuan admin. '
            'Anda akan dapat login setelah akun diaktifkan.'
        )
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def forgot_password(request):
    """Kirim link reset password ke email user."""
    identifier = request.data.get('identifier', '').strip()
    if not identifier:
        return Response({'detail': 'Username atau email diperlukan.'}, status=status.HTTP_400_BAD_REQUEST)

    user = (
        User.objects.filter(username=identifier).first() or
        User.objects.filter(email=identifier).first()
    )

    # Selalu response sukses agar tidak bocorkan info akun
    success_msg = 'Jika akun ditemukan dan memiliki email terdaftar, link reset password akan dikirim.'

    if not user or not user.email:
        return Response({'detail': success_msg})

    # Hapus token lama yang belum dipakai
    PasswordResetToken.objects.filter(user=user, is_used=False).update(is_used=True)

    reset_token = PasswordResetToken.objects.create(
        user=user,
        expires_at=timezone.now() + timedelta(hours=1),
    )

    frontend_url = getattr(django_settings, 'FRONTEND_URL', '').rstrip('/')
    if not frontend_url:
        scheme = request.scheme
        host = request.get_host().split(':')[0]
        frontend_url = f'{scheme}://{host}'

    reset_url = f'{frontend_url}/reset-password?token={reset_token.token}'

    subject = 'Reset Password PTMA Monitoring'
    message = (
        f'Halo {user.get_full_name() or user.username},\n\n'
        f'Kami menerima permintaan reset password untuk akun Anda.\n\n'
        f'Klik link berikut untuk membuat password baru:\n{reset_url}\n\n'
        f'Link berlaku selama 1 jam. Jika Anda tidak meminta reset password, abaikan email ini.\n\n'
        f'PTMA Monitoring System'
    )
    from_email = getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@ptma.id')
    send_mail(subject, message, from_email, [user.email], fail_silently=True)

    return Response({'detail': success_msg})


@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password(request):
    """Reset password menggunakan token dari email."""
    token_str = request.data.get('token', '').strip()
    new_password = request.data.get('new_password', '').strip()
    confirm_password = request.data.get('confirm_password', '').strip()

    if not token_str:
        return Response({'detail': 'Token diperlukan.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        reset_token = PasswordResetToken.objects.select_related('user').get(token=token_str)
    except (PasswordResetToken.DoesNotExist, Exception):
        return Response({'detail': 'Token tidak valid.'}, status=status.HTTP_400_BAD_REQUEST)

    if not reset_token.is_valid():
        return Response({'detail': 'Token sudah kadaluarsa atau sudah digunakan.'}, status=status.HTTP_400_BAD_REQUEST)

    if not new_password or not confirm_password:
        return Response({'detail': 'Password baru diperlukan.'}, status=status.HTTP_400_BAD_REQUEST)

    if len(new_password) < 8:
        return Response({'detail': 'Password minimal 8 karakter.'}, status=status.HTTP_400_BAD_REQUEST)

    if new_password != confirm_password:
        return Response({'detail': 'Konfirmasi password tidak cocok.'}, status=status.HTTP_400_BAD_REQUEST)

    user = reset_token.user
    user.set_password(new_password)
    user.save()

    # Tandai semua token reset user ini sebagai sudah dipakai
    PasswordResetToken.objects.filter(user=user).update(is_used=True)
    # Hapus session token agar user harus login ulang
    Token.objects.filter(user=user).delete()

    return Response({'detail': 'Password berhasil direset. Silakan login dengan password baru.'})


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
