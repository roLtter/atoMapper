package api

import (
	"io"
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/mitrichev/atomapper/backend/internal/jobs"
)

func NewRouter(svc *jobs.Service) *gin.Engine {
	r := gin.Default()
	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"ok": true})
	})

	r.GET("/api/llm", func(c *gin.Context) {
		info, err := svc.LLMStatus()
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, info)
	})

	r.POST("/api/jobs", func(c *gin.Context) {
		reactant, product, model, ok := readXYZPair(c)
		if !ok {
			return
		}
		job, err := svc.CreateMapJob(reactant, product, model)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusAccepted, gin.H{"job_id": job.ID})
	})

	r.POST("/api/jobs/normalize", func(c *gin.Context) {
		reactant, product, _, ok := readXYZPair(c)
		if !ok {
			return
		}
		job, err := svc.CreateNormalizeJob(reactant, product)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusAccepted, gin.H{"job_id": job.ID})
	})

	r.POST("/api/jobs/from-mapping", func(c *gin.Context) {
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
		mappingFile, err := c.FormFile("mapping")
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "mapping required"})
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
		mf, err := mappingFile.Open()
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		defer mf.Close()
		reactant, _ := io.ReadAll(rf)
		product, _ := io.ReadAll(pf)
		mapping, _ := io.ReadAll(mf)

		job, err := svc.CreateFromMappingJob(reactant, product, mapping)
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

func readXYZPair(c *gin.Context) (reactant, product []byte, model string, ok bool) {
	reactantFile, err := c.FormFile("reactant")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "reactant required"})
		return nil, nil, "", false
	}
	productFile, err := c.FormFile("product")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "product required"})
		return nil, nil, "", false
	}
	rf, err := reactantFile.Open()
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return nil, nil, "", false
	}
	defer rf.Close()
	pf, err := productFile.Open()
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return nil, nil, "", false
	}
	defer pf.Close()
	reactant, _ = io.ReadAll(rf)
	product, _ = io.ReadAll(pf)
	model = c.PostForm("model")
	return reactant, product, model, true
}
