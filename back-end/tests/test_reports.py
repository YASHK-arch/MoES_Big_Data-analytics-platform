import io

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.db.session import async_session_factory
from app.main import app
from app.models.media import ReportMedia
from app.models.report import WeatherReport
from app.services.storage import storage_service


@pytest.fixture(autouse=True)
def ensure_storage_ready():
    """Ensure MinIO bucket exists before running tests."""
    storage_service.ensure_bucket_exists()


@pytest.mark.asyncio
async def test_submit_citizen_report_success():
    """Test successful submission of a citizen report without media attachments."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        form_data = {
            "latitude": "19.0760",
            "longitude": "72.8777",
            "category_code": "FLOOD_WATERLOGGING",
            "severity": "HIGH",
            "title": "Severe knee-deep waterlogging near station subway",
            "description": "Traffic completely halted. Water level rising steadily.",
            "location_name": "Kurla Station West, Mumbai",
        }

        response = await client.post("/api/v1/reports", data=form_data)

        assert response.status_code == 201, response.text
        json_data = response.json()

        assert json_data["success"] is True
        assert "data" in json_data
        data = json_data["data"]

        assert "id" in data
        assert data["tracking_id"].startswith("RPT-")
        # Inline pipeline runs on creation; processing_status is COMPLETED after successful run
        assert data["processing_status"] in ("QUEUED", "COMPLETED")
        assert data["verification_status"] == "PENDING"
        assert data["media_count"] == 0
        assert "meta" in json_data
        assert "request_id" in json_data["meta"]

        # Verify DB persistence directly
        async with async_session_factory() as session:
            stmt = select(WeatherReport).where(WeatherReport.id == data["id"])
            result = await session.execute(stmt)
            db_report = result.scalar_one_or_none()

            assert db_report is not None
            assert db_report.title == form_data["title"]
            assert db_report.severity == "HIGH"
            assert db_report.latitude == 19.0760
            assert db_report.longitude == 72.8777
            # Inline pipeline now sets COMPLETED with a real credibility score
            assert db_report.processing_status in ("QUEUED", "COMPLETED")
            assert db_report.verification_status == "PENDING"
            assert db_report.credibility_score >= 0.0

            # Verify spatial point representation in PostGIS
            spatial_query = await session.execute(
                text(
                    "SELECT ST_AsText(geom) AS point_text "
                    "FROM weather_reports WHERE id = :report_id"
                ),
                {"report_id": data["id"]},
            )
            row = spatial_query.fetchone()
            assert row is not None
            assert row[0] == "POINT(72.8777 19.076)"


@pytest.mark.asyncio
async def test_submit_citizen_report_with_media():
    """Test successful submission of a citizen report with an attached image."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        form_data = {
            "latitude": "18.5204",
            "longitude": "73.8567",
            "category_code": "HEAVY_RAINFALL",
            "severity": "MODERATE",
            "title": "Continuous heavy downpour in Shivajinagar",
            "description": "Drainage overflowing along the main arterial road.",
            "location_name": "Shivajinagar, Pune",
        }

        valid_png_data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00"
            b"\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe"
            b"\xa7Cv\xfe\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        fake_image = io.BytesIO(valid_png_data)
        files = [
            ("media_files", ("flood_photo.png", fake_image, "image/png")),
        ]

        response = await client.post(
            "/api/v1/reports",
            data=form_data,
            files=files,
        )

        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["media_count"] == 1

        # Verify media metadata in database and file in MinIO
        async with async_session_factory() as session:
            stmt = select(ReportMedia).where(ReportMedia.report_id == data["id"])
            result = await session.execute(stmt)
            media_record = result.scalar_one_or_none()

            assert media_record is not None
            assert media_record.media_type == "IMAGE"
            assert media_record.mime_type == "image/png"
            assert media_record.file_size_bytes == len(valid_png_data)
            assert len(media_record.sha256_hash) == 64

            # Verify MinIO S3 object exists
            s3_obj = storage_service.client.get_object(
                Bucket=media_record.storage_bucket,
                Key=media_record.storage_key,
            )
            downloaded_bytes = s3_obj["Body"].read()
            assert downloaded_bytes == valid_png_data


