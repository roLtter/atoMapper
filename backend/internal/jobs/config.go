package jobs

import (
	"os"
	"strconv"
)

type Config struct {
	DataDir         string
	ChemWorkerURL   string
	RedisAddr       string
	MaxUploadBytes  int64
	MaxAtoms        int
}

func ConfigFromEnv() Config {
	maxUpload := int64(2_000_000)
	if v := os.Getenv("MAX_UPLOAD_BYTES"); v != "" {
		if n, err := strconv.ParseInt(v, 10, 64); err == nil {
			maxUpload = n
		}
	}
	maxAtoms := 100
	if v := os.Getenv("MAX_ATOMS"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			maxAtoms = n
		}
	}
	dataDir := os.Getenv("DATA_DIR")
	if dataDir == "" {
		dataDir = "./data"
	}
	chem := os.Getenv("CHEM_WORKER_URL")
	if chem == "" {
		chem = "http://127.0.0.1:8000"
	}
	redisAddr := os.Getenv("REDIS_ADDR")
	if redisAddr == "" {
		redisAddr = "127.0.0.1:6379"
	}
	return Config{
		DataDir:        dataDir,
		ChemWorkerURL:  chem,
		RedisAddr:      redisAddr,
		MaxUploadBytes: maxUpload,
		MaxAtoms:       maxAtoms,
	}
}
