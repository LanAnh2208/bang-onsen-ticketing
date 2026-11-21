from django import forms
from core.models import phone_validator, cccd_validator


class InternalLoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        label='Tên đăng nhập',
        error_messages={'required': 'Vui lòng nhập tên đăng nhập.'},
        widget=forms.TextInput(attrs={
            'class': 'pos-input',
            'autocomplete': 'username',
            'autofocus': 'autofocus',
        })
    )
    password = forms.CharField(
        label='Mật khẩu',
        error_messages={'required': 'Vui lòng nhập mật khẩu.'},
        widget=forms.PasswordInput(attrs={
            'class': 'pos-input',
            'autocomplete': 'current-password',
        })
    )


class CounterCustomerForm(forms.Form):
    customer_name = forms.CharField(
        max_length=100,
        required=False,
        label='Họ và tên khách hàng',
        widget=forms.TextInput(attrs={'class': 'pos-input'})
    )
    phone = forms.CharField(
        max_length=10,
        required=False,
        validators=[phone_validator],
        label='Số điện thoại',
        widget=forms.TextInput(attrs={'class': 'pos-input', 'maxlength': '10', 'inputmode': 'numeric'})
    )
    cccd_number = forms.CharField(
        max_length=12,
        required=False,
        validators=[cccd_validator],
        label='Số CCCD',
        widget=forms.TextInput(attrs={'class': 'pos-input', 'maxlength': '12', 'inputmode': 'numeric'})
    )