@pytest.mark.asyncio
async def test_submit_report_invalid_latitude():
    """Test validation rejection when latitude exceeds 90 degrees."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        form_data = {
            "latitude": "95.5000",
            "longitude": "72.8777",
            "category_code": "FLOOD_WATERLOGGING",
            "severity": "MODERATE",
            "title": "Invalid latitude report",
        }
        response = await client.post("/api/v1/reports", data=form_data)
        assert response.status_code == 422
        json_data = response.json()
        assert json_data["success"] is False
        assert json_data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_submit_report_invalid_longitude():
    """Test validation rejection when longitude exceeds 180 degrees."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        form_data = {
            "latitude": "19.0760",
            "longitude": "-195.0000",
            "category_code": "FLOOD_WATERLOGGING",
            "severity": "MODERATE",
            "title": "Invalid longitude report",
        }
        response = await client.post("/api/v1/reports", data=form_data)
        assert response.status_code == 422
        json_data = response.json()
        assert json_data["success"] is False
        assert json_data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_submit_report_missing_title():
    """Test validation rejection when required title field is omitted."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        form_data = {
            "latitude": "19.0760",
            "longitude": "72.8777",
            "category_code": "FLOOD_WATERLOGGING",
            "severity": "MODERATE",
        }
        response = await client.post("/api/v1/reports", data=form_data)
        assert response.status_code == 422
        json_data = response.json()
        assert json_data["success"] is False


@pytest.mark.asyncio
async def test_submit_report_unsupported_media_mime_type():
    """Test rejection when uploading an unsupported file type."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        form_data = {
            "latitude": "19.0760",
            "longitude": "72.8777",
            "category_code": "FLOOD_WATERLOGGING",
            "severity": "MODERATE",
            "title": "Report with unsupported PDF",
        }
        fake_pdf = io.BytesIO(b"%PDF-1.4 fake_pdf_content")
        files = [
            ("media_files", ("document.pdf", fake_pdf, "application/pdf")),
        ]
        response = await client.post("/api/v1/reports", data=form_data, files=files)
        assert response.status_code == 400
        json_data = response.json()
        assert json_data["success"] is False
        assert "Unsupported media MIME type" in json_data["error"]["message"]


@pytest.mark.asyncio
async def test_tracking_id_uniqueness():
    """Test that consecutive reports receive distinct tracking identifiers."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        form_data = {
            "latitude": "19.0760",
            "longitude": "72.8777",
            "category_code": "FLOOD_WATERLOGGING",
            "severity": "LOW",
            "title": "Report 1 for tracking test",
        }
        res1 = await client.post("/api/v1/reports", data=form_data)
        res2 = await client.post("/api/v1/reports", data=form_data)

        assert res1.status_code == 201
        assert res2.status_code == 201

        id1 = res1.json()["data"]["tracking_id"]
        id2 = res2.json()["data"]["tracking_id"]
        assert id1 != id2


@pytest.mark.asyncio
async def test_get_report_by_tracking_id_success():
    """Test retrieving public status of a report using its tracking ID."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create a report
        create_res = await client.post(
            "/api/v1/reports",
            data={
                "latitude": "28.6139",
                "longitude": "77.2090",
                "category_code": "EXTREME_HEAT",
                "severity": "HIGH",
                "title": "Heatwave alert in Central Delhi",
                "description": "Temperature crossed 45 degrees Celsius.",
                "location_name": "Connaught Place, New Delhi",
            },
        )
        assert create_res.status_code == 201
        tracking_id = create_res.json()["data"]["tracking_id"]
        report_id = create_res.json()["data"]["id"]

        # Look up by tracking ID
        get_res = await client.get(f"/api/v1/reports/{tracking_id}")
        assert get_res.status_code == 200
        json_data = get_res.json()

        assert json_data["success"] is True
        data = json_data["data"]
        assert data["id"] == report_id
        assert data["tracking_id"] == tracking_id
        assert data["title"] == "Heatwave alert in Central Delhi"
        assert data["severity"] == "HIGH"
        # Inline pipeline runs on creation; processing_status is COMPLETED after successful run
        assert data["processing_status"] in ("QUEUED", "COMPLETED")
        assert data["verification_status"] == "PENDING"
        assert data["credibility_score"] >= 0.0
        assert data["location"]["latitude"] == 28.6139
        assert data["location"]["longitude"] == 77.2090
        assert data["location"]["name"] == "Connaught Place, New Delhi"
        assert data["category"]["code"] == "EXTREME_HEAT"


