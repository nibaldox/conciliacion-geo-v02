import api.database as db


def test_holes_3d_returns_nullable_geometry_provenance_and_counts(client):
    session_id = "holes-3d-contract"
    db.get_or_create_session(session_id)
    db.save_blast_upload(session_id, {
        "accepted_rows": [
            {
                "hole_id": "DUP", "source_row_index": 7,
                "X": 10, "Y": 20, "Z_collar": 100,
                "X_toe": 11, "Y_toe": 20, "Z_toe": 80,
                "surface_sample_status": "sampled",
                "surface_sample_method": "vertical_ray",
                "Banco_Original": "B-100",
            },
            {"hole_id": "DUP", "source_row_index": 8, "X": 12, "Y": 21, "Z_collar": None},
            {"hole_id": "NOGEO", "source_row_index": 9, "X": 1, "Y": 2},
        ],
        "rejected_rows": [
            {"hole_id": "BAD", "source_row_index": 10, "error_code": "BAD_ROW"},
            {"hole_id": "BAD", "source_row_index": 10, "error_code": "BAD_TOE"},
        ],
        "processing_summary": {"rejected_source_rows": 1, "rejection_records": 2},
    })

    response = client.get("/api/v1/blast/holes/3d", headers={"X-Session-ID": session_id})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "total_loaded": 3, "drawable": 1, "complete_geometry": 1,
        "collar_only": 0, "without_geometry": 2, "rejected": 1,
    }
    assert body["holes"][0]["collar"] == [10.0, 20.0, 100.0]
    assert body["holes"][0]["toe"] == [11.0, 20.0, 80.0]
    assert body["holes"][0]["provenance"]["surface_sample_method"] == "vertical_ray"
    assert body["holes"][0]["attributes"]["Banco_Original"] == "B-100"
    assert body["holes"][1]["collar"] is None
    assert body["holes"][1]["toe"] is None
    assert body["holes"][0]["row_id"] != body["holes"][1]["row_id"]
    assert len(body["rejected_rows"]) == 2
    assert {row["error_code"] for row in body["rejected_rows"]} == {"BAD_ROW", "BAD_TOE"}


def test_holes_3d_empty_session(client):
    response = client.get("/api/v1/blast/holes/3d", headers={"X-Session-ID": "holes-3d-empty"})
    assert response.status_code == 200
    assert response.json()["holes"] == []
    assert response.json()["summary"]["total_loaded"] == 0


