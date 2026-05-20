import pytest
from explore.bandit import apply_action, batch_stats, score_card_with_stats


@pytest.mark.django_db
def test_apply_action_saved_increments_alpha(tenant_a):
    from explore.models import TagDict
    TagDict.objects.create(tenant=tenant_a, tag="ml", alpha=1.0, beta=1.0)

    apply_action(tenant_a.id, ["ml"], "saved")
    td = TagDict.objects.get(tenant=tenant_a, tag="ml")
    assert td.alpha == 2.0
    assert td.beta == 1.0


@pytest.mark.django_db
def test_apply_action_skipped_increments_beta(tenant_a):
    from explore.models import TagDict
    TagDict.objects.create(tenant=tenant_a, tag="physics", alpha=1.0, beta=1.0)

    apply_action(tenant_a.id, ["physics"], "skipped")
    td = TagDict.objects.get(tenant=tenant_a, tag="physics")
    assert td.beta == 2.0
    assert td.alpha == 1.0


@pytest.mark.django_db
def test_tenant_isolation(tenant_a, tenant_b):
    from explore.models import TagDict
    TagDict.objects.create(tenant=tenant_a, tag="nlp", alpha=2.0, beta=1.0)
    TagDict.objects.create(tenant=tenant_b, tag="nlp", alpha=0.5, beta=5.0)

    stats_a = batch_stats(tenant_a.id, {"nlp"})
    stats_b = batch_stats(tenant_b.id, {"nlp"})
    assert stats_a["nlp"][0] == 2.0
    assert stats_b["nlp"][0] == 0.5
