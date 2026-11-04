package main

import (
	"log"
	"os"

	"github.com/mitrichev/atomapper/backend/internal/api"
	"github.com/mitrichev/atomapper/backend/internal/jobs"
)

func main() {
	cfg := jobs.ConfigFromEnv()
	svc, err := jobs.NewService(cfg)
	if err != nil {
		log.Fatal(err)
	}
	r := api.NewRouter(svc)
	addr := os.Getenv("HTTP_ADDR")
	if addr == "" {
		addr = ":8080"
	}
	log.Printf("listening on %s", addr)
	if err := r.Run(addr); err != nil {
		log.Fatal(err)
	}
}
