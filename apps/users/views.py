"""Views for Users app"""

from django.contrib.auth import get_user_model, authenticate
from django.utils import timezone
from rest_framework import serializers, viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.authtoken.models import Token

from .serializers import UserSerializer

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """Login dan dapatkan token"""
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

    token, _ = Token.objects.get_or_create(user=user)
    user.last_active = timezone.now()
    user.save(update_fields=['last_active'])

    return Response({
        'token': token.key,
        'user': UserSerializer(user).data
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
