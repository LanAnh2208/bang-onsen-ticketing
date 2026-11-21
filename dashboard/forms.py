from django import forms
from core.models import Service, ServicePrice, Voucher


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = [
            'service_id',
            'service_name',
            'description',
            'image',
            'daily_capacity',
            'service_status',
        ]
        widgets = {
            'service_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'VD: ONSEN_VIP'}),
            'service_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tên gói dịch vụ Onsen'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'daily_capacity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'service_status': forms.Select(attrs={'class': 'form-control'}),
        }


class ServicePriceForm(forms.ModelForm):
    class Meta:
        model = ServicePrice
        fields = [
            'service',
            'ticket_type',
            'day_type',
            'price',
            'quang_tri_price',
        ]
        widgets = {
            'service': forms.Select(attrs={'class': 'form-control'}),
            'ticket_type': forms.Select(attrs={'class': 'form-control'}),
            'day_type': forms.Select(attrs={'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': '1000'}),
            'quang_tri_price': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': '1000'}),
        }


class VoucherForm(forms.ModelForm):
    class Meta:
        model = Voucher
        fields = [
            'voucher_code',
            'discount_type',
            'discount_value',
            'valid_from',
            'valid_to',
            'usage_limit',
            'voucher_status',
        ]
        widgets = {
            'voucher_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'VD: ONSEN20'}),
            'discount_type': forms.Select(attrs={'class': 'form-control'}),
            'discount_value': forms.NumberInput(attrs={'class': 'form-control', 'min': 0.01, 'step': '0.01'}),
            'valid_from': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'valid_to': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'usage_limit': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'voucher_status': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean_voucher_code(self):
        return self.cleaned_data['voucher_code'].strip().upper()

    def clean(self):
        cleaned_data = super().clean()
        discount_type = cleaned_data.get('discount_type')
        discount_value = cleaned_data.get('discount_value')
        valid_from = cleaned_data.get('valid_from')
        valid_to = cleaned_data.get('valid_to')

        if discount_type == 'Percent' and discount_value is not None and discount_value > 100:
            self.add_error('discount_value', 'Mức giảm theo phần trăm không được vượt quá 100%.')

        if valid_from and valid_to and valid_to < valid_from:
            self.add_error('valid_to', 'Ngày hết hạn phải lớn hơn hoặc bằng ngày bắt đầu.')

        return cleaned_data