def test_holes_3d_legacy_rejections_deduplicate_source_rows(client):
    session_id = "holes-3d-legacy-rejections"
    db.get_or_create_session(session_id)
    db.save_blast_upload(session_id, {
        "accepted_rows": [],
        "rejected_rows": [
            {"hole_id": "BAD", "source_row_index": 12, "error_code": "BAD_X"},
            {"hole_id": "BAD", "source_row_index": 12, "error_code": "BAD_Z"},
            {"hole_id": "WORSE", "source_row_index": 13, "error_code": "BAD_X"},
        ],
    })

    response = client.get(
        "/api/v1/blast/holes/3d", headers={"X-Session-ID": session_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["rejected"] == 2
    assert len(body["rejected_rows"]) == 3


def test_holes_3d_classifies_against_session_section(client):
    session_id = "holes-3d-section"
    db.get_or_create_session(session_id)
    db.save_sections(session_id, [{
        "name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0,
        "length": 100.0, "sector": "A",
    }])
    db.save_blast_upload(session_id, {
        "accepted_rows": [
            {"hole_id": "CROSS", "source_row_index": 1,
             "X": -1, "Y": 0, "Z_collar": 10, "X_toe": 1, "Y_toe": 0, "Z_toe": 0},
            {"hole_id": "NEAR", "source_row_index": 2,
             "X": 2, "Y": 0, "Z_collar": 10, "X_toe": 2, "Y_toe": 10, "Z_toe": 0},
        ],
        "rejected_rows": [],
    })

    response = client.get(
        "/api/v1/blast/holes/3d?section_id=0&corridor_m=3",
        headers={"X-Session-ID": session_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["section_id"] == 0
    assert body["corridor_m"] == 3.0
    assert [hole["section_relation"] for hole in body["holes"]] == [
        "exact_intersection", "near_section",
    ]


def test_holes_3d_section_is_session_scoped(client):
    first_session, second_session = "holes-3d-owner", "holes-3d-other"
    db.get_or_create_session(first_session)
    db.get_or_create_session(second_session)
    db.save_sections(first_session, [{
        "name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0,
        "length": 100.0, "sector": "A",
    }])
    db.save_blast_upload(first_session, {"accepted_rows": [], "rejected_rows": []})

    response = client.get(
        "/api/v1/blast/holes/3d?section_id=0",
        headers={"X-Session-ID": second_session},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error_code"] == "SECTION_NOT_FOUND"


def test_holes_3d_maps_processor_accepted_row_field_names(client):
    session_id = "holes-3d-core-row"
    db.get_or_create_session(session_id)
    db.save_blast_upload(session_id, {
        "accepted_rows": [{
            "uniqid": "BH-00042", "source_row_index": 41,
            "X": 100.0, "Y": 200.0, "Z_collar": 350.0,
            "X_toe": 102.0, "Y_toe": 200.0, "Z_toe": 338.0,
            "Banco_Original": "350", "fecha_tronadura": "2026-10-31",
            "Z_collar_semantic": "design_surface_estimate",
            "surface_sample_status": "sampled",
            "surface_sample_reason": "sampled on design surface",
            "surface_sample_method": "vertical_ray",
            "surface_sample_mesh_id": "mesh-design-1",
            "surface_sample_mesh_sha256": "abc123",
            "surface_sample_unit": "m",
            "surface_sample_assumption": "shared CRS, datum and metres",
        }],
        "rejected_rows": [],
    })

    response = client.get("/api/v1/blast/holes/3d", headers={"X-Session-ID": session_id})

    assert response.status_code == 200
    hole = response.json()["holes"][0]
    assert hole["hole_id"] == "BH-00042"
    assert hole["collar"] == [100.0, 200.0, 350.0]
    assert hole["toe"] == [102.0, 200.0, 338.0]
    assert hole["attributes"]["Banco_Original"] == "350"
    assert hole["attributes"]["fecha_tronadura"] == "2026-10-31"
    assert hole["provenance"]["z_collar_semantic"] == "design_surface_estimate"
    assert hole["provenance"]["surface_sample_mesh_id"] == "mesh-design-1"
    assert hole["provenance"]["surface_sample_assumption"] == "shared CRS, datum and metres"


def test_holes_3d_preserves_per_row_visualization_attributes_and_omits_missing_values(client):
    session_id = "holes-3d-visualization-attributes"
    db.get_or_create_session(session_id)
    db.save_blast_upload(session_id, {
        "accepted_rows": [
            {
                "hole_id": "FULL", "source_row_index": 1,
                "X": 1, "Y": 2, "Z_collar": 300,
                "Nombre_Malla_Original": "Malla Norte", "holes_polygon": "POLY-7",
                "Nombre_Fase": "Fase 2", "Banco_Original": "B-300",
                "Kilos_Cargados_real": 125.5, "Carga_kg": "124.5",
                "PF": "210.25", "pf_g_per_ton": 212.0,
                "Diam_mm": 165, "Diametro": "165.0",
                "dureza": "Dura", "indice_dureza": 72.5,
                "tasa_penetracion": "18.2", "Len": 14.0, "Incl": 12.0,
            },
            {
                "hole_id": "SPARSE", "source_row_index": 2,
                "X": 3, "Y": 4, "Z_collar": 301,
                "Nombre_Malla_Original": None, "PF": float("nan"),
                "Kilos_Cargados_real": None, "Kilos_Cargados": 125,
                "Len": None, "Incl": float("nan"),
            },
        ],
        "rejected_rows": [],
    })

    response = client.get(
        "/api/v1/blast/holes/3d", headers={"X-Session-ID": session_id},
    )

    assert response.status_code == 200
    full, sparse = response.json()["holes"]
    assert full["attributes"] == {
        "Nombre_Malla_Original": "Malla Norte", "holes_polygon": "POLY-7",
        "Nombre_Fase": "Fase 2", "Banco_Original": "B-300",
        "Kilos_Cargados_real": 125.5, "Carga_kg": "124.5",
        "PF": "210.25", "pf_g_per_ton": 212.0,
        "Diam_mm": 165, "Diametro": "165.0",
        "dureza": "Dura", "indice_dureza": 72.5,
        "tasa_penetracion": "18.2", "Len": 14.0, "Incl": 12.0,
    }
    assert sparse["attributes"] == {
        "Nombre_Malla_Original": None, "PF": None,
        "Kilos_Cargados_real": None, "Kilos_Cargados": 125,
        "Len": None, "Incl": None,
    }
    assert sparse["collar"] == [3.0, 4.0, 301.0]


def test_holes_3d_keeps_legacy_visualization_attributes(client):
    session_id = "holes-3d-legacy-attributes"
    db.get_or_create_session(session_id)
    db.save_blast_upload(session_id, {
        "holes": [{
            "hole_id": "LEGACY", "X": 1, "Y": 2, "Z_collar": 3,
            "Banco_Original": "B-1", "Len": 10, "Incl": 5,
            "Diam_mm": 150, "dureza": "Media",
        }],
        "rejected_rows": [],
    })

    response = client.get(
        "/api/v1/blast/holes/3d", headers={"X-Session-ID": session_id},
    )

    assert response.status_code == 200
    hole = response.json()["holes"][0]
    assert hole["hole_id"] == "LEGACY"
    assert hole["attributes"] == {
        "Banco_Original": "B-1", "Len": 10, "Incl": 5,
        "Diam_mm": 150, "dureza": "Media",
    }
    assert hole["collar"] == [1.0, 2.0, 3.0]


def test_holes_3d_preserves_frontend_filter_and_color_aliases_as_present(client):
    session_id = "holes-3d-frontend-aliases"
    db.get_or_create_session(session_id)
    db.save_blast_upload(session_id, {
        "accepted_rows": [{
            "hole_id": "ALIASES", "X": 10, "Y": 20, "Z_collar": 300,
            "Nombre_Banco": "B-300", "Diametro_mm": 165, "diameter_mm": 166,
            "Dureza": "Roca dura", "hardness": "hard",
            "Indice_Dureza": 70, "hardness_index": 71,
            "Tasa_Penetracion": 18, "penetration_rate": 19,
            "Longitud_real": 12.5, "depth_m": 13.5,
            "Inclinacion": 7, "inclination": 8,
        }],
        "rejected_rows": [],
    })

    response = client.get(
        "/api/v1/blast/holes/3d", headers={"X-Session-ID": session_id},
    )

    assert response.status_code == 200
    attributes = response.json()["holes"][0]["attributes"]
    assert attributes == {
        "Nombre_Banco": "B-300", "Diametro_mm": 165, "diameter_mm": 166,
        "Dureza": "Roca dura", "hardness": "hard",
        "Indice_Dureza": 70, "hardness_index": 71,
        "Tasa_Penetracion": 18, "penetration_rate": 19,
        "Longitud_real": 12.5, "depth_m": 13.5,
        "Inclinacion": 7, "inclination": 8,
    }


def test_holes_3d_does_not_create_absent_frontend_aliases(client):
    session_id = "holes-3d-no-frontend-aliases"
    db.get_or_create_session(session_id)
    db.save_blast_upload(session_id, {
        "accepted_rows": [{
            "hole_id": "NO-ALIASES", "X": 10, "Y": 20, "Z_collar": 300,
            "Diam_mm": None,
        }],
        "rejected_rows": [],
    })

    response = client.get(
        "/api/v1/blast/holes/3d", headers={"X-Session-ID": session_id},
    )

    assert response.status_code == 200
    attributes = response.json()["holes"][0]["attributes"]
    assert attributes == {"Diam_mm": None}


def test_holes_3d_uses_persisted_asymmetric_section_limits(client):
    session_id = "holes-3d-asymmetric-section"
    db.get_or_create_session(session_id)
    db.save_sections(session_id, [{
        "name": "S-ASYM", "origin": [0.0, 0.0], "azimuth": 0.0,
        "length": 100.0, "length_up": 80.0, "length_down": 20.0, "sector": "A",
    }])
    db.save_blast_upload(session_id, {
        "accepted_rows": [{
            "hole_id": "UPPER-BOUND", "X": -1, "Y": 70, "Z_collar": 10,
            "X_toe": 1, "Y_toe": 70, "Z_toe": 0,
        }],
        "rejected_rows": [],
    })

    response = client.get(
        "/api/v1/blast/holes/3d?section_id=0&corridor_m=2",
        headers={"X-Session-ID": session_id},
    )

    assert response.status_code == 200
    assert response.json()["holes"][0]["section_relation"] == "exact_intersection"


def test_row_identity_matches_3d_and_profile_for_duplicate_hole_ids(client):
    session_id = "holes-3d-profile-identity"
    headers = {"X-Session-ID": session_id}
    db.get_or_create_session(session_id)
    db.save_sections(session_id, [{
        "name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0,
        "length": 100.0, "sector": "A",
    }])
    db.save_blast_upload(session_id, {
        "accepted_rows": [
            {"hole_id": "DUP", "source_row_index": 31,
             "X": 0, "Y": -3, "Z_collar": 100, "X_toe": 0, "Y_toe": -2, "Z_toe": 90},
            {"hole_id": "DUP", "source_row_index": 32,
             "X": 0, "Y": 3, "Z_collar": 100, "X_toe": 0, "Y_toe": 2, "Z_toe": 90},
        ],
        "rejected_rows": [],
    })

    holes_3d = client.get("/api/v1/blast/holes/3d", headers=headers).json()["holes"]
    profile = client.get(
        "/api/v1/process/profiles/0/blast-holes", headers=headers,
        params={"tolerance": 10},
    ).json()["holes"]
    profile_again = client.get(
        "/api/v1/process/profiles/0/blast-holes", headers=headers,
        params={"tolerance": 10},
    ).json()["holes"]

    ids_3d = {hole["row_id"] for hole in holes_3d}
    assert len(ids_3d) == 2
    assert {hole["row_id"] for hole in profile} == ids_3d
    assert {hole["profile_point_kind"] for hole in profile} == {"projected_collar"}
    assert [hole["row_id"] for hole in profile_again] == [hole["row_id"] for hole in profile]


def test_row_identity_handles_duplicate_source_index_and_id_after_profile_sort(client):
    session_id = "holes-3d-profile-adversarial-identity"
    headers = {"X-Session-ID": session_id}
    db.get_or_create_session(session_id)
    db.save_sections(session_id, [{
        "name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0,
        "length": 100.0, "sector": "A",
    }])
    db.save_blast_upload(session_id, {
        "accepted_rows": [
            {"hole_id": "DUP", "source_row_index": 7,
             "X": 0, "Y": 4, "Z_collar": 100, "X_toe": 0, "Y_toe": 3, "Z_toe": 90},
            {"hole_id": "DUP", "source_row_index": 7,
             "X": 0, "Y": -4, "Z_collar": 100, "X_toe": 0, "Y_toe": -3, "Z_toe": 90},
        ],
        "rejected_rows": [],
    })

    holes_3d = client.get("/api/v1/blast/holes/3d", headers=headers).json()["holes"]
    profile = client.get(
        "/api/v1/process/profiles/0/blast-holes", headers=headers,
        params={"tolerance": 10},
    ).json()["holes"]

    assert holes_3d[0]["row_id"] != holes_3d[1]["row_id"]
    assert profile[0]["row_id"] == holes_3d[1]["row_id"]
    assert profile[1]["row_id"] == holes_3d[0]["row_id"]


def test_profile_includes_exact_segment_crossing_even_when_endpoints_outside_radius(client):
    session_id = "holes-profile-crossing-outside-radius"
    headers = {"X-Session-ID": session_id}
    db.get_or_create_session(session_id)
    db.save_sections(session_id, [{
        "name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0,
        "length": 100.0, "sector": "A",
    }])
    db.save_blast_upload(session_id, {
        "accepted_rows": [{
            "hole_id": "CROSS-OUTSIDE", "source_row_index": 15,
            "X": -100, "Y": 0, "Z_collar": 100,
            "X_toe": 100, "Y_toe": 0, "Z_toe": 80,
        }],
        "rejected_rows": [],
    })

    response = client.get(
        "/api/v1/process/profiles/0/blast-holes", headers=headers,
        params={"tolerance": 2},
    )

    assert response.status_code == 200
    holes = response.json()["holes"]
    assert len(holes) == 1
    assert holes[0]["section_relation"] == "exact_intersection"
    assert holes[0]["profile_point_kind"] == "intersection"
    assert holes[0]["distance"] == 0.0
    assert holes[0]["elevation"] == 90.0
    assert holes[0]["is_within_tolerance"] is False


def test_profile_omits_legacy_hole_without_collar_elevation(client):
    session_id = "holes-profile-no-collar-elevation"
    headers = {"X-Session-ID": session_id}
    db.get_or_create_session(session_id)
    db.save_sections(session_id, [{
        "name": "S-01", "origin": [0.0, 0.0], "azimuth": 0.0,
        "length": 100.0, "sector": "A",
    }])
    db.save_blast_upload(session_id, {
        "accepted_rows": [{
            "hole_id": "NO-Z", "source_row_index": 21, "X": 0, "Y": 2,
        }],
        "rejected_rows": [],
    })

    response = client.get(
        "/api/v1/process/profiles/0/blast-holes", headers=headers,
        params={"tolerance": 2},
    )

    assert response.status_code == 200
    assert response.json()["holes"] == []
