from nested_admin.nested import NestedTabularInline


class ReadOnlyNestedTabularInline(NestedTabularInline):
    extra = 0

    def has_add_permission(self, request, obj):
        return

    def has_delete_permission(self, request, obj=None):
        return False