@pytest.mark.asyncio
async def test_get_report_by_uuid_success():
    """Test retrieving report using its UUID."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_res = await client.post(
            "/api/v1/reports",
            data={
                "latitude": "12.9716",
                "longitude": "77.5946",
                "category_code": "URBAN_FLOOD",
                "severity": "MODERATE",
                "title": "Waterlogging in Koramangala",
                "location_name": "Koramangala 4th Block, Bengaluru",
            },
        )
        assert create_res.status_code == 201
        report_id = create_res.json()["data"]["id"]
        tracking_id = create_res.json()["data"]["tracking_id"]

        get_res = await client.get(f"/api/v1/reports/{report_id}")
        assert get_res.status_code == 200
        data = get_res.json()["data"]
        assert data["id"] == report_id
        assert data["tracking_id"] == tracking_id


@pytest.mark.asyncio
async def test_get_report_nonexistent_returns_404():
    """Test that looking up a nonexistent tracking ID returns 404 with standard error envelope."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/reports/RPT-20260101-NONEXISTENT")
        assert response.status_code == 404
        json_data = response.json()
        assert json_data["success"] is False
        assert json_data["error"]["code"] == "RESOURCE_NOT_FOUND"
        assert "does not exist" in json_data["error"]["message"]


@pytest.mark.asyncio
async def test_get_report_malformed_id_returns_422():
    """Test that malformed identifier (spaces, invalid symbols) returns 422 validation error."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/reports/bad%20id%20with%20spaces!")
        assert response.status_code == 422
        json_data = response.json()
        assert json_data["success"] is False
        assert json_data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_get_report_privacy_no_internal_leak():
    """Test that public tracking response excludes internal DB keys, audit logs, and secrets."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_res = await client.post(
            "/api/v1/reports",
            data={
                "latitude": "19.0760",
                "longitude": "72.8777",
                "category_code": "CYCLONE_STORM",
                "severity": "SEVERE",
                "title": "Severe coastal wind gusts",
            },
        )
        tracking_id = create_res.json()["data"]["tracking_id"]

        get_res = await client.get(f"/api/v1/reports/{tracking_id}")
        data = get_res.json()["data"]

        # Ensure private/internal fields are NOT present in public response
        assert "source_id" not in data
        assert "raw_payload" not in data
        assert "text_embedding" not in data
        assert "credibility_explanation" not in data
        assert "audit_logs" not in data


