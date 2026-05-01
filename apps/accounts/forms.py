from django import forms
from django.utils import timezone
from django.db import IntegrityError
from apps.core.models import Company, Building
from .models import Customer


def notify_customer_registration_needing_approval(customer):
    """Notify company admins when a newly created customer needs approval."""
    if not customer or customer.is_approved or not customer.company_id:
        return
    try:
        from apps.accounts.models import StaffUser
        from apps.core.models import Notification
        for staff in StaffUser.objects.filter(
            company=customer.company,
            is_active=True,
            role__in=[StaffUser.ROLE_ADMIN, StaffUser.ROLE_SUPERADMIN],
        ):
            Notification.objects.create(
                company=customer.company,
                staff_user=staff,
                notif_type=Notification.TYPE_ORDER,
                title=f'New Customer Registration: {customer.name}',
                message=f'{customer.name} ({customer.email}) registered and needs approval.',
                link=f'/dashboard/customers/{customer.pk}/edit/',
            )
    except (IntegrityError, AttributeError, ImportError):
        pass


class StaffLoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'your@email.com', 'autofocus': True})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': '••••••••'})
    )


class CustomerLoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'placeholder': 'your@email.com',
            'class': 'form-control',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': '••••••••',
            'class': 'form-control',
        })
    )


class CustomerRegisterForm(forms.ModelForm):
    password  = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Choose a password'})
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Repeat password'})
    )
    name = forms.CharField(max_length=250)
    phone = forms.CharField(max_length=30)
    date_of_birth = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={'type': 'date'}),
        input_formats=['%Y-%m-%d'],
    )
    company = forms.ModelChoiceField(
        queryset=Company.objects.filter(is_active=True, is_deleted=False),
        empty_label='— Select your company —'
    )
    building = forms.ModelChoiceField(
        queryset=Building.objects.filter(is_active=True, is_deleted=False),
        empty_label='— Select building/floor —',
        required=True
    )

    class Meta:
        model  = Customer
        fields = ['name', 'phone', 'email', 'date_of_birth', 'company', 'building']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].widget.attrs['placeholder'] = 'your@email.com'
        self.fields['building'].queryset = Building.objects.none()
        selected_company = None
        if self.is_bound:
            try:
                selected_company = int((self.data.get('company') or 0)) or None
            except (TypeError, ValueError):
                selected_company = None
        elif self.initial.get('company'):
            try:
                selected_company = int(getattr(self.initial.get('company'), 'pk', self.initial.get('company')))
            except (TypeError, ValueError):
                selected_company = None
        elif getattr(self.instance, 'company_id', None):
            selected_company = self.instance.company_id
        if selected_company:
            self.fields['building'].queryset = Building.objects.filter(company_id=selected_company, is_active=True, is_deleted=False).order_by('name')
        for name, field in self.fields.items():
            widget = field.widget
            css = widget.attrs.get('class', '')
            if isinstance(widget, forms.Select):
                widget.attrs['class'] = (css + ' form-select').strip()
            elif isinstance(widget, forms.Textarea):
                widget.attrs['class'] = (css + ' form-control').strip()
                widget.attrs.setdefault('rows', 3)
            else:
                widget.attrs['class'] = (css + ' form-control').strip()
        self.fields['name'].widget.attrs.setdefault('placeholder', 'Full name')
        self.fields['phone'].widget.attrs.setdefault('placeholder', 'Phone number')
        self.fields['date_of_birth'].widget.attrs.setdefault('max', timezone.localdate().isoformat())
        self.fields['password'].widget.attrs.setdefault('autocomplete', 'new-password')
        self.fields['password2'].widget.attrs.setdefault('autocomplete', 'new-password')

    def clean_phone(self):
        return (self.cleaned_data.get('phone') or '').strip()

    def clean_building(self):
        building = self.cleaned_data.get('building')
        company = self.cleaned_data.get('company')
        if not building:
            raise forms.ValidationError('Please select your building.')
        if company and getattr(building, 'company_id', None) != getattr(company, 'id', None):
            raise forms.ValidationError('Please select a building from the selected company.')
        return building

    def clean_date_of_birth(self):
        value = self.cleaned_data.get('date_of_birth')
        today = timezone.localdate()
        if not value:
            raise forms.ValidationError('Birth date is required.')
        if value > today:
            raise forms.ValidationError('Birth date cannot be in the future.')
        return value

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        company = self.cleaned_data.get('company')
        if not email:
            return email

        if company:
            existing = Customer.objects.filter(
                company=company,
                email__iexact=email,
            )
            if existing.exists():
                raise forms.ValidationError('An account with this email already exists for this company.')

            # Legacy/import fallback: catch rows with whitespace-padded emails.
            for candidate_email in Customer.objects.filter(company=company).values_list('email', flat=True):
                if (candidate_email or '').strip().lower() == email:
                    raise forms.ValidationError('An account with this email already exists for this company.')
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Passwords do not match.')
        return cleaned

    def save(self, commit=True, email_verified=False):
        customer = super().save(commit=False)
        customer.set_password(self.cleaned_data['password'])
        customer.name = (self.cleaned_data.get('name') or '').strip()
        customer.phone = (self.cleaned_data.get('phone') or '').strip()
        customer.email = (self.cleaned_data.get('email') or '').strip().lower()
        customer.date_of_birth = self.cleaned_data.get('date_of_birth')
        customer.is_email_verified = bool(email_verified)
        # Auto-set is_approved based on company setting
        company = self.cleaned_data.get('company')
        if company and getattr(company, 'require_customer_approval', False):
            customer.is_approved = False
        else:
            customer.is_approved = True
        if commit:
            customer.save()
            notify_customer_registration_needing_approval(customer)
        return customer

    def build_pending_payload(self):
        customer = self.save(commit=False, email_verified=False)
        return {
            'name': customer.name,
            'phone': customer.phone,
            'email': customer.email,
            'company_id': customer.company_id,
            'building_id': customer.building_id,
            'date_of_birth': customer.date_of_birth.isoformat() if customer.date_of_birth else '',
            'password_hash': customer.password_hash,
            'is_approved': customer.is_approved,
        }


class CustomerProfileForm(forms.ModelForm):
    class Meta:
        model  = Customer
        fields = ['name', 'phone']

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['phone'].required = True
