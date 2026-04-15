from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class UsernameOrProfileIdBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = (username or kwargs.get(get_user_model().USERNAME_FIELD) or "").strip()
        if not identifier or password is None:
            return None

        UserModel = get_user_model()
        username_field = f"{UserModel.USERNAME_FIELD}__iexact"

        matches = list(
            UserModel._default_manager.filter(
                Q(**{username_field: identifier})
                | Q(profile__employee_id__iexact=identifier)
                | Q(profile__registration_number__iexact=identifier)
            ).distinct()[:2]
        )

        if len(matches) != 1:
            return None

        user = matches[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
