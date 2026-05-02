from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from apps.accounts.models import StaffUser, Customer
from apps.accounts.decorators import enforce_customer_active_state
from apps.accounts.views import _try_auto_create_google_customer, _verify_google_app_id_token
from apps.api.authentication import NeverQJWTAuthentication, make_tokens_for_staff, make_tokens_for_customer
from apps.api.serializers import LoginSerializer, FCMTokenSerializer
from apps.api.models import FCMDevice


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        email = ser.validated_data['email'].lower().strip()
        password = ser.validated_data['password']

        # Try StaffUser first
        try:
            staff = StaffUser.objects.get(email__iexact=email, is_active=True)
            if staff.check_password(password):
                tokens = make_tokens_for_staff(staff)
                return Response({
                    **tokens,
                    'user_type': 'staff',
                    'role': staff.role,
                    'name': staff.name,
                    'email': staff.email,
                    'company_id': staff.company_id,
                })
        except StaffUser.DoesNotExist:
            pass

        # Try Customer. Customer.email is not unique because the same person can
        # have accounts across companies/buildings, so never use get() here.
        customers = list(
            Customer.objects.select_related('company', 'building').filter(
                email__iexact=email,
                is_deleted=False,
            )
        )
        matched_customers = [customer for customer in customers if customer.check_password(password)]

        if matched_customers:
            active_customers = [customer for customer in matched_customers if customer.is_active]
            approved_customers = [
                customer for customer in active_customers
                if customer.is_approved and customer.is_email_verified
            ]

            if len(approved_customers) == 1:
                customer = approved_customers[0]
                tokens = make_tokens_for_customer(customer)
                return Response({
                    **tokens,
                    'user_type': 'customer',
                    'role': 'customer',
                    'name': customer.name,
                    'email': customer.email,
                    'company_id': customer.company_id,
                })

            if len(approved_customers) > 1:
                return Response(
                    {'detail': 'Multiple customer accounts found for this email. Please use the web portal to select an account.'},
                    status=status.HTTP_409_CONFLICT,
                )

            if any(customer.is_approved and not customer.is_email_verified for customer in active_customers):
                return Response(
                    {'detail': 'Please verify your email before signing in.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if any(not customer.is_active for customer in matched_customers):
                return Response(
                    {'detail': 'Your account is inactive. Please contact admin.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return Response(
                {'detail': 'Your account is pending approval.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {'detail': 'Invalid email or password.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )


def _customer_token_response(customer, *, extra=None):
    tokens = make_tokens_for_customer(customer)
    payload = {
        **tokens,
        'user_type': 'customer',
        'role': 'customer',
        'name': customer.name,
        'email': customer.email,
        'company_id': customer.company_id,
    }
    if extra:
        payload.update(extra)
    return payload


class GoogleLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        raw_id_token = (request.data.get('id_token') or '').strip()
        selected_customer_id = request.data.get('customer_id')
        if not raw_id_token:
            return Response({'detail': 'Missing Google id token.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user_info = _verify_google_app_id_token(raw_id_token)
        except Exception as exc:
            return Response(
                {'detail': f'Google token verification failed: {exc}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = (user_info.get('email') or '').strip().lower()
        name = (user_info.get('name') or '').strip()
        customers = list(
            Customer.objects.select_related('company', 'building').filter(
                email__iexact=email,
                is_deleted=False,
            )
        )
        if not customers:
            customers = [
                customer for customer in Customer.objects.select_related('company', 'building').filter(is_deleted=False)
                if (customer.email or '').strip().lower() == email
            ]

        if not customers:
            created = _try_auto_create_google_customer(email=email, name=name)
            if created:
                customers = [created]
            else:
                return Response(
                    {
                        'detail': 'No customer account found for this Google email. Please sign up first.',
                        'auth_status': 'register_required',
                        'email': email,
                        'name': name,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        for customer in customers:
            enforce_customer_active_state(customer)

        for customer in customers:
            if customer.is_active and customer.is_approved and not customer.is_email_verified:
                customer.is_email_verified = True
                customer.save(update_fields=['is_email_verified'])

        approved_customers = [
            customer for customer in customers
            if customer.is_active and customer.is_approved and customer.is_email_verified
        ]

        if not approved_customers:
            if any(not customer.is_active for customer in customers):
                return Response({'detail': 'Your account is inactive. Please contact admin.'}, status=status.HTTP_403_FORBIDDEN)
            return Response({'detail': 'Your account is pending approval. Please contact admin.'}, status=status.HTTP_403_FORBIDDEN)

        if selected_customer_id:
            selected = next((customer for customer in approved_customers if str(customer.pk) == str(selected_customer_id)), None)
            if selected is None:
                return Response({'detail': 'Please select a valid customer account.'}, status=status.HTTP_400_BAD_REQUEST)
            return Response(_customer_token_response(selected, extra={'auth_status': 'logged_in'}))

        if len(approved_customers) > 1:
            return Response(
                {
                    'detail': 'Select the company account you want to use.',
                    'auth_status': 'select_account',
                    'accounts': [
                        {
                            'id': customer.pk,
                            'name': customer.name,
                            'email': customer.email,
                            'company_id': customer.company_id,
                            'company_name': customer.company.name if customer.company_id else '',
                            'building_name': customer.building.name if customer.building_id else '',
                        }
                        for customer in approved_customers
                    ],
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(_customer_token_response(approved_customers[0], extra={'auth_status': 'logged_in'}))


class TokenRefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'detail': 'Refresh token required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            return Response({'access': str(token.access_token)})
        except TokenError as e:
            return Response({'detail': str(e)}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass
        # Deactivate FCM token if provided
        fcm_token = request.data.get('fcm_token')
        if fcm_token:
            FCMDevice.objects.filter(token=fcm_token).update(is_active=False)
        return Response({'detail': 'Logged out.'})


class FCMTokenView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = FCMTokenSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        token = ser.validated_data['token']
        platform = ser.validated_data['platform']

        user = request.user
        is_staff = isinstance(user, StaffUser)

        # Upsert: if token exists update owner, else create
        FCMDevice.objects.filter(token=token).exclude(
            **({'staff_user': user} if is_staff else {'customer': user})
        ).delete()

        kwargs = {
            'token': token,
            'defaults': {
                'platform': platform,
                'is_active': True,
                'staff_user': user if is_staff else None,
                'customer': user if not is_staff else None,
            },
        }
        FCMDevice.objects.update_or_create(**kwargs)

        return Response({'detail': 'FCM token registered.'})
