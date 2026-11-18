"""Registry index persistence: activations survive new instances/restarts."""

import joblib  # noqa: F401 (ensures joblib present for artifact parity checks)


def _tiny_model():
    from sklearn.dummy import DummyClassifier

    return DummyClassifier(strategy="prior")


def test_register_and_activate_survive_new_instance(tmp_path):
    from sklearn.preprocessing import StandardScaler

    from services.ml.registry import ModelRegistry

    store = str(tmp_path / "registry")
    r1 = ModelRegistry(store)
    r1.register(
        name="testmodel",
        version="v1",
        model=_tiny_model(),
        calibrator=None,
        scaler=StandardScaler(),
        features=["a", "b"],
        metrics={"accuracy": 0.5},
        training_data_hash="sha256:test",
        hyperparameters={},
    )
    r1.set_active("testmodel", "v1")

    # A fresh instance (new request, restarted process) sees it.
    r2 = ModelRegistry(store)
    assert r2.active_versions.get("testmodel") == "v1"
    assert r2.list_versions("testmodel")[0]["status"] == "active"


def test_corrupt_index_fails_open(tmp_path):
    from services.ml.registry import ModelRegistry

    store = tmp_path / "registry"
    store.mkdir()
    (store / "registry_index.json").write_text("{not json", encoding="utf-8")
    r = ModelRegistry(str(store))
    assert r.models == {}
    assert r.active_versions == {}
    assert r.list_versions("anything") == []
