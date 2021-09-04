from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "per_page"
    max_page_size = 5000

    def get_paginated_response(self, data):
        per_page = self.page.paginator.per_page
        total = self.page.paginator.count
        page_number = int(self.request.query_params.get(self.page_query_param, 1))
        bottom = (page_number - 1) * per_page
        top = bottom + per_page
        if top >= total:
            top = total

        return Response(
            {
                "total": total,
                "from": bottom + 1,
                "to": top,
                "per_page": per_page,
                "current_page": self.page.number,
                "next_page": self.page.next_page_number() if self.page.has_next() else None,
                "prev_page": self.page.previous_page_number() if self.page.has_previous() else None,
                "next_page_url": self.get_next_link(),
                "prev_page_url": self.get_previous_link(),
                "data": data,
            }
        )
