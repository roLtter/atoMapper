package api

import (
	"io"
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
	"github.com/mitrichev/atomapper/backend/internal/jobs"
)

func NewRouter(svc *jobs.Service) *gin.Engine {
	r := gin.Default()
	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"ok": true})
	})

	r.POST("/api/jobs", func(c *gin.Context) {
		reactantFile, err := c.FormFile("reactant")
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "reactant required"})
			return
		}
		productFile, err := c.FormFile("product")
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "product required"})
			return
		}
		rf, err := reactantFile.Open()
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		defer rf.Close()
		pf, err := productFile.Open()
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		defer pf.Close()
		reactant, _ := io.ReadAll(rf)
		product, _ := io.ReadAll(pf)

		charge, _ := strconv.Atoi(c.DefaultPostForm("charge", "0"))
		mult, _ := strconv.Atoi(c.DefaultPostForm("multiplicity", "1"))
		model := c.PostForm("model")
		useLLM := c.DefaultPostForm("use_llm", "false") == "true"

		job, err := svc.CreateJob(reactant, product, charge, mult, model, useLLM)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusAccepted, gin.H{"job_id": job.ID})
	})

	r.GET("/api/jobs/:id", func(c *gin.Context) {
		job, err := svc.GetJob(c.Param("id"))
		if err != nil {
			c.JSON(http.StatusNotFound, gin.H{"error": "not found"})
			return
		}
		c.JSON(http.StatusOK, job)
	})

	r.GET("/api/jobs/:id/files/:name", func(c *gin.Context) {
		path, err := svc.OpenFile(c.Param("id"), c.Param("name"))
		if err != nil {
			c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
			return
		}
		c.File(path)
	})

	return r
}