@pytest.mark.asyncio
async def test_get_report_with_media_returns_valid_url():
    """Test that retrieving report with media returns valid accessible media URLs."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        valid_png_data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00"
            b"\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe"
            b"\xa7Cv\xfe\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        fake_png = io.BytesIO(valid_png_data)
        files = [
            ("media_files", ("evidence.png", fake_png, "image/png")),
        ]
        create_res = await client.post(
            "/api/v1/reports",
            data={
                "latitude": "19.0760",
                "longitude": "72.8777",
                "category_code": "FLOOD_WATERLOGGING",
                "severity": "HIGH",
                "title": "Evidence media test report",
            },
            files=files,
        )
        assert create_res.status_code == 201
        tracking_id = create_res.json()["data"]["tracking_id"]

        get_res = await client.get(f"/api/v1/reports/{tracking_id}")
        assert get_res.status_code == 200
        media_list = get_res.json()["data"]["media"]
        assert len(media_list) == 1
        assert "url" in media_list[0]
        media_url = media_list[0]["url"]

        # Verify presigned URL characteristics
        assert "weather-media" in media_url
        assert "X-Amz-Signature=" in media_url or "Signature=" in media_url
        assert "X-Amz-Expires=" in media_url or "Expires=" in media_url
        assert media_list[0]["media_type"] == "IMAGE"
        assert len(media_list[0]["sha256_hash"]) == 64

        # Verify list endpoint also returns the valid presigned media URL
        list_res = await client.get("/api/v1/reports?page_size=10")
        assert list_res.status_code == 200
        items = list_res.json()["data"]
        matching_item = next((item for item in items if item["tracking_id"] == tracking_id), None)
        assert matching_item is not None
        assert len(matching_item["media"]) == 1
        assert "weather-media" in matching_item["media"][0]["url"]


@pytest.mark.asyncio
async def test_list_reports_success_and_pagination():
    """Test listing reports with page and page_size limits."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create 2 reports
        await client.post(
            "/api/v1/reports",
            data={
                "latitude": "12.9716",
                "longitude": "77.5946",
                "category_code": "HEAVY_RAINFALL",
                "severity": "MODERATE",
                "title": "Bengaluru heavy rain event",
            },
        )
        await client.post(
            "/api/v1/reports",
            data={
                "latitude": "13.0827",
                "longitude": "80.2707",
                "category_code": "FLOOD_WATERLOGGING",
                "severity": "HIGH",
                "title": "Chennai flood event",
            },
        )

        res = await client.get("/api/v1/reports?page=1&page_size=10")
        assert res.status_code == 200
        json_data = res.json()
        assert json_data["success"] is True
        assert isinstance(json_data["data"], list)
        assert len(json_data["data"]) >= 2
        assert "pagination" in json_data
        assert json_data["pagination"]["page"] == 1
        assert json_data["pagination"]["page_size"] == 10
        assert json_data["pagination"]["total_records"] >= 2


@pytest.mark.asyncio
async def test_list_reports_multi_page_consistency():
    """Test that multi-page pagination returns disjoint sets and consistent total counts."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_p1 = await client.get("/api/v1/reports?page=1&page_size=5")
        assert res_p1.status_code == 200
        data_p1 = res_p1.json()

        total_records = data_p1["pagination"]["total_records"]
        total_pages = data_p1["pagination"]["total_pages"]
        assert total_pages >= 1

        if total_records > 5:
            res_p2 = await client.get("/api/v1/reports?page=2&page_size=5")
            assert res_p2.status_code == 200
            data_p2 = res_p2.json()

            # Total records must be identical across pages
            assert data_p2["pagination"]["total_records"] == total_records
            assert data_p2["pagination"]["page"] == 2

            # IDs from Page 1 and Page 2 must be disjoint
            p1_ids = {r["id"] for r in data_p1["data"]}
            p2_ids = {r["id"] for r in data_p2["data"]}
            assert p1_ids.isdisjoint(p2_ids)


@pytest.mark.asyncio
async def test_list_reports_filter_by_category():
    """Test filtering reports by category code."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/api/v1/reports",
            data={
                "latitude": "28.6139",
                "longitude": "77.2090",
                "category_code": "EXTREME_HEAT",
                "severity": "SEVERE",
                "title": "Delhi heatwave record",
            },
        )

        res = await client.get("/api/v1/reports?category=EXTREME_HEAT")
        assert res.status_code == 200
        data = res.json()["data"]
        for item in data:
            code = item["category"]["code"]
            title = item["category"]["title"].upper()
            assert code == "EXTREME_HEAT" or "HEAT" in title


