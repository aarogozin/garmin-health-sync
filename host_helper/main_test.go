package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestAuthorizationRequiresCapabilityToken(t *testing.T) {
	h := &helper{token: "correct-token"}
	next := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusNoContent) })
	handler := h.authorize(next)

	missing := httptest.NewRequest(http.MethodGet, "/health", nil)
	missingResponse := httptest.NewRecorder()
	handler.ServeHTTP(missingResponse, missing)
	if missingResponse.Code != http.StatusUnauthorized {
		t.Fatalf("missing token returned %d", missingResponse.Code)
	}

	valid := httptest.NewRequest(http.MethodGet, "/health", nil)
	valid.Header.Set("X-Garmin-Health-Sync-Token", "correct-token")
	validResponse := httptest.NewRecorder()
	handler.ServeHTTP(validResponse, valid)
	if validResponse.Code != http.StatusNoContent {
		t.Fatalf("valid token returned %d", validResponse.Code)
	}
}

func TestPlistUsesFixedLauncherCommandAndEscapesPath(t *testing.T) {
	t.Setenv("GARMIN_SYNC_RUNTIME_DIR", "/tmp/private-runtime")
	t.Setenv("GARMIN_SYNC_ARCHIVE_HOST_DIR", "/tmp/Health & Notes")
	t.Setenv("GARMIN_SYNC_HOST_BRIDGE_TOKEN", "must-not-be-in-plist")
	content := plist("/tmp/a&b", 7, 30)
	if !strings.Contains(content, "/tmp/a&amp;b/health-sync") {
		t.Fatal("plist did not escape project path")
	}
	if !strings.Contains(content, "<string>sync</string><string>daily</string>") {
		t.Fatal("plist did not use the fixed daily sync command")
	}
	if !strings.Contains(content, "/tmp/private-runtime") || !strings.Contains(content, "/tmp/Health &amp; Notes") {
		t.Fatal("schedule lost the configured runtime/archive directories")
	}
	if strings.Contains(content, "must-not-be-in-plist") {
		t.Fatal("schedule persisted a session capability")
	}
}

func TestInstallRejectsInvalidPayloadsWithoutHostActions(t *testing.T) {
	h := &helper{}
	for _, body := range []string{`{}`, `{"hour":7}`, `{"hour":24,"minute":0}`, `{"hour":7,"minute":60}`, `{"hour":7,"minute":0,"command":"whoami"}`, `{"hour":7,"minute":0} {}`} {
		request := httptest.NewRequest(http.MethodPost, "/schedule/install", strings.NewReader(body))
		response := httptest.NewRecorder()
		h.install(response, request)
		if response.Code != http.StatusBadRequest {
			t.Fatalf("invalid payload returned %d", response.Code)
		}
	}
}
