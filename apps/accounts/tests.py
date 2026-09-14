from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, Permission
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.facilities.models import Warehouse, WarehouseMembership, WarehouseRole

from .permissions import ensure_modify_permissions, selectable_permissions


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()


class UserPermissionTests(TestCase):
    def test_old_function_permissions_are_not_selectable_or_recreated(self):
        retired = ContentType.objects.create(app_label="maintenance", model="maintenanceplan")
        Permission.objects.create(content_type=retired, codename="view_maintenanceplan", name="Old view")
        ensure_modify_permissions(apps.get_app_config("maintenance"))
        self.assertFalse(selectable_permissions().filter(content_type=retired).exists())
        self.assertFalse(Permission.objects.filter(content_type=retired, codename="modify_maintenanceplan").exists())
        self.assertFalse(selectable_permissions().filter(content_type__app_label="sessions").exists())

    def test_legacy_grants_merge_for_users_groups_and_warehouse_roles(self):
        content_type = ContentType.objects.get(app_label="workorders", model="workorder")
        legacy = [Permission.objects.create(content_type=content_type, codename=f"{action}_workorder", name=action)
                  for action in ("add", "change", "delete")]
        user = get_user_model().objects.create_user(username="legacy-user", email="legacy@example.com")
        group = Group.objects.create(name="Legacy group")
        role = WarehouseRole.objects.create(code="LEGACY", name="Legacy role")
        user.user_permissions.add(legacy[0])
        group.permissions.add(legacy[1])
        role.permissions.add(legacy[2])
        for _ in range(2):
            ensure_modify_permissions(apps.get_app_config("workorders"))
        for owner in (user.user_permissions, group.permissions, role.permissions):
            self.assertEqual(list(owner.values_list("codename", flat=True)), ["modify_workorder"])
        self.assertFalse(Permission.objects.filter(pk__in=[p.pk for p in legacy]).exists())
        self.assertTrue(get_user_model().objects.get(pk=user.pk).has_perm("workorders.add_workorder"))

    def test_simple_password_is_allowed(self):
        form = CustomUserCreationForm(
            data={"username": "simple-user", "password1": "1", "password2": "1"}
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_permission_selector_has_only_view_and_modify(self):
        permissions = selectable_permissions().filter(
            content_type__app_label="workorders",
            content_type__model="workorder",
        )

        self.assertSetEqual(
            set(permissions.values_list("codename", flat=True)),
            {"view_workorder", "modify_workorder"},
        )

    def test_group_modify_permission_enables_all_write_actions(self):
        user = get_user_model().objects.create_user(
            username="group-user",
            email="group-user@example.com",
            password="1",
        )
        group = Group.objects.create(name="工单录入员")
        permission = Permission.objects.get(
            content_type__app_label="workorders",
            codename="modify_workorder",
        )
        group.permissions.add(permission)

        # Prime Django's permission cache before assigning the group.
        self.assertFalse(user.has_perm("workorders.add_workorder"))

        user.groups.add(group)
        user.refresh_from_db()

        self.assertTrue(user.is_staff)
        self.assertFalse(user.user_permissions.exists())
        self.assertTrue(user.has_perm("workorders.modify_workorder"))
        self.assertTrue(user.has_perm("workorders.add_workorder"))
        self.assertTrue(user.has_perm("workorders.change_workorder"))
        self.assertTrue(user.has_perm("workorders.delete_workorder"))
        self.assertFalse(user.has_perm("workorders.view_workorder"))

    def test_warehouse_role_permissions_are_effective(self):
        user = get_user_model().objects.create_user(
            username="role-user",
            email="role-user@example.com",
            password="1",
        )
        warehouse = Warehouse.objects.create(code="ROLE-WH", name="角色测试仓")
        permission = Permission.objects.get(
            content_type__app_label="workorders",
            codename="view_workorder",
        )
        role = WarehouseRole.objects.create(code="CUSTOM", name="自定义角色")
        role.permissions.add(permission)

        WarehouseMembership.objects.create(warehouse=warehouse, user=user, role=role)
        user.refresh_from_db()

        self.assertTrue(user.is_staff)
        self.assertTrue(user.has_perm("workorders.view_workorder"))
        self.assertFalse(user.has_perm("workorders.change_workorder"))


class UserAdminTests(TestCase):
    def setUp(self):
        self.admin_user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="1",
        )
        self.client.force_login(self.admin_user)

    def test_new_user_form_uses_one_name_field_and_no_timezone(self):
        response = self.client.get(reverse("admin:accounts_user_add"))

        fields = set(response.context["adminform"].form.fields)
        self.assertIn("display_name", fields)
        self.assertIn("email", fields)
        self.assertNotIn("first_name", fields)
        self.assertNotIn("last_name", fields)
        self.assertNotIn("timezone", fields)

    def test_admin_account_change_page_is_read_only(self):
        url = reverse("admin:accounts_user_change", args=[self.admin_user.pk])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="_save"')
        self.assertNotContains(response, 'class="deletelink"')
        self.assertNotContains(response, "password/change")

        update_response = self.client.post(url, {"username": "renamed-admin"})
        self.assertEqual(update_response.status_code, 403)
        self.admin_user.refresh_from_db()
        self.assertEqual(self.admin_user.username, "admin")


class LanguageSupportTests(TestCase):
    def test_login_page_uses_english_and_spanish_catalogs(self):
        english = self.client.get(reverse("login"), HTTP_ACCEPT_LANGUAGE="en")
        spanish = self.client.get(reverse("login"), HTTP_ACCEPT_LANGUAGE="es")

        self.assertContains(english, "Sign in")
        self.assertContains(spanish, "Iniciar sesión")
        self.assertContains(spanish, "Sistema de gestión de mantenimiento")

    def test_language_selection_is_persisted_in_cookie(self):
        response = self.client.post(
            reverse("set_language"),
            {"language": "es", "next": reverse("login")},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, "es")
