package main

import (
	"context"
	"crypto/subtle"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

const label = "com.local.garmin-health-sync.docker"

type helper struct {
	token       string
	projectRoot string
	mutationMu  sync.Mutex
}

type scheduleRequest struct {
	Hour   *int `json:"hour"`
	Minute *int `json:"minute"`
}

// main exposes a capability-protected loopback service for fixed macOS actions.
func main() {
	readyFile := flag.String("ready-file", "", "private ready-file path")
	projectRoot := flag.String("project-root", "", "project root")
	flag.Parse()
	token := os.Getenv("GARMIN_SYNC_HOST_BRIDGE_TOKEN")
	if token == "" || *readyFile == "" || *projectRoot == "" {
		fmt.Fprintln(os.Stderr, "missing private helper configuration")
		os.Exit(2)
	}
	root, err := filepath.Abs(*projectRoot)
	if err != nil {
		fmt.Fprintln(os.Stderr, "invalid project root")
		os.Exit(2)
	}
	launcher := filepath.Join(root, "health-sync")
	if info, err := os.Stat(launcher); err != nil || info.Mode()&0111 == 0 {
		fmt.Fprintln(os.Stderr, "project launcher is unavailable")
		os.Exit(2)
	}

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		fmt.Fprintln(os.Stderr, "could not start loopback helper")
		os.Exit(2)
	}
	port := listener.Addr().(*net.TCPAddr).Port
	if err := writeReady(*readyFile, port); err != nil {
		fmt.Fprintln(os.Stderr, "could not write helper readiness")
		os.Exit(2)
	}

	h := &helper{token: token, projectRoot: root}
	mux := http.NewServeMux()
	mux.HandleFunc("/health", h.health)
	mux.HandleFunc("/schedule/status", h.status)
	mux.HandleFunc("/schedule/install", h.install)
	mux.HandleFunc("/schedule/run", h.run)
	mux.HandleFunc("/schedule/remove", h.remove)
	mux.HandleFunc("/archive/open", h.openArchive)
	server := &http.Server{Handler: h.authorize(mux), ReadHeaderTimeout: 3 * time.Second, ReadTimeout: 5 * time.Second, WriteTimeout: 5 * time.Second}
	if err := server.Serve(listener); err != nil && err != http.ErrServerClosed {
		fmt.Fprintln(os.Stderr, "host helper stopped unexpectedly")
	}
}

// authorize rejects browser-originated requests unless they hold the current private token.
func (h *helper) authorize(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet && r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		provided := r.Header.Get("X-Garmin-Health-Sync-Token")
		if len(provided) != len(h.token) || subtle.ConstantTimeCompare([]byte(provided), []byte(h.token)) != 1 {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (h *helper) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
}

// status reports launchd state without returning host commands, identifiers or API secrets.
func (h *helper) status(w http.ResponseWriter, _ *http.Request) {
	h.mutationMu.Lock()
	defer h.mutationMu.Unlock()
	plist := h.plistPath()
	installed := fileExists(plist)
	loaded := installed && h.launchctl("print", h.domain()+"/"+label) == nil
	writeJSON(w, http.StatusOK, map[string]bool{"supported": true, "installed": installed, "loaded": loaded, "legacy": false})
}

// install atomically replaces the fixed plist; concurrent mutations are serialized.
func (h *helper) install(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var payload scheduleRequest
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1024))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil || payload.Hour == nil || payload.Minute == nil || *payload.Hour < 0 || *payload.Hour > 23 || *payload.Minute < 0 || *payload.Minute > 59 {
		http.Error(w, "invalid schedule", http.StatusBadRequest)
		return
	}
	if err := decoder.Decode(new(any)); err != io.EOF {
		http.Error(w, "invalid schedule", http.StatusBadRequest)
		return
	}
	h.mutationMu.Lock()
	defer h.mutationMu.Unlock()
	if err := os.MkdirAll(filepath.Dir(h.plistPath()), 0700); err != nil {
		http.Error(w, "could not configure schedule", http.StatusInternalServerError)
		return
	}
	content := plist(h.projectRoot, *payload.Hour, *payload.Minute)
	temp, err := os.CreateTemp(filepath.Dir(h.plistPath()), ".garmin-health-sync-")
	if err != nil {
		http.Error(w, "could not configure schedule", http.StatusInternalServerError)
		return
	}
	name := temp.Name()
	defer temp.Close()
	defer os.Remove(name)
	if _, err = temp.WriteString(content); err != nil {
		http.Error(w, "could not configure schedule", http.StatusInternalServerError)
		return
	}
	if err = temp.Chmod(0600); err != nil {
		http.Error(w, "could not configure schedule", http.StatusInternalServerError)
		return
	}
	if err = temp.Close(); err != nil || os.Rename(name, h.plistPath()) != nil {
		http.Error(w, "could not configure schedule", http.StatusInternalServerError)
		return
	}
	_ = h.launchctl("bootout", h.domain(), h.plistPath())
	if err := h.launchctl("bootstrap", h.domain(), h.plistPath()); err != nil {
		http.Error(w, "could not load schedule", http.StatusInternalServerError)
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"installed": true})
}

