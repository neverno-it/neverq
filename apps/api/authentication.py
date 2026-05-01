from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.backends import TokenBackend
from django.conf import settings


def _get_token_backend():
    return TokenBackend(
        algorithm=settings.SIMPLE_JWT.get('ALGORITHM', 'HS256'),
        signing_key=settings.SIMPLE_JWT.get('SIGNING_KEY', settings.SECRET_KEY),
    )


class NeverQJWTAuthentication(BaseAuthentication):
    """
    Handles JWT tokens for both StaffUser (Django auth user) and Customer (custom model).
    Token payload carries user_type='staff'|'customer' to distinguish.
    """

    def authenticate(self, request):
        header = request.META.get('HTTP_AUTHORIZATION', '')
        if not header.startswith('Bearer '):
            return None

        raw_token = header.split(' ', 1)[1].strip()
        if not raw_token:
            return None

        try:
            payload = _get_token_backend().decode(raw_token, verify=True)
        except TokenError as e:
            raise AuthenticationFailed(str(e))

        user_type = payload.get('user_type', 'staff')

        if user_type == 'customer':
            return self._authenticate_customer(payload)
        return self._authenticate_staff(payload)

    def _authenticate_staff(self, payload):
        from apps.accounts.models import StaffUser
        user_id = payload.get('user_id')
        if not user_id:
            raise AuthenticationFailed('Invalid token payload.')
        try:
            user = StaffUser.objects.get(pk=user_id, is_active=True)
        except StaffUser.DoesNotExist:
            raise AuthenticationFailed('Staff user not found or inactive.')
        return (user, {'user_type': 'staff', 'payload': payload})

    def _authenticate_customer(self, payload):
        from apps.accounts.models import Customer
        customer_id = payload.get('customer_id')
        if not customer_id:
            raise AuthenticationFailed('Invalid token payload.')
        try:
            customer = Customer.objects.select_related('company').get(
                pk=customer_id, is_active=True, is_deleted=False
            )
        except Customer.DoesNotExist:
            raise AuthenticationFailed('Customer not found or inactive.')
        return (customer, {'user_type': 'customer', 'payload': payload})

    def authenticate_header(self, request):
        return 'Bearer'


def make_tokens_for_staff(staff_user):
    token = RefreshToken.for_user(staff_user)
    token['user_type'] = 'staff'
    token['role'] = staff_user.role
    token['name'] = staff_user.name
    token['company_id'] = staff_user.company_id
    return {
        'refresh': str(token),
        'access': str(token.access_token),
    }


def make_tokens_for_customer(customer):
    token = RefreshToken()
    token['user_type'] = 'customer'
    token['customer_id'] = customer.id
    token['user_id'] = customer.id
    token['email'] = customer.email
    token['name'] = customer.name
    token['company_id'] = customer.company_id
    return {
        'refresh': str(token),
        'access': str(token.access_token),
    }
