from django.contrib.auth.models import Group

from .models import (
    ROLE_ADMIN,
    ROLE_COD,
    ROLE_DEAN,
    ROLE_INTERNAL_AUDITOR,
    ROLE_LAB_TECHNICIAN,
    ROLE_LECTURER,
)


ROLE_LABEL_MAP = {
    ROLE_ADMIN: "Admin",
    ROLE_DEAN: "Dean",
    ROLE_COD: "COD",
    ROLE_LECTURER: "Lecturer",
    ROLE_LAB_TECHNICIAN: "Lab Technician",
    ROLE_INTERNAL_AUDITOR: "Auditor",
}

ROLE_GROUP_MAP = {
    ROLE_ADMIN: "Admin",
    ROLE_DEAN: "Dean",
    ROLE_COD: "COD",
    ROLE_LECTURER: "Lecturer",
    ROLE_LAB_TECHNICIAN: "Lab Technician",
    ROLE_INTERNAL_AUDITOR: "Auditor",
}

LEGACY_GROUP_ROLE_MAP = {
    "system_admin": ROLE_ADMIN,
    "Faculty Administrator": ROLE_ADMIN,
    "administrator": ROLE_ADMIN,
    "Dean of Faculty": ROLE_DEAN,
    "dean": ROLE_DEAN,
    "chair_department": ROLE_COD,
    "Chair of Department": ROLE_COD,
    "cod": ROLE_COD,
    "lecturer_staff": ROLE_LECTURER,
    "lecturer": ROLE_LECTURER,
    "technician": ROLE_LAB_TECHNICIAN,
    "Lab Technician": ROLE_LAB_TECHNICIAN,
    "Auditor": ROLE_INTERNAL_AUDITOR,
    "internal_auditor": ROLE_INTERNAL_AUDITOR,
    "Internal Auditor": ROLE_INTERNAL_AUDITOR,
    "External Auditor": ROLE_INTERNAL_AUDITOR,
}


def get_role_label(role: str, default: str = "") -> str:
    if not role:
        return default

    return ROLE_LABEL_MAP.get(role, role.replace("_", " ").title())


def bootstrap_role_groups():
    groups = {}
    for role, group_name in ROLE_GROUP_MAP.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        groups[role] = group
    return groups


def infer_user_role(user) -> str:
    if user.is_superuser:
        return ROLE_ADMIN

    profile = getattr(user, "profile", None)
    if profile and profile.role:
        return profile.role

    group_names = set(user.groups.values_list("name", flat=True))
    for group_name in group_names:
        if group_name in LEGACY_GROUP_ROLE_MAP:
            return LEGACY_GROUP_ROLE_MAP[group_name]

    return ""


def sync_user_role_group(user):
    role = infer_user_role(user)
    if not role:
        return

    groups = bootstrap_role_groups()
    target_group = groups[role]
    user.groups.add(target_group)


def user_has_role(user, *roles: str) -> bool:
    return infer_user_role(user) in roles


def user_is_department_scoped(user) -> bool:
    return user_has_role(user, ROLE_COD, ROLE_LECTURER, ROLE_LAB_TECHNICIAN)
