"""Google Cloud Identity Groups API client for dual-group governance."""

import logging

import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class CloudIdentityGroupManager:
    """Manages group memberships in enabled and disabled Antigravity groups using Cloud Identity API."""

    def __init__(self, enabled_group_email: str, disabled_group_email: str):
        self.enabled_group_email = enabled_group_email
        self.disabled_group_email = disabled_group_email
        self._service = None
        self._group_keys: dict[str, str] = {}  # email -> group resource name e.g. groups/{id}

    def _get_service(self):
        if self._service is None:
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-identity.groups"])
            self._service = build("cloudidentity", "v1", credentials=credentials, cache_discovery=False)
        return self._service

    def _lookup_group_name(self, group_email: str) -> str | None:
        if group_email in self._group_keys:
            return self._group_keys[group_email]
        try:
            service = self._get_service()
            response = service.groups().lookup(groupKey_id=group_email).execute()
            name = response.get("name")
            if name:
                self._group_keys[group_email] = name
            return name
        except Exception as e:
            logger.error(f"Failed to lookup Cloud Identity group {group_email}: {e}")
            return None

    def get_group_members(self, group_email: str) -> set[str]:
        """Fetch all member emails for a given group."""
        group_name = self._lookup_group_name(group_email)
        if not group_name:
            return set()

        members = set()
        try:
            service = self._get_service()
            page_token = None
            while True:
                response = service.groups().memberships().list(parent=group_name, pageToken=page_token).execute()
                for membership in response.get("memberships", []):
                    member_key = membership.get("preferredMemberKey", {}).get("id")
                    if member_key:
                        members.add(member_key.lower().strip())
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        except Exception as e:
            logger.error(f"Failed to list members of group {group_email}: {e}")
        return members

    def add_member_to_group(self, group_email: str, user_email: str) -> bool:
        """Add user email to group."""
        group_name = self._lookup_group_name(group_email)
        if not group_name:
            return False
        clean_email = user_email.lower().strip()
        try:
            service = self._get_service()
            body = {
                "preferredMemberKey": {"id": clean_email},
                "roles": [{"name": "MEMBER"}],
            }
            service.groups().memberships().create(parent=group_name, body=body).execute()
            logger.info(f"Added {clean_email} to {group_email}")
            return True
        except HttpError as e:
            if e.resp.status == 409:
                logger.info(f"User {clean_email} already a member of {group_email}")
                return True
            logger.error(f"Failed to add {clean_email} to {group_email}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to add {clean_email} to {group_email}: {e}")
            return False

    def remove_member_from_group(self, group_email: str, user_email: str) -> bool:
        """Remove user email from group."""
        group_name = self._lookup_group_name(group_email)
        if not group_name:
            return False
        clean_email = user_email.lower().strip()
        service = self._get_service()

        mem_resource_name = None
        # First attempt quick direct lookup
        try:
            lookup_res = (
                service.groups()
                .memberships()
                .lookup(parent=group_name, memberKey_id=clean_email)
                .execute()
            )
            mem_resource_name = lookup_res.get("name")
        except HttpError:
            # External members or non-directory identities return 403 on lookup
            pass
        except Exception as e:
            logger.warning(f"Lookup failed for {clean_email} in {group_email}: {e}")

        # Fallback to listing memberships if lookup didn't yield a name
        if not mem_resource_name:
            try:
                page_token = None
                while True:
                    list_res = service.groups().memberships().list(parent=group_name, pageToken=page_token).execute()
                    for m in list_res.get("memberships", []):
                        if m.get("preferredMemberKey", {}).get("id", "").lower() == clean_email:
                            mem_resource_name = m.get("name")
                            break
                    if mem_resource_name or not list_res.get("nextPageToken"):
                        break
                    page_token = list_res.get("nextPageToken")
            except Exception as e:
                logger.error(f"Failed to list memberships while removing {clean_email} from {group_email}: {e}")

        if not mem_resource_name:
            # User is already absent from the group
            return True

        try:
            service.groups().memberships().delete(name=mem_resource_name).execute()
            logger.info(f"Removed {clean_email} from {group_email}")
            return True
        except HttpError as e:
            if e.resp.status == 404:
                return True
            logger.error(f"Failed to delete membership {mem_resource_name} ({clean_email}) from {group_email}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to remove {clean_email} from {group_email}: {e}")
            return False

    def reconcile_user_group(
        self,
        user_email: str,
        target_group: str,  # "ENABLED" or "DISABLED"
    ) -> bool:
        """Move user to target group and ensure removal from the opposite group."""
        user = user_email.lower().strip()
        if target_group == "ENABLED":
            self.add_member_to_group(self.enabled_group_email, user)
            self.remove_member_from_group(self.disabled_group_email, user)
        else:
            self.add_member_to_group(self.disabled_group_email, user)
            self.remove_member_from_group(self.enabled_group_email, user)
        return True
