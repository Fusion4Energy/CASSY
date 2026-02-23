from cassy.auxiliary.init_folders import init_paths_assessment, init_bolts_assessment


def test_init_paths_assessment(tmp_path):
    # test with default name
    init_paths_assessment(tmp_path)
    assert (tmp_path / "config").exists()
    assert (tmp_path / "stresses").exists()
    assert (tmp_path / "additional_materials").exists()
    assert (tmp_path / "config" / "model_example.xlsx").exists()


def test_init_bolts_assessment(tmp_path):
    # test with default name
    init_bolts_assessment(tmp_path)
    assert (tmp_path / "config").exists()
    assert (tmp_path / "actions").exists()
    assert (tmp_path / "additional_materials").exists()
    assert (tmp_path / "geometries").exists()
    assert (tmp_path / "geometries" / "M12_insert.xlsx").exists()
    assert (tmp_path / "geometries" / "M12_bolt.xlsx").exists()
    assert (tmp_path / "config" / "Flange1.xlsx").exists()
