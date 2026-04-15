from django.contrib.contenttypes.models import ContentType

from .models import AuditLog


SENSITIVE_FIELD_NAMES = {"password"}


def flatten_field_names(data, prefix=""):
    field_names = []
    for key, value in (data or {}).items():
        qualified_name = f"{prefix}.{key}" if prefix else key
        if key in SENSITIVE_FIELD_NAMES or qualified_name in SENSITIVE_FIELD_NAMES:
            continue
        if isinstance(value, dict):
            field_names.extend(flatten_field_names(value, qualified_name))
        else:
            field_names.append(qualified_name)
    return field_names


def log_audit_event(*, actor, action, instance=None, model_class=None, object_id=None, object_repr="", source="", metadata=None):
    resolved_model = model_class or (instance.__class__ if instance is not None else None)
    content_type = ContentType.objects.get_for_model(resolved_model) if resolved_model else None
    resolved_object_id = object_id if object_id is not None else getattr(instance, "pk", "")
    resolved_object_repr = object_repr or (str(instance) if instance is not None else "")

    AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        actor_username=getattr(actor, "username", "") or "",
        action=action,
        target_content_type=content_type,
        target_object_id=str(resolved_object_id or ""),
        target_repr=resolved_object_repr[:255],
        source=source[:255] if source else "",
        metadata=metadata or {},
    )
