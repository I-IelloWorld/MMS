class RequestUserFormMixin:
    """Pass the current admin user to ModelForms that scope related fields."""

    def get_form(self, request, obj=None, change=False, **kwargs):
        form_class = super().get_form(request, obj=obj, change=change, **kwargs)
        request_user = request.user

        class RequestAwareForm(form_class):
            def __init__(self, *args, **form_kwargs):
                form_kwargs.setdefault("user", request_user)
                super().__init__(*args, **form_kwargs)

        return RequestAwareForm
