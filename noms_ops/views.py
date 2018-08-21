from django.views.generic import FormView

from noms_ops.forms import CreditForm, SenderForm, PrisonerForm
from noms_ops.models import prisons, sources, statuses


class FilterView(FormView):
    get = FormView.post
    form_valid = FormView.form_invalid

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['data'] = self.request.GET.dict()
        return kwargs

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data.update(
            object_list=context_data['form'].object_list,
            prisons=prisons,
            sources=sources,
            statuses=statuses,
        )
        return context_data


class CreditView(FilterView):
    title = 'Credits'
    template_name = 'noms_ops/credits.html'
    form_class = CreditForm


class SenderView(FilterView):
    title = 'Payment sources'
    template_name = 'noms_ops/senders.html'
    form_class = SenderForm


class PrisonerView(FilterView):
    title = 'Prisoners'
    template_name = 'noms_ops/prisoners.html'
    form_class = PrisonerForm
