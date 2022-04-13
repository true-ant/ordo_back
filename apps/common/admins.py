class ReadOnlyAdminMixin:
    extra = 0

    def has_add_permission(self, *args, **kwargs):
        return

    def has_delete_permission(self, *args, **kwargs):
        return False
