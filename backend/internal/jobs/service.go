package jobs

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

type Status string

const (
	StatusQueued  Status = "queued"
	StatusRunning Status = "running"
	StatusDone    Status = "done"
	StatusFailed  Status = "failed"
)

type Job struct {
	ID        string `json:"job_id"`
	Status    Status `json:"status"`
	Step      string `json:"step"`
	Error     string `json:"error,omitempty"`
	CreatedAt time.Time `json:"created_at"`
}

type Service struct {
	cfg    Config
	rdb    *redis.Client
	mu     sync.Mutex
	memory map[string]*Job
	client *http.Client
}

func NewService(cfg Config) (*Service, error) {
	if err := os.MkdirAll(cfg.DataDir, 0o755); err != nil {
		return nil, err
	}
	s := &Service{
		cfg:    cfg,
		memory: map[string]*Job{},
		client: &http.Client{Timeout: 30 * time.Minute},
	}
	s.rdb = redis.NewClient(&redis.Options{Addr: cfg.RedisAddr})
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()
	if err := s.rdb.Ping(ctx).Err(); err != nil {
		s.rdb = nil
	}
	return s, nil
}

func (s *Service) CreateJob(reactant, product []byte, charge, multiplicity int, model string, useLLM bool) (*Job, error) {
	if int64(len(reactant)) > s.cfg.MaxUploadBytes || int64(len(product)) > s.cfg.MaxUploadBytes {
		return nil, fmt.Errorf("file too large")
	}
	if err := validateXYZAtomCount(reactant, s.cfg.MaxAtoms); err != nil {
		return nil, err
	}
	if err := validateXYZAtomCount(product, s.cfg.MaxAtoms); err != nil {
		return nil, err
	}

	id := uuid.NewString()
	job := &Job{ID: id, Status: StatusQueued, Step: "queued", CreatedAt: time.Now().UTC()}
	dir := filepath.Join(s.cfg.DataDir, id)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, err
	}
	if err := os.WriteFile(filepath.Join(dir, "reactant.xyz"), reactant, 0o644); err != nil {
		return nil, err
	}
	if err := os.WriteFile(filepath.Join(dir, "product.xyz"), product, 0o644); err != nil {
		return nil, err
	}
	meta := map[string]any{
		"charge":       charge,
		"multiplicity": multiplicity,
		"model":        model,
		"use_llm":      useLLM,
	}
	b, _ := json.Marshal(meta)
	_ = os.WriteFile(filepath.Join(dir, "meta.json"), b, 0o644)

	if err := s.saveJob(job); err != nil {
		return nil, err
	}
	go s.run(id, reactant, product, charge, multiplicity, model, useLLM)
	return job, nil
}

func (s *Service) GetJob(id string) (*Job, error) {
	return s.loadJob(id)
}

func (s *Service) OpenFile(id, name string) (string, error) {
	allowed := map[string]bool{
		"reactant_mapped.xyz": true,
		"product_mapped.xyz":  true,
		"mapping.json":        true,
		"report.md":           true,
	}
	if !allowed[name] {
		return "", fmt.Errorf("unknown file")
	}
	path := filepath.Join(s.cfg.DataDir, id, name)
	if _, err := os.Stat(path); err != nil {
		return "", err
	}
	return path, nil
}

func (s *Service) run(id string, reactant, product []byte, charge, multiplicity int, model string, useLLM bool) {
	_ = s.update(id, StatusRunning, "chem-worker", "")
	body := &bytes.Buffer{}
	w := multipart.NewWriter(body)
	_ = writeFileField(w, "reactant", "reactant.xyz", reactant)
	_ = writeFileField(w, "product", "product.xyz", product)
	_ = w.WriteField("charge", fmt.Sprintf("%d", charge))
	_ = w.WriteField("multiplicity", fmt.Sprintf("%d", multiplicity))
	if useLLM {
		_ = w.WriteField("use_llm", "true")
	} else {
		_ = w.WriteField("use_llm", "false")
	}
	if model != "" {
		_ = w.WriteField("model", model)
	}
	_ = w.Close()

	req, err := http.NewRequest(http.MethodPost, strings.TrimRight(s.cfg.ChemWorkerURL, "/")+"/map", body)
	if err != nil {
		_ = s.update(id, StatusFailed, "error", err.Error())
		return
	}
	req.Header.Set("Content-Type", w.FormDataContentType())
	resp, err := s.client.Do(req)
	if err != nil {
		_ = s.update(id, StatusFailed, "error", err.Error())
		return
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 300 {
		_ = s.update(id, StatusFailed, "error", string(respBody))
		return
	}

	var mapped struct {
		JobID string `json:"job_id"`
	}
	if err := json.Unmarshal(respBody, &mapped); err != nil {
		_ = s.update(id, StatusFailed, "error", err.Error())
		return
	}

	files := []string{"reactant_mapped.xyz", "product_mapped.xyz", "mapping.json", "report.md"}
	for _, name := range files {
		if err := s.fetchWorkerFile(mapped.JobID, name, filepath.Join(s.cfg.DataDir, id, name)); err != nil {
			_ = s.update(id, StatusFailed, "error", err.Error())
			return
		}
	}
	_ = s.update(id, StatusDone, "done", "")
}

func (s *Service) fetchWorkerFile(workerJobID, name, dest string) error {
	url := fmt.Sprintf("%s/jobs/%s/files/%s", strings.TrimRight(s.cfg.ChemWorkerURL, "/"), workerJobID, name)
	resp, err := s.client.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("fetch %s: %s", name, string(b))
	}
	f, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = io.Copy(f, resp.Body)
	return err
}

func writeFileField(w *multipart.Writer, field, filename string, data []byte) error {
	part, err := w.CreateFormFile(field, filename)
	if err != nil {
		return err
	}
	_, err = part.Write(data)
	return err
}

func validateXYZAtomCount(data []byte, maxAtoms int) error {
	lines := bytes.Split(data, []byte("\n"))
	if len(lines) == 0 {
		return fmt.Errorf("empty xyz")
	}
	var n int
	if _, err := fmt.Sscanf(strings.TrimSpace(string(lines[0])), "%d", &n); err != nil {
		return fmt.Errorf("invalid xyz atom count")
	}
	if n > maxAtoms {
		return fmt.Errorf("atom limit is %d", maxAtoms)
	}
	return nil
}

func (s *Service) saveJob(job *Job) error {
	s.mu.Lock()
	s.memory[job.ID] = job
	s.mu.Unlock()
	if s.rdb == nil {
		return nil
	}
	b, err := json.Marshal(job)
	if err != nil {
		return err
	}
	return s.rdb.Set(context.Background(), "job:"+job.ID, b, 24*time.Hour).Err()
}

func (s *Service) loadJob(id string) (*Job, error) {
	if s.rdb != nil {
		b, err := s.rdb.Get(context.Background(), "job:"+id).Bytes()
		if err == nil {
			var job Job
			if err := json.Unmarshal(b, &job); err == nil {
				return &job, nil
			}
		}
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	job, ok := s.memory[id]
	if !ok {
		return nil, fmt.Errorf("not found")
	}
	cp := *job
	return &cp, nil
}

func (s *Service) update(id string, status Status, step, errMsg string) error {
	job, err := s.loadJob(id)
	if err != nil {
		job = &Job{ID: id, CreatedAt: time.Now().UTC()}
	}
	job.Status = status
	job.Step = step
	job.Error = errMsg
	return s.saveJob(job)
}
