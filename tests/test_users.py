def test_list_users_requires_admin(client, normal_user_and_token, auth_header):
    _, token = normal_user_and_token
    resp = client.get("/api/users", headers=auth_header(token))
    assert resp.status_code == 403


def test_admin_can_list_users(client, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    resp = client.get("/api/users", headers=auth_header(token))
    assert resp.status_code == 200


def test_owner_can_update_own_profile(client, normal_user_and_token, auth_header):
    user, token = normal_user_and_token
    resp = client.put(
        f"/api/users/{user.id}",
        json={"username": "renamed"},
        headers=auth_header(token),
    )
    assert resp.status_code == 200
    assert resp.get_json()["user"]["username"] == "renamed"


def test_non_owner_cannot_update_others_profile(
    client, normal_user_and_token, admin_user_and_token, auth_header
):
    admin_user, admin_token = admin_user_and_token
    user, user_token = normal_user_and_token

    resp = client.put(
        f"/api/users/{admin_user.id}",
        json={"username": "hijacked"},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 403
