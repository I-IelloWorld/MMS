def set_widget_attr(field, name, value):
    """Set an attribute on both a widget and Django Admin's wrapped widget."""
    widget = field.widget
    while widget:
        widget.attrs[name] = value
        widget = getattr(widget, "widget", None)


def remove_widget_attr(field, name):
    widget = field.widget
    while widget:
        widget.attrs.pop(name, None)
        widget = getattr(widget, "widget", None)
