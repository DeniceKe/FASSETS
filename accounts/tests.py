from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import Department, Faculty

User = get_user_model()


class SignUpViewTests(TestCase):
    def setUp(self):
        faculty = Faculty.objects.create(name="Faculty of Science")
        self.department = Department.objects.create(code="CHEM", name="Chemistry", faculty=faculty)

    def test_signup_creates_user_profile_details(self):
        response = self.client.post(
            "/accounts/signup/",
            {
                "username": "newstudent",
                "first_name": "New",
                "last_name": "Student",
                "email": "student@example.com",
                "phone_number": "0700000000",
                "user_type": "student",
                "registration_number": "SCI/001/26",
                "employee_id": "",
                "department": self.department.id,
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertRedirects(response, "/accounts/login/")
        user = User.objects.get(username="newstudent")
        self.assertEqual(user.profile.department, self.department)
        self.assertEqual(user.profile.registration_number, "SCI/001/26")
