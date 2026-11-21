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
	ID        string    `json:"job_id"`
	Status    Status    `json:"status"`
	Step      string    `json:"step"`
	Error     string    `json:"error,omitempty"`
	Kind      string    `json:"kind,omitempty"`
	CreatedAt time.Time `json:"created_at"`
}

type Service struct {
	cfg    Config
	rdb    *redis.Client
	store  *objectStore
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
	store, err := newObjectStore(cfg)
	if err != nil {
		fmt.Printf("minio disabled: %v\n", err)
		store = nil
	}
	s.store = store
	return s, nil
}

func (s *Service) CreateMapJob(reactant, product []byte, model string) (*Job, error) {
	if err := s.validatePair(reactant, product); err != nil {
		return nil, err
	}
	id := uuid.NewString()
	job := &Job{ID: id, Status: StatusQueued, Step: "queued", Kind: "map", CreatedAt: time.Now().UTC()}
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
	meta := map[string]any{"model": model, "kind": "map"}
	b, _ := json.Marshal(meta)
	_ = os.WriteFile(filepath.Join(dir, "meta.json"), b, 0o644)
	if err := s.saveJob(job); err != nil {
		return nil, err
	}
	go s.runMap(id, reactant, product, model)
	return job, nil
}

func (s *Service) CreateNormalizeJob(reactant, product []byte) (*Job, error) {
	if err := s.validatePair(reactant, product); err != nil {
		return nil, err
	}
	id := uuid.NewString()
	job := &Job{ID: id, Status: StatusQueued, Step: "queued", Kind: "normalize", CreatedAt: time.Now().UTC()}
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
	meta := map[string]any{"kind": "normalize"}
	b, _ := json.Marshal(meta)
	_ = os.WriteFile(filepath.Join(dir, "meta.json"), b, 0o644)
	if err := s.saveJob(job); err != nil {
		return nil, err
	}
	go s.runNormalize(id, reactant, product)
	return job, nil
}

func (s *Service) CreateFromMappingJob(reactant, product, mapping []byte) (*Job, error) {
	if err := s.validatePair(reactant, product); err != nil {
		return nil, err
	}
	if int64(len(mapping)) > s.cfg.MaxUploadBytes {
		return nil, fmt.Errorf("file too large")
	}
	id := uuid.NewString()
	job := &Job{ID: id, Status: StatusQueued, Step: "queued", Kind: "from-mapping", CreatedAt: time.Now().UTC()}
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
	if err := os.WriteFile(filepath.Join(dir, "mapping_in.json"), mapping, 0o644); err != nil {
		return nil, err
	}
	meta := map[string]any{"kind": "from-mapping"}
	b, _ := json.Marshal(meta)
	_ = os.WriteFile(filepath.Join(dir, "meta.json"), b, 0o644)
	if err := s.saveJob(job); err != nil {
		return nil, err
	}
	go s.runFromMapping(id, reactant, product, mapping)
	return job, nil
}

func (s *Service) GetJob(id string) (*Job, error) {
	return s.loadJob(id)
}

func (s *Service) LLMStatus() (map[string]any, error) {
	url := strings.TrimRight(s.cfg.ChemWorkerURL, "/") + "/llm"
	resp, err := s.client.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 300 {
		return nil, fmt.Errorf("%s", string(body))
	}
	var out map[string]any
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, err
	}
	return out, nil
}

func (s *Service) OpenFile(id, name string) (string, error) {
	allowed := map[string]bool{
		"reactant_mapped.xyz": true,
		"product_mapped.xyz":  true,
		"reactant_norm.xyz":   true,
		"product_norm.xyz":    true,
		"prompt.txt":          true,
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

func (s *Service) validatePair(reactant, product []byte) error {
	if int64(len(reactant)) > s.cfg.MaxUploadBytes || int64(len(product)) > s.cfg.MaxUploadBytes {
		return fmt.Errorf("file too large")
	}
	if err := validateXYZAtomCount(reactant, s.cfg.MaxAtoms); err != nil {
		return err
	}
	return validateXYZAtomCount(product, s.cfg.MaxAtoms)
}

func (s *Service) runMap(id string, reactant, product []byte, model string) {
	_ = s.update(id, StatusRunning, "chem-worker", "")
	body := &bytes.Buffer{}
	w := multipart.NewWriter(body)
	_ = writeFileField(w, "reactant", "reactant.xyz", reactant)
	_ = writeFileField(w, "product", "product.xyz", product)
	if model != "" {
		_ = w.WriteField("model", model)
	}
	_ = w.Close()
	s.finishWorkerCall(id, "/map", body, w.FormDataContentType(), []string{
		"reactant_mapped.xyz", "product_mapped.xyz", "mapping.json", "report.md",
	})
}

func (s *Service) runNormalize(id string, reactant, product []byte) {
	_ = s.update(id, StatusRunning, "chem-worker", "")
	body := &bytes.Buffer{}
	w := multipart.NewWriter(body)
	_ = writeFileField(w, "reactant", "reactant.xyz", reactant)
	_ = writeFileField(w, "product", "product.xyz", product)
	_ = w.Close()
	s.finishWorkerCall(id, "/normalize", body, w.FormDataContentType(), []string{
		"reactant_norm.xyz", "product_norm.xyz", "prompt.txt", "report.md",
	})
}

func (s *Service) runFromMapping(id string, reactant, product, mapping []byte) {
	_ = s.update(id, StatusRunning, "chem-worker", "")
	body := &bytes.Buffer{}
	w := multipart.NewWriter(body)
	_ = writeFileField(w, "reactant", "reactant_mapped.xyz", reactant)
	_ = writeFileField(w, "product", "product_mapped.xyz", product)
	_ = writeFileField(w, "mapping", "mapping.json", mapping)
	_ = w.Close()
	s.finishWorkerCall(id, "/from-mapping", body, w.FormDataContentType(), []string{
		"reactant_mapped.xyz", "product_mapped.xyz", "mapping.json", "report.md",
	})
}

func (s *Service) finishWorkerCall(id, path string, body *bytes.Buffer, contentType string, files []string) {
	req, err := http.NewRequest(http.MethodPost, strings.TrimRight(s.cfg.ChemWorkerURL, "/")+path, body)
	if err != nil {
		_ = s.update(id, StatusFailed, "error", err.Error())
		return
	}
	req.Header.Set("Content-Type", contentType)
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

	for _, name := range files {
		dest := filepath.Join(s.cfg.DataDir, id, name)
		if err := s.fetchWorkerFile(mapped.JobID, name, dest); err != nil {
			_ = s.update(id, StatusFailed, "error", err.Error())
			return
		}
		if s.store != nil && s.store.enabled() {
			if err := s.store.putFile(id, name, dest); err != nil {
				_ = s.update(id, StatusFailed, "error", fmt.Sprintf("minio upload: %v", err))
				return
			}
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