@pytest.mark.asyncio
async def test_list_reports_filter_by_severity():
    """Test filtering reports by severity level."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/reports?severity=SEVERE")
        assert res.status_code == 200
        data = res.json()["data"]
        for item in data:
            assert item["severity"] == "SEVERE"


@pytest.mark.asyncio
async def test_list_reports_filter_by_status():
    """Test filtering reports by verification status or comma-separated list."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/reports?status=PENDING,VERIFIED")
        assert res.status_code == 200
        data = res.json()["data"]
        for item in data:
            assert item["verification_status"] in ("PENDING", "VERIFIED")


@pytest.mark.asyncio
async def test_list_reports_filter_by_bbox():
    """Test PostGIS spatial bounding box filtering."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create a report in Mumbai (lat: 18.95, lon: 72.82)
        await client.post(
            "/api/v1/reports",
            data={
                "latitude": "18.9500",
                "longitude": "72.8200",
                "category_code": "HEAVY_RAINFALL",
                "severity": "MODERATE",
                "title": "Mumbai South coastal rain",
            },
        )

        # Mumbai Bounding Box: min_lon=72.7, min_lat=18.8, max_lon=73.0, max_lat=19.3
        mumbai_bbox = "72.7,18.8,73.0,19.3"
        res = await client.get(f"/api/v1/reports?bbox={mumbai_bbox}")
        assert res.status_code == 200
        data = res.json()["data"]
        assert len(data) >= 1

        # Coordinates should fall within Mumbai bbox
        for item in data:
            lat = item["location"]["latitude"]
            lon = item["location"]["longitude"]
            assert 18.8 <= lat <= 19.3
            assert 72.7 <= lon <= 73.0


@pytest.mark.asyncio
async def test_list_reports_invalid_bbox():
    """Test that invalid bbox format or bounds returns 422 error."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Malformed bbox
        res = await client.get("/api/v1/reports?bbox=not_a_valid_bbox")
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"

        # Out-of-bounds bbox
        res2 = await client.get("/api/v1/reports?bbox=200,10,210,20")
        assert res2.status_code == 422
        assert res2.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_list_reports_invalid_date_range():
    """Test that from_date > to_date returns 422 error."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/api/v1/reports?from_date=2026-08-30T00:00:00Z&to_date=2026-08-20T00:00:00Z"
        )
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_list_reports_privacy_no_internal_leak():
    """Test that list report records exclude internal DB keys and audit fields."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/reports")
        assert res.status_code == 200
        data = res.json()["data"]
        if data:
            first = data[0]
            assert "source_id" not in first
            assert "raw_payload" not in first
            assert "text_embedding" not in first
        assert "credibility_explanation" not in first
        assert "audit_logs" not in first


@pytest.mark.asyncio
async def test_verify_report_action_success(api_client: AsyncClient):
    """Test verifying a report persists VERIFIED status and audit history."""
    # Create a report
    create_res = await api_client.post(
        "/api/v1/reports",
        data={
            "latitude": "19.0760",
            "longitude": "72.8777",
            "category_code": "FLOOD_WATERLOGGING",
            "severity": "HIGH",
            "title": "Mumbai waterlogging test verification",
        },
    )
    assert create_res.status_code == 201
    tracking_id = create_res.json()["data"]["tracking_id"]

    # Verify the report via canonical verification route
    verify_res = await api_client.post(
        f"/api/v1/verification/{tracking_id}/verify",
        json={"notes": "Confirmed by Ward Officer", "broadcast_alert": True},
    )
    assert verify_res.status_code == 200
    verified_data = verify_res.json()["data"]
    assert verified_data["verification"]["status"] == "VERIFIED"
    assert len(verified_data["verification_history"]) >= 1
    assert verified_data["verification_history"][0]["new_status"] == "VERIFIED"
    assert verified_data["verification_history"][0]["notes"] == "Confirmed by Ward Officer"
    assert verified_data["verification_history"][0]["reviewer_name"] == "Authorized Reviewer"


