from django.contrib.auth import get_user_model
from django.conf import settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from pathlib import Path
import re
import shutil

from accounts.models import Department, Faculty
from assets.models import Location

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

    def test_signup_requires_registration_number_for_students(self):
        response = self.client.post(
            "/accounts/signup/",
            {
                "username": "studentmissingid",
                "first_name": "Missing",
                "last_name": "StudentId",
                "email": "missingstudentid@example.com",
                "phone_number": "0700000001",
                "user_type": "student",
                "registration_number": "",
                "employee_id": "",
                "department": self.department.id,
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registration number is required for students.")
        self.assertFalse(User.objects.filter(username="studentmissingid").exists())

    def test_signup_requires_employee_id_for_staff(self):
        response = self.client.post(
            "/accounts/signup/",
            {
                "username": "staffmissingid",
                "first_name": "Missing",
                "last_name": "StaffId",
                "email": "missingstaffid@example.com",
                "phone_number": "0700000002",
                "user_type": "staff",
                "registration_number": "",
                "employee_id": "",
                "department": self.department.id,
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff ID is required for staff accounts.")
        self.assertFalse(User.objects.filter(username="staffmissingid").exists())


class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="resetuser",
            email="resetuser@example.com",
            password="OldStrongPass123!",
        )

    def test_password_reset_email_is_sent(self):
        response = self.client.post(reverse("password_reset"), {"email": self.user.email})

        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("FASSETS password reset request", mail.outbox[0].subject)
        self.assertIn("/accounts/reset/", mail.outbox[0].body)

    def test_user_can_complete_password_reset(self):
        self.client.post(reverse("password_reset"), {"email": self.user.email})
        self.assertEqual(len(mail.outbox), 1)

        match = re.search(r"http://testserver(?P<path>/accounts/reset/\S+)", mail.outbox[0].body)
        self.assertIsNotNone(match)

        reset_path = match.group("path")
        response = self.client.get(reset_path, follow=True)
        self.assertEqual(response.status_code, 200)

        post_response = self.client.post(
            response.request["PATH_INFO"],
            {
                "new_password1": "NewStrongPass123!",
                "new_password2": "NewStrongPass123!",
            },
            follow=True,
        )

        self.assertRedirects(post_response, reverse("password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewStrongPass123!"))


class AlternateLoginIdentifierTests(TestCase):
    def setUp(self):
        faculty = Faculty.objects.create(name="Faculty of Science")
        department = Department.objects.create(code="CS", name="Computer Science", faculty=faculty)

        self.staff_user = User.objects.create_user(
            username="staffmember",
            email="staff@example.com",
            password="StrongPass123!",
        )
        self.staff_user.profile.employee_id = "STF-001"
        self.staff_user.profile.user_type = "staff"
        self.staff_user.profile.department = department
        self.staff_user.profile.save()

        self.student_user = User.objects.create_user(
            username="studentmember",
            email="student@example.com",
            password="StrongPass123!",
        )
        self.student_user.profile.registration_number = "SCI/2026/001"
        self.student_user.profile.user_type = "student"
        self.student_user.profile.department = department
        self.student_user.profile.save()

    def test_user_can_login_with_staff_id(self):
        response = self.client.post(
            reverse("login"),
            {"username": "STF-001", "password": "StrongPass123!"},
        )

        self.assertRedirects(response, "/dashboard/")

    def test_user_can_login_with_student_id(self):
        response = self.client.post(
            reverse("login"),
            {"username": "SCI/2026/001", "password": "StrongPass123!"},
        )

        self.assertRedirects(response, "/dashboard/")

    def test_login_page_highlights_link_to_more_information(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-highlight-link', html=False)
        self.assertContains(response, reverse("assets:about") + "#system-overview")
        self.assertContains(response, reverse("assets:about") + "#workflow-overview")
        self.assertContains(response, reverse("assets:about") + "#leadership-oversight")

    def test_login_with_stale_csrf_token_redirects_back_to_login(self):
        csrf_client = Client(enforce_csrf_checks=True)

        response = csrf_client.post(
            reverse("login"),
            {
                "username": "staffmember",
                "password": "StrongPass123!",
                "csrfmiddlewaretoken": "stale-token",
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("login"))
        self.assertContains(response, "Your sign-in page expired.")


class LogoutViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="logoutuser",
            email="logout@example.com",
            password="StrongPass123!",
        )

    def test_logout_view_signs_user_out_with_get_request(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("logout"))

        self.assertRedirects(response, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_view_signs_user_out_with_post_without_csrf_token(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)


class ProfileViewTests(TestCase):
    def setUp(self):
        faculty = Faculty.objects.create(name="Faculty of Science")
        self.department = Department.objects.create(code="PHY", name="Physics", faculty=faculty)
        self.staff_location = Location.objects.create(
            department=self.department,
            building="Physics Block",
            floor="2",
            room="Lab 4",
            room_type="lab",
        )
        self.user = User.objects.create_user(
            username="profileuser",
            email="profile@example.com",
            password="StrongPass123!",
            first_name="Profile",
            last_name="User",
        )
        self.user.profile.department = self.department
        self.user.profile.user_type = "student"
        self.user.profile.registration_number = "PHY/001/26"
        self.user.profile.phone_number = "0700111222"
        self.user.profile.role = "lecturer"
        self.user.profile.save()
        self.temp_media_root = Path(settings.BASE_DIR) / "test-media-accounts"
        self.temp_media_root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.temp_media_root, ignore_errors=True))

    def test_profile_page_shows_account_details(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Account")
        self.assertContains(response, "Profile User")
        self.assertContains(response, self.user.email)
        self.assertContains(response, self.department.name)
        self.assertContains(response, "PHY/001/26")
        self.assertContains(response, "0700111222")
        self.assertContains(response, reverse("password_change"))

    def test_student_profile_only_shows_student_id(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("profile"))

        self.assertContains(response, "Student ID")
        self.assertContains(response, "PHY/001/26")
        self.assertNotContains(response, "Staff ID")

    def test_staff_profile_only_shows_staff_id(self):
        self.user.profile.user_type = "staff"
        self.user.profile.registration_number = ""
        self.user.profile.employee_id = "EMP-001"
        self.user.profile.staff_location = self.staff_location
        self.user.profile.save()
        self.client.force_login(self.user)

        response = self.client.get(reverse("profile"))

        self.assertContains(response, "Staff ID")
        self.assertContains(response, "EMP-001")
        self.assertContains(response, "Office / Lab")
        self.assertContains(response, str(self.staff_location))
        self.assertNotContains(response, "Student ID")

    def test_topbar_shows_static_greeting_instead_of_profile_link(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("profile"))

        hour = timezone.localtime().hour
        if hour < 12:
            greeting = "Good Morning"
        elif hour < 17:
            greeting = "Good Afternoon"
        else:
            greeting = "Good Evening"

        self.assertContains(
            response,
            f'<span class="pill greeting-pill">{greeting}, {self.user.first_name}!</span>',
            html=True,
        )
        self.assertNotContains(
            response,
            f'href="{reverse("profile")}"',
            html=False,
        )
        self.assertNotContains(response, ">My Profile<", html=False)

    def test_user_can_update_editable_profile_details(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profile"),
            {
                "first_name": "Updated",
                "last_name": "Member",
                "email": "updated@example.com",
                "phone_number": "0712345678",
                "user_type": "staff",
                "registration_number": "",
                "employee_id": "EMP-909",
            },
        )

        self.assertRedirects(response, reverse("profile"))
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")
        self.assertEqual(self.user.last_name, "Member")
        self.assertEqual(self.user.email, "updated@example.com")
        self.assertEqual(self.user.profile.phone_number, "0712345678")
        self.assertEqual(self.user.profile.user_type, "student")
        self.assertEqual(self.user.profile.registration_number, "PHY/001/26")
        self.assertEqual(self.user.profile.employee_id, "")

    def test_user_can_upload_profile_photo(self):
        self.client.force_login(self.user)
        photo = SimpleUploadedFile(
            "avatar.gif",
            (
                b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
                b"\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00"
                b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
            ),
            content_type="image/gif",
        )

        with override_settings(MEDIA_ROOT=str(self.temp_media_root)):
            response = self.client.post(
                reverse("profile"),
                {
                    "first_name": self.user.first_name,
                    "last_name": self.user.last_name,
                    "email": self.user.email,
                    "phone_number": self.user.profile.phone_number,
                    "photo": photo,
                },
            )

        self.assertRedirects(response, reverse("profile"))
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.photo.name)
        self.assertIn(f"profiles/{self.user.id}/", self.user.profile.photo.name)

    def test_staff_user_can_update_profile_location(self):
        self.user.profile.user_type = "staff"
        self.user.profile.registration_number = ""
        self.user.profile.employee_id = "EMP-021"
        self.user.profile.save()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profile"),
            {
                "first_name": self.user.first_name,
                "last_name": self.user.last_name,
                "email": self.user.email,
                "phone_number": self.user.profile.phone_number,
                "staff_location": self.staff_location.id,
            },
        )

        self.assertRedirects(response, reverse("profile"))
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.staff_location, self.staff_location)

    def test_user_can_change_password_from_account(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "StrongPass123!",
                "new_password1": "NewProfilePass123!",
                "new_password2": "NewProfilePass123!",
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("password_change_done"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewProfilePass123!"))

    def test_password_change_page_uses_account_template(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("password_change"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Change password")
        self.assertContains(response, "Current password")
        self.assertContains(response, "Back to Profile")

    def test_password_change_rejects_incorrect_current_password(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "WrongPass123!",
                "new_password1": "ReplacementPass123!",
                "new_password2": "ReplacementPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your old password was entered incorrectly")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("StrongPass123!"))
