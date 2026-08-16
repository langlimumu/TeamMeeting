from .database import *
from .sso_http import *

def permissions_for(user):
    is_admin = bool(user and user.get("role") == "admin")
    if is_admin:
        operations = {
            module: {action: True for action in PERMISSION_ACTIONS}
            for module in MODULE_KEYS
        }
    elif not user:
        with connect() as conn:
            rows = rows_to_list(
                conn.execute(
                    """
                    SELECT module_key, can_view
                    FROM module_permissions
                    WHERE user_type_key=?
                    ORDER BY module_key
                    """,
                    (GUEST_USER_TYPE_KEY,),
                ).fetchall()
            )
        operations = {
            row["module_key"]: {
                "view": bool(row["can_view"]),
                "create": False,
                "edit": False,
                "delete": False,
            }
            for row in rows
        }
    else:
        with connect() as conn:
            rows = rows_to_list(
                conn.execute(
                    """
                    SELECT module_key, can_view, can_create, can_edit, can_delete
                    FROM module_permissions
                    WHERE user_type_key=?
                    ORDER BY module_key
                    """,
                    (user.get("user_type") or DEFAULT_USER_TYPE_KEY,),
                ).fetchall()
            )
        operations = {
            row["module_key"]: {
                "view": bool(row["can_view"]),
                "create": bool(row["can_create"]),
                "edit": bool(row["can_edit"]),
                "delete": bool(row["can_delete"]),
            }
            for row in rows
        }
        if operations.get("processes", {}).get("view"):
            operations["processes"]["create"] = True
    modules = sorted(module for module, actions in operations.items() if actions.get("view"))
    return {
        "isAdmin": is_admin,
        "userType": user.get("user_type") if user else GUEST_USER_TYPE_KEY,
        "modules": modules,
        "operations": operations,
        "canManageUsers": is_admin,
        "canPublishRules": is_admin,
        "canRecordScores": is_admin,
        "canManageLinks": is_admin,
        "canManageSchedule": is_admin,
        "canManageMembers": is_admin,
        "canManageMeetingTopics": is_admin,
        "canManageAttendance": is_admin,
        "canManageSystem": is_admin,
        "canCreateMeeting": bool(operations.get("meetings", {}).get("create")),
        "canPostThankYou": bool(operations.get("thanks", {}).get("create")),
    }


def date_filter(query, column):
    clauses = ["1=1"]
    params = []
    if query.get("from") and query["from"][0]:
        clauses.append(f"{column} >= ?")
        params.append(query["from"][0])
    if query.get("to") and query["to"][0]:
        clauses.append(f"{column} <= ?")
        params.append(query["to"][0])
    return " AND ".join(clauses), params


