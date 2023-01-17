from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class UserSignupTests(APITestCase):
    def setUp(self) -> None:
        self.data = {
            "company_name": "Company Name",
            "first_name": "First",
            "last_name": "Last",
            "email": "test@test.com",
            "password": "test",
        }
        self.url = reverse("signup")

    def test_create_account(self):
        response = self.client.post(self.url, data=self.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_create_account_missing_data(self):
        for k, _ in self.data.items():
            data = self.data.copy()
            data.pop(k)
            response = self.client.post(self.url, data=data)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, data)