@pytest.mark.asyncio
async def test_reject_report_action_success(api_client: AsyncClient):
    """Test rejecting a report persists REJECTED status via canonical verification router."""
    create_res = await api_client.post(
        "/api/v1/reports",
        data={
            "latitude": "28.6139",
            "longitude": "77.2090",
            "category_code": "HAILSTORM",
            "severity": "MODERATE",
            "title": "Delhi hailstorm false report",
        },
    )
    assert create_res.status_code == 201
    tracking_id = create_res.json()["data"]["tracking_id"]

    reject_res = await api_client.post(
        f"/api/v1/verification/{tracking_id}/reject",
        json={"rejection_reason": "INACCURATE_LOCATION", "notes": "No hail observed"},
    )
    assert reject_res.status_code == 200
    rejected_data = reject_res.json()["data"]
    assert rejected_data["verification"]["status"] == "REJECTED"
    assert len(rejected_data["verification_history"]) >= 1
    assert rejected_data["verification_history"][0]["new_status"] == "REJECTED"
    assert rejected_data["verification_history"][0]["notes"] == "No hail observed"


@pytest.mark.asyncio
async def test_mark_duplicate_and_review_actions(api_client: AsyncClient):
    """Test marking report under review and duplicate via canonical verification router."""
    create_res = await api_client.post(
        "/api/v1/reports",
        data={
            "latitude": "12.9716",
            "longitude": "77.5946",
            "category_code": "HEAVY_RAINFALL",
            "severity": "MODERATE",
            "title": "Bengaluru heavy rain duplicate check",
        },
    )
    assert create_res.status_code == 201
    tracking_id = create_res.json()["data"]["tracking_id"]

    # Place under review
    review_res = await api_client.post(
        f"/api/v1/verification/{tracking_id}/review",
        json={"notes": "Checking with local AWS"},
    )
    assert review_res.status_code == 200
    assert review_res.json()["data"]["verification"]["status"] == "UNDER_REVIEW"

    # Mark duplicate
    dup_res = await api_client.post(
        f"/api/v1/verification/{tracking_id}/mark-duplicate",
        json={"canonical_report_id": "RPT-EXISTING-001", "notes": "Duplicate of report 001"},
    )
    assert dup_res.status_code == 200
    assert dup_res.json()["data"]["verification"]["status"] == "DUPLICATE"
    assert len(dup_res.json()["data"]["verification_history"]) >= 2


@pytest.mark.asyncio
async def test_legacy_triage_routes_and_admin_reports_absent():
    """Verify removed legacy triage endpoints and /admin/reports are unregistered (404/405)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_res = await client.post(
            "/api/v1/reports",
            data={
                "latitude": "19.0760",
                "longitude": "72.8777",
                "category_code": "FLOOD_WATERLOGGING",
                "severity": "MODERATE",
                "title": "Legacy Route Absence Verification",
            },
        )
        assert create_res.status_code == 201
        tracking_id = create_res.json()["data"]["tracking_id"]

        # 1. Legacy mutation routes on /reports/{id} must not exist
        res_legacy_verify = await client.post(f"/api/v1/reports/{tracking_id}/verify")
        assert res_legacy_verify.status_code in (404, 405)

        res_legacy_reject = await client.post(f"/api/v1/reports/{tracking_id}/reject")
        assert res_legacy_reject.status_code in (404, 405)

        res_legacy_dup = await client.post(f"/api/v1/reports/{tracking_id}/duplicate")
        assert res_legacy_dup.status_code in (404, 405)

        res_legacy_review = await client.post(f"/api/v1/reports/{tracking_id}/review")
        assert res_legacy_review.status_code in (404, 405)

        # 2. Duplicate /admin/reports router mount must not exist
        res_admin_list = await client.get("/api/v1/admin/reports")
        assert res_admin_list.status_code == 404

        res_admin_intake = await client.post("/api/v1/admin/reports")
        assert res_admin_intake.status_code == 404

        res_admin_verify = await client.post(f"/api/v1/admin/reports/{tracking_id}/verify")
        assert res_admin_verify.status_code == 404
