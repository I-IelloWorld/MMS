from pathlib import Path

from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from apps.facilities.access import accessible_warehouses

from .models import ImportBatch


class EquipmentImportForm(forms.ModelForm):
    class Meta:
        model = ImportBatch
        fields = ("warehouse", "source_file")
        widgets = {
            "warehouse": forms.Select(attrs={"class": "form-select"}),
            "source_file": forms.FileInput(attrs={"class": "form-control", "accept": ".csv,.xlsx"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["warehouse"].queryset = accessible_warehouses(user).filter(status="ACTIVE")

    def clean_source_file(self):
        upload = self.cleaned_data["source_file"]
        suffix = Path(upload.name).suffix.lower()
        if suffix not in {".csv", ".xlsx"}:
            raise forms.ValidationError(_("只支持 CSV 或 XLSX 文件。"))
        if upload.size > settings.MMS_MAX_UPLOAD_BYTES:
            raise forms.ValidationError(_("导入文件不能超过 4 MB。"))
        return upload
