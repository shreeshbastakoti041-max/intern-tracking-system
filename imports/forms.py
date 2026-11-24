from django import forms

MAX_BYTES = 10 * 1024 * 1024


class WorkbookUploadForm(forms.Form):
    file = forms.FileField(
        label="Intern tracker workbook (.xlsx)",
        widget=forms.ClearableFileInput(attrs={"accept": ".xlsx"}),
    )
    save = forms.BooleanField(
        required=False,
        label="Save to the database",
        help_text="Leave unchecked to do a dry run: everything is checked and reported, "
        "nothing is saved.",
    )
    replace = forms.BooleanField(
        required=False,
        label="Replace earlier imports",
        help_text="Removes entries from previous imports first. Entries typed into the app "
        "are kept.",
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Choose an Excel workbook ending in .xlsx.")
        if f.size > MAX_BYTES:
            raise forms.ValidationError("The file is larger than 10 MB.")
        return f
