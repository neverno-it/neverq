from rest_framework.permissions import BasePermission
from apps.accounts.models import StaffUser, Customer


class IsStaff(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user is not None
            and isinstance(request.user, StaffUser)
            and request.user.is_active
        )


class IsCustomer(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user is not None
            and isinstance(request.user, Customer)
            and request.user.is_active
        )


class IsKitchenStaff(BasePermission):
    def has_permission(self, request, view):
        if not isinstance(request.user, StaffUser) or not request.user.is_active:
            return False
        return request.user.role in (
            StaffUser.ROLE_CAFEMAN,
            StaffUser.ROLE_ADMIN,
            StaffUser.ROLE_SUPERADMIN,
        )


class IsPOSStaff(BasePermission):
    def has_permission(self, request, view):
        if not isinstance(request.user, StaffUser) or not request.user.is_active:
            return False
        return request.user.role in (
            StaffUser.ROLE_POS,
            StaffUser.ROLE_ADMIN,
            StaffUser.ROLE_SUPERADMIN,
        )


class IsAdminStaff(BasePermission):
    def has_permission(self, request, view):
        if not isinstance(request.user, StaffUser) or not request.user.is_active:
            return False
        return request.user.role in (
            StaffUser.ROLE_ADMIN,
            StaffUser.ROLE_SUPERADMIN,
        )


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        if not isinstance(request.user, StaffUser) or not request.user.is_active:
            return False
        return request.user.role == StaffUser.ROLE_SUPERADMIN
