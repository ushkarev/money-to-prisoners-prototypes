import collections
import re
from urllib.parse import urlencode

from django import forms
from django.core.exceptions import ValidationError
from django.utils.dateformat import format as format_date
from govuk_forms.fields import SplitDateField
from govuk_forms.forms import GOVUKForm

from noms_ops.models import AmountPattern, credits_list, prisons, sources, statuses
from noms_ops.templatetags.noms_ops import currency


def insert_blank_option(choices, title='Select an option'):
    new_choices = [('', title)]
    new_choices.extend(choices)
    return new_choices


def parse_amount(value, as_int=True):
    # assumes a valid amount in pounds, i.e. validate_amount passes
    value = value.lstrip('£')
    if '.' in value:
        value = value.replace('.', '')
    else:
        value += '00'
    if as_int:
        return int(value)
    return value


def validate_amount(amount):
    if not re.match(r'^£?\d+(\.\d\d)?$', amount):
        raise ValidationError('Invalid amount', code='invalid')


def validate_prisoner_number(prisoner_number):
    if not re.match(r'^[a-z]\d\d\d\d[a-z]{2}$', prisoner_number, flags=re.I):
        raise ValidationError('Invalid prisoner number', code='invalid')


class FilterForm(GOVUKForm):
    auto_replace_widgets = True

    ordering = forms.ChoiceField(label='Order by', required=False,
                                 initial='-received_at',
                                 choices=[
                                     ('received_at', 'Received date (oldest to newest)'),
                                     ('-received_at', 'Received date (newest to oldest)'),
                                     ('amount', 'Amount sent (low to high)'),
                                     ('-amount', 'Amount sent (high to low)'),
                                     ('source', 'Payment source (A to Z)'),
                                     ('-source', 'Payment source (Z to A)'),
                                     ('prison', 'Prison (A to Z)'),
                                     ('-prison', 'Prison (Z to A)'),
                                     ('prisoner_name', 'Prisoner name (A to Z)'),
                                     ('-prisoner_name', 'Prisoner name (Z to A)'),
                                     ('prisoner_number', 'Prisoner number (A to Z)'),
                                     ('-prisoner_number', 'Prisoner number (Z to A)'),
                                     ('status', 'Status (A to Z)'),
                                     ('-status', 'Status (Z to A)'),
                                 ])

    received_at__gte = SplitDateField(label='Received since', help_text='for example 13/02/2018', required=False)
    received_at__lt = SplitDateField(label='Received before', help_text='for example 13/02/2018', required=False)

    status = forms.ChoiceField(label='Credited status', required=False, choices=list(statuses.items()))

    amount_pattern = forms.ChoiceField(label='Amount (£)', required=False, choices=AmountPattern.get_choices())
    amount_exact = forms.CharField(label=AmountPattern.exact.value, validators=[validate_amount], required=False)
    amount_pence = forms.IntegerField(label=AmountPattern.pence.value, min_value=0, max_value=99, required=False)

    prisoner_number = forms.CharField(label='Prisoner number', validators=[validate_prisoner_number], required=False)
    prisoner_name = forms.CharField(label='Prisoner name', required=False)
    prison = forms.ChoiceField(label='Prison', required=False, choices=list(prisons.items()))
    prison_region = forms.ChoiceField(label='Prison region', required=False, choices=[])
    prison_population = forms.ChoiceField(label='Prison type', required=False, choices=[])
    prison_category = forms.ChoiceField(label='Prison category', required=False, choices=[])

    sender_name = forms.CharField(label='Sender name', required=False)
    source = forms.ChoiceField(label='Payment method', required=False, choices=insert_blank_option(
        list(sources.items()),
        title='Any method',
    ))
    sender_sort_code = forms.CharField(label='Sender sort code', help_text='for example 01-23-45', required=False)
    sender_account_number = forms.CharField(label='Sender account number', required=False)
    sender_roll_number = forms.CharField(label='Sender roll number', required=False)
    card_number_last_digits = forms.CharField(label='Last 4 digits of card number', max_length=4, required=False)
    sender_email = forms.EmailField(label='Sender email', required=False)
    postcode = forms.CharField(label='Sender postcode', required=False)
    ip_address = forms.GenericIPAddressField(label='Sender IP address', required=False)

    sections = {
        'date': ('received_at__gte', 'received_at__lt'),
        'amount': ('amount_pattern', 'amount_exact', 'amount_pence'),
        'source': (
            'source', 'sender_name',
            'sender_sort_code', 'sender_account_number', 'sender_roll_number',
            'card_number_last_digits', 'sender_email', 'postcode', 'ip_address',
        ),
        'prisoner': ('prisoner_number', 'prisoner_name'),
        'prison': ('prison', 'prison_region', 'prison_population', 'prison_category'),
        'status': ('status',),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.is_bound:
            data = {
                name: field.initial
                for name, field in self.fields.items()
                if field.initial is not None
            }
            data.update(self.initial)
            data.update(self.data)
            for key in ('received_at__gte', 'received_at__lt'):
                values = data.get(key, '').split('-')
                if len(values) != 3:
                    continue
                data.update({
                    '%s_%s' % (key, i): value
                    for i, value in enumerate(reversed(values))
                })
            self.data = data

    def clean_amount_exact(self):
        if self.cleaned_data.get('amount_pattern') != 'exact':
            return ''
        amount = self.cleaned_data.get('amount_exact')
        if not amount:
            raise ValidationError('This field is required for the selected amount pattern', code='required')
        return amount

    def clean_amount_pence(self):
        if self.cleaned_data.get('amount_pattern') != 'pence':
            return None
        amount = self.cleaned_data.get('amount_pence')
        if amount is None:
            raise ValidationError('This field is required for the selected amount pattern', code='required')
        return amount

    def clean_prisoner_number(self):
        prisoner_number = self.cleaned_data.get('prisoner_number')
        if prisoner_number:
            return prisoner_number.upper()
        return prisoner_number

    def clean_sender_sort_code(self):
        if self.cleaned_data.get('source') != 'bank_transfer':
            return ''
        sender_sort_code = self.cleaned_data.get('sender_sort_code')
        if sender_sort_code:
            sender_sort_code = sender_sort_code.replace('-', '')
        return sender_sort_code

    def clean_sender_account_number(self):
        if self.cleaned_data.get('source') != 'bank_transfer':
            return ''
        return self.cleaned_data.get('sender_account_number')

    def clean_sender_roll_number(self):
        if self.cleaned_data.get('source') != 'bank_transfer':
            return ''
        return self.cleaned_data.get('sender_roll_number')

    def clean_card_number_last_digits(self):
        if self.cleaned_data.get('source') != 'online':
            return ''
        return self.cleaned_data.get('card_number_last_digits')

    def get_query_data(self):
        data = collections.OrderedDict()
        for field in self:
            value = self.cleaned_data.get(field.name)
            if value in [None, '', []]:
                continue
            data[field.name] = value
        return data

    def is_section_selected(self, section):
        query_data = self.get_query_data()
        return any(query_data.get(field) for field in self.sections.get(section))

    @property
    def filtered(self):
        return any(value for key, value in self.get_query_data().items() if key != 'ordering')

    @property
    def filters(self):
        query_data = self.get_query_data()
        filters = []

        def get_query(*excluded_fields):
            return urlencode([
                (key, value)
                for key, value in query_data.items()
                if key not in excluded_fields
            ], doseq=True)

        received_at__gte = query_data.get('received_at__gte')
        received_at__lt = query_data.get('received_at__lt')
        if received_at__gte or received_at__lt:
            if received_at__gte and received_at__lt:
                label = 'Received between %s and %s' % (format_date(received_at__gte, 'j N Y'),
                                                        format_date(received_at__lt, 'j N Y'))
            elif received_at__gte:
                label = 'Received since %s' % format_date(received_at__gte, 'j N Y')
            else:
                label = 'Received before %s' % format_date(received_at__lt, 'j N Y')
            filters.append((
                label,
                get_query('received_at__gte', 'received_at__lt')
            ))

        status = query_data.get('status')
        if status:
            filters.append((
                'Status: %s' % statuses[status].lower(),
                get_query('status')
            ))

        amount_pattern = query_data.get('amount_pattern')
        amount_exact = query_data.get('amount_exact', '0')
        amount_pence = query_data.get('amount_pence', '0')
        if amount_pattern:
            if amount_pattern == 'exact':
                label = 'exactly %s' % currency(parse_amount(amount_exact))
            elif amount_pattern == 'pence':
                label = 'exactly %s pence' % amount_pence
            else:
                label = AmountPattern[amount_pattern].value.lower()
            filters.append((
                'Amount: %s' % label,
                get_query('amount_pattern', 'amount_exact', 'amount_pence')
            ))

        prison = query_data.get('prison')
        if prison:
            filters.append((
                'Prison: %s' % prisons[prison],
                get_query('prison')
            ))

        source = query_data.get('source')
        if source:
            filters.append((
                'Payment method: %s' % sources[source].lower(),
                get_query('source')
            ))

        skipped_fields = {
            'ordering',
            'received_at__gte', 'received_at__lt',
            'prison', 'source', 'status',
            'amount_pattern', 'amount_exact', 'amount_pence',
        }
        return filters + [
            (
                '%s: %s' % (field.label, query_data[field.name]),
                get_query(field.name)
            )
            for field in self
            if field.name not in skipped_fields and field.name in query_data
        ]

    @property
    def credits_list(self):
        if not self.is_valid():
            return []

        query_data = self.get_query_data()
        ordering = query_data.pop('ordering', '') or self['ordering'].initial
        if ordering.startswith('-'):
            reverse = True
            ordering = ordering[1:]
        else:
            reverse = False

        def compare(credit):
            received_at__gte = query_data.get('received_at__gte')
            if received_at__gte:
                if credit['received_at'].date() < received_at__gte:
                    return False

            received_at__lt = query_data.get('received_at__lt')
            if received_at__lt:
                if credit['received_at'].date() > received_at__lt:
                    return False

            amount_pattern = query_data.get('amount_pattern')
            if amount_pattern == 'not_integral':
                if not bool(credit['amount'] % 100):
                    return False
            elif amount_pattern == 'not_multiple_5':
                if str(credit['amount'])[-3:] not in ('000', '500'):
                    return False
            elif amount_pattern == 'not_multiple_10':
                if str(credit['amount'])[-3:] != '000':
                    return False
            elif amount_pattern == 'gte_100':
                if credit['amount'] >= 10000:
                    return False
            elif amount_pattern == 'exact':
                if credit['amount'] != parse_amount(query_data['amount_exact']):
                    return False
            elif amount_pattern == 'pence':
                if credit['amount'] % 100 != int(query_data['amount_pence']):
                    return False

            for key in ('prisoner_name', 'sender_name', 'postcode'):
                value = query_data.get(key)
                if not value:
                    continue
                if value.upper() not in credit[key].upper():
                    return False


            for key in (
                'prisoner_number', 'prison',
                'status', 'source',
                'sender_sort_code', 'sender_account_number',
                'card_number_last_digits', 'sender_email', 'ip_address',
            ):
                value = query_data.get(key)
                if not value:
                    continue
                if credit[key] != value:
                    return False

            return True

        return sorted(filter(compare, credits_list), key=lambda credit: credit[ordering], reverse=reverse)