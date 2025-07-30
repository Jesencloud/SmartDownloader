# tests/test_failure_ui_backend.py

import time
from unittest.mock import patch

from fastapi.testclient import TestClient

# The 'client' fixture is provided by conftest.py and is an instance of TestClient.


def test_download_failure_flow(client: TestClient):
    """
    Tests the backend flow for a failed download.

    This test ensures that when a Celery task fails, the API correctly
    reports the 'FAILURE' status. The frontend UI relies on this status
    to display the failure state with its "Retry" button.
    """
    print("🧪 Testing backend flow for download failure UI...")

    # 1. Arrange: Mock the Celery task to simulate an immediate failure.
    # We patch 'web.main.download_video_task.delay' as that is how the task is initiated.
    with patch("web.main.download_video_task.delay") as mock_task_delay:
        # We also need to mock AsyncResult to control the state that the API polls.
        mock_async_result_patcher = patch("web.main.AsyncResult")
        mock_async_result = mock_async_result_patcher.start()

        # Configure the mock for the task instance that AsyncResult will represent.
        task_instance_mock = mock_async_result.return_value
        task_instance_mock.id = "test-failure-task-id-123"
        task_instance_mock.status = "PENDING"
        task_instance_mock.result = None

        # Configure the .delay() method to return our mocked task instance.
        mock_task_delay.return_value = task_instance_mock

        # 2. Act: Start a download via the API. We expect this to "fail" because of our mock.
        print("   - Starting a download task (which is mocked to fail)...")
        download_request = {
            "url": "https://example.com/video-that-will-fail",
            "download_type": "video",
            "format_id": "best",
            "resolution": "1080p",
            "title": "Failure Test",
        }
        response = client.post("/downloads", json=download_request)

        assert response.status_code == 202, "The API should accept the initial download request."
        task_id = response.json()["task_id"]
        assert task_id == "test-failure-task-id-123"
        print(f"   - Task started successfully with ID: {task_id}")

        # 3. Assert: Poll the status endpoint and verify it transitions to 'FAILURE'.
        print("   - Polling API for FAILURE status...")

        # Simulate the task failing in the "backend" by changing the mock's state.
        task_instance_mock.status = "FAILURE"
        task_instance_mock.result = "Simulated yt-dlp crash."

        # Poll the status endpoint a few times to see the state change.
        final_status = ""
        final_result = None
        for i in range(5):  # Poll up to 5 times
            time.sleep(0.1)  # A short delay to simulate a real-world polling interval.
            status_response = client.get(f"/downloads/{task_id}")
            assert status_response.status_code == 200, "The status endpoint should always be available."

            status_data = status_response.json()
            final_status = status_data["status"]
            final_result = status_data["result"]

            if final_status == "FAILURE":
                print("   - ✅ Correctly received 'FAILURE' status from the API.")
                assert "Simulated yt-dlp crash" in final_result, "The failure reason should be in the result."
                print("   - ✅ Failure reason was correctly reported by the API.")
                break

        # Stop the patcher for AsyncResult to clean up.
        mock_async_result_patcher.stop()

        assert final_status == "FAILURE", f"Expected status to be 'FAILURE', but it ended as '{final_status}'."

    print("✅ Backend test for failure UI support passed.")