// run starts the already installed launchd job, without accepting command arguments.
func (h *helper) run(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	h.mutationMu.Lock()
	defer h.mutationMu.Unlock()
	if !fileExists(h.plistPath()) || h.launchctl("kickstart", h.domain()+"/"+label) != nil {
		http.Error(w, "could not run schedule", http.StatusConflict)
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"started": true})
}

// remove deletes only the fixed Garmin Health Sync Docker LaunchAgent.
func (h *helper) remove(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	h.mutationMu.Lock()
	defer h.mutationMu.Unlock()
	if !fileExists(h.plistPath()) {
		writeJSON(w, http.StatusOK, map[string]bool{"removed": false})
		return
	}
	_ = h.launchctl("bootout", h.domain(), h.plistPath())
	if err := os.Remove(h.plistPath()); err != nil {
		http.Error(w, "could not remove schedule", http.StatusInternalServerError)
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"removed": true})
}

// openArchive opens the launcher's configured folder, never a request-supplied path.
func (h *helper) openArchive(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	path := os.Getenv("GARMIN_SYNC_ARCHIVE_HOST_DIR")
	if path == "" || !fileExists(path) {
		http.Error(w, "archive unavailable", http.StatusNotFound)
		return
	}
	if err := exec.Command("/usr/bin/open", path).Run(); err != nil {
		http.Error(w, "could not open archive", http.StatusInternalServerError)
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"opened": true})
}

func (h *helper) plistPath() string {
	return filepath.Join(os.Getenv("HOME"), "Library", "LaunchAgents", label+".plist")
}
func (h *helper) domain() string { return "gui/" + strconv.Itoa(os.Getuid()) }

// launchctl bounds host command execution and never forwards its output to callers.
func (h *helper) launchctl(args ...string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 4*time.Second)
	defer cancel()
	return exec.CommandContext(ctx, "/bin/launchctl", args...).Run()
}
func fileExists(path string) bool { _, err := os.Stat(path); return err == nil }
func writeJSON(w http.ResponseWriter, status int, value interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
func writeReady(path string, port int) error {
	content := fmt.Sprintf("{\"port\":%d}\n", port)
	return os.WriteFile(path, []byte(content), 0600)
}

// plist pins the launcher and storage environment so launchd reuses the same credentials.
func plist(root string, hour, minute int) string {
	launcher := xml(root + "/health-sync")
	environment := "<key>EnvironmentVariables</key><dict>"
	for _, key := range []string{"GARMIN_SYNC_RUNTIME_DIR", "GARMIN_SYNC_ARCHIVE_HOST_DIR"} {
		if value := os.Getenv(key); value != "" {
			environment += "<key>" + key + "</key><string>" + xml(value) + "</string>"
		}
	}
	environment += "</dict>"
	return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n<plist version=\"1.0\"><dict><key>Label</key><string>" + label + "</string><key>ProgramArguments</key><array><string>" + launcher + "</string><string>sync</string><string>daily</string></array>" + environment + "<key>StartCalendarInterval</key><dict><key>Hour</key><integer>" + strconv.Itoa(hour) + "</integer><key>Minute</key><integer>" + strconv.Itoa(minute) + "</integer></dict><key>ProcessType</key><string>Background</string></dict></plist>\n"
}
func xml(value string) string {
	return strings.NewReplacer("&", "&amp;", "<", "&lt;", ">", "&gt;", "\"", "&quot;", "'", "&apos;").Replace(value)
}
