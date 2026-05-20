import pytest
from subscriptions.services import (
    create_subscription,
    delete_subscription,
    get_subscription,
    list_subscriptions,
    update_subscription,
)


@pytest.mark.django_db
def test_crud_isolation(tenant_a, tenant_b):
    sub_a = create_subscription(tenant_a.id, description="ML papers")
    sub_b = create_subscription(tenant_b.id, description="Physics papers")

    # tenant_a cannot see tenant_b's subscription
    assert get_subscription(tenant_a.id, sub_b.id) is None
    assert get_subscription(tenant_b.id, sub_a.id) is None

    # list is scoped to tenant
    assert len(list_subscriptions(tenant_a.id)) == 1
    assert len(list_subscriptions(tenant_b.id)) == 1


@pytest.mark.django_db
def test_update(tenant_a):
    sub = create_subscription(tenant_a.id, description="original")
    updated = update_subscription(tenant_a.id, sub.id, description="updated", active=False)
    assert updated.description == "updated"
    assert updated.active is False


@pytest.mark.django_db
def test_delete(tenant_a):
    sub = create_subscription(tenant_a.id, description="to delete")
    assert delete_subscription(tenant_a.id, sub.id) is True
    assert get_subscription(tenant_a.id, sub.id) is None


@pytest.mark.django_db
def test_delete_wrong_tenant(tenant_a, tenant_b):
    sub = create_subscription(tenant_a.id, description="mine")
    assert delete_subscription(tenant_b.id, sub.id) is False
