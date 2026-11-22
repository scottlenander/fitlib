"""Shared settings for test clients."""

# The app only answers requests for loopback hosts (see fitlib.api.security), so test clients
# use this address instead of TestClient's default "testserver".
LOCAL = "http://127.0.0.1